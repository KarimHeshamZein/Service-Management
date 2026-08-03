"""Installed-path discovery for console operations."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class InstallPaths:
    root: Path
    current: Path
    shared: Path
    env_file: Path
    machine_settings: Path
    logs: Path
    backups: Path
    service_executable: Path
    deploy_script: Path
    program_data: Path

    @classmethod
    def from_root(cls, root: Path | str) -> "InstallPaths":
        resolved = Path(root).expanduser().resolve()
        program_data = Path(os.getenv("PROGRAMDATA", r"C:\ProgramData"))
        return cls(
            root=resolved,
            current=resolved / "current",
            shared=resolved / "shared",
            env_file=resolved / "shared" / ".env",
            machine_settings=resolved / "shared" / "machine-settings.json",
            logs=resolved / "logs",
            backups=resolved / "backups",
            service_executable=resolved / "ServiceManagementSystem.exe",
            deploy_script=resolved / "current" / "scripts" / "Deploy-Release.ps1",
            program_data=program_data / "ServiceManagementSystem",
        )
