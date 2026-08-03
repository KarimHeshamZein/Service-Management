"""Elevated single-instance launcher for the local Service Console."""
from __future__ import annotations

import argparse
import ctypes
import os
import subprocess
import sys
from pathlib import Path

from .paths import InstallPaths


# Loaded only after the installed production environment has been selected.
# Importing app.machine_config earlier also imports app.config through the package.
EnvFileError = None
NamedMutex = None


def is_elevated() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def request_elevation(install_root: Path) -> bool:
    parameters = subprocess.list2cmdline(
        ["-m", "console", "--install-root", str(install_root), "--elevated"]
    )
    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        sys.executable,
        parameters,
        str(install_root / "current"),
        1,
    )
    return result > 32


def _message(text: str) -> None:
    ctypes.windll.user32.MessageBoxW(None, text, "Service Console", 0x10)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Service Management System console")
    parser.add_argument("--install-root", default=r"C:\ServiceManagement")
    parser.add_argument("--elevated", action="store_true")
    options = parser.parse_args(argv)
    root = Path(options.install_root).expanduser().resolve()
    if not is_elevated():
        if options.elevated or not request_elevation(root):
            _message("Administrator approval was refused. The Service Console cannot open.")
            return 1
        return 0
    paths = InstallPaths.from_root(root)
    if not paths.env_file.is_file():
        _message(f"The installed configuration was not found at {paths.env_file}.")
        return 1
    os.environ["SMS_ENV_FILE"] = str(paths.env_file)
    os.environ["ENVIRONMENT"] = "production"
    global EnvFileError, NamedMutex
    if EnvFileError is None or NamedMutex is None:
        from app.machine_config.env_file import EnvFileError as _EnvFileError
        from app.machine_config.env_file import NamedMutex as _NamedMutex

        if EnvFileError is None:
            EnvFileError = _EnvFileError
        if NamedMutex is None:
            NamedMutex = _NamedMutex
    try:
        with NamedMutex(r"Global\AfaqyServiceManagement.Console", 0.1):
            from .config_store import reconcile_runtime_profile

            reconcile_runtime_profile(paths)
            from .app import ConsoleApp

            ConsoleApp(paths).run()
    except EnvFileError:
        _message("Another Service Console is already open.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
