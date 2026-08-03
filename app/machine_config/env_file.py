"""Atomic, serialized updates for the protected production environment file."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol

from dotenv import dotenv_values

ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
FULL_CONTROL = 0x1F01FF
# Windows normalizes a Read allow-rule by adding Synchronize (0x100000).
READ_ACCESS = 0x120089


class EnvFileError(RuntimeError):
    """A protected environment update could not be completed safely."""


class AclManager(Protocol):
    def apply(self, path: Path) -> None: ...

    def verify(self, path: Path) -> bool: ...


@dataclass(frozen=True)
class EnvWriteResult:
    path: Path
    backup_path: Path | None
    changed_keys: tuple[str, ...]


class NamedMutex:
    """Cross-process Windows mutex with a thread-lock fallback for tooling."""

    _fallback_guard = threading.Lock()
    _fallback_locks: dict[str, threading.Lock] = {}

    def __init__(self, name: str, timeout_seconds: float = 30) -> None:
        self.name = name
        self.timeout_seconds = timeout_seconds
        self._handle: int | None = None
        self._fallback: threading.Lock | None = None

    def __enter__(self) -> "NamedMutex":
        if os.name != "nt":
            with self._fallback_guard:
                self._fallback = self._fallback_locks.setdefault(
                    self.name, threading.Lock()
                )
            if not self._fallback.acquire(timeout=self.timeout_seconds):
                raise EnvFileError("The production configuration is busy. Try again.")
            return self
        kernel32 = _kernel32()
        handle = kernel32.CreateMutexW(None, False, self.name)
        if not handle:
            raise EnvFileError("The production configuration lock could not be opened.")
        result = kernel32.WaitForSingleObject(handle, int(self.timeout_seconds * 1000))
        if result not in (0x00000000, 0x00000080):
            kernel32.CloseHandle(handle)
            raise EnvFileError("The production configuration is busy. Try again.")
        self._handle = handle
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._fallback is not None:
            self._fallback.release()
            return
        if self._handle is not None:
            kernel32 = _kernel32()
            kernel32.ReleaseMutex(self._handle)
            kernel32.CloseHandle(self._handle)
            self._handle = None


class WindowsEnvAcl:
    """Apply and verify the production file's explicit least-privilege DACL."""

    _apply_script = r"""
$path = $env:SMS_ACL_TARGET
$system = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')
$localService = [Security.Principal.SecurityIdentifier]::new('S-1-5-19')
$admins = [Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')
$acl = [Security.AccessControl.FileSecurity]::new()
$acl.SetOwner($admins)
$acl.SetAccessRuleProtection($true, $false)
foreach ($sid in @($system, $admins)) {
  $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
    $sid, [Security.AccessControl.FileSystemRights]::FullControl,
    [Security.AccessControl.AccessControlType]::Allow))
}
$acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
  $localService, [Security.AccessControl.FileSystemRights]::Read,
  [Security.AccessControl.AccessControlType]::Allow))
Set-Acl -LiteralPath $path -AclObject $acl
"""
    _inspect_script = r"""
$acl = Get-Acl -LiteralPath $env:SMS_ACL_TARGET
$rules = @($acl.Access | ForEach-Object {
  [ordered]@{
    sid=$_.IdentityReference.Translate(
      [Security.Principal.SecurityIdentifier]).Value
    rights=[int64]$_.FileSystemRights
    type=[string]$_.AccessControlType
    inherited=[bool]$_.IsInherited
  }
})
$ownerAccount = [Security.Principal.NTAccount]::new([string]$acl.Owner)
$owner = $ownerAccount.Translate([Security.Principal.SecurityIdentifier]).Value
[ordered]@{protected=$acl.AreAccessRulesProtected; owner=$owner; rules=$rules} |
  ConvertTo-Json -Compress -Depth 4
"""

    def apply(self, path: Path) -> None:
        result = _powershell_acl(self._apply_script, path)
        if result.returncode != 0:
            raise EnvFileError("The production configuration ACL could not be applied.")

    def verify(self, path: Path) -> bool:
        result = _powershell_acl(self._inspect_script, path)
        if result.returncode != 0:
            return False
        try:
            value = json.loads(result.stdout)
            rules = value["rules"]
            if isinstance(rules, dict):
                rules = [rules]
            actual = {
                item["sid"]: (int(item["rights"]), item["type"], item["inherited"])
                for item in rules
            }
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return False
        expected = {
            "S-1-5-18": FULL_CONTROL,
            "S-1-5-32-544": FULL_CONTROL,
            "S-1-5-19": READ_ACCESS,
        }
        return (
            bool(value["protected"])
            and value.get("owner") == "S-1-5-32-544"
            and set(actual) == set(expected)
            and all(
                actual[sid] == (rights, "Allow", False)
                for sid, rights in expected.items()
            )
        )


def update_env_file(
    path: Path | str,
    updates: Mapping[str, str],
    *,
    acl: AclManager | None = None,
    timeout_seconds: float = 30,
) -> EnvWriteResult:
    """Atomically update named values while preserving comments and rollback data."""
    target = Path(path)
    if not target.is_absolute():
        raise EnvFileError("The production environment path must be absolute.")
    clean_updates = _validated_updates(updates)
    target.parent.mkdir(parents=True, exist_ok=True)
    manager = acl or _default_acl_manager()
    backup: Path | None = None
    mutex_name = _mutex_name(target)
    with NamedMutex(mutex_name, timeout_seconds):
        try:
            backup = target.with_name(target.name + ".bak") if target.exists() else None
            original = target.read_text(encoding="utf-8") if target.exists() else ""
            content = _render(original, clean_updates)
            _commit(target, content, manager, backup)
        except EnvFileError:
            raise
        except Exception:
            raise EnvFileError(
                "The production configuration could not be read; nothing was changed."
            ) from None
    return EnvWriteResult(target, backup, tuple(sorted(clean_updates)))


def read_env_file(path: Path | str) -> dict[str, str]:
    """Read an environment file without changing process environment state."""
    target = Path(path)
    if not target.is_absolute():
        raise EnvFileError("The production environment path must be absolute.")
    try:
        values = dotenv_values(target)
    except (OSError, UnicodeError, ValueError):
        raise EnvFileError("The production configuration could not be read.") from None
    return {str(name): str(value or "") for name, value in values.items()}


def _commit(
    target: Path,
    content: str,
    acl: AclManager,
    backup: Path | None,
) -> None:
    staged: Path | None = None
    replaced = False
    try:
        if backup is not None:
            _prepare_backup(target, backup, acl)
        staged = _stage_text(target.parent, content, acl)
        os.replace(staged, target)
        staged = None
        replaced = True
        acl.apply(target)
        if not acl.verify(target):
            raise EnvFileError("The production configuration ACL verification failed.")
    except Exception:
        if replaced:
            _restore(target, backup, acl)
        message = (
            "The production configuration update failed; the previous file was restored."
            if backup is not None
            else "The production configuration update failed; no file was retained."
        )
        raise EnvFileError(message) from None
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


def _prepare_backup(target: Path, backup: Path, acl: AclManager) -> None:
    staged = _stage_copy(target, acl)
    try:
        os.replace(staged, backup)
        acl.apply(backup)
        if not acl.verify(backup):
            backup.unlink(missing_ok=True)
            raise EnvFileError("The protected configuration backup could not be verified.")
    finally:
        staged.unlink(missing_ok=True)


def _restore(target: Path, backup: Path | None, acl: AclManager) -> None:
    if backup is None:
        target.unlink(missing_ok=True)
        return
    staged = _stage_copy(backup, acl)
    try:
        os.replace(staged, target)
        acl.apply(target)
        if not acl.verify(target):
            raise EnvFileError("The previous production configuration could not be restored.")
    finally:
        staged.unlink(missing_ok=True)


def _stage_text(directory: Path, content: str, acl: AclManager) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=".sms-env-", dir=directory)
    path = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        acl.apply(path)
        if not acl.verify(path):
            raise EnvFileError("The staged production configuration ACL is invalid.")
        return path
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _stage_copy(source: Path, acl: AclManager) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=".sms-env-backup-", dir=source.parent)
    os.close(descriptor)
    path = Path(name)
    try:
        shutil.copyfile(source, path)
        with path.open("r+b") as handle:
            os.fsync(handle.fileno())
        acl.apply(path)
        if not acl.verify(path):
            raise EnvFileError("The staged configuration backup ACL is invalid.")
        return path
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _validated_updates(updates: Mapping[str, str]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for name, value in updates.items():
        if not ENV_NAME_RE.fullmatch(str(name)):
            raise EnvFileError("An environment setting name is invalid.")
        text = str(value)
        if "\n" in text or "\r" in text or "\0" in text:
            raise EnvFileError(f"Environment setting {name} must contain one line.")
        cleaned[str(name)] = text
    return cleaned


def _render(original: str, updates: Mapping[str, str]) -> str:
    pending = dict(updates)
    rendered: list[str] = []
    for line in original.splitlines():
        match = re.match(r"^\s*([A-Z][A-Z0-9_]*)\s*=", line)
        if match and match.group(1) in updates:
            name = match.group(1)
            if name in pending:
                rendered.append(f"{name}={_env_value(pending.pop(name))}")
            continue
        rendered.append(line)
    rendered.extend(f"{name}={_env_value(value)}" for name, value in pending.items())
    return "\n".join(rendered).rstrip("\n") + "\n"


def _env_value(value: str) -> str:
    if value and not re.search(r"[\s#'\"]", value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _mutex_name(path: Path) -> str:
    digest = hashlib.sha256(str(path.resolve()).lower().encode("utf-8")).hexdigest()
    return rf"Global\AfaqyServiceManagement.Env.{digest[:32]}"


def _kernel32():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.WaitForSingleObject.restype = ctypes.c_uint32
    kernel32.ReleaseMutex.argtypes = [ctypes.c_void_p]
    kernel32.ReleaseMutex.restype = ctypes.c_bool
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_bool
    return kernel32


def _powershell_acl(script: str, path: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["SMS_ACL_TARGET"] = str(path)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
        creationflags=flags,
    )


def _default_acl_manager() -> AclManager:
    if os.name != "nt":
        raise EnvFileError("Protected production environment writes require Windows.")
    return WindowsEnvAcl()
