[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$DumpPath,
    [string]$UploadsSnapshot = '',
    [switch]$DatabaseOnly,
    [string]$InstallRoot = 'C:\ServiceManagement',
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')]
    [string]$ServiceName = 'ServiceManagementSystem',
    [string]$PgRestoreExecutable = 'pg_restore.exe',
    [ValidateRange(10, 300)]
    [int]$HealthTimeoutSeconds = 60
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

function Resolve-DatabaseParts {
    param([string]$DatabaseUrl)
    $normalized = $DatabaseUrl -replace '^postgresql(\+[^:]+)?://', 'postgresql://'
    try { $uri = [Uri]$normalized }
    catch { throw 'DATABASE_URL is invalid. Restore did not start.' }
    $credentials = $uri.UserInfo -split ':', 2
    $database = [Uri]::UnescapeDataString($uri.AbsolutePath.TrimStart('/'))
    if (-not $uri.Host -or -not $credentials[0] -or -not $database) {
        throw 'DATABASE_URL is incomplete. Restore did not start.'
    }
    return [ordered]@{
        Host = $uri.Host
        Port = if ($uri.Port -gt 0) { $uri.Port } else { 5432 }
        Username = [Uri]::UnescapeDataString($credentials[0])
        Password = if ($credentials.Count -gt 1) {
            [Uri]::UnescapeDataString($credentials[1])
        } else { '' }
        Database = $database
    }
}

function Resolve-PostgreSqlTool {
    param([string]$Requested, [string]$SiblingName)
    $command = Get-Command $Requested -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    if (Test-Path -LiteralPath $Requested -PathType Leaf) {
        return (Resolve-Path -LiteralPath $Requested).Path
    }
    $restoreCommand = Get-Command $PgRestoreExecutable -ErrorAction SilentlyContinue
    if ($restoreCommand) {
        $sibling = Join-Path (Split-Path -Parent $restoreCommand.Source) $SiblingName
        if (Test-Path -LiteralPath $sibling -PathType Leaf) { return $sibling }
    }
    throw "$SiblingName was not found. Restore did not start."
}

function Invoke-PgRestore {
    param([string]$Executable, [string]$Dump, [Collections.IDictionary]$Database)
    & $Executable --clean --if-exists --exit-on-error --no-owner --no-privileges `
        "--host=$($Database.Host)" "--port=$($Database.Port)" `
        "--username=$($Database.Username)" "--dbname=$($Database.Database)" $Dump
    if ($LASTEXITCODE -ne 0) { throw 'pg_restore could not restore the database.' }
}

function Get-DumpRevision {
    param([string]$Executable, [string]$Dump)
    $temporary = Join-Path ([IO.Path]::GetTempPath()) (
        'sms-alembic-' + [Guid]::NewGuid().ToString('N') + '.sql'
    )
    try {
        & $Executable --data-only --table=alembic_version --file=$temporary $Dump
        if ($LASTEXITCODE -ne 0) { throw 'The backup schema version could not be read.' }
        $content = Get-Content -LiteralPath $temporary -Raw
        $match = [Regex]::Match($content, '(?m)^([0-9a-f]{12})\s*$')
        if (-not $match.Success) { throw 'The backup has no readable Alembic schema version.' }
        return $match.Groups[1].Value
    } finally {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    }
}

function Get-CurrentRevision {
    param([string]$Psql, [Collections.IDictionary]$Database)
    $result = & $Psql --no-password --no-psqlrc --quiet --tuples-only --no-align `
        "--host=$($Database.Host)" "--port=$($Database.Port)" `
        "--username=$($Database.Username)" "--dbname=$($Database.Database)" `
        --command 'SELECT version_num FROM alembic_version;'
    if ($LASTEXITCODE -ne 0 -or -not $result) {
        throw 'The installed database schema version could not be read.'
    }
    return ([string]($result | Select-Object -First 1)).Trim()
}

function Test-UploadsSnapshot {
    param([string]$Path, [string]$ExpectedTimestamp)
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw 'The upload snapshot folder was not found.'
    }
    if ([IO.Path]::GetFileName($Path.TrimEnd('\')) -cne "uploads-$ExpectedTimestamp") {
        throw 'The dump and upload snapshot timestamps do not match.'
    }
    $reparsePoint = Get-ChildItem -LiteralPath $Path -Recurse -Force |
        Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint } |
        Select-Object -First 1
    if ($reparsePoint) { throw 'The upload snapshot contains an unsafe reparse point.' }
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script as Windows Administrator.'
}
if ($DatabaseOnly -and $UploadsSnapshot) {
    throw 'Choose an upload snapshot or DatabaseOnly, not both.'
}
if (-not $DatabaseOnly -and -not $UploadsSnapshot) {
    throw 'Choose the matching upload snapshot, or explicitly use DatabaseOnly.'
}

$root = [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')
$dump = if (Test-Path -LiteralPath $DumpPath -PathType Leaf) {
    (Resolve-Path -LiteralPath $DumpPath).Path
} else { throw 'The PostgreSQL dump file was not found.' }
$dumpName = [IO.Path]::GetFileName($dump)
$dumpMatch = [Regex]::Match($dumpName, '^service-management-(\d{8}-\d{6})\.dump$')
if (-not $dumpMatch.Success) {
    throw 'Choose a scheduled service-management-YYYYMMDD-HHMMSS.dump file.'
}
$timestamp = $dumpMatch.Groups[1].Value
$snapshot = if ($UploadsSnapshot) {
    (Resolve-Path -LiteralPath $UploadsSnapshot).Path
} else { '' }
if ($snapshot) { Test-UploadsSnapshot -Path $snapshot -ExpectedTimestamp $timestamp }

$environmentPath = Join-Path $root 'shared\.env'
if (-not (Test-Path -LiteralPath $environmentPath -PathType Leaf)) {
    throw 'The installed production .env file was not found. Restore did not start.'
}
$uploadPath = Read-DotEnvValue -Path $environmentPath -Name 'UPLOAD_DIR'
if (-not $uploadPath -or -not [IO.Path]::IsPathRooted($uploadPath)) {
    throw 'UPLOAD_DIR must be an absolute installed path. Restore did not start.'
}
if ($snapshot -and -not (Test-Path -LiteralPath $uploadPath -PathType Container)) {
    throw 'The current production upload directory was not found. Restore did not start.'
}
$database = Resolve-DatabaseParts (Read-DotEnvValue $environmentPath 'DATABASE_URL')
$pgRestore = Resolve-PostgreSqlTool -Requested $PgRestoreExecutable `
    -SiblingName 'pg_restore.exe'
$psql = Resolve-PostgreSqlTool -Requested 'psql.exe' -SiblingName 'psql.exe'
$pgDump = Resolve-PostgreSqlTool -Requested 'pg_dump.exe' -SiblingName 'pg_dump.exe'

# Readability and pairing checks happen before the service is stopped.
$listing = & $pgRestore --list $dump 2>&1
if ($LASTEXITCODE -ne 0 -or -not $listing) {
    throw 'The PostgreSQL dump is unreadable. Restore did not start.'
}
$dumpRevision = Get-DumpRevision -Executable $pgRestore -Dump $dump
$hadPassword = Test-Path -LiteralPath 'Env:PGPASSWORD'
$oldPassword = $env:PGPASSWORD
$env:PGPASSWORD = $database.Password
try {
    $currentRevision = Get-CurrentRevision -Psql $psql -Database $database
    if ($dumpRevision -cne $currentRevision) {
        throw (
            "Backup schema $dumpRevision does not match installed schema $currentRevision. " +
            'Deploy the matching application version and use a controlled migration; restore did not start.'
        )
    }

    Write-Host "Verified dump: $dumpName"
    Write-Host "Verified schema: $dumpRevision"
    if ($snapshot) { Write-Host "Verified upload snapshot: $snapshot" }
    Write-Host 'The service will stop and current production data will be replaced.'
    $confirmation = Read-Host 'Type RESTORE SERVICE MANAGEMENT to continue'
    if ($confirmation -cne 'RESTORE SERVICE MANAGEMENT') {
        throw 'The confirmation did not match. Restore did not start.'
    }

    $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if (-not $service) { throw "Windows service '$ServiceName' was not found." }
    Stop-Service -Name $ServiceName -Force

    $safetyRoot = Join-Path $root (
        'backups\restore-safety-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')
    )
    New-Item -ItemType Directory -Path $safetyRoot -Force | Out-Null
    $safetyDump = Join-Path $safetyRoot 'database-before-restore.dump'
    & $pgDump --format=custom --no-owner --no-privileges `
        "--host=$($database.Host)" "--port=$($database.Port)" `
        "--username=$($database.Username)" "--file=$safetyDump" $database.Database
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $safetyDump)) {
        Start-Service -Name $ServiceName
        throw 'The pre-restore safety dump failed. Production was not changed.'
    }

    $stagedUploads = ''
    $oldUploads = ''
    $uploadsSwapped = $false
    try {
        if ($snapshot) {
            $uploadParent = Split-Path -Parent $uploadPath
            $stagedUploads = Join-Path $uploadParent (
                'uploads.restore-staged-' + [Guid]::NewGuid().ToString('N')
            )
            New-Item -ItemType Directory -Path $stagedUploads | Out-Null
            Get-ChildItem -LiteralPath $snapshot -Force | Copy-Item `
                -Destination $stagedUploads -Recurse -Force
            if ((Get-ChildItem $snapshot -File -Recurse).Count -ne
                (Get-ChildItem $stagedUploads -File -Recurse).Count) {
                throw 'The staged upload snapshot is incomplete.'
            }
            if (Test-Path -LiteralPath $uploadPath -PathType Container) {
                Set-Acl -LiteralPath $stagedUploads -AclObject (Get-Acl $uploadPath)
            }
        }

        Invoke-PgRestore -Executable $pgRestore -Dump $dump -Database $database
        if ($snapshot) {
            $oldUploads = "$uploadPath.restore-old-$timestamp"
            Move-Item -LiteralPath $uploadPath -Destination $oldUploads
            Move-Item -LiteralPath $stagedUploads -Destination $uploadPath
            $uploadsSwapped = $true
        }

        Start-Service -Name $ServiceName
        $port = Read-DotEnvValue -Path $environmentPath -Name 'APP_PORT'
        if (-not $port) { $port = '8993' }
        $deadline = [DateTime]::UtcNow.AddSeconds($HealthTimeoutSeconds)
        $healthy = $false
        do {
            Start-Sleep -Seconds 2
            try {
                $response = Invoke-WebRequest "http://127.0.0.1:$port/login" `
                    -UseBasicParsing -TimeoutSec 5
                $healthy = $response.StatusCode -eq 200
            } catch { $healthy = $false }
        } while (-not $healthy -and [DateTime]::UtcNow -lt $deadline)
        if (-not $healthy) { throw 'The restored application did not pass its health check.' }
        if ($oldUploads) { Remove-Item -LiteralPath $oldUploads -Recurse -Force }
        Write-Host 'Restore completed and the application passed its health check.'
        Write-Host "Pre-restore safety dump: $safetyDump"
    } catch {
        $restoreError = $_.Exception.Message
        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
        try { Invoke-PgRestore -Executable $pgRestore -Dump $safetyDump -Database $database }
        catch { $restoreError += ' The pre-restore database could not be restored automatically.' }
        if ($uploadsSwapped) {
            Remove-Item -LiteralPath $uploadPath -Recurse -Force -ErrorAction SilentlyContinue
            Move-Item -LiteralPath $oldUploads -Destination $uploadPath -ErrorAction SilentlyContinue
        } elseif ($stagedUploads) {
            Remove-Item -LiteralPath $stagedUploads -Recurse -Force -ErrorAction SilentlyContinue
        }
        Start-Service -Name $ServiceName -ErrorAction SilentlyContinue
        throw "Restore failed and rollback was attempted. $restoreError"
    }
} finally {
    if ($hadPassword) { $env:PGPASSWORD = $oldPassword }
    else { Remove-Item -LiteralPath 'Env:PGPASSWORD' -ErrorAction SilentlyContinue }
    $database.Password = $null
}
