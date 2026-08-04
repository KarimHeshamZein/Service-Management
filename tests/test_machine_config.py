"""Machine configuration core regression tests."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import traceback
from io import StringIO
from pathlib import Path

import psycopg2
import pytest
from dotenv import dotenv_values

import bootstrap_cli
from app.machine_config.endpoints import endpoint_updates
from app.machine_config.env_file import (
    EnvFileError,
    READ_ACCESS,
    WindowsEnvAcl,
    _powershell_acl,
    update_env_file,
)
from app.machine_config.firewall import (
    FirewallRule,
    apply_firewall_rules,
    detect_firewall_state,
    expected_rules,
    read_firewall_rules,
)
from app.machine_config.ports import check_port, parse_excluded_port_ranges
from app.machine_config.validation import validate_network
from app.models import User
from app.security import verify_password


class RecordingAcl:
    def __init__(self, target: Path | None = None, *, fail_target_once: bool = False):
        self.target = target
        self.fail_target_once = fail_target_once
        self.applied: list[Path] = []
        self.verified: list[Path] = []

    def apply(self, path: Path) -> None:
        self.applied.append(path)

    def verify(self, path: Path) -> bool:
        self.verified.append(path)
        if self.fail_target_once and path == self.target:
            self.fail_target_once = False
            return False
        return True


def _profile(**overrides):
    values = {
        "public_enabled": True,
        "public_ip": "203.0.113.20",
        "public_port": 8993,
        "allowed_remote_ips": "198.51.100.0/24\n198.51.100.7/32",
        "local_ip": "192.168.10.50",
        "configure_static_local_ip": True,
        "local_port": 8993,
        "internal_port": 8993,
    }
    values.update(overrides)
    return values


def test_endpoint_values_are_recomputed_for_every_address_and_port_change():
    original = endpoint_updates(_profile())
    changed = endpoint_updates(
        _profile(public_ip="203.0.113.99", public_port=8123, local_port=8123, internal_port=8123)
    )
    local = endpoint_updates(_profile(public_enabled=False))

    assert original["PUBLIC_BASE_URL"] == "http://203.0.113.20:8993"
    assert changed["PUBLIC_BASE_URL"] == "http://203.0.113.99:8123"
    assert changed["APP_PORT"] == "8123"
    assert local["PUBLIC_BASE_URL"] == "http://192.168.10.50:8993"
    assert all(value["APP_HOST"] == "0.0.0.0" for value in (original, changed, local))
    assert all(value["SESSION_HTTPS_ONLY"] == "false" for value in (original, changed, local))


def test_shared_network_validation_reuses_application_rules():
    _, errors = validate_network(
        _profile(public_port=9443, tls_enabled=True),
        base={
            **_profile(),
            "local_interface": "",
            "configure_static_local_ip": False,
            "local_prefix_length": 24,
            "local_gateway": "",
            "local_dns_servers": "",
            "postgres_host": "127.0.0.1",
            "postgres_port": 5432,
            "backup_enabled": False,
            "backup_interval_days": 1,
            "backup_retention_count": 30,
            "backup_include_uploads": True,
            "backup_upload_retention_count": 7,
            "backup_directory": r"C:\ServiceManagement\backups\scheduled",
            "pg_dump_executable": r"C:\Program Files\PostgreSQL\16\bin\pg_dump.exe",
        },
    )

    assert "public_port" in errors
    assert errors["tls_enabled"] == "HTTPS is not available yet. Use HTTP."


def test_windows_excluded_ranges_are_parsed_and_honoured():
    ranges = parse_excluded_port_ranges(
        "Start Port    End Port\n----------    --------\n      8000        8100\n"
        "     50000       50059     *\n"
    )

    assert 8050 in ranges[0]
    status = check_port(8050, excluded_ranges=ranges)
    assert status.available is False
    assert status.excluded is True


def test_bound_port_is_reported_unavailable():
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    try:
        status = check_port(port, host="127.0.0.1", excluded_ranges=())
    finally:
        listener.close()

    assert status.available is False
    assert status.excluded is False


def test_firewall_state_is_detected_per_complete_profile():
    rules = expected_rules(_profile())
    observed = [
        {
            "name": rule.name,
            "protocol": "TCP",
            "direction": "Inbound",
            "action": "Allow",
            "local_port": str(rule.local_port),
            "local_address": [rule.local_address],
            "remote_addresses": list(rule.remote_addresses),
        }
        for rule in rules
    ]

    configured = detect_firewall_state(_profile(), observed)
    drifted = detect_firewall_state(
        _profile(),
        [{**observed[0], "local_port": "9000"}, observed[1]],
    )
    missing = detect_firewall_state(_profile(), observed[:1])

    assert configured.state == "configured"
    assert drifted.state == "drifted"
    assert drifted.drifted == ("SMS Local HTTP",)
    assert missing.state == "missing"
    assert missing.missing == ("SMS Public HTTP",)

    stale_public = detect_firewall_state(
        _profile(public_enabled=False),
        observed,
    )
    assert stale_public.state == "drifted"
    assert stale_public.unexpected == ("SMS Public HTTP",)


def test_dhcp_profile_always_gets_a_local_subnet_firewall_rule():
    rules = expected_rules(
        _profile(
            local_ip="192.168.10.50",
            configure_static_local_ip=False,
            public_enabled=False,
        )
    )

    assert rules == (
        FirewallRule("SMS Local HTTP", "Any", 8993, ("LocalSubnet",)),
    )


def test_dhcp_validation_accepts_an_empty_local_address():
    profile, errors = validate_network(
        {"local_ip": "", "configure_static_local_ip": False},
        base={
            **_profile(public_enabled=False),
            "local_interface": "Ethernet",
            "local_prefix_length": 24,
            "local_gateway": "",
            "local_dns_servers": "",
            "postgres_host": "127.0.0.1",
            "postgres_port": 5432,
            "backup_enabled": False,
            "backup_interval_days": 1,
            "backup_retention_count": 30,
            "backup_include_uploads": True,
            "backup_upload_retention_count": 7,
            "backup_directory": r"C:\ServiceManagement\backups\scheduled",
            "pg_dump_executable": r"C:\Program Files\PostgreSQL\16\bin\pg_dump.exe",
        },
    )

    assert "local_ip" not in errors
    assert profile["local_ip"] == ""


def test_firewall_writer_wraps_an_empty_rule_set_for_windows_powershell():
    calls = []

    def runner(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    apply_firewall_rules((), runner=runner)

    arguments, options = calls[0]
    assert json.loads(options["env"]["SMS_FIREWALL_RULES"]) == {"rules": []}
    assert "$rules = @($config.rules)" in arguments[-1]
    assert "$rules = @($env:SMS_FIREWALL_RULES | ConvertFrom-Json)" not in arguments[-1]
    assert "Get-NetFirewallRule -ErrorAction Stop" in arguments[-1]
    assert "Where-Object { $_.DisplayName -in $managedNames }" in arguments[-1]
    assert "Get-NetFirewallRule -DisplayName $name" not in arguments[-1]


def test_firewall_reader_does_not_query_potentially_missing_names(monkeypatch):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, stdout="[]", stderr="")

    monkeypatch.setattr("app.machine_config.firewall.subprocess.run", run)

    assert read_firewall_rules() == ()
    arguments, _options = calls[0]
    assert "Get-NetFirewallRule -ErrorAction Stop" in arguments[-1]
    assert "$_.DisplayName -in $managedNames" in arguments[-1]
    assert "Get-NetFirewallRule -DisplayName $name" not in arguments[-1]


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell JSON behavior requires Windows")
@pytest.mark.parametrize("rule_count", [0, 1, 2])
def test_windows_powershell_decodes_wrapped_firewall_rule_counts(rule_count):
    payload = json.dumps(
        {
            "rules": [
                {
                    "name": f"Rule {index}",
                    "local_address": "192.0.2.10",
                    "local_port": 8995 + index,
                    "remote_addresses": ["LocalSubnet"],
                }
                for index in range(rule_count)
            ]
        },
        separators=(",", ":"),
    )
    environment = os.environ.copy()
    environment["SMS_FIREWALL_RULES"] = payload
    command = r"""
$config = $env:SMS_FIREWALL_RULES | ConvertFrom-Json
$rules = @($config.rules)
Write-Output $rules.Count
foreach ($rule in $rules) { Write-Output ([string]$rule.name) }
"""

    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[0] == str(rule_count)
    assert lines[1:] == [f"Rule {index}" for index in range(rule_count)]


@pytest.mark.skipif(os.name != "nt", reason="Windows Firewall cmdlets require Windows")
def test_windows_firewall_filter_succeeds_when_managed_rules_do_not_exist():
    command = r"""
$ErrorActionPreference = 'Stop'
$managedNames = @(
  'SMS pytest rule that must not exist 7A118F',
  'SMS pytest rule that must not exist C3D942'
)
Get-NetFirewallRule -ErrorAction Stop |
  Where-Object { $_.DisplayName -in $managedNames } |
  Remove-NetFirewallRule -ErrorAction Stop
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_environment_write_is_atomic_backed_up_and_acl_verified(tmp_path):
    target = (tmp_path / ".env").resolve()
    target.write_text("# keep\nAPP_PORT=8993\nSECRET_KEY=old\n", encoding="utf-8")
    acl = RecordingAcl()

    result = update_env_file(target, {"APP_PORT": "8123"}, acl=acl)

    assert target.read_text(encoding="utf-8") == "# keep\nAPP_PORT=8123\nSECRET_KEY=old\n"
    assert result.backup_path is not None
    assert result.backup_path.read_text(encoding="utf-8").endswith("APP_PORT=8993\nSECRET_KEY=old\n")
    assert target in acl.applied
    assert target in acl.verified
    assert result.backup_path in acl.verified


def test_windows_acl_verifier_requires_exact_owner_and_three_explicit_rules(monkeypatch):
    value = {
        "protected": True,
        "owner": "S-1-5-32-544",
        "rules": [
            {"sid": "S-1-5-18", "rights": 0x1F01FF, "type": "Allow", "inherited": False},
            {"sid": "S-1-5-32-544", "rights": 0x1F01FF, "type": "Allow", "inherited": False},
            {"sid": "S-1-5-19", "rights": 0x120089, "type": "Allow", "inherited": False},
        ],
    }

    def inspect_acl(_script, _path):
        return subprocess.CompletedProcess([], 0, stdout=json.dumps(value), stderr="")

    monkeypatch.setattr("app.machine_config.env_file._powershell_acl", inspect_acl)
    manager = WindowsEnvAcl()
    assert manager.verify(Path(r"C:\ServiceManagement\shared\.env")) is True

    value["rules"].append(
        {"sid": "S-1-5-21-999", "rights": 1, "type": "Allow", "inherited": False}
    )
    assert manager.verify(Path(r"C:\ServiceManagement\shared\.env")) is False


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL inspection requires Windows")
def test_windows_acl_inspection_translates_the_real_owner_string(tmp_path):
    target = (tmp_path / "acl-inspection.txt").resolve()
    target.write_text("read-only inspection\n", encoding="utf-8")

    result = _powershell_acl(WindowsEnvAcl._inspect_script, target)

    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value["owner"].startswith("S-1-")
    assert isinstance(value["rules"], (dict, list))


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL normalization requires Windows")
def test_windows_read_rule_normalizes_to_read_plus_synchronize():
    command = r"""
$sid = [Security.Principal.SecurityIdentifier]::new('S-1-5-19')
$rule = [Security.AccessControl.FileSystemAccessRule]::new(
    $sid,
    [Security.AccessControl.FileSystemRights]::Read,
    [Security.AccessControl.AccessControlType]::Allow
)
[int64]$rule.FileSystemRights
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert int(result.stdout.strip()) == READ_ACCESS == 0x120089


def test_acl_verification_failure_restores_previous_environment_without_secret_leak(tmp_path):
    target = (tmp_path / ".env").resolve()
    target.write_text("APP_PORT=8993\nDATABASE_URL=old\n", encoding="utf-8")
    secret = "Planted-Database-Password-9371"
    acl = RecordingAcl(target, fail_target_once=True)

    try:
        update_env_file(target, {"DATABASE_URL": f"postgresql://user:{secret}@db/app"}, acl=acl)
    except EnvFileError as exc:
        rendered_error = str(exc) + traceback.format_exc()
    else:
        raise AssertionError("the planted ACL verification failure was accepted")

    assert target.read_text(encoding="utf-8") == "APP_PORT=8993\nDATABASE_URL=old\n"
    assert secret not in rendered_error


def test_environment_values_with_spaces_quotes_and_hashes_round_trip(tmp_path):
    target = (tmp_path / ".env").resolve()
    target.write_text("APP_PORT=8993\n", encoding="utf-8")
    value = 'complex # value with "quotes" and C:\\path'

    update_env_file(target, {"SMTP_PASSWORD": value}, acl=RecordingAcl())

    assert dotenv_values(target)["SMTP_PASSWORD"] == value


def test_concurrent_environment_updates_serialize_without_losing_keys(tmp_path):
    target = (tmp_path / ".env").resolve()
    target.write_text("BASE=1\n", encoding="utf-8")
    acl = RecordingAcl()
    errors: list[Exception] = []

    def write(index: int) -> None:
        try:
            update_env_file(target, {f"WORKER_{index}": str(index)}, acl=acl)
        except Exception as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    workers = [threading.Thread(target=write, args=(index,)) for index in range(6)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)

    text = target.read_text(encoding="utf-8")
    assert errors == []
    assert all(not worker.is_alive() for worker in workers)
    assert all(f"WORKER_{index}={index}" in text for index in range(6))


class FakeEngine:
    def __init__(self, failure: Exception | None = None):
        self.failure = failure
        self.disposed = False

    def connect(self):
        if self.failure:
            raise self.failure
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, _query):
        return None

    def dispose(self):
        self.disposed = True


class FakeCursor:
    def __init__(self):
        self.results = [None, None]
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, statement, parameters=None):
        self.executions.append((statement, parameters))

    def fetchone(self):
        return self.results.pop(0)


class FakePostgresConnection:
    def __init__(self):
        self.autocommit = False
        self.cursor_instance = FakeCursor()
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


def test_database_test_uses_throwaway_engine_and_redacts_failures():
    secret = "Never-Print-This-Password-4812"
    engine = FakeEngine(OSError(secret))
    result = bootstrap_cli.test_database_command(
        {
            "host": "127.0.0.1",
            "port": 5432,
            "database": "service_management",
            "username": "service_management",
            "password": secret,
        },
        engine_factory=lambda *_args, **_kwargs: engine,
    )

    assert result["ok"] is False
    assert engine.disposed is True
    assert secret not in json.dumps(result)


def test_json_cli_reads_password_from_stdin_and_never_outputs_it():
    secret = "Only-In-Standard-Input-5197"
    output = StringIO()
    exit_code = bootstrap_cli.main(
        ["test-database"],
        stdin=StringIO(
            json.dumps(
                {
                    "host": "bad host!",
                    "port": 5432,
                    "database": "service_management",
                    "username": "service_management",
                    "password": secret,
                }
            )
        ),
        stdout=output,
    )

    response = json.loads(output.getvalue())
    assert exit_code == 1
    assert response["ok"] is False
    assert secret not in output.getvalue()


def test_json_cli_rejects_password_supplied_as_an_argument():
    secret = "Never-Accept-Argv-Password-2491"
    output = StringIO()

    exit_code = bootstrap_cli.main(
        ["test-database", secret],
        stdin=StringIO("{}"),
        stdout=output,
    )

    assert exit_code == 2
    assert json.loads(output.getvalue())["errors"]["command"]
    assert secret not in output.getvalue()


def test_role_database_creation_uses_bound_password_and_redacts_result():
    secret = "Application-Role-Secret-7318"
    connection = FakePostgresConnection()
    result = bootstrap_cli.create_role_database_command(
        {
            "admin": {
                "host": "127.0.0.1",
                "port": 5432,
                "database": "postgres",
                "username": "postgres",
                "password": "Admin-Secret-4819",
            },
            "application": {
                "database": "service_management_new",
                "username": "service_management_new",
                "password": secret,
            },
        },
        connector=lambda **_kwargs: connection,
    )

    assert result["ok"] is True
    assert connection.autocommit is True
    assert connection.closed is True
    create_role_call = connection.cursor_instance.executions[2]
    assert create_role_call[1] == (secret,)
    assert secret not in str(create_role_call[0])
    assert secret not in json.dumps(result)


def test_role_database_connection_failure_does_not_expose_driver_message():
    secret = "Driver-Message-Secret-1937"

    def fail(**_kwargs):
        raise psycopg2.OperationalError(secret)

    result = bootstrap_cli.create_role_database_command(
        {
            "admin": {
                "host": "127.0.0.1",
                "port": 5432,
                "database": "postgres",
                "username": "postgres",
                "password": secret,
            },
            "application": {
                "database": "service_management_new",
                "username": "service_management_new",
                "password": secret,
            },
        },
        connector=fail,
    )

    assert result["ok"] is False
    assert secret not in json.dumps(result)


def test_json_cli_create_admin_calls_existing_core(db):
    db.query(User).delete()
    db.commit()
    password = "Bootstrap@5719"

    result = bootstrap_cli.create_admin_command(
        {"full_name": "First Admin", "username": "first.admin", "password": password}
    )

    assert result["ok"] is True
    created = db.query(User).one()
    assert created.username == "first.admin"
    assert created.password_hash != password
    assert verify_password(password, created.password_hash)
    assert password not in json.dumps(result)


def test_release_package_includes_bootstrap_cli():
    package_script = Path("scripts/New-ReleasePackage.ps1").read_text(encoding="utf-8")
    deploy_script = Path("scripts/Deploy-Release.ps1").read_text(encoding="utf-8")

    assert "'bootstrap_cli.py'" in package_script
    assert "'bootstrap_cli.py'" in deploy_script
