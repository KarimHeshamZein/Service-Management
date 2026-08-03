"""Production release packages preserve secrets and persistent data."""
from __future__ import annotations

import re
import subprocess
import zipfile
from pathlib import Path


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
    assert "Unblock-File" in launcher
    assert "-Verb RunAs" in launcher
    assert "System.Windows.Forms" in wizard
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

    assert "function Get-DatabaseSchemaVersion" in deploy
    assert "-RedirectStandardOutput $stdoutPath" in deploy
    assert "-RedirectStandardError $stderrPath" in deploy
    assert "if ($process.ExitCode -ne 0)" in deploy
    assert "Database schema verification returned no revision" in deploy
    assert "$venvPython -m alembic current 2>&1" not in deploy
