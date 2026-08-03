"""Release updates, backup operations and redacted diagnostics."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from app.deployment_config import database_backup_windows_script, validate_profile
from app.machine_config.firewall import detect_firewall_state

from .config_store import load_profile, save_profile
from .paths import InstallPaths
from .security import redact
from .service_core import ServiceController


class SystemOperationError(RuntimeError):
    """A local maintenance operation failed without exposing its output."""


class SystemController:
    def __init__(
        self,
        paths: InstallPaths,
        service: ServiceController,
        *,
        runner: Callable[..., Any] = subprocess.run,
    ) -> None:
        self.paths = paths
        self.service = service
        self.runner = runner

    def version(self) -> str:
        try:
            value = json.loads((self.paths.current / "release.json").read_text(encoding="utf-8-sig"))
            return str(value.get("version") or "Unknown")
        except (OSError, ValueError, TypeError):
            return "Unknown"

    def firewall_state(self) -> str:
        try:
            return detect_firewall_state(load_profile(self.paths.machine_settings)).state
        except Exception:
            return "unavailable"

    def backup_status(self) -> dict[str, Any]:
        if not self.backup_profile().get("backup_enabled"):
            return {
                "ok": True,
                "message": "Automatic backups are disabled. Enable and save them below.",
            }
        path = self.paths.program_data / "database-backup-status.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
            return value if isinstance(value, dict) else {"ok": False, "message": "Malformed status"}
        except (OSError, ValueError, TypeError):
            return {"ok": False, "message": "No readable backup status is available."}

    def run_backup_now(self) -> None:
        if not self.backup_profile().get("backup_enabled"):
            raise SystemOperationError(
                "Automatic backups are disabled. Enable and save the backup schedule first."
            )
        script = "Start-ScheduledTask -TaskName 'ServiceManagementSystem Database Backup'"
        self._powershell(script, "The scheduled backup could not be started.")

    def backup_profile(self) -> dict[str, Any]:
        return load_profile(self.paths.machine_settings)

    def configure_backups(self, values: Mapping[str, Any]) -> None:
        previous = self.backup_profile()
        candidate = dict(previous)
        candidate.update(
            {
                field: values[field]
                for field in (
                    "backup_enabled",
                    "backup_interval_days",
                    "backup_retention_count",
                    "backup_include_uploads",
                    "backup_upload_retention_count",
                    "backup_directory",
                    "pg_dump_executable",
                )
                if field in values
            }
        )
        cleaned, errors = validate_profile(candidate)
        backup_errors = [
            errors[field]
            for field in (
                "backup_interval_days",
                "backup_retention_count",
                "backup_upload_retention_count",
                "backup_directory",
                "pg_dump_executable",
            )
            if field in errors
        ]
        if backup_errors:
            raise SystemOperationError(backup_errors[0])
        if cleaned["backup_enabled"] and not Path(cleaned["pg_dump_executable"]).is_file():
            raise SystemOperationError(
                "pg_dump.exe was not found. Select the PostgreSQL backup tool and try again."
            )

        updated = dict(previous)
        for field in (
            "backup_enabled",
            "backup_interval_days",
            "backup_retention_count",
            "backup_include_uploads",
            "backup_upload_retention_count",
            "backup_directory",
            "pg_dump_executable",
        ):
            updated[field] = cleaned[field]
        save_profile(self.paths.machine_settings, updated)
        try:
            self.install_backup_schedule()
        except Exception:
            save_profile(self.paths.machine_settings, previous)
            try:
                self._install_backup_schedule(previous)
            except Exception:
                pass
            raise SystemOperationError(
                "The backup schedule could not be installed. The previous settings were restored."
            ) from None

    def install_backup_schedule(self) -> None:
        self._install_backup_schedule(self.backup_profile())

    def _install_backup_schedule(self, profile: Mapping[str, Any]) -> None:
        script_path = self.paths.program_data / "install_database_backup_task.ps1"
        self.paths.program_data.mkdir(parents=True, exist_ok=True)
        script_path.write_text(database_backup_windows_script(profile), encoding="utf-8")
        result = self.runner(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
                "-InstallRoot",
                str(self.paths.root),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            raise SystemOperationError("The automatic backup schedule could not be installed.")

    def install_update(self, release_zip: Path, checksum_file: Path) -> None:
        verify_release_checksum(release_zip, checksum_file)
        wheelhouse = _find_wheelhouse(release_zip)
        arguments = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.paths.deploy_script),
            "-ReleasePackage",
            str(release_zip),
            "-InstallRoot",
            str(self.paths.root),
            "-ServiceName",
            self.service.service_name,
        ]
        if wheelhouse is not None:
            arguments.extend(["-WheelhousePath", str(wheelhouse)])
        result = self.runner(
            arguments,
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            raise SystemOperationError("The verified release package could not be installed.")

    def export_diagnostics(self, destination: Path) -> None:
        value = {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "version": self.version(),
            "service_status": self.service.status(),
            "firewall_state": self.firewall_state(),
            "backup_status": self.backup_status(),
            "paths": {
                "root": str(self.paths.root),
                "logs": str(self.paths.logs),
                "backups": str(self.paths.backups),
            },
            "recent_logs": self.service.recent_logs(400),
        }
        rendered = redact(json.dumps(value, ensure_ascii=False, indent=2))
        destination.write_text(rendered + "\n", encoding="utf-8")

    def _powershell(self, script: str, message: str) -> None:
        result = self.runner(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            raise SystemOperationError(message)


def verify_release_checksum(release_zip: Path, checksum_file: Path) -> str:
    """Verify one release ZIP against a companion or bundle SHA-256 manifest."""
    if not release_zip.is_file() or not checksum_file.is_file():
        raise SystemOperationError("Select an existing release ZIP and SHA-256 file.")
    expected = _expected_checksum(release_zip, checksum_file)
    digest = hashlib.sha256()
    with release_zip.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    actual = digest.hexdigest()
    if actual.lower() != expected.lower():
        raise SystemOperationError("Release ZIP checksum verification failed.")
    return actual


def _expected_checksum(release_zip: Path, checksum_file: Path) -> str:
    for line in checksum_file.read_text(encoding="utf-8-sig").splitlines():
        parts = line.strip().split(maxsplit=1)
        if not parts or len(parts[0]) != 64:
            continue
        if len(parts) == 1 or Path(parts[1].lstrip("* ").replace("/", os.sep)).name == release_zip.name:
            if all(character in "0123456789abcdefABCDEF" for character in parts[0]):
                return parts[0]
    raise SystemOperationError("The SHA-256 file has no entry for the selected release ZIP.")


def _find_wheelhouse(release_zip: Path) -> Path | None:
    for candidate in (release_zip.parent / "wheelhouse", release_zip.parent.parent / "wheelhouse"):
        if candidate.is_dir():
            return candidate
    return None
