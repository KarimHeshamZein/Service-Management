"""Production release packages preserve secrets and persistent data."""
from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
import zipfile
from pathlib import Path

import psycopg2


ROOT = Path(__file__).resolve().parents[1]


def test_release_package_contains_runtime_but_excludes_persistent_data(tmp_path):
    script = ROOT / "scripts" / "New-ReleasePackage.ps1"
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-File",
            str(script),
            "-Version",
            "0.0.0-test",
            "-OutputDirectory",
            str(tmp_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    archive = tmp_path / "service-management-0.0.0-test.zip"
    assert archive.is_file()
    with zipfile.ZipFile(archive) as package:
        names = {name.replace("\\", "/") for name in package.namelist()}

    assert {
        "app/main.py",
        "app/static/fonts/NotoSansArabic-Regular.ttf",
        "app/static/fonts/NotoSansArabic-Bold.ttf",
        "app/static/fonts/OFL-Noto.txt",
        "alembic.ini",
        "requirements.txt",
        "release.json",
        "create_admin.py",
        "bootstrap_cli.py",
        "serve.py",
        "console/__main__.py",
        "scripts/Install-ServiceConsoleShortcuts.ps1",
        "scripts/Launch-ServiceConsole.ps1",
        "scripts/Deploy-Release.ps1",
        "scripts/Install-Offline.ps1",
        "scripts/Restore-Backup.ps1",
        "scripts/New-OfflineBundle.ps1",
        "docs/PRODUCTION_UPDATES.md",
    }.issubset(names)
    assert not any(
        part in {".env", ".venv", "data", "tests", "tmp", "__pycache__", ".pytest_cache"}
        for name in names
        for part in name.split("/")
    )
    assert not any(name.endswith((".pyc", ".pyo")) for name in names)


def test_install_server_script_parses_cleanly():
    script = ROOT / "scripts" / "Install-Server.ps1"
    escaped_path = str(script).replace("'", "''")
    command = (
        "$tokens = $null; $parseErrors = $null; "
        "[System.Management.Automation.Language.Parser]::ParseFile("
        f"'{escaped_path}', [ref]$tokens, [ref]$parseErrors) | Out-Null; "
        "if ($parseErrors.Count -gt 0) { "
        "$parseErrors | ForEach-Object { Write-Error $_.ToString() }; exit 1 }"
    )

    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_install_server_script_has_secure_bootstrap_contract():
    script = ROOT / "scripts" / "Install-Server.ps1"
    text = script.read_text(encoding="utf-8")
    lowered = text.lower()

    assert "sc.exe create" not in lowered
    assert "nssm" not in lowered
    assert "read-host" not in lowered
    assert "[security.securestring]$databasepassword" in lowered
    assert "security.cryptography.randomnumbergenerator" in lowered
    assert "replace-me-with-a-long-random-value" not in text
    assert re.search(
        r"Set-EnvironmentValue\s+\$environmentLines\s+'SECRET_KEY'\s+\$secretKey",
        text,
    )
    assert "APP_HOST=127.0.0.1" not in text
    assert re.search(
        r"Set-EnvironmentValue\s+\$environmentLines\s+'APP_HOST'\s+'0\.0\.0\.0'",
        text,
    )
    assert re.search(
        r"Set-EnvironmentValue\s+\$environmentLines\s+'PUBLIC_BASE_URL'",
        text,
    )
    assert '"http://127.0.0.1:$Port"' in text
    assert "<user>LocalService</user>" in text
    assert '<env name="SMS_ENV_FILE"' in text
    assert '<env name="TEMP"' in text
    assert '<arguments>serve.py</arguments>' in text
    assert "S-1-5-19" in text
    assert (
        "$environmentExists = Test-Path -LiteralPath $environmentPath -PathType Leaf"
        in text
    )
    assert "Environment file already exists; left completely unchanged" in text
    assert "$databasePasswordPlaintext = ConvertFrom-SecureValue" in text
    assert "Password = $databasePasswordPlaintext" in text
    assert "$databasePassword = ConvertFrom-SecureValue" not in text


def test_install_server_script_is_in_source_and_release_package(tmp_path):
    install_script = ROOT / "scripts" / "Install-Server.ps1"
    assert install_script.is_file()

    package_script = ROOT / "scripts" / "New-ReleasePackage.ps1"
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-File",
            str(package_script),
            "-Version",
            "0.0.1-install-test",
            "-OutputDirectory",
            str(tmp_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    archive = tmp_path / "service-management-0.0.1-install-test.zip"
    with zipfile.ZipFile(archive) as package:
        names = {name.replace("\\", "/") for name in package.namelist()}

    assert "scripts/Install-Server.ps1" in names


def test_offline_deployment_scripts_parse_cleanly():
    for script_name in (
        "Install-Offline.ps1",
        "New-OfflineBundle.ps1",
        "Deploy-Release.ps1",
        "Uninstall-Server.ps1",
        "Restore-Backup.ps1",
        "Install-ServiceConsoleShortcuts.ps1",
        "Launch-ServiceConsole.ps1",
    ):
        script = ROOT / "scripts" / script_name
        escaped_path = str(script).replace("'", "''")
        command = (
            "$tokens = $null; $parseErrors = $null; "
            "[System.Management.Automation.Language.Parser]::ParseFile("
            f"'{escaped_path}', [ref]$tokens, [ref]$parseErrors) | Out-Null; "
            "if ($parseErrors.Count -gt 0) { "
            "$parseErrors | ForEach-Object { Write-Error $_.ToString() }; exit 1 }"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        assert result.returncode == 0, f"{script_name}: {result.stderr}"


def test_offline_bundle_is_local_only_and_integrity_checked():
    builder = (ROOT / "scripts" / "New-OfflineBundle.ps1").read_text(
        encoding="utf-8"
    )
    installer = (ROOT / "scripts" / "Install-Offline.ps1").read_text(
        encoding="utf-8"
    )
    lowered_builder = builder.lower()

    for download_command in ("invoke-webrequest", "start-bitstransfer", "webclient"):
        assert download_command not in lowered_builder
    for parameter in (
        "$PythonInstallerPath",
        "$PostgreSqlInstallerPath",
        "$DotNetInstallerPath",
        "$WinSwPath",
    ):
        assert parameter in builder
    assert "-m pip download" in builder
    assert "--only-binary=:all:" in builder
    assert "--platform win_amd64" in builder
    assert "--python-version 311" in builder
    assert "checksums.sha256" in builder
    assert "docs\\OFFLINE_INSTALL.md" in builder
    assert "Test-BundleChecksums" in installer
    assert installer.index("Test-BundleChecksums -BundleRoot") < installer.index(
        "Start-Process"
    )
    postgres_start = re.search(
        r"Start-Process\s+-FilePath\s+\$postgresInstaller\s+-Wait\s+-PassThru",
        installer,
    )
    assert postgres_start
    assert "Include_tcltk=1" in installer
    assert "import tkinter" in installer


def test_graphical_setup_and_offline_engine_have_a_noninteractive_contract():
    launcher = (ROOT / "Setup-ServiceManagement.cmd").read_text(encoding="utf-8")
    wizard = (ROOT / "Setup-ServiceManagement.ps1").read_text(encoding="utf-8")
    installer = (ROOT / "scripts" / "Install-Offline.ps1").read_text(
        encoding="utf-8"
    )
    builder = (ROOT / "scripts" / "New-OfflineBundle.ps1").read_text(
        encoding="utf-8"
    )

    assert "ExecutionPolicy Bypass" in launcher
    assert launcher.count("WindowStyle Hidden") >= 2
    assert 'start "" powershell.exe' in launcher
    assert "Unblock-File" in launcher
    assert "-Verb RunAs" in launcher
    assert "System.Windows.Forms" in wizard
    assert "[PowerShell]::Create()" in wizard
    assert ".BeginInvoke()" in wizard
    assert "[Windows.Forms.Timer]::new()" in wizard
    assert "ConcurrentQueue[string]" in wizard
    assert "TryDequeue([ref]$line)" in wizard
    assert "$eventArgs.Cancel = $true" in wizard
    assert "& $installer @arguments 6>&1" not in wizard
    assert "New installation" in wizard
    assert "Repair existing installation" in wizard
    assert "ProgramData" in wizard
    assert "[REDACTED]" in wizard
    assert "Read-Host" not in installer
    assert "Type READY" not in installer
    assert "create-role-database" in installer
    assert "create-admin" in installer
    assert "ConvertTo-Json" in installer
    assert "Test-VendorSignatures" in installer
    assert "bundle.json" in installer
    assert "ServiceManagementSystem\\Installer" in installer
    assert "Setup-ServiceManagement.cmd" in builder
    assert "Setup-ServiceManagement.ps1" in builder
    assert "Launch-ServiceConsole.ps1" in builder
    assert 'Set-Content -LiteralPath "$archivePath.sha256"' in builder


def test_graphical_setup_keeps_secrets_in_memory_during_background_install():
    wizard = (ROOT / "Setup-ServiceManagement.ps1").read_text(encoding="utf-8")

    assert "[hashtable]::Synchronized(@{ Error = '' })" in wizard
    assert "AddArgument($arguments)" in wizard
    assert "AddArgument($script:installerSecrets)" in wizard
    assert "AddArgument($script:installerProgressQueue)" in wizard
    assert "line.Replace($secret, '[REDACTED]')" in wizard
    assert "Get-Content -LiteralPath $script:installerLogPath" not in wizard
    assert "password" not in " ".join(
        line.lower()
        for line in wizard.splitlines()
        if "set-content" in line.lower()
    )


def test_installer_refuses_unknown_folders_and_requires_explicit_initialization():
    installer = (ROOT / "scripts" / "Install-Offline.ps1").read_text(
        encoding="utf-8"
    )

    assert "is not a known installation" in installer
    assert "Repair requires an installation recorded" in installer
    assert "[switch]$InitializeNewDatabase" in installer
    assert "requires explicit new-database initialization" in installer


def test_repair_deploys_the_bundled_release_when_versions_differ():
    installer = (ROOT / "scripts" / "Install-Offline.ps1").read_text(
        encoding="utf-8"
    )

    assert "function Get-ReleasePackageVersion" in installer
    assert "$installedReleaseVersion -ceq $bundledReleaseVersion" in installer
    assert "} elseif ($repairSameRelease) {" in installer
    assert "Repair is installing bundled release $bundledReleaseVersion" in installer
    repair_branch = installer.index("} elseif ($repairSameRelease) {")
    deployment_branch = installer.index("} else {", repair_branch)
    deploy_call = installer.index(
        "& $deployRelease -ReleasePackage $releasePackages[0].FullName",
        deployment_branch,
    )
    assert repair_branch < deployment_branch < deploy_call
    assert "several minutes. Do not close Setup." in installer


def test_deployment_recreates_only_a_release_not_targeted_by_current():
    deploy = (ROOT / "scripts" / "Deploy-Release.ps1").read_text(
        encoding="utf-8"
    )

    existing_release = deploy.index("if (Test-Path -LiteralPath $releasePath)")
    current_guard = deploy.index(
        "Get-CurrentReleaseTarget -CurrentPath $currentPath", existing_release
    )
    refusal = deploy.index(
        'throw "Release $($releaseInfo.version) is already installed."',
        current_guard,
    )
    recovery = deploy.index(
        "Remove-Item -LiteralPath $releasePath -Recurse -Force", refusal
    )
    recreate = deploy.index(
        "New-Item -ItemType Directory -Path $releasePath -Force", recovery
    )

    assert existing_release < current_guard < refusal < recovery < recreate
    assert "Removing incomplete inactive release" in deploy
    assert "$currentTarget -ieq" in deploy
    assert "$currentTargetAfterFailure -ine" in deploy


def test_release_switch_uses_junction_only_deletion_and_preserves_target(tmp_path):
    deploy = (ROOT / "scripts" / "Deploy-Release.ps1").read_text(
        encoding="utf-8"
    )
    assert "[IO.Directory]::Delete($currentItem.FullName)" in deploy
    assert "Remove-Item -LiteralPath $CurrentPath" not in deploy

    target = tmp_path / "old-release"
    target.mkdir()
    marker = target / "must-survive.txt"
    marker.write_text("persistent release marker", encoding="utf-8")
    junction = tmp_path / "current"
    command = (
        f"$link=New-Item -ItemType Junction -Path '{junction}' "
        f"-Target '{target}'; [IO.Directory]::Delete($link.FullName); "
        f"if(Test-Path -LiteralPath '{junction}'){{exit 2}}; "
        f"if(-not(Test-Path -LiteralPath '{marker}')){{exit 3}}"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert marker.read_text(encoding="utf-8") == "persistent release marker"


def test_repair_deployment_runs_backup_migration_switch_and_health_check(tmp_path):
    """Exercise the repair deployment stages without changing a real service."""
    pg_dump = Path(r"C:\Program Files\PostgreSQL\16\bin\pg_dump.exe")
    if os.name != "nt" or not pg_dump.is_file():
        return

    database_name = f"sms_repair_{uuid.uuid4().hex[:12]}"
    admin_connection = psycopg2.connect(
        "postgresql://postgres:postgres@localhost:5432/postgres"
    )
    admin_connection.autocommit = True
    with admin_connection.cursor() as cursor:
        cursor.execute(f'CREATE DATABASE "{database_name}"')

    install_root = tmp_path / "install"
    shared = install_root / "shared"
    uploads = shared / "uploads"
    releases = install_root / "releases"
    old_release = releases / "0.0.0-old"
    package_output = tmp_path / "packages"
    for directory in (uploads, old_release, install_root / "backups"):
        directory.mkdir(parents=True, exist_ok=True)
    marker = old_release / "old-release-marker.txt"
    marker.write_text("old release survives", encoding="utf-8")
    (uploads / "photo-marker.txt").write_text("photo backup", encoding="utf-8")
    environment_path = shared / ".env"
    environment_path.write_text(
        "\n".join(
            (
                "ENVIRONMENT=production",
                "SECRET_KEY=repair-e2e-secret-key",
                f"DATABASE_URL=postgresql://postgres:postgres@localhost:5432/{database_name}",
                f"UPLOAD_DIR={uploads}",
                "APP_HOST=0.0.0.0",
                "APP_PORT=18995",
            )
        )
        + "\n",
        encoding="utf-8",
    )

    def ps_quote(path: Path) -> str:
        return str(path).replace("'", "''")

    junction_setup = (
        f"New-Item -ItemType Junction -Path '{ps_quote(install_root / 'current')}' "
        f"-Target '{ps_quote(old_release)}' | Out-Null; "
        f"New-Item -ItemType Junction -Path '{ps_quote(install_root / '.venv')}' "
        f"-Target '{ps_quote(ROOT / '.venv')}' | Out-Null"
    )
    try:
        setup_result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", junction_setup],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        assert setup_result.returncode == 0, setup_result.stderr

        package_result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-File",
                str(ROOT / "scripts" / "New-ReleasePackage.ps1"),
                "-Version",
                "0.0.0-repair-e2e",
                "-OutputDirectory",
                str(package_output),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=40,
            check=False,
        )
        assert package_result.returncode == 0, package_result.stderr
        package = package_output / "service-management-0.0.0-repair-e2e.zip"

        deploy_script = ROOT / "scripts" / "Deploy-Release.ps1"
        deploy_command = f"""
Add-Type -AssemblyName System.ServiceProcess
$script:FakeStatus = [System.ServiceProcess.ServiceControllerStatus]::Running
function global:Get-Service {{
    [CmdletBinding()] param([string]$Name)
    [pscustomobject]@{{ Status = $script:FakeStatus }}
}}
function global:Stop-Service {{
    [CmdletBinding()] param([string]$Name, [switch]$Force)
    $script:FakeStatus = [System.ServiceProcess.ServiceControllerStatus]::Stopped
}}
function global:Start-Service {{
    [CmdletBinding()] param([string]$Name)
    $script:FakeStatus = [System.ServiceProcess.ServiceControllerStatus]::Running
}}
function global:Invoke-WebRequest {{
    [CmdletBinding()] param([string]$Uri, [switch]$UseBasicParsing, [int]$TimeoutSec)
    [pscustomobject]@{{ StatusCode = 200 }}
}}
. '{ps_quote(deploy_script)}' `
    -ReleasePackage '{ps_quote(package)}' `
    -InstallRoot '{ps_quote(install_root)}' `
    -ServiceName 'RepairE2ESimulatedService' `
    -PgDumpExecutable '{ps_quote(pg_dump)}' `
    -HealthTimeoutSeconds 10 `
    -SkipDependencyInstall
if ($script:FakeStatus -ne [System.ServiceProcess.ServiceControllerStatus]::Running) {{ exit 9 }}
"""
        deploy_result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", deploy_command],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        assert deploy_result.returncode == 0, (
            deploy_result.stdout + "\n" + deploy_result.stderr
        )

        deployment = json.loads(
            (install_root / "deployment.json").read_text(encoding="utf-8-sig")
        )
        assert deployment["version"] == "0.0.0-repair-e2e"
        assert (install_root / "current" / "release.json").is_file()
        assert marker.read_text(encoding="utf-8") == "old release survives"
        backup = Path(deployment["backup_path"])
        assert (backup / "database.dump").stat().st_size > 0
        assert (backup / "production.env").is_file()
        assert (backup / "uploads" / "photo-marker.txt").is_file()
        assert not list(backup.glob("alembic-*.stdout"))
        assert not list(backup.glob("alembic-*.stderr"))
    finally:
        for junction in (install_root / "current", install_root / ".venv"):
            if junction.exists():
                cleanup_command = (
                    f"$item=Get-Item -LiteralPath '{ps_quote(junction)}' -Force; "
                    "[IO.Directory]::Delete($item.FullName)"
                )
                subprocess.run(
                    ["powershell.exe", "-NoProfile", "-Command", cleanup_command],
                    capture_output=True,
                    timeout=20,
                    check=False,
                )
        with admin_connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (database_name,),
            )
            cursor.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        admin_connection.close()


def test_bootstrap_progress_cannot_contaminate_the_runtime_dictionary():
    installer = (ROOT / "scripts" / "Install-Offline.ps1").read_text(
        encoding="utf-8"
    )

    assert "function Write-InstallerProgress" in installer
    assert "Write-Host ([string]$_)" in installer
    assert installer.count("2>&1 |\n        Write-InstallerProgress") == 1
    assert "2>&1 |\n            Write-InstallerProgress" in installer
    assert "return [ordered]@{ Python = $python; Cli =" in installer
    assert "source-refresh-" in installer
    assert "Expand-Archive -LiteralPath $ReleasePackage -DestinationPath $stagedSource" in installer

    command = (
        "function Write-InstallerProgress { process { Write-Host ([string]$_) } }; "
        "$value = & { @('pip output', 'pip warning') | Write-InstallerProgress; "
        "return [ordered]@{ Python='python.exe'; Cli='bootstrap_cli.py' } }; "
        "if ($value -isnot [Collections.IDictionary]) { exit 1 }; "
        "if ($value.Python -cne 'python.exe') { exit 2 }"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_safe_uninstall_preserves_data_by_default_and_requires_typed_confirmation():
    uninstaller = (ROOT / "scripts" / "Uninstall-Server.ps1").read_text(
        encoding="utf-8"
    )

    assert "[switch]$RemovePersistentData" in uninstaller
    assert "Type DELETE SERVICE MANAGEMENT DATA to continue" in uninstaller
    assert "Persistent database, uploads, backups and configuration were preserved" in uninstaller
    assert "Remove-ApplicationDatabase" in uninstaller
    assert "dropdb.exe" in uninstaller


def test_restore_verifies_before_stop_and_has_guarded_rollback():
    restore = (ROOT / "scripts" / "Restore-Backup.ps1").read_text(
        encoding="utf-8"
    )

    assert restore.index("--list $dump") < restore.index("Stop-Service")
    assert restore.index("Get-DumpRevision") < restore.index("Stop-Service")
    assert "dump and upload snapshot timestamps do not match" in restore
    assert "Backup schema $dumpRevision does not match installed schema" in restore
    assert "Type RESTORE SERVICE MANAGEMENT to continue" in restore
    assert "database-before-restore.dump" in restore
    assert "Invoke-PgRestore -Executable $pgRestore -Dump $safetyDump" in restore
    assert "[switch]$DatabaseOnly" in restore


def test_current_deployment_guides_use_the_graphical_setup_and_service_console():
    guide_names = (
        "FIRST_DEPLOYMENT_GUIDE.md",
        "OFFLINE_INSTALL.md",
        "PRODUCTION_UPDATES.md",
    )
    guides = "\n".join(
        (ROOT / "docs" / name).read_text(encoding="utf-8") for name in guide_names
    )

    assert "Setup-ServiceManagement.cmd" in guides
    assert "Service Management Console" in guides
    assert "Restore-Backup.ps1" in guides
    assert "Type `READY`" not in guides
    assert "download and run `apply_windows_settings.ps1`" not in guides


def test_deploy_release_supports_an_offline_wheelhouse():
    deploy = (ROOT / "scripts" / "Deploy-Release.ps1").read_text(encoding="utf-8")

    assert "[string]$WheelhousePath" in deploy
    assert "--no-index" in deploy
    assert '"--find-links=$resolvedWheelhouse"' in deploy
    assert "Offline wheelhouse directory not found" in deploy
    assert "New-Item -ItemType HardLink -Path (Join-Path $releasePath '.env')" not in deploy
    assert "$env:SMS_ENV_FILE = $environmentPath" in deploy


def test_deploy_release_tolerates_alembic_info_on_stderr():
    deploy = (ROOT / "scripts" / "Deploy-Release.ps1").read_text(encoding="utf-8")
    installer = (ROOT / "scripts" / "Install-Offline.ps1").read_text(
        encoding="utf-8"
    )

    assert "function Get-DatabaseSchemaVersion" in deploy
    assert "function Invoke-AlembicUpgrade" in deploy
    assert "function Invoke-AlembicUpgrade" in installer
    assert "@('-m', 'alembic', 'upgrade', 'head')" in deploy
    assert "@('-m', 'alembic', 'upgrade', 'head')" in installer
    assert "-RedirectStandardOutput $stdoutPath" in deploy
    assert "-RedirectStandardError $stderrPath" in deploy
    assert "-RedirectStandardError $stderrPath" in installer
    assert "if ($process.ExitCode -ne 0)" in deploy
    assert "if ($process.ExitCode -ne 0)" in installer
    assert "Database schema verification returned no revision" in deploy
    assert "$venvPython -m alembic current 2>&1" not in deploy
    assert "& $venvPython -m alembic upgrade head" not in deploy
    assert "& $venvPython -m alembic upgrade head" not in installer
    assert "function Read-CapturedText" in deploy
    assert "function Read-CapturedText" in installer
    assert "$content = Get-Content -LiteralPath $Path -Raw" in deploy
    assert "$content = Get-Content -LiteralPath $Path -Raw" in installer
    assert "if ($null -eq $content) { return '' }" in deploy
    assert "if ($null -eq $content) { return '' }" in installer
    assert deploy.count("Read-CapturedText -Path $stdoutPath") == 2
    assert deploy.count("Read-CapturedText -Path $stderrPath") == 2
    assert installer.count("Read-CapturedText -Path $stdoutPath") == 1
    assert installer.count("Read-CapturedText -Path $stderrPath") == 1
    assert "(Get-Content -LiteralPath $stdoutPath -Raw).Trim()" not in deploy
    assert "(Get-Content -LiteralPath $stdoutPath -Raw).Trim()" not in installer


def test_graphical_setup_records_actionable_powershell_failure_details():
    wizard = (ROOT / "Setup-ServiceManagement.ps1").read_text(encoding="utf-8")

    assert "$_.InvocationInfo.PositionMessage" in wizard
    assert "$_.ScriptStackTrace" in wizard
    assert "PowerShell stack:" in wizard
