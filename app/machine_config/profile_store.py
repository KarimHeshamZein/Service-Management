"""Persistent, secret-free machine profile storage."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from app.deployment_config import PROFILE_FIELDS, default_profile
from app.machine_config.env_file import EnvFileError, NamedMutex


class MachineProfileError(RuntimeError):
    """The machine profile could not be read or saved."""


def load_profile(path: Path) -> dict[str, Any]:
    profile = default_profile()
    if not path.exists():
        return profile
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, TypeError):
        raise MachineProfileError("The machine settings file is unreadable.") from None
    if not isinstance(value, dict):
        raise MachineProfileError("The machine settings file is malformed.")
    return {**profile, **{key: value.get(key) for key in PROFILE_FIELDS if key in value}}


def save_profile(path: Path, profile: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    value = {key: profile.get(key) for key in PROFILE_FIELDS}
    try:
        with NamedMutex(_mutex_name(path), 30):
            _atomic_json(path, value)
    except (OSError, EnvFileError):
        raise MachineProfileError("The machine settings could not be saved.") from None


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    descriptor, name = tempfile.mkstemp(prefix=".sms-settings-", dir=path.parent)
    staged = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)


def _mutex_name(path: Path) -> str:
    digest = hashlib.sha256(str(path.resolve()).lower().encode("utf-8")).hexdigest()
    return rf"Global\AfaqyServiceManagement.Settings.{digest[:32]}"
