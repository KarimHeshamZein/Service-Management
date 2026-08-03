[CmdletBinding()]
param(
    [string]$InstallRoot = 'C:\ServiceManagement',
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')]
    [string]$ServiceName = 'ServiceManagementSystem',
    [switch]$RemovePersistentData
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Read-DotEnvValue {
    param([string]$Path, [string]$Name)
    $line = Get-Content -LiteralPath $Path |
        Where-Object { $_ -match "^\s*$([Regex]::Escape($Name))\s*=" } |
        Select-Object -Last 1
    if (-not $line) { return $null }
    return (($line -split '=', 2)[1]).Trim().Trim('"').Trim("'")
}

function Remove-ApplicationDatabase {
    param([string]$EnvironmentPath)
    $databaseUrl = Read-DotEnvValue -Path $EnvironmentPath -Name 'DATABASE_URL'
    if (-not $databaseUrl) { throw 'DATABASE_URL is missing; persistent data was not removed.' }
    $normalized = $databaseUrl -replace '^postgresql(\+[^:]+)?://', 'postgresql://'
    try { $uri = [Uri]$normalized }
    catch { throw 'DATABASE_URL is invalid; persistent data was not removed.' }
    $credentials = $uri.UserInfo -split ':', 2
    $database = [Uri]::UnescapeDataString($uri.AbsolutePath.TrimStart('/'))
    $username = [Uri]::UnescapeDataString($credentials[0])
    $password = if ($credentials.Count -gt 1) {
        [Uri]::UnescapeDataString($credentials[1])
    } else { '' }
    $dropDatabase = Get-Command 'dropdb.exe' -ErrorAction SilentlyContinue
    if (-not $dropDatabase) {
        $dropDatabase = Get-ChildItem (Join-Path $env:ProgramFiles 'PostgreSQL') `
            -Filter 'dropdb.exe' -File -Recurse -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending | Select-Object -First 1
    }
    if (-not $dropDatabase) { throw 'dropdb.exe was not found; persistent data was not removed.' }
    $sourceProperty = $dropDatabase.PSObject.Properties['Source']
    $dropExecutable = if ($sourceProperty -and $sourceProperty.Value) {
        [string]$sourceProperty.Value
    } else { [string]$dropDatabase.FullName }
    $hadPassword = Test-Path -LiteralPath 'Env:PGPASSWORD'
    $oldPassword = $env:PGPASSWORD
    try {
        $env:PGPASSWORD = $password
        & $dropExecutable --no-password --force "--host=$($uri.Host)" `
            "--port=$(if ($uri.Port -gt 0) { $uri.Port } else { 5432 })" `
            "--username=$username" $database
        if ($LASTEXITCODE -ne 0) {
            throw 'The PostgreSQL database could not be removed; filesystem data was preserved.'
        }
    } finally {
        if ($hadPassword) { $env:PGPASSWORD = $oldPassword }
        else { Remove-Item -LiteralPath 'Env:PGPASSWORD' -ErrorAction SilentlyContinue }
        $password = $null
    }
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script as Windows Administrator.'
}

$root = [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')
$driveRoot = [IO.Path]::GetPathRoot($root).TrimEnd('\')
if ($root -ieq $driveRoot -or $root -ieq [IO.Path]::GetFullPath($env:SystemRoot).TrimEnd('\')) {
    throw 'InstallRoot must identify the dedicated application directory.'
}
$programDataRoot = Join-Path $env:ProgramData 'ServiceManagementSystem'
$statePath = Join-Path $programDataRoot 'Installer\state.json'
if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
    throw 'This folder is not recorded as an installation. No files were removed.'
}
try { $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json }
catch { throw 'Installer state is unreadable. No files were removed.' }
if ([string]$state.install_root.TrimEnd('\') -ine $root) {
    throw 'Installer state points to a different folder. No files were removed.'
}
$currentPath = Join-Path $root 'current'
if (Test-Path -LiteralPath $currentPath) {
    $currentItem = Get-Item -LiteralPath $currentPath -Force
    if (-not ($currentItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'The current application path is not a junction. No files were removed.'
    }
}

if ($RemovePersistentData) {
    Write-Host 'This permanently deletes the database, uploads, backups and configuration.'
    $confirmation = Read-Host 'Type DELETE SERVICE MANAGEMENT DATA to continue'
    if ($confirmation -cne 'DELETE SERVICE MANAGEMENT DATA') {
        throw 'The confirmation did not match. Persistent data was not removed.'
    }
}

$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($service) {
    if ($service.Status -ne [ServiceProcess.ServiceControllerStatus]::Stopped) {
        Stop-Service -Name $ServiceName -Force
    }
    $serviceExecutable = Join-Path $root "$ServiceName.exe"
    if (Test-Path -LiteralPath $serviceExecutable -PathType Leaf) {
        & $serviceExecutable uninstall
        if ($LASTEXITCODE -ne 0) { throw 'The Windows service could not be removed.' }
    } else {
        sc.exe delete $ServiceName | Out-Null
    }
}

foreach ($shortcut in @(
    (Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) 'Service Management Console.lnk'),
    (Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\Afaqy\Service Management Console.lnk'),
    (Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\Afaqy\Uninstall Service Management.lnk')
)) {
    Remove-Item -LiteralPath $shortcut -Force -ErrorAction SilentlyContinue
}
Remove-Item -LiteralPath (Join-Path $programDataRoot 'Launch-ServiceConsole.ps1') `
    -Force -ErrorAction SilentlyContinue

if ($RemovePersistentData) {
    $environmentPath = Join-Path $root 'shared\.env'
    if (Test-Path -LiteralPath $environmentPath -PathType Leaf) {
        Remove-ApplicationDatabase -EnvironmentPath $environmentPath
    }
    Remove-Item -LiteralPath $root -Recurse -Force
    Remove-Item -LiteralPath $programDataRoot -Recurse -Force
    Write-Host 'The application and all persistent data were removed.'
    Write-Host 'The PostgreSQL server software itself was left installed.'
    exit 0
}

if (Test-Path -LiteralPath $currentPath) {
    [IO.Directory]::Delete($currentPath)
}
foreach ($path in @(
    (Join-Path $root 'releases'),
    (Join-Path $root '.venv'),
    (Join-Path $root "$ServiceName.exe"),
    (Join-Path $root "$ServiceName.xml"),
    (Join-Path $root 'Uninstall-ServiceManagement.ps1')
)) {
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Recurse -Force }
}
Write-Host 'The application was uninstalled.'
Write-Host "Persistent database, uploads, backups and configuration were preserved under $root."
