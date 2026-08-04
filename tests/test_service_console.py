"""Local Service Console core and launcher regression tests."""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from app.machine_config.env_file import EnvFileError
from app.machine_config.ports import PortStatus
from console import __main__ as launcher
from console.config_store import load_profile, reconcile_runtime_profile, save_profile
from console.database_core import DatabaseController, DatabaseOperationError
from console.paths import InstallPaths
from console.security import redact
from console.service_core import ServiceController, ServiceOperationError
from console.system_core import SystemController, SystemOperationError, verify_release_checksum
from console.tabs.network import initial_adapter


class Result:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = ""


def test_network_tab_selects_a_safe_active_adapter_default():
    adapters = ("Ethernet", "Wi-Fi")

    assert initial_adapter("Wi-Fi", adapters) == "Wi-Fi"
    assert initial_adapter("Disabled adapter", adapters) == "Ethernet"
    assert initial_adapter("", adapters) == "Ethernet"
    assert initial_adapter("", ()) == ""


def _paths(tmp_path: Path) -> InstallPaths:
    paths = InstallPaths.from_root(tmp_path / "ServiceManagement")
    for directory in (
        paths.current / "scripts",
        paths.shared,
        paths.logs,
        paths.backups,
        paths.program_data,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    paths.env_file.write_text(
        "APP_PORT=8993\nPUBLIC_BASE_URL=http://127.0.0.1:8993\n"
        "DATABASE_URL=postgresql://service:HiddenPassword@localhost/app\n",
        encoding="utf-8",
    )
    profile = {
        "public_enabled": False,
        "tls_enabled": False,
        "public_ip": "",
        "public_port": 8993,
        "allowed_remote_ips": "",
        "local_interface": "Ethernet",
        "local_ip": "192.168.1.20",
        "local_port": 8993,
        "configure_static_local_ip": False,
        "local_prefix_length": 24,
        "local_gateway": "192.168.1.1",
        "local_dns_servers": "192.168.1.1",
        "internal_port": 8993,
        "postgres_host": "127.0.0.1",
        "postgres_port": 5432,
        "backup_enabled": False,
        "backup_interval_days": 1,
        "backup_retention_count": 30,
        "backup_include_uploads": True,
        "backup_upload_retention_count": 7,
        "backup_directory": str(paths.backups / "scheduled"),
        "pg_dump_executable": r"C:\Program Files\PostgreSQL\16\bin\pg_dump.exe",
    }
    save_profile(paths.machine_settings, profile)
    return paths


def test_elevation_refusal_is_clear_and_does_not_launch_gui(monkeypatch, tmp_path):
    messages = []
    monkeypatch.setattr(launcher, "is_elevated", lambda: False)
    monkeypatch.setattr(launcher, "request_elevation", lambda _root: False)
    monkeypatch.setattr(launcher, "_message", messages.append)

    result = launcher.main(["--install-root", str(tmp_path)])

    assert result == 1
    assert "approval was refused" in messages[0]


def test_concurrent_console_instance_is_refused(monkeypatch, tmp_path):
    paths = _paths(tmp_path)
    messages = []

    class BusyMutex:
        def __init__(self, *_args):
            pass

        def __enter__(self):
            raise EnvFileError("busy")

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(launcher, "is_elevated", lambda: True)
    monkeypatch.setattr(launcher, "NamedMutex", BusyMutex)
    monkeypatch.setattr(launcher, "_message", messages.append)

    assert launcher.main(["--install-root", str(paths.root)]) == 1
    assert messages == ["Another Service Console is already open."]


def test_failed_port_health_check_restores_env_profile_and_firewall(
    monkeypatch, tmp_path
):
    paths = _paths(tmp_path)
    env_updates = []
    firewall_updates = []
    commands = []
    monkeypatch.setattr(
        "console.service_core.check_port",
        lambda port: PortStatus(port, True, message="available"),
    )
    controller = ServiceController(
        paths,
        runner=lambda args, **_kwargs: commands.append(args) or Result(),
        env_writer=lambda path, updates: env_updates.append((path, updates)),
        firewall_writer=lambda rules: firewall_updates.append(tuple(rules)),
        health_checker=lambda _port: False,
    )

    with pytest.raises(
        ServiceOperationError,
        match="checking the new HTTP endpoint.*previous configuration was restored",
    ):
        controller.change_port(8123)

    assert env_updates[0][1]["APP_PORT"] == "8123"
    assert env_updates[-1][1]["APP_PORT"] == "8993"
    assert load_profile(paths.machine_settings)["internal_port"] == 8993
    assert len(firewall_updates) == 2
    service_actions = [
        action
        for command in commands
        if command[0] == "powershell.exe"
        for action in ("start", "stop", "restart")
        if f"$action = '{action}'" in command[-1]
    ]
    assert service_actions == ["restart", "restart"]


def test_port_rollback_starts_service_when_failed_restart_left_it_stopped(
    monkeypatch, tmp_path
):
    paths = _paths(tmp_path)
    commands = []
    monkeypatch.setattr(
        "console.service_core.check_port",
        lambda port: PortStatus(port, True, message="available"),
    )

    def runner(args, **_kwargs):
        commands.append(args)
        if args[0] == "powershell.exe" and "$action = 'restart'" in args[-1]:
            return Result(returncode=1)
        if args[0] == "powershell.exe":
            return Result(stdout="Stopped")
        return Result()

    controller = ServiceController(
        paths,
        runner=runner,
        env_writer=lambda *_args: None,
        firewall_writer=lambda _rules: None,
    )

    with pytest.raises(
        ServiceOperationError,
        match="restarting the Windows service.*previous configuration was restored",
    ):
        controller.change_port(8123)

    service_actions = [
        action
        for command in commands
        if command[0] == "powershell.exe"
        for action in ("start", "stop", "restart")
        if f"$action = '{action}'" in command[-1]
    ]
    assert service_actions == ["restart", "start"]
    assert load_profile(paths.machine_settings)["internal_port"] == 8993


def test_port_failure_identifies_the_failed_rollback_stage(monkeypatch, tmp_path):
    paths = _paths(tmp_path)
    writes = []
    monkeypatch.setattr(
        "console.service_core.check_port",
        lambda port: PortStatus(port, True, message="available"),
    )

    def env_writer(_path, updates):
        writes.append(updates)
        if len(writes) == 2:
            raise RuntimeError("simulated rollback write failure")

    controller = ServiceController(
        paths,
        runner=lambda *_args, **_kwargs: Result(stdout="Running"),
        env_writer=env_writer,
        firewall_writer=lambda _rules: None,
        health_checker=lambda _port: False,
    )

    with pytest.raises(
        ServiceOperationError,
        match=(
            "failed while checking the new HTTP endpoint.*"
            "rollback failed while restoring the production environment"
        ),
    ):
        controller.change_port(8123)


def test_service_restart_uses_windows_control_and_waits_for_both_states(tmp_path):
    paths = _paths(tmp_path)
    calls = []
    controller = ServiceController(
        paths,
        runner=lambda args, **kwargs: calls.append((args, kwargs)) or Result(stdout="Running"),
    )

    controller.restart()

    arguments, options = calls[0]
    script = arguments[-1]
    assert arguments[0] == "powershell.exe"
    assert "$action = 'restart'" in script
    assert "Stop-Service -InputObject $service" in script
    assert "Start-Service -InputObject $service" in script
    assert script.count("$service.WaitForStatus") >= 2
    assert str(paths.service_executable) not in arguments
    assert options["timeout"] == 90


def test_console_reconciles_stale_profile_to_installed_runtime_port(tmp_path):
    paths = _paths(tmp_path)
    paths.env_file.write_text(
        "APP_PORT=8997\nPUBLIC_BASE_URL=http://127.0.0.1:8993\n",
        encoding="utf-8",
    )

    profile = reconcile_runtime_profile(paths)

    assert profile["public_port"] == 8997
    assert profile["local_port"] == 8997
    assert profile["internal_port"] == 8997
    assert load_profile(paths.machine_settings)["internal_port"] == 8997


def test_open_application_uses_current_app_port_not_stale_public_url(
    monkeypatch, tmp_path
):
    paths = _paths(tmp_path)
    paths.env_file.write_text(
        "APP_PORT=8997\nPUBLIC_BASE_URL=http://127.0.0.1:8993\n",
        encoding="utf-8",
    )
    opened = []
    monkeypatch.setattr("console.service_core.webbrowser.open", opened.append)
    controller = ServiceController(paths)

    controller.open_application()

    assert opened == ["http://127.0.0.1:8997"]


def test_failed_database_health_check_restores_url_and_machine_profile(tmp_path):
    paths = _paths(tmp_path)
    env_updates = []
    service = ServiceController(
        paths,
        runner=lambda *_args, **_kwargs: Result(),
        health_checker=lambda _port: False,
    )
    controller = DatabaseController(
        paths,
        service,
        env_writer=lambda path, updates: env_updates.append((path, updates)),
        connection_tester=lambda _values: {"ok": True, "errors": {}, "message": "ok"},
    )

    with pytest.raises(DatabaseOperationError, match="previous connection was restored"):
        controller.save(
            {
                "host": "db-new.local",
                "port": 5433,
                "database": "service_management",
                "username": "service_management",
                "password": "CandidatePassword@3718",
            }
        )

    assert "db-new.local" in env_updates[0][1]["DATABASE_URL"]
    assert env_updates[-1][1]["DATABASE_URL"].endswith("@localhost/app")
    restored = load_profile(paths.machine_settings)
    assert restored["postgres_host"] == "127.0.0.1"
    assert restored["postgres_port"] == 5432


def test_recent_logs_and_diagnostics_are_redacted(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    secret = "Never-In-Diagnostics-4817"
    (paths.logs / "service.log").write_text(
        f"DATABASE_URL=postgresql://user:{secret}@db/app\nSECRET_KEY={secret}\n",
        encoding="utf-8",
    )
    service = ServiceController(paths, runner=lambda *_args, **_kwargs: Result(stdout="Running"))
    assert secret not in service.recent_logs()
    system = SystemController(paths, service)
    monkeypatch.setattr(system, "firewall_state", lambda: "configured")
    destination = tmp_path / "diagnostics.json"

    system.export_diagnostics(destination)

    assert secret not in destination.read_text(encoding="utf-8")
    assert secret not in redact(f'password={secret}')


def test_update_verifies_checksum_and_invokes_deploy_release(tmp_path):
    paths = _paths(tmp_path)
    paths.deploy_script.write_text("# deployment entry point", encoding="utf-8")
    release = tmp_path / "service-management-2.0.0.zip"
    release.write_bytes(b"verified release bytes")
    digest = hashlib.sha256(release.read_bytes()).hexdigest()
    checksum = tmp_path / "release.sha256"
    checksum.write_text(f"{digest}  {release.name}\n", encoding="utf-8")
    calls = []
    service = ServiceController(paths, runner=lambda *_args, **_kwargs: Result())
    system = SystemController(
        paths,
        service,
        runner=lambda args, **_kwargs: calls.append(args) or Result(),
    )

    system.install_update(release, checksum)

    arguments = calls[0]
    assert str(paths.deploy_script) in arguments
    assert "-ReleasePackage" in arguments
    assert str(release) in arguments
    assert not any("alembic" in argument.lower() for argument in arguments)


def test_wrong_release_checksum_is_refused(tmp_path):
    release = tmp_path / "release.zip"
    release.write_bytes(b"release")
    checksum = tmp_path / "release.sha256"
    checksum.write_text(f"{'0' * 64}  {release.name}\n", encoding="utf-8")

    with pytest.raises(SystemOperationError, match="checksum verification failed"):
        verify_release_checksum(release, checksum)


def test_backup_configuration_is_validated_saved_and_installed(tmp_path):
    paths = replace(_paths(tmp_path), program_data=tmp_path / "ProgramData")
    pg_dump = tmp_path / "pg_dump.exe"
    pg_dump.write_bytes(b"test executable")
    calls = []
    service = ServiceController(paths, runner=lambda *_args, **_kwargs: Result())
    system = SystemController(
        paths,
        service,
        runner=lambda args, **_kwargs: calls.append(args) or Result(),
    )

    system.configure_backups(
        {
            "backup_enabled": True,
            "backup_interval_days": "3",
            "backup_retention_count": "14",
            "backup_include_uploads": True,
            "backup_upload_retention_count": "6",
            "backup_directory": r"D:\ServiceManagementBackups",
            "pg_dump_executable": str(pg_dump),
        }
    )

    saved = load_profile(paths.machine_settings)
    assert saved["backup_enabled"] is True
    assert saved["backup_interval_days"] == 3
    assert saved["backup_retention_count"] == 14
    assert saved["backup_upload_retention_count"] == 6
    assert len(calls) == 1
    generated = (paths.program_data / "install_database_backup_task.ps1").read_text(
        encoding="utf-8"
    )
    assert "$enabled = $true" in generated
    assert "$intervalDays = 3" in generated


def test_invalid_backup_configuration_changes_nothing(tmp_path):
    paths = _paths(tmp_path)
    before = load_profile(paths.machine_settings)
    calls = []
    service = ServiceController(paths, runner=lambda *_args, **_kwargs: Result())
    system = SystemController(
        paths,
        service,
        runner=lambda args, **_kwargs: calls.append(args) or Result(),
    )

    with pytest.raises(SystemOperationError, match="from 1 to 365"):
        system.configure_backups({"backup_interval_days": "0"})

    assert load_profile(paths.machine_settings) == before
    assert calls == []


def test_failed_backup_schedule_restores_previous_profile(tmp_path):
    paths = replace(_paths(tmp_path), program_data=tmp_path / "ProgramData")
    pg_dump = tmp_path / "pg_dump.exe"
    pg_dump.write_bytes(b"test executable")
    profile = load_profile(paths.machine_settings)
    profile["pg_dump_executable"] = str(pg_dump)
    save_profile(paths.machine_settings, profile)
    before = load_profile(paths.machine_settings)
    calls = []
    service = ServiceController(paths, runner=lambda *_args, **_kwargs: Result())

    def fail_then_succeed(args, **_kwargs):
        calls.append(args)
        return Result(returncode=1 if len(calls) == 1 else 0)

    system = SystemController(paths, service, runner=fail_then_succeed)
    with pytest.raises(SystemOperationError, match="previous settings were restored"):
        system.configure_backups({"backup_enabled": True})

    assert load_profile(paths.machine_settings) == before
    assert len(calls) == 2


def test_run_backup_now_refuses_when_automatic_backups_are_disabled(tmp_path):
    paths = _paths(tmp_path)
    calls = []
    service = ServiceController(paths, runner=lambda *_args, **_kwargs: Result())
    system = SystemController(
        paths,
        service,
        runner=lambda args, **_kwargs: calls.append(args) or Result(),
    )

    with pytest.raises(SystemOperationError, match="Enable and save"):
        system.run_backup_now()

    assert calls == []


def test_console_sources_do_not_use_invoke_expression_or_duplicate_deployment():
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("console").rglob("*.py")
    )
    shortcut = Path("scripts/Install-ServiceConsoleShortcuts.ps1").read_text(
        encoding="utf-8"
    )

    assert "Invoke-Expression" not in source
    assert "alembic upgrade" not in source
    assert "Deploy-Release.ps1" in source
    assert "Launch-ServiceConsole.ps1" in shortcut
    assert "$shortcut.TargetPath = $powershell" in shortcut
    assert "$shortcut.TargetPath = $pythonWindowed" not in shortcut
    assert "S-1-5-32-545" in shortcut


def test_console_launcher_elevates_before_accessing_the_protected_installation():
    launcher_script = Path("scripts/Launch-ServiceConsole.ps1").read_text(
        encoding="utf-8"
    )

    assert "-Verb RunAs" in launcher_script
    assert "pythonw.exe" in launcher_script
    assert "'-m', 'console'" in launcher_script
    assert "Run the installer in Repair mode" in launcher_script
    assert "DATABASE_URL" not in launcher_script
    assert "password" not in launcher_script.lower()


def test_console_selects_production_environment_before_importing_the_gui():
    source = Path("console/__main__.py").read_text(encoding="utf-8")

    assert source.index('os.environ["SMS_ENV_FILE"]') < source.index(
        "from .app import ConsoleApp"
    )
