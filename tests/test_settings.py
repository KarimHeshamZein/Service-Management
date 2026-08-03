import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import settings
from app.deployment_config import (
    PROFILE_FIELDS,
    audit_json,
    database_backup_windows_script,
    validate_profile,
)
from app.models import DeploymentSettings, DeploymentSettingsAudit
from app.routers import settings as settings_router
from tests.conftest import ADMIN, CUSTOMER_A, LEADER_A, login, logout


def _valid_profile(**overrides):
    profile = {
        "public_enabled": "1",
        "public_ip": "203.0.113.20",
        "public_port": "8993",
        "allowed_remote_ips": "198.51.100.4",
        "local_interface": "Ethernet 2",
        "local_ip": "192.168.10.50",
        "local_port": "8993",
        "configure_static_local_ip": "1",
        "local_prefix_length": "24",
        "local_gateway": "192.168.10.1",
        "local_dns_servers": "192.168.10.1, 1.1.1.1",
        "internal_port": "8993",
        "postgres_host": "127.0.0.1",
        "postgres_port": "5432",
        "backup_enabled": "1",
        "backup_interval_days": "3",
        "backup_retention_count": "20",
        "backup_include_uploads": "1",
        "backup_upload_retention_count": "7",
        "backup_directory": r"C:\ServiceManagement\backups\scheduled",
        "pg_dump_executable": (
            r"C:\Program Files\PostgreSQL\16\bin\pg_dump.exe"
        ),
        "action": "save",
    }
    profile.update(overrides)
    return profile


def test_backup_windows_paths_reject_command_characters():
    valid = _valid_profile()
    _, errors = validate_profile(valid)
    assert "backup_directory" not in errors
    assert "pg_dump_executable" not in errors

    malicious = r'C:\x" & whoami & "'
    _, errors = validate_profile(
        _valid_profile(
            backup_directory=malicious,
            pg_dump_executable=malicious,
        )
    )
    assert "backup_directory" in errors
    assert "pg_dump_executable" in errors


def test_upload_backup_fields_validate_and_round_trip():
    profile, errors = validate_profile(_valid_profile())
    assert errors == {}
    assert profile["backup_include_uploads"] is True
    assert profile["backup_upload_retention_count"] == 7

    disabled, errors = validate_profile(
        _valid_profile(
            backup_include_uploads="",
            backup_upload_retention_count="365",
        )
    )
    assert errors == {}
    assert disabled["backup_include_uploads"] is False
    assert disabled["backup_upload_retention_count"] == 365

    for invalid in ("0", "366", "not-a-number"):
        _, errors = validate_profile(
            _valid_profile(backup_upload_retention_count=invalid)
        )
        assert "backup_upload_retention_count" in errors


def test_settings_is_administrator_only_and_hidden_from_other_roles(client):
    assert client.get("/settings").status_code == 303

    login(client, *LEADER_A)
    reports = client.get("/reports")
    assert 'href="/settings"' not in reports.text
    assert client.get("/settings").status_code == 403
    assert client.get("/settings/windows-script").status_code == 404
    assert client.get("/settings/database-backup-script").status_code == 404

    logout(client)
    login(client, *CUSTOMER_A)
    assert client.get("/settings").status_code == 403

    logout(client)
    login(client, *ADMIN)
    page = client.get("/settings")
    assert page.status_code == 200
    assert 'href="/settings"' in page.text
    assert "Public HTTP access" in page.text
    assert "Machine settings are read-only here." in page.text
    assert 'action="/settings"' not in page.text
    assert "windows-script" not in page.text
    assert "database-backup-script" not in page.text


def test_web_settings_are_read_only_and_machine_script_routes_are_removed(client, db):
    login(client, *ADMIN)
    data = _valid_profile()
    response = client.post("/settings", data=data)
    assert response.status_code == 405
    assert db.get(DeploymentSettings, 1) is None
    assert db.query(DeploymentSettingsAudit).count() == 0
    assert client.get("/settings/windows-script").status_code == 404
    assert client.get("/settings/database-backup-script").status_code == 404


def test_settings_router_defines_no_machine_mutation_endpoint():
    source = (Path(__file__).parents[1] / "app" / "routers" / "settings.py").read_text(
        encoding="utf-8"
    )
    assert "@router.post" not in source
    assert '"/windows-script"' not in source
    assert '"/database-backup-script"' not in source


def test_read_only_settings_prefers_the_local_machine_profile(
    client, tmp_path, monkeypatch
):
    env_file = tmp_path / "shared" / ".env"
    env_file.parent.mkdir()
    (env_file.parent / "machine-settings.json").write_text(
        json.dumps({"local_ip": "192.168.50.20", "local_port": 8993}),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_router, "ENV_FILE", env_file)
    login(client, *ADMIN)

    page = client.get("/settings")

    assert page.status_code == 200
    assert "192.168.50.20:8993" in page.text


def test_read_only_settings_surfaces_an_unreadable_machine_profile(
    client, tmp_path, monkeypatch
):
    env_file = tmp_path / "shared" / ".env"
    env_file.parent.mkdir()
    (env_file.parent / "machine-settings.json").write_text("not-json", encoding="utf-8")
    monkeypatch.setattr(settings_router, "ENV_FILE", env_file)
    login(client, *ADMIN)

    page = client.get("/settings")

    assert page.status_code == 200
    assert "The local machine settings file is unreadable" in page.text


def test_read_only_settings_preserve_legacy_audit_history(client, db):
    profile, errors = validate_profile(_valid_profile())
    assert errors == {}
    _save_backup_profile(db)
    db.add(
        DeploymentSettingsAudit(
            configuration_version=1,
            edited_by_id=1,
            editor_name="Test Admin",
            before_json="{}",
            after_json=audit_json(profile),
        )
    )
    db.commit()
    login(client, *ADMIN)

    page = client.get("/settings")

    assert page.status_code == 200
    assert "Profile version 1" in page.text
    assert "Test Admin" in page.text
    assert "Settings audit" in page.text


def test_database_backup_task_generator_remains_secret_free():
    profile, errors = validate_profile(_valid_profile())
    assert errors == {}
    script = database_backup_windows_script(profile)
    assert "$intervalDays = 3" in script
    assert "$retentionCount = 20" in script
    assert "Register-ScheduledTask" in script
    assert "S-1-5-19" in script
    assert r"Join-Path $InstallRoot 'shared\.env'" in script
    assert str(settings.upload_dir) not in script
    assert "postgresql://postgres:postgres" not in script
    dump_position = script.index("& $PgDumpExecutable")
    snapshot_position = script.index(
        "$uploadSetting = Read-DotEnvValue 'UPLOAD_DIR'"
    )
    assert dump_position < snapshot_position
    assert '"service-management-$timestamp.dump"' in script
    assert '"uploads-$timestamp"' in script
    assert "foreach ($sourceFile in $sourceFiles)" in script
    assert "foreach ($previousFile" not in script
    assert "New-Item -ItemType HardLink" in script
    for status_field in (
        "last_success_utc",
        "uploads_snapshot",
        "uploads_mode",
        "interval_days",
    ):
        assert status_field in script
    assert script.index("$snapshotComplete = $true") < script.index(
        "Remove-OldBackupItems 'uploads-*'"
    )


def test_database_backup_script_guards_upload_logic_when_snapshots_are_disabled():
    profile, errors = validate_profile(_valid_profile(backup_include_uploads=""))
    assert errors == {}
    script = database_backup_windows_script(profile)
    assert "$includeUploads = 0" in script
    assert "if ($IncludeUploads -eq 1)" in script
    assert "include_uploads = $includeUploads" in script
    assert "$IncludeUploads = [int]$config.include_uploads" in script


def test_backup_task_action_stays_short_with_long_configured_paths():
    long_backup_directory = (
        r"D:\ServiceManagementSystem\Backups\Scheduled"
        + r"\Database-And-Upload-Snapshots\Deep-Production-Path" * 4
    )
    long_pg_dump = (
        r"C:\Program Files\PostgreSQL\16"
        + r"\Long-Installation-Directory" * 4
        + r"\bin\pg_dump.exe"
    )
    profile, errors = validate_profile(
        _valid_profile(
            backup_directory=long_backup_directory,
            pg_dump_executable=long_pg_dump,
        )
    )
    assert errors == {}

    script = database_backup_windows_script(profile)
    task_command = (
        "powershell.exe -NoProfile -ExecutionPolicy Bypass -File "
        '"C:\\ProgramData\\ServiceManagementSystem\\Backup-Database.ps1"'
    )
    assert len(task_command) == 116
    assert len(task_command) < 200
    assert "$taskCommand = 'powershell.exe ' + $taskArguments" in script
    assert long_backup_directory in script
    assert long_pg_dump in script
    task_section = script[script.index("$taskArguments ="):]
    assert long_backup_directory not in task_section
    assert long_pg_dump not in task_section


def test_backup_disable_is_a_clean_no_op_when_the_task_does_not_exist():
    profile, errors = validate_profile(_valid_profile(backup_enabled=""))
    assert errors == {}

    script = database_backup_windows_script(profile)
    disable_start = script.index("if (-not $enabled)")
    disable_end = script.index("if (-not (Test-Path -LiteralPath $envPath))")
    disable_branch = script[disable_start:disable_end]
    assert "Unregister-ScheduledTask" in disable_branch
    assert "-ErrorAction SilentlyContinue" in disable_branch
    assert "schtasks.exe" not in disable_branch
    assert "exit 0" in disable_branch


def _save_backup_profile(db, **overrides):
    profile, errors = validate_profile(_valid_profile(**overrides))
    assert errors == {}
    saved = DeploymentSettings(
        id=1,
        updated_by_id=1,
        updated_by_name="Test Admin",
    )
    for field in PROFILE_FIELDS:
        setattr(saved, field, profile[field])
    db.add(saved)
    db.commit()


def _write_backup_status(root, value):
    status_dir = root / "ServiceManagementSystem"
    status_dir.mkdir(parents=True, exist_ok=True)
    (status_dir / "database-backup-status.json").write_text(
        json.dumps(value),
        encoding="utf-8",
    )


def test_settings_marks_stale_backup_as_error(client, db, monkeypatch, tmp_path):
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path))
    login(client, *ADMIN)
    _save_backup_profile(db)
    completed = datetime.now(timezone.utc) - timedelta(days=9)
    _write_backup_status(
        tmp_path,
        {
            "ok": True,
            "completed_utc": completed.isoformat(),
            "last_success_utc": completed.isoformat(),
            "backup_file": r"C:\backups\stale.dump",
            "uploads_snapshot": r"C:\backups\uploads-stale",
            "uploads_mode": "hardlink",
            "interval_days": 3,
            "message": "Backup completed.",
        },
    )

    page = client.get("/settings")
    assert 'data-backup-state="error"' in page.text
    assert "latest backup is stale" in page.text
    assert "Last completed 9 days ago." in page.text


def test_settings_shows_fresh_complete_backup_as_success(client, db, monkeypatch, tmp_path):
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path))
    login(client, *ADMIN)
    _save_backup_profile(db)
    completed = datetime.now(timezone.utc) - timedelta(hours=2)
    _write_backup_status(
        tmp_path,
        {
            "ok": True,
            "completed_utc": completed.isoformat(),
            "last_success_utc": completed.isoformat(),
            "backup_file": r"C:\backups\fresh.dump",
            "uploads_snapshot": r"C:\backups\uploads-fresh",
            "uploads_mode": "hardlink",
            "interval_days": 3,
            "message": "Database and upload snapshot completed.",
        },
    )

    page = client.get("/settings")
    assert 'data-backup-state="success"' in page.text
    assert "Last completed 2 hours ago." in page.text
    assert "Complete upload snapshot (hardlink mode)" in page.text


def test_settings_marks_missing_and_malformed_status_as_error(
    client, db, monkeypatch, tmp_path
):
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path))
    login(client, *ADMIN)
    _save_backup_profile(db)

    missing = client.get("/settings")
    assert 'data-backup-state="error"' in missing.text
    assert "status is missing or unreadable" in missing.text

    status_dir = tmp_path / "ServiceManagementSystem"
    status_dir.mkdir(parents=True)
    (status_dir / "database-backup-status.json").write_text(
        "{truncated",
        encoding="utf-8",
    )
    malformed = client.get("/settings")
    assert malformed.status_code == 200
    assert 'data-backup-state="error"' in malformed.text


def test_failed_backup_shows_last_success_and_disabled_uploads_are_informational(
    client, db, monkeypatch, tmp_path
):
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path))
    login(client, *ADMIN)
    _save_backup_profile(db, backup_include_uploads="")
    attempted = datetime.now(timezone.utc) - timedelta(hours=1)
    succeeded = datetime.now(timezone.utc) - timedelta(days=2)
    _write_backup_status(
        tmp_path,
        {
            "ok": False,
            "completed_utc": attempted.isoformat(),
            "last_success_utc": succeeded.isoformat(),
            "backup_file": "",
            "uploads_snapshot": "",
            "uploads_mode": "skipped",
            "interval_days": 3,
            "message": "pg_dump failed.",
        },
    )
    failed = client.get("/settings")
    assert 'data-backup-state="error"' in failed.text
    assert "Last successful backup 2 days ago." in failed.text

    _write_backup_status(
        tmp_path,
        {
            "ok": True,
            "completed_utc": attempted.isoformat(),
            "last_success_utc": attempted.isoformat(),
            "backup_file": r"C:\backups\database-only.dump",
            "uploads_snapshot": "",
            "uploads_mode": "skipped",
            "interval_days": 3,
            "message": "Database backup completed; upload snapshots are disabled.",
        },
    )
    database_only = client.get("/settings")
    assert 'data-backup-state="info"' in database_only.text
    assert "restore will not include photos" in database_only.text
