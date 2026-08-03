"""Validation and Windows Server script generation for staged deployment settings."""
from __future__ import annotations

import ipaddress
import json
import re
from pathlib import PureWindowsPath
from typing import Any, Mapping

from sqlalchemy.engine import make_url

from .config import settings
from .models import DeploymentSettings

PROFILE_FIELDS = (
    "public_enabled",
    "tls_enabled",
    "public_ip",
    "public_port",
    "allowed_remote_ips",
    "local_interface",
    "local_ip",
    "local_port",
    "configure_static_local_ip",
    "local_prefix_length",
    "local_gateway",
    "local_dns_servers",
    "internal_port",
    "postgres_host",
    "postgres_port",
    "backup_enabled",
    "backup_interval_days",
    "backup_retention_count",
    "backup_include_uploads",
    "backup_upload_retention_count",
    "backup_directory",
    "pg_dump_executable",
)

HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)
WINDOWS_PATH_RE = re.compile(r"^[A-Za-z0-9 \\/:._-]+$")


def default_profile() -> dict[str, Any]:
    database = make_url(settings.database_url)
    return {
        "public_enabled": False,
        "tls_enabled": False,
        "public_ip": "",
        "public_port": settings.app_port,
        "allowed_remote_ips": "",
        "local_interface": "",
        "local_ip": "",
        "local_port": settings.app_port,
        "configure_static_local_ip": False,
        "local_prefix_length": 24,
        "local_gateway": "",
        "local_dns_servers": "",
        "internal_port": settings.app_port,
        "postgres_host": database.host or "127.0.0.1",
        "postgres_port": database.port or 5432,
        "backup_enabled": False,
        "backup_interval_days": 1,
        "backup_retention_count": 30,
        "backup_include_uploads": True,
        "backup_upload_retention_count": 7,
        "backup_directory": r"C:\ServiceManagement\backups\scheduled",
        "pg_dump_executable": (
            r"C:\Program Files\PostgreSQL\16\bin\pg_dump.exe"
        ),
    }


def profile_dict(profile: DeploymentSettings | Mapping[str, Any]) -> dict[str, Any]:
    return {
        field: (
            getattr(profile, field)
            if isinstance(profile, DeploymentSettings)
            else profile.get(field)
        )
        for field in PROFILE_FIELDS
    }


def public_profile(profile: DeploymentSettings | Mapping[str, Any]) -> dict[str, Any]:
    """Return the complete secret-free representation used by the audit trail."""
    return profile_dict(profile)


def _text(raw: Any) -> str:
    return str(raw or "").strip()


def _port(raw: Any, field: str, errors: dict[str, str]) -> int:
    value = _text(raw)
    if not value.isdigit() or not 1 <= int(value) <= 65535:
        errors[field] = "Enter a port from 1 to 65535."
        return 0
    return int(value)


def _bounded_int(
    raw: Any,
    field: str,
    errors: dict[str, str],
    *,
    minimum: int,
    maximum: int,
) -> int:
    value = _text(raw)
    if not value.isdigit() or not minimum <= int(value) <= maximum:
        errors[field] = f"Enter a number from {minimum} to {maximum}."
        return minimum
    return int(value)


def _ipv4(
    raw: Any,
    field: str,
    errors: dict[str, str],
    *,
    required: bool,
) -> str:
    value = _text(raw)
    if not value and not required:
        return ""
    try:
        return str(ipaddress.IPv4Address(value))
    except ipaddress.AddressValueError:
        errors[field] = "Enter a valid IPv4 address."
        return value


def _lines(raw: Any) -> list[str]:
    return [
        value.strip()
        for value in re.split(r"[\r\n,;]+", _text(raw))
        if value.strip()
    ]


def validate_profile(form: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    errors: dict[str, str] = {}
    public_enabled = _text(form.get("public_enabled")).lower() in {
        "1",
        "true",
        "on",
        "yes",
    }
    tls_enabled = _text(form.get("tls_enabled")).lower() in {
        "1",
        "true",
        "on",
        "yes",
    }
    static_local = _text(form.get("configure_static_local_ip")).lower() in {
        "1",
        "true",
        "on",
        "yes",
    }
    backup_enabled = _text(form.get("backup_enabled")).lower() in {
        "1",
        "true",
        "on",
        "yes",
    }
    backup_include_uploads = _text(form.get("backup_include_uploads")).lower() in {
        "1",
        "true",
        "on",
        "yes",
    }
    cleaned: dict[str, Any] = {
        "public_enabled": public_enabled,
        "tls_enabled": tls_enabled,
        "public_ip": _ipv4(
            form.get("public_ip"),
            "public_ip",
            errors,
            required=public_enabled,
        ),
        "public_port": _port(form.get("public_port"), "public_port", errors),
        "local_interface": _text(form.get("local_interface")),
        "local_ip": _ipv4(
            form.get("local_ip"),
            "local_ip",
            errors,
            required=True,
        ),
        "local_port": _port(form.get("local_port"), "local_port", errors),
        "configure_static_local_ip": static_local,
        "internal_port": _port(form.get("internal_port"), "internal_port", errors),
        "postgres_host": _text(form.get("postgres_host")),
        "postgres_port": _port(
            form.get("postgres_port"),
            "postgres_port",
            errors,
        ),
        "backup_enabled": backup_enabled,
        "backup_interval_days": _bounded_int(
            form.get("backup_interval_days"),
            "backup_interval_days",
            errors,
            minimum=1,
            maximum=365,
        ),
        "backup_retention_count": _bounded_int(
            form.get("backup_retention_count"),
            "backup_retention_count",
            errors,
            minimum=1,
            maximum=365,
        ),
        "backup_include_uploads": backup_include_uploads,
        "backup_upload_retention_count": _bounded_int(
            form.get("backup_upload_retention_count"),
            "backup_upload_retention_count",
            errors,
            minimum=1,
            maximum=365,
        ),
        "backup_directory": _text(form.get("backup_directory")),
        "pg_dump_executable": _text(form.get("pg_dump_executable")),
    }

    prefix = _text(form.get("local_prefix_length"))
    if not prefix.isdigit() or not 1 <= int(prefix) <= 32:
        errors["local_prefix_length"] = "Enter a prefix length from 1 to 32."
        cleaned["local_prefix_length"] = 24
    else:
        cleaned["local_prefix_length"] = int(prefix)

    cleaned["local_gateway"] = _ipv4(
        form.get("local_gateway"),
        "local_gateway",
        errors,
        required=False,
    )
    dns_servers = _lines(form.get("local_dns_servers"))
    for value in dns_servers:
        try:
            ipaddress.IPv4Address(value)
        except ipaddress.AddressValueError:
            errors["local_dns_servers"] = (
                "Enter valid IPv4 DNS addresses, separated by commas or lines."
            )
            break
    cleaned["local_dns_servers"] = "\n".join(dns_servers)

    remote_networks = _lines(form.get("allowed_remote_ips"))
    normalized_networks: list[str] = []
    for value in remote_networks:
        try:
            normalized_networks.append(
                str(ipaddress.ip_network(value, strict=False))
            )
        except ValueError:
            errors["allowed_remote_ips"] = (
                "Enter valid IP addresses or networks, separated by commas or lines."
            )
            break
    cleaned["allowed_remote_ips"] = "\n".join(normalized_networks)
    if public_enabled and not normalized_networks and "allowed_remote_ips" not in errors:
        errors["allowed_remote_ips"] = (
            "Enter the remote IP addresses or networks permitted to use "
            "the public listener."
        )

    if static_local and not cleaned["local_interface"]:
        errors["local_interface"] = "Enter the Windows LAN adapter name."
    if "\n" in cleaned["local_interface"] or "\r" in cleaned["local_interface"]:
        errors["local_interface"] = "Enter one Windows adapter name."

    postgres_host = cleaned["postgres_host"]
    try:
        ipaddress.ip_address(postgres_host)
    except ValueError:
        if not HOSTNAME_RE.fullmatch(postgres_host):
            errors["postgres_host"] = "Enter a valid PostgreSQL host or IP address."

    if tls_enabled:
        errors["tls_enabled"] = "HTTPS is not available yet. Use HTTP."

    application_ports = {
        cleaned["public_port"],
        cleaned["local_port"],
        cleaned["internal_port"],
    }
    if 0 not in application_ports and len(application_ports) > 1:
        message = "Use the same application port for local, public and internal access."
        errors["local_port"] = message
        errors["internal_port"] = message
        errors["public_port"] = message
    if cleaned["postgres_port"] in {
        cleaned["public_port"] if public_enabled else None,
        cleaned["local_port"],
    } and cleaned["postgres_host"] in {
        cleaned["public_ip"],
        cleaned["local_ip"],
    }:
        errors["postgres_port"] = "PostgreSQL cannot share a web endpoint."

    for field in ("backup_directory", "pg_dump_executable"):
        value = cleaned[field]
        if not value:
            errors[field] = "Enter an absolute Windows path."
        elif (
            "\n" in value
            or "\r" in value
            or not PureWindowsPath(value).is_absolute()
            or not WINDOWS_PATH_RE.fullmatch(value)
        ):
            errors[field] = "Enter an absolute Windows path."

    return cleaned, errors


def _ps(value: Any) -> str:
    return "'" + str(value or "").replace("'", "''") + "'"


def _ps_array(values: list[str]) -> str:
    return "@(" + ", ".join(_ps(value) for value in values) + ")"


def windows_script(
    profile: Mapping[str, Any],
    *,
    version: int,
    previous: Mapping[str, Any] | None = None,
    rollback: bool = False,
) -> str:
    """Generate a secret-free, explicit elevated Windows configuration script."""
    current = profile_dict(profile)
    public_remote = _lines(current["allowed_remote_ips"]) or ["Any"]
    dns_servers = _lines(current["local_dns_servers"])
    endpoint_scheme = "http"
    action = "Rollback" if rollback else "Apply"

    backup_setup = (
        f"""$backupRoot = Join-Path $InstallRoot 'backups\\deployment-settings'
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
$backupPath = Join-Path $backupRoot 'env-before-version-{version}.txt'
$networkStatePath = Join-Path $backupRoot 'network-before-version-{version}.json'
if (-not (Test-Path -LiteralPath $backupPath)) {{
    Copy-Item -LiteralPath $envPath -Destination $backupPath
}}"""
        if not rollback
        else f"""$backupRoot = Join-Path $InstallRoot 'backups\\deployment-settings'
$backupPath = Join-Path $backupRoot 'env-before-version-{version}.txt'
$networkStatePath = Join-Path $backupRoot 'network-before-version-{version}.json'"""
    )
    environment_update = (
        f"""Set-EnvValue $envPath 'APP_HOST' '0.0.0.0'
Set-EnvValue $envPath 'APP_PORT' ([string]$internalPort)
Set-EnvValue $envPath 'APP_RELOAD' 'false'
Set-EnvValue $envPath 'SESSION_HTTPS_ONLY' 'false'
$baseUrl = if ($publicEnabled) {{ "{endpoint_scheme}://${{publicIp}}:${{publicPort}}" }} else {{ "{endpoint_scheme}://${{localIp}}:${{localPort}}" }}
Set-EnvValue $envPath 'PUBLIC_BASE_URL' $baseUrl
Set-DatabaseEndpoint $envPath $postgresHost $postgresPort"""
        if not rollback
        else """if (-not (Test-Path -LiteralPath $backupPath)) {
    throw "The environment backup was not found at $backupPath."
}
Copy-Item -LiteralPath $backupPath -Destination $envPath -Force"""
    )
    network_finalize = (
        """@{
    AddedStaticIp = $addedStaticIp
    InterfaceAlias = $localInterface
    IPAddress = $localIp
    PreviousDnsServers = $previousDnsServers
} | ConvertTo-Json | Set-Content -LiteralPath $networkStatePath -Encoding UTF8"""
        if not rollback
        else """if (Test-Path -LiteralPath $networkStatePath) {
    $networkState = Get-Content -LiteralPath $networkStatePath -Raw | ConvertFrom-Json
    if ($networkState.PreviousDnsServers -and $networkState.InterfaceAlias) {
        Set-DnsClientServerAddress -InterfaceAlias $networkState.InterfaceAlias `
            -ServerAddresses @($networkState.PreviousDnsServers)
    }
    if ($networkState.AddedStaticIp -and $networkState.InterfaceAlias -and $networkState.IPAddress) {
        Get-NetIPAddress -InterfaceAlias $networkState.InterfaceAlias `
            -AddressFamily IPv4 -IPAddress $networkState.IPAddress `
            -ErrorAction SilentlyContinue |
            Remove-NetIPAddress -Confirm:$false
    }
}"""
    )

    return f"""#requires -Version 5.1
#requires -RunAsAdministrator
<#
{action} Service Management System Windows deployment profile version {version}.
Save this file in the installed application's current directory before running it.
The script never contains or prints the PostgreSQL password or SECRET_KEY.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$envPath = Join-Path $InstallRoot 'shared\\.env'
if (-not (Test-Path -LiteralPath $envPath)) {{
    throw "The shared .env file was not found at $envPath. Run this script from the installed application's current directory."
}}

$publicEnabled = ${str(bool(current["public_enabled"])).lower()}
$publicIp = {_ps(current["public_ip"])}
$publicPort = {int(current["public_port"] or 0)}
$localInterface = {_ps(current["local_interface"])}
$localIp = {_ps(current["local_ip"])}
$localPort = {int(current["local_port"] or 0)}
$configureStaticLocalIp = ${str(bool(current["configure_static_local_ip"])).lower()}
$localPrefixLength = {int(current["local_prefix_length"] or 24)}
$localGateway = {_ps(current["local_gateway"])}
$dnsServers = {_ps_array(dns_servers)}
$internalPort = {int(current["internal_port"] or 8993)}
$postgresHost = {_ps(current["postgres_host"])}
$postgresPort = {int(current["postgres_port"] or 5432)}
$allowedRemoteIps = {_ps_array(public_remote)}
function Set-EnvValue([string]$Path, [string]$Name, [string]$Value) {{
    $lines = [System.Collections.Generic.List[string]]::new()
    $found = $false
    foreach ($line in [System.IO.File]::ReadAllLines($Path)) {{
        if ($line -match ('^' + [regex]::Escape($Name) + '=')) {{
            $lines.Add("$Name=$Value")
            $found = $true
        }} else {{
            $lines.Add($line)
        }}
    }}
    if (-not $found) {{ $lines.Add("$Name=$Value") }}
    [System.IO.File]::WriteAllLines(
        $Path,
        $lines,
        [System.Text.UTF8Encoding]::new($false)
    )
}}

function Set-DatabaseEndpoint([string]$Path, [string]$HostName, [int]$Port) {{
    $line = [System.IO.File]::ReadAllLines($Path) |
        Where-Object {{ $_ -match '^DATABASE_URL=' }} |
        Select-Object -First 1
    if (-not $line) {{ throw 'DATABASE_URL is missing from .env.' }}
    $url = $line.Substring('DATABASE_URL='.Length)
    $pattern = '^(?<scheme>postgresql(?:\\+[^:]+)?://)(?<userinfo>.*@)?(?<host>\\[[^\\]]+\\]|[^:/]+)(?::\\d+)?(?<path>/.*)$'
    $match = [regex]::Match($url, $pattern)
    if (-not $match.Success) {{ throw 'DATABASE_URL is not a supported PostgreSQL URL.' }}
    $replacement = $match.Groups['scheme'].Value +
        $match.Groups['userinfo'].Value + $HostName + ':' + $Port +
        $match.Groups['path'].Value
    Set-EnvValue $Path 'DATABASE_URL' $replacement
}}

{backup_setup}
$addedStaticIp = $false
$previousDnsServers = @()

if ($publicEnabled) {{
    $assignedPublic = Get-NetIPAddress -AddressFamily IPv4 -IPAddress $publicIp -ErrorAction SilentlyContinue
    if (-not $assignedPublic) {{ throw "Public IP $publicIp is not assigned to this Windows Server." }}
}}

if ($configureStaticLocalIp) {{
    $adapter = Get-NetAdapter -Name $localInterface -ErrorAction Stop
    if ($adapter.Status -eq 'Disabled') {{ throw "LAN adapter $localInterface is disabled." }}
    $previousDnsServers = @(
        (Get-DnsClientServerAddress -InterfaceAlias $localInterface -AddressFamily IPv4).ServerAddresses
    )
    $existingIp = Get-NetIPAddress -InterfaceAlias $localInterface -AddressFamily IPv4 |
        Where-Object IPAddress -eq $localIp
    if (-not $existingIp) {{
        $parameters = @{{
            InterfaceAlias = $localInterface
            IPAddress = $localIp
            PrefixLength = $localPrefixLength
            AddressFamily = 'IPv4'
        }}
        if ($localGateway) {{ $parameters.DefaultGateway = $localGateway }}
        New-NetIPAddress @parameters | Out-Null
        $addedStaticIp = $true
    }}
    if ($dnsServers.Count -gt 0) {{
        Set-DnsClientServerAddress -InterfaceAlias $localInterface -ServerAddresses $dnsServers
    }}
}} elseif ($localIp) {{
    $assignedLocal = Get-NetIPAddress -AddressFamily IPv4 -IPAddress $localIp -ErrorAction SilentlyContinue
    if (-not $assignedLocal) {{ throw "LAN IP $localIp is not assigned to this Windows Server." }}
}}

Get-NetFirewallRule -DisplayName 'SMS Public HTTP' -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule
Get-NetFirewallRule -DisplayName 'SMS Local HTTP' -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule

if ($localIp) {{
    New-NetFirewallRule -DisplayName 'SMS Local HTTP' -Direction Inbound -Action Allow `
        -Protocol TCP -LocalAddress $localIp -LocalPort $localPort -RemoteAddress LocalSubnet | Out-Null
}}

if ($publicEnabled) {{
    New-NetFirewallRule -DisplayName 'SMS Public HTTP' -Direction Inbound -Action Allow `
        -Protocol TCP -LocalAddress $publicIp -LocalPort $publicPort `
        -RemoteAddress $allowedRemoteIps | Out-Null
}}

{environment_update}
{network_finalize}

Write-Host ''
Write-Host '{action} completed.' -ForegroundColor Green
Write-Host "Public endpoint: $(if ($publicEnabled) {{ "{endpoint_scheme}://${{publicIp}}:${{publicPort}}" }} else {{ 'Disabled' }})"
Write-Host "Local endpoint:  {endpoint_scheme}://${{localIp}}:${{localPort}}"
Write-Host "Restart the Service Management System process to load the updated .env."
Write-Host "PostgreSQL must already be listening on $postgresHost`:$postgresPort."
"""


def database_backup_windows_script(
    profile: DeploymentSettings | Mapping[str, Any],
) -> str:
    """Generate an elevated installer for the recurring complete backup task."""
    values = profile_dict(profile)
    enabled = "$true" if values["backup_enabled"] else "$false"
    include_uploads = 1 if values["backup_include_uploads"] else 0
    runner = r"""$ErrorActionPreference = 'Stop'
$configPath = Join-Path $PSScriptRoot 'database-backup-config.json'
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
    throw "The backup configuration file was not found at $configPath"
}
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$EnvPath = [string]$config.env_path
$BackupDirectory = [string]$config.backup_directory
$PgDumpExecutable = [string]$config.pg_dump_executable
$RetentionCount = [int]$config.retention_count
$IncludeUploads = [int]$config.include_uploads
$UploadRetentionCount = [int]$config.upload_retention_count
$IntervalDays = [int]$config.interval_days
$statusRoot = Join-Path $env:ProgramData 'ServiceManagementSystem'
$statusPath = Join-Path $statusRoot 'database-backup-status.json'
New-Item -ItemType Directory -Force -Path $statusRoot | Out-Null
function Read-DotEnvValue([string]$Name) {
    $line = Get-Content -LiteralPath $EnvPath |
        Where-Object { $_ -match ('^\s*' + [Regex]::Escape($Name) + '\s*=') } |
        Select-Object -Last 1
    if (-not $line) { return $null }
    $value = ($line -split '=', 2)[1].Trim()
    if ($value.Length -ge 2 -and (
        ($value.StartsWith('"') -and $value.EndsWith('"')) -or
        ($value.StartsWith("'") -and $value.EndsWith("'"))
    )) { return $value.Substring(1, $value.Length - 2) }
    return $value
}
function Remove-OldBackupItems(
    [string]$Filter,
    [int]$Keep,
    [bool]$Directories
) {
    $items = Get-ChildItem -LiteralPath $BackupDirectory -Filter $Filter |
        Where-Object { if ($Directories) { $_.PSIsContainer } else { -not $_.PSIsContainer } } |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -Skip $Keep
    foreach ($item in $items) {
        try {
            Remove-Item -LiteralPath $item.FullName -Force -Recurse:$Directories
        } catch {
            $script:pruneWarnings.Add($_.Exception.Message)
        }
    }
}
$previousLastSuccess = ''
if (Test-Path -LiteralPath $statusPath -PathType Leaf) {
    try {
        $previousStatus = Get-Content -LiteralPath $statusPath -Raw | ConvertFrom-Json
        if ($previousStatus.last_success_utc) {
            $previousLastSuccess = [string]$previousStatus.last_success_utc
        } elseif ($previousStatus.ok -and $previousStatus.completed_utc) {
            $previousLastSuccess = [string]$previousStatus.completed_utc
        }
    } catch {
        $previousLastSuccess = ''
    }
}
$outputPath = ''
$uploadsSnapshot = ''
$uploadsMode = if ($IncludeUploads -eq 1) { 'copy' } else { 'skipped' }
$snapshotComplete = $false
$pruneWarnings = [System.Collections.Generic.List[string]]::new()
try {
    $databaseUrl = Read-DotEnvValue 'DATABASE_URL'
    if (-not $databaseUrl) { throw 'DATABASE_URL is missing from .env.' }
    $normalized = $databaseUrl -replace '^postgresql(\+[^:]+)?://', 'postgresql://'
    $uri = [Uri]$normalized
    $credentials = $uri.UserInfo -split ':', 2
    $databaseName = [Uri]::UnescapeDataString($uri.AbsolutePath.TrimStart('/'))
    if (-not $uri.Host -or -not $credentials[0] -or -not $databaseName) {
        throw 'DATABASE_URL is incomplete.'
    }
    if (-not (Test-Path -LiteralPath $PgDumpExecutable -PathType Leaf)) {
        throw "pg_dump.exe was not found at $PgDumpExecutable"
    }
    New-Item -ItemType Directory -Force -Path $BackupDirectory | Out-Null
    $timestamp = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')
    $outputPath = Join-Path $BackupDirectory "service-management-$timestamp.dump"
    $oldPassword = $env:PGPASSWORD
    try {
        $env:PGPASSWORD = if ($credentials.Count -gt 1) {
            [Uri]::UnescapeDataString($credentials[1])
        } else { '' }
        & $PgDumpExecutable --format=custom --no-owner --no-privileges `
            "--host=$($uri.Host)" `
            "--port=$(if ($uri.Port -gt 0) { $uri.Port } else { 5432 })" `
            "--username=$([Uri]::UnescapeDataString($credentials[0]))" `
            "--file=$outputPath" $databaseName
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $outputPath)) {
            throw 'pg_dump did not create a valid backup.'
        }
    } finally {
        $env:PGPASSWORD = $oldPassword
    }

    # Dump first, then snapshot uploads: a concurrent new photo can become a harmless
    # orphan, but it cannot become a database reference missing from the snapshot.
    if ($IncludeUploads -eq 1) {
        $uploadSetting = Read-DotEnvValue 'UPLOAD_DIR'
        if (-not $uploadSetting) { throw 'UPLOAD_DIR is missing from .env.' }
        $projectRoot = Split-Path -Parent $EnvPath
        $uploadSource = if ([IO.Path]::IsPathRooted($uploadSetting)) {
            [IO.Path]::GetFullPath($uploadSetting)
        } else {
            [IO.Path]::GetFullPath((Join-Path $projectRoot $uploadSetting))
        }
        if (-not (Test-Path -LiteralPath $uploadSource -PathType Container)) {
            throw "UPLOAD_DIR was not found at $uploadSource"
        }
        $previousSnapshot = Get-ChildItem -LiteralPath $BackupDirectory -Filter 'uploads-*' |
            Where-Object { $_.PSIsContainer } |
            Sort-Object LastWriteTimeUtc -Descending |
            Select-Object -First 1
        $uploadsSnapshot = Join-Path $BackupDirectory "uploads-$timestamp"
        New-Item -ItemType Directory -Path $uploadsSnapshot | Out-Null
        $sourceFiles = @(Get-ChildItem -LiteralPath $uploadSource -File -Recurse)
        $hardlinkUsed = $false
        $hardlinkFailed = $false
        foreach ($sourceFile in $sourceFiles) {
            $relativePath = $sourceFile.FullName.Substring($uploadSource.Length).
                TrimStart([char[]]'\/')
            $destination = Join-Path $uploadsSnapshot $relativePath
            $destinationParent = Split-Path -Parent $destination
            New-Item -ItemType Directory -Force -Path $destinationParent | Out-Null
            $previousFile = if ($previousSnapshot) {
                Join-Path $previousSnapshot.FullName $relativePath
            } else { '' }
            # Relative-path identity is sufficient because upload storage keys are UUIDs
            # and stored files are immutable. Revisit this if uploads are ever rewritten.
            if ($previousFile -and (Test-Path -LiteralPath $previousFile -PathType Leaf)) {
                try {
                    New-Item -ItemType HardLink -Path $destination -Target $previousFile `
                        -ErrorAction Stop | Out-Null
                    $hardlinkUsed = $true
                } catch {
                    Copy-Item -LiteralPath $sourceFile.FullName -Destination $destination
                    $hardlinkFailed = $true
                }
            } else {
                Copy-Item -LiteralPath $sourceFile.FullName -Destination $destination
            }
        }
        $snapshotFiles = @(Get-ChildItem -LiteralPath $uploadsSnapshot -File -Recurse)
        if ($snapshotFiles.Count -ne $sourceFiles.Count) {
            throw 'The upload snapshot did not contain every current upload.'
        }
        foreach ($sourceFile in $sourceFiles) {
            $relativePath = $sourceFile.FullName.Substring($uploadSource.Length).
                TrimStart([char[]]'\/')
            if (-not (Test-Path -LiteralPath (Join-Path $uploadsSnapshot $relativePath) -PathType Leaf)) {
                throw "The upload snapshot is missing $relativePath"
            }
        }
        $uploadsMode = if ($previousSnapshot -and $hardlinkUsed -and -not $hardlinkFailed) {
            'hardlink'
        } else { 'copy' }
        $snapshotComplete = $true
    }

    # Retention runs only after the dump and optional snapshot have completed and
    # verified. Deleting an old hardlinked tree only decrements its NTFS link counts.
    if ($IncludeUploads -eq 1) {
        Remove-OldBackupItems 'uploads-*' $UploadRetentionCount $true
    }
    Remove-OldBackupItems 'service-management-*.dump' $RetentionCount $false
    $completedUtc = [DateTime]::UtcNow.ToString('o')
    $message = if ($IncludeUploads -eq 1) {
        'Database and upload snapshot completed.'
    } else {
        'Database backup completed; upload snapshots are disabled.'
    }
    if ($pruneWarnings.Count -gt 0) {
        $message += ' Backup completed, but one or more older backups could not be pruned.'
    }
    [ordered]@{
        ok = $true
        completed_utc = $completedUtc
        last_success_utc = $completedUtc
        backup_file = $outputPath
        uploads_snapshot = $uploadsSnapshot
        uploads_mode = $uploadsMode
        interval_days = $IntervalDays
        message = $message
    } | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
} catch {
    if ($uploadsSnapshot -and -not $snapshotComplete -and (
        Test-Path -LiteralPath $uploadsSnapshot -PathType Container
    )) {
        Remove-Item -LiteralPath $uploadsSnapshot -Recurse -Force -ErrorAction SilentlyContinue
    }
    [ordered]@{
        ok = $false
        completed_utc = [DateTime]::UtcNow.ToString('o')
        last_success_utc = $previousLastSuccess
        backup_file = ''
        uploads_snapshot = ''
        uploads_mode = $uploadsMode
        interval_days = $IntervalDays
        message = $_.Exception.Message
    } | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
    throw
}
"""
    return f"""# Run in elevated Windows PowerShell from the installed application's current directory.
[CmdletBinding()]
param(
    [string]$InstallRoot = (Split-Path -Parent $PSScriptRoot)
)
$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {{
    throw 'Run this script as Windows Administrator.'
}}
$enabled = {enabled}
$intervalDays = {int(values["backup_interval_days"])}
$retentionCount = {int(values["backup_retention_count"])}
$includeUploads = {include_uploads}
$uploadRetentionCount = {int(values["backup_upload_retention_count"])}
$backupDirectory = {_ps(values["backup_directory"])}
$pgDumpExecutable = {_ps(values["pg_dump_executable"])}
$envPath = Join-Path $InstallRoot 'shared\\.env'
$taskName = 'ServiceManagementSystem Database Backup'
$runnerRoot = Join-Path $env:ProgramData 'ServiceManagementSystem'
$runnerPath = Join-Path $runnerRoot 'Backup-Database.ps1'
$configPath = Join-Path $runnerRoot 'database-backup-config.json'
if (-not $enabled) {{
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false `
        -ErrorAction SilentlyContinue
    Write-Host 'Automatic database backup task disabled.'
    exit 0
}}
if (-not (Test-Path -LiteralPath $envPath)) {{
    throw "The application .env file was not found at $envPath"
}}
New-Item -ItemType Directory -Force -Path $runnerRoot | Out-Null
@'
{runner}
'@ | Set-Content -LiteralPath $runnerPath -Encoding UTF8
[ordered]@{{
    env_path = $envPath
    backup_directory = $backupDirectory
    pg_dump_executable = $pgDumpExecutable
    retention_count = $retentionCount
    include_uploads = $includeUploads
    upload_retention_count = $uploadRetentionCount
    interval_days = $intervalDays
}} | ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding UTF8
$systemSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')
$localServiceSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-19')
$administratorsSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')
$runnerAcl = [Security.AccessControl.DirectorySecurity]::new()
$runnerAcl.SetOwner($administratorsSid)
$runnerAcl.SetAccessRuleProtection($true, $false)
foreach ($sid in @($systemSid, $administratorsSid)) {{
    $runnerAcl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
        $sid,
        [Security.AccessControl.FileSystemRights]::FullControl,
        [Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit',
        [Security.AccessControl.PropagationFlags]::None,
        [Security.AccessControl.AccessControlType]::Allow
    ))
}}
$runnerAcl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
    $localServiceSid,
    [Security.AccessControl.FileSystemRights]'ReadAndExecute, Synchronize',
    [Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit',
    [Security.AccessControl.PropagationFlags]::None,
    [Security.AccessControl.AccessControlType]::Allow
))
Set-Acl -LiteralPath $runnerRoot -AclObject $runnerAcl
$configAcl = [Security.AccessControl.FileSecurity]::new()
$configAcl.SetOwner($administratorsSid)
$configAcl.SetAccessRuleProtection($true, $false)
$configAcl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
    $systemSid,
    [Security.AccessControl.FileSystemRights]::FullControl,
    [Security.AccessControl.AccessControlType]::Allow
))
$configAcl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
    $administratorsSid,
    [Security.AccessControl.FileSystemRights]::FullControl,
    [Security.AccessControl.AccessControlType]::Allow
))
Set-Acl -LiteralPath $configPath -AclObject $configAcl
$taskArguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $runnerPath + '"'
$taskCommand = 'powershell.exe ' + $taskArguments
$taskAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $taskArguments
$taskTrigger = New-ScheduledTaskTrigger -Daily -DaysInterval $intervalDays -At '02:00'
$taskPrincipal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' `
    -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName $taskName -Action $taskAction `
    -Trigger $taskTrigger -Principal $taskPrincipal -Force | Out-Null
Write-Host "Automatic backup scheduled every $intervalDays day(s) at 02:00."
Write-Host "Backup directory: $backupDirectory"
Write-Host "Upload snapshots: $(if ($includeUploads -eq 1) {{ 'Enabled' }} else {{ 'Disabled' }})"
"""


def audit_json(profile: DeploymentSettings | Mapping[str, Any]) -> str:
    return json.dumps(public_profile(profile), sort_keys=True)
