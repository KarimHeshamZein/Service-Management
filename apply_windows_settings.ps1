#requires -Version 5.1
#requires -RunAsAdministrator
<#
Apply Service Management System Windows deployment profile version 1.
Save this file in the project root before running it.
The script never contains or prints the PostgreSQL password or SECRET_KEY.
#>
[CmdletBinding()]
param(
    [string]$ProjectRoot = (Split-Path -Parent $MyInvocation.MyCommand.Path)
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$envPath = Join-Path $ProjectRoot '.env'
if (-not (Test-Path -LiteralPath $envPath)) {
    throw "The .env file was not found in $ProjectRoot. Save this script in the project root."
}

$publicEnabled = $false
$publicIp = ''
$publicPort = 8993
$localInterface = ''
$localIp = '172.16.17.175'
$localPort = 8993
$configureStaticLocalIp = $false
$localPrefixLength = 24
$localGateway = '172.16.16.1'
$dnsServers = @()
$internalPort = 8993
$postgresHost = 'localhost'
$postgresPort = 5432
$allowedRemoteIps = @('Any')
$previousPublicIp = ''
$previousPublicPort = 8993
$previousLocalIp = ''
$previousLocalPort = 8993

function Set-EnvValue([string]$Path, [string]$Name, [string]$Value) {
    $lines = [System.Collections.Generic.List[string]]::new()
    $found = $false
    foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
        if ($line -match ('^' + [regex]::Escape($Name) + '=')) {
            $lines.Add("$Name=$Value")
            $found = $true
        } else {
            $lines.Add($line)
        }
    }
    if (-not $found) { $lines.Add("$Name=$Value") }
    [System.IO.File]::WriteAllLines(
        $Path,
        $lines,
        [System.Text.UTF8Encoding]::new($false)
    )
}

function Set-DatabaseEndpoint([string]$Path, [string]$HostName, [int]$Port) {
    $line = [System.IO.File]::ReadAllLines($Path) |
        Where-Object { $_ -match '^DATABASE_URL=' } |
        Select-Object -First 1
    if (-not $line) { throw 'DATABASE_URL is missing from .env.' }
    $url = $line.Substring('DATABASE_URL='.Length)
    $pattern = '^(?<scheme>postgresql(?:\+[^:]+)?://)(?<userinfo>.*@)?(?<host>\[[^\]]+\]|[^:/]+)(?::\d+)?(?<path>/.*)$'
    $match = [regex]::Match($url, $pattern)
    if (-not $match.Success) { throw 'DATABASE_URL is not a supported PostgreSQL URL.' }
    $replacement = $match.Groups['scheme'].Value +
        $match.Groups['userinfo'].Value + $HostName + ':' + $Port +
        $match.Groups['path'].Value
    Set-EnvValue $Path 'DATABASE_URL' $replacement
}

$backupRoot = Join-Path $ProjectRoot 'data\deployment-backups'
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
$backupPath = Join-Path $backupRoot 'env-before-version-1.txt'
$networkStatePath = Join-Path $backupRoot 'network-before-version-1.json'
if (-not (Test-Path -LiteralPath $backupPath)) {
    Copy-Item -LiteralPath $envPath -Destination $backupPath
}
$addedStaticIp = $false
$previousDnsServers = @()

$ipHelper = Get-Service -Name 'iphlpsvc' -ErrorAction Stop
if ($ipHelper.StartType -ne 'Automatic') {
    Set-Service -Name 'iphlpsvc' -StartupType Automatic
}
if ($ipHelper.Status -ne 'Running') {
    Start-Service -Name 'iphlpsvc'
}

if ($publicEnabled) {
    $assignedPublic = Get-NetIPAddress -AddressFamily IPv4 -IPAddress $publicIp -ErrorAction SilentlyContinue
    if (-not $assignedPublic) { throw "Public IP $publicIp is not assigned to this Windows Server." }
}

if ($configureStaticLocalIp) {
    $adapter = Get-NetAdapter -Name $localInterface -ErrorAction Stop
    if ($adapter.Status -eq 'Disabled') { throw "LAN adapter $localInterface is disabled." }
    $previousDnsServers = @(
        (Get-DnsClientServerAddress -InterfaceAlias $localInterface -AddressFamily IPv4).ServerAddresses
    )
    $existingIp = Get-NetIPAddress -InterfaceAlias $localInterface -AddressFamily IPv4 |
        Where-Object IPAddress -eq $localIp
    if (-not $existingIp) {
        $parameters = @{
            InterfaceAlias = $localInterface
            IPAddress = $localIp
            PrefixLength = $localPrefixLength
            AddressFamily = 'IPv4'
        }
        if ($localGateway) { $parameters.DefaultGateway = $localGateway }
        New-NetIPAddress @parameters | Out-Null
        $addedStaticIp = $true
    }
    if ($dnsServers.Count -gt 0) {
        Set-DnsClientServerAddress -InterfaceAlias $localInterface -ServerAddresses $dnsServers
    }
} elseif ($localIp) {
    $assignedLocal = Get-NetIPAddress -AddressFamily IPv4 -IPAddress $localIp -ErrorAction SilentlyContinue
    if (-not $assignedLocal) { throw "LAN IP $localIp is not assigned to this Windows Server." }
}

if ($previousPublicIp -and $previousPublicPort -gt 0) {
    netsh interface portproxy delete v4tov4 listenaddress=$previousPublicIp listenport=$previousPublicPort protocol=tcp | Out-Null
}
if ($previousLocalIp -and $previousLocalPort -gt 0) {
    netsh interface portproxy delete v4tov4 listenaddress=$previousLocalIp listenport=$previousLocalPort protocol=tcp | Out-Null
}

Get-NetFirewallRule -DisplayName 'SMS Public HTTP' -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule
Get-NetFirewallRule -DisplayName 'SMS Local HTTP' -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule

if ($localIp) {
    netsh interface portproxy add v4tov4 listenaddress=$localIp listenport=$localPort connectaddress=127.0.0.1 connectport=$internalPort protocol=tcp | Out-Null
    New-NetFirewallRule -DisplayName 'SMS Local HTTP' -Direction Inbound -Action Allow `
        -Protocol TCP -LocalAddress $localIp -LocalPort $localPort -RemoteAddress LocalSubnet | Out-Null
}

if ($publicEnabled) {
    netsh interface portproxy add v4tov4 listenaddress=$publicIp listenport=$publicPort connectaddress=127.0.0.1 connectport=$internalPort protocol=tcp | Out-Null
    New-NetFirewallRule -DisplayName 'SMS Public HTTP' -Direction Inbound -Action Allow `
        -Protocol TCP -LocalAddress $publicIp -LocalPort $publicPort `
        -RemoteAddress $allowedRemoteIps | Out-Null
}

Set-EnvValue $envPath 'APP_HOST' '127.0.0.1'
Set-EnvValue $envPath 'APP_PORT' ([string]$internalPort)
Set-EnvValue $envPath 'APP_RELOAD' 'false'
Set-EnvValue $envPath 'SESSION_HTTPS_ONLY' 'false'
$baseUrl = if ($publicEnabled) { "http://${publicIp}:${publicPort}" } else { "http://${localIp}:${localPort}" }
Set-EnvValue $envPath 'PUBLIC_BASE_URL' $baseUrl
Set-DatabaseEndpoint $envPath $postgresHost $postgresPort
@{
    AddedStaticIp = $addedStaticIp
    InterfaceAlias = $localInterface
    IPAddress = $localIp
    PreviousDnsServers = $previousDnsServers
} | ConvertTo-Json | Set-Content -LiteralPath $networkStatePath -Encoding UTF8

Write-Host ''
Write-Host 'Apply completed.' -ForegroundColor Green
Write-Host "Public endpoint: $(if ($publicEnabled) { "http://${publicIp}:${publicPort}" } else { 'Disabled' })"
Write-Host "Local endpoint:  http://${localIp}:${localPort}"
Write-Host "Restart the Service Management System process to load the updated .env."
Write-Host "PostgreSQL must already be listening on $postgresHost`:$postgresPort."
