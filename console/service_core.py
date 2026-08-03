"""Windows service lifecycle, health and transactional port changes."""
from __future__ import annotations

import os
import subprocess
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any, Callable

from app.machine_config.endpoints import endpoint_updates
from app.machine_config.env_file import read_env_file, update_env_file
from app.machine_config.firewall import apply_firewall_rules, expected_rules
from app.machine_config.ports import check_port

from .config_store import load_profile, save_profile
from .paths import InstallPaths
from .security import redact


class ServiceOperationError(RuntimeError):
    """A service operation failed without exposing subprocess output."""


class ServiceController:
    def __init__(
        self,
        paths: InstallPaths,
        *,
        service_name: str = "ServiceManagementSystem",
        runner: Callable[..., Any] = subprocess.run,
        env_writer=update_env_file,
        firewall_writer=apply_firewall_rules,
        health_checker=None,
    ) -> None:
        self.paths = paths
        self.service_name = service_name
        self.runner = runner
        self.env_writer = env_writer
        self.firewall_writer = firewall_writer
        self.health_checker = health_checker or self.wait_for_health

    def status(self) -> str:
        script = (
            "$service=Get-Service -Name $env:SMS_SERVICE_NAME -ErrorAction Stop; "
            "[string]$service.Status"
        )
        result = self._powershell(script)
        return result.stdout.strip() if result.returncode == 0 else "Unavailable"

    def start(self) -> None:
        self._service_command("start")

    def stop(self) -> None:
        self._service_command("stop")

    def restart(self) -> None:
        self._service_command("restart")

    def health_check(self, port: int | None = None, timeout: float = 5) -> bool:
        selected = port or int(read_env_file(self.paths.env_file).get("APP_PORT", "8993"))
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{selected}/login", timeout=timeout
            ) as response:
                return response.status == 200
        except (OSError, urllib.error.URLError):
            return False

    def wait_for_health(self, port: int, timeout: float = 30) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            if self.health_check(port, timeout=min(2, remaining)):
                return True
            time.sleep(min(0.5, max(0, deadline - time.monotonic())))

    def open_application(self) -> None:
        values = read_env_file(self.paths.env_file)
        port = int(values.get("APP_PORT", "8993"))
        webbrowser.open(f"http://127.0.0.1:{port}")

    def check_candidate_port(self, port: int):
        current = int(read_env_file(self.paths.env_file).get("APP_PORT", "8993"))
        if port == current:
            return None
        return check_port(port)

    def change_port(self, port: int) -> None:
        if not 1 <= port <= 65535:
            raise ServiceOperationError("Enter a port from 1 to 65535.")
        status = self.check_candidate_port(port)
        if status is not None and not status.available:
            raise ServiceOperationError(status.message)
        old_profile = load_profile(self.paths.machine_settings)
        new_profile = {
            **old_profile,
            "public_port": port,
            "local_port": port,
            "internal_port": port,
        }
        old_updates = endpoint_updates(old_profile)
        stage = "saving the machine settings"
        try:
            save_profile(self.paths.machine_settings, new_profile)
            stage = "updating the production environment"
            self.env_writer(self.paths.env_file, endpoint_updates(new_profile))
            stage = "updating Windows Firewall"
            self.firewall_writer(expected_rules(new_profile))
            stage = "restarting the Windows service"
            self.restart()
            stage = "checking the new HTTP endpoint"
            if not self.health_checker(port):
                raise ServiceOperationError("The application did not become healthy on the new port.")
        except Exception:
            try:
                self._restore_port(old_profile, old_updates)
            except ServiceOperationError as rollback_error:
                raise ServiceOperationError(
                    f"The port change failed while {stage}. {rollback_error}"
                ) from None
            raise ServiceOperationError(
                f"The port change failed while {stage}. "
                "The previous configuration was restored."
            ) from None

    def recent_logs(self, max_lines: int = 200) -> str:
        candidates = sorted(self.paths.logs.glob("*"), key=lambda item: item.stat().st_mtime)
        lines: list[str] = []
        for path in candidates[-4:]:
            if not path.is_file():
                continue
            try:
                lines.extend(path.read_text(encoding="utf-8", errors="replace").splitlines())
            except OSError:
                continue
        return redact("\n".join(lines[-max_lines:]))

    def _restore_port(self, profile: dict[str, Any], updates: dict[str, str]) -> None:
        stage = "restoring the machine settings"
        try:
            save_profile(self.paths.machine_settings, profile)
            stage = "restoring the production environment"
            self.env_writer(self.paths.env_file, updates)
            stage = "restoring Windows Firewall"
            self.firewall_writer(expected_rules(profile))
            stage = "restarting the previous Windows service configuration"
            if self.status().strip().lower() == "stopped":
                self.start()
            else:
                self.restart()
        except Exception:
            raise ServiceOperationError(
                f"Automatic rollback failed while {stage}. Open the logs."
            ) from None

    def _service_command(self, action: str) -> None:
        if action not in {"start", "stop", "restart"}:
            raise ServiceOperationError("Unsupported service action.")
        script = rf"""
$ErrorActionPreference = 'Stop'
$action = '{action}'
$service = Get-Service -Name $env:SMS_SERVICE_NAME -ErrorAction Stop
$timeout = [TimeSpan]::FromSeconds(60)
if ($action -eq 'stop') {{
    if ($service.Status -ne [ServiceProcess.ServiceControllerStatus]::Stopped) {{
        Stop-Service -InputObject $service -Force -ErrorAction Stop
        $service.WaitForStatus([ServiceProcess.ServiceControllerStatus]::Stopped, $timeout)
    }}
}} elseif ($action -eq 'start') {{
    if ($service.Status -ne [ServiceProcess.ServiceControllerStatus]::Running) {{
        if ($service.Status -ne [ServiceProcess.ServiceControllerStatus]::Stopped) {{
            $service.WaitForStatus([ServiceProcess.ServiceControllerStatus]::Stopped, $timeout)
        }}
        Start-Service -InputObject $service -ErrorAction Stop
        $service.WaitForStatus([ServiceProcess.ServiceControllerStatus]::Running, $timeout)
    }}
}} else {{
    if ($service.Status -ne [ServiceProcess.ServiceControllerStatus]::Stopped) {{
        Stop-Service -InputObject $service -Force -ErrorAction Stop
        $service.WaitForStatus([ServiceProcess.ServiceControllerStatus]::Stopped, $timeout)
    }}
    Start-Service -InputObject $service -ErrorAction Stop
    $service.WaitForStatus([ServiceProcess.ServiceControllerStatus]::Running, $timeout)
}}
$service.Refresh()
[string]$service.Status
"""
        result = self._powershell(script, timeout=90)
        if result.returncode != 0:
            raise ServiceOperationError(f"The Windows service could not {action}.")

    def _powershell(self, script: str, *, timeout: int = 20):
        environment = os.environ.copy()
        environment["SMS_SERVICE_NAME"] = self.service_name
        return self.runner(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            env=environment,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
