# Run in elevated Windows PowerShell from the application root.
$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script as Windows Administrator.'
}
$enabled = $true
$intervalDays = 1
$retentionCount = 30
$includeUploads = 1
$uploadRetentionCount = 7
$backupDirectory = 'C:\ServiceManagement\backups\scheduled'
$pgDumpExecutable = 'C:\Program Files\PostgreSQL\16\bin\pg_dump.exe'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$envPath = Join-Path $projectRoot '.env'
$taskName = 'ServiceManagementSystem Database Backup'
$runnerRoot = Join-Path $env:ProgramData 'ServiceManagementSystem'
$runnerPath = Join-Path $runnerRoot 'Backup-Database.ps1'
$configPath = Join-Path $runnerRoot 'database-backup-config.json'
if (-not $enabled) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false `
        -ErrorAction SilentlyContinue
    Write-Host 'Automatic database backup task disabled.'
    exit 0
}
if (-not (Test-Path -LiteralPath $envPath)) {
    throw "The application .env file was not found at $envPath"
}
New-Item -ItemType Directory -Force -Path $runnerRoot | Out-Null
@'
$ErrorActionPreference = 'Stop'
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

'@ | Set-Content -LiteralPath $runnerPath -Encoding UTF8
[ordered]@{
    env_path = $envPath
    backup_directory = $backupDirectory
    pg_dump_executable = $pgDumpExecutable
    retention_count = $retentionCount
    include_uploads = $includeUploads
    upload_retention_count = $uploadRetentionCount
    interval_days = $intervalDays
} | ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding UTF8
$systemSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')
$administratorsSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')
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
Write-Host "Upload snapshots: $(if ($includeUploads -eq 1) { 'Enabled' } else { 'Disabled' })"
