[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ReleasePackage,

    [string]$InstallRoot = 'C:\ServiceManagement',
    [string]$ServiceName = 'ServiceManagementSystem',
    [string]$PythonExecutable = 'python.exe',
    [string]$PgDumpExecutable = 'pg_dump.exe',
    [string]$WheelhousePath,
    [ValidateRange(10, 300)]
    [int]$HealthTimeoutSeconds = 60,
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Read-DotEnvValue {
    param([string]$Path, [string]$Name)
    $line = Get-Content -LiteralPath $Path |
        Where-Object { $_ -match "^\s*$([Regex]::Escape($Name))\s*=" } |
        Select-Object -Last 1
    if (-not $line) { return $null }
    $value = ($line -split '=', 2)[1].Trim()
    if (
        $value.Length -ge 2 -and
        (($value.StartsWith('"') -and $value.EndsWith('"')) -or
         ($value.StartsWith("'") -and $value.EndsWith("'")))
    ) {
        return $value.Substring(1, $value.Length - 2)
    }
    return $value
}

function Resolve-DatabaseParts {
    param([string]$DatabaseUrl)
    $normalized = $DatabaseUrl -replace '^postgresql(\+[^:]+)?://', 'postgresql://'
    try {
        $uri = [Uri]$normalized
    } catch {
        throw 'DATABASE_URL is not a valid PostgreSQL URL.'
    }
    if ($uri.Scheme -ne 'postgresql' -or -not $uri.Host) {
        throw 'DATABASE_URL must use PostgreSQL and include a host.'
    }
    $credentials = $uri.UserInfo -split ':', 2
    if (-not $credentials[0]) {
        throw 'DATABASE_URL must include a PostgreSQL username.'
    }
    return [ordered]@{
        Host = $uri.Host
        Port = if ($uri.Port -gt 0) { $uri.Port } else { 5432 }
        Username = [Uri]::UnescapeDataString($credentials[0])
        Password = if ($credentials.Count -gt 1) {
            [Uri]::UnescapeDataString($credentials[1])
        } else { '' }
        Database = [Uri]::UnescapeDataString($uri.AbsolutePath.TrimStart('/'))
    }
}

function Set-CurrentRelease {
    param([string]$CurrentPath, [string]$TargetPath)
    if (Test-Path -LiteralPath $CurrentPath) {
        $currentItem = Get-Item -LiteralPath $CurrentPath -Force
        if (-not ($currentItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "The current path exists but is not a junction: $CurrentPath"
        }
        Remove-Item -LiteralPath $CurrentPath -Force
    }
    New-Item -ItemType Junction -Path $CurrentPath -Target $TargetPath | Out-Null
}

function Get-DatabaseSchemaVersion {
    param(
        [string]$PythonExecutable,
        [string]$WorkingDirectory,
        [string]$CaptureDirectory
    )
    $captureId = [Guid]::NewGuid().ToString('N')
    $stdoutPath = Join-Path $CaptureDirectory "alembic-current-$captureId.stdout"
    $stderrPath = Join-Path $CaptureDirectory "alembic-current-$captureId.stderr"
    try {
        # Windows PowerShell promotes native stderr to ErrorRecord when
        # ErrorActionPreference is Stop. Alembic writes ordinary INFO logging
        # there, so capture both streams and trust the native process exit code.
        $process = Start-Process -FilePath $PythonExecutable `
            -ArgumentList @('-m', 'alembic', 'current') `
            -WorkingDirectory $WorkingDirectory -WindowStyle Hidden `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath -Wait -PassThru
        $stdout = if (Test-Path -LiteralPath $stdoutPath) {
            (Get-Content -LiteralPath $stdoutPath -Raw).Trim()
        } else { '' }
        $stderr = if (Test-Path -LiteralPath $stderrPath) {
            (Get-Content -LiteralPath $stderrPath -Raw).Trim()
        } else { '' }
        if ($process.ExitCode -ne 0) {
            $detail = if ($stderr) { " $stderr" } else { '' }
            throw "Database schema verification failed.$detail"
        }
        if (-not $stdout) {
            throw 'Database schema verification returned no revision.'
        }
        return $stdout
    } finally {
        Remove-Item -LiteralPath $stdoutPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $stderrPath -Force -ErrorAction SilentlyContinue
    }
}

$packagePath = (Resolve-Path -LiteralPath $ReleasePackage).Path
$root = [IO.Path]::GetFullPath($InstallRoot)
if ($root -in @([IO.Path]::GetPathRoot($root), $env:SystemRoot)) {
    throw 'InstallRoot must be a dedicated application directory.'
}
$sharedRoot = Join-Path $root 'shared'
$environmentPath = Join-Path $sharedRoot '.env'
$uploadsPath = Join-Path $sharedRoot 'uploads'
$releasesRoot = Join-Path $root 'releases'
$backupsRoot = Join-Path $root 'backups'
$currentPath = Join-Path $root 'current'
$venvPython = Join-Path $root '.venv\Scripts\python.exe'
$resolvedWheelhouse = $null
if ($WheelhousePath) {
    if (-not (Test-Path -LiteralPath $WheelhousePath -PathType Container)) {
        throw "Offline wheelhouse directory not found: $WheelhousePath"
    }
    $resolvedWheelhouse = (Resolve-Path -LiteralPath $WheelhousePath).Path
    if (-not (Get-ChildItem -LiteralPath $resolvedWheelhouse -Filter '*.whl' -File)) {
        throw "Offline wheelhouse contains no Python wheels: $resolvedWheelhouse"
    }
}

if (-not (Test-Path -LiteralPath $environmentPath)) {
    throw "Persistent environment file not found: $environmentPath"
}
$databaseUrl = Read-DotEnvValue -Path $environmentPath -Name 'DATABASE_URL'
if (-not $databaseUrl) {
    throw 'DATABASE_URL is missing from the persistent .env file.'
}
$configuredUploadDir = Read-DotEnvValue -Path $environmentPath -Name 'UPLOAD_DIR'
if (-not $configuredUploadDir -or -not [IO.Path]::IsPathRooted($configuredUploadDir)) {
    throw 'UPLOAD_DIR in the production .env must be an absolute persistent path.'
}
if (
    [IO.Path]::GetFullPath($configuredUploadDir).TrimEnd('\') -ne
    [IO.Path]::GetFullPath($uploadsPath).TrimEnd('\')
) {
    throw "UPLOAD_DIR must point to the shared upload directory: $uploadsPath"
}

$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $service) {
    throw "Windows service '$ServiceName' was not found."
}

$manifestEntry = 'release.json'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::OpenRead($packagePath)
try {
    $manifest = $archive.Entries |
        Where-Object { $_.FullName -eq $manifestEntry } |
        Select-Object -First 1
    if (-not $manifest) { throw 'The package does not contain release.json.' }
    $reader = New-Object IO.StreamReader($manifest.Open())
    try { $releaseInfo = ($reader.ReadToEnd() | ConvertFrom-Json) }
    finally { $reader.Dispose() }
} finally {
    $archive.Dispose()
}
if ($releaseInfo.version -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$') {
    throw 'The release manifest contains an invalid version.'
}

$releasePath = Join-Path $releasesRoot $releaseInfo.version
if (Test-Path -LiteralPath $releasePath) {
    throw "Release $($releaseInfo.version) is already installed."
}
New-Item -ItemType Directory -Path $releasePath -Force | Out-Null
New-Item -ItemType Directory -Path $uploadsPath -Force | Out-Null
New-Item -ItemType Directory -Path $backupsRoot -Force | Out-Null

$serviceWasRunning = $service.Status -eq [ServiceProcess.ServiceControllerStatus]::Running
$serviceStoppedByDeployment = $false
try {
    Expand-Archive -LiteralPath $packagePath -DestinationPath $releasePath
    foreach ($required in @('app', 'alembic', 'alembic.ini', 'bootstrap_cli.py', 'requirements.txt', 'serve.py')) {
        if (-not (Test-Path -LiteralPath (Join-Path $releasePath $required))) {
            throw "The release is incomplete; missing $required."
        }
    }
    if (-not (Test-Path -LiteralPath $venvPython)) {
        & $PythonExecutable -m venv (Join-Path $root '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the production virtual environment.' }
    }

    Stop-Service -Name $ServiceName -Force
    $serviceStoppedByDeployment = $true

    $timestamp = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')
    $backupPath = Join-Path $backupsRoot "$timestamp-before-$($releaseInfo.version)"
    New-Item -ItemType Directory -Path $backupPath | Out-Null
    Copy-Item -LiteralPath $environmentPath -Destination (Join-Path $backupPath 'production.env')
    if (Test-Path -LiteralPath $uploadsPath) {
        Copy-Item -LiteralPath $uploadsPath -Destination (
            Join-Path $backupPath 'uploads'
        ) -Recurse
    }

    $database = Resolve-DatabaseParts $databaseUrl
    if (-not $database.Database) { throw 'DATABASE_URL must include a database name.' }
    $pgDump = Get-Command $PgDumpExecutable -ErrorAction SilentlyContinue
    if (-not $pgDump) { throw "pg_dump was not found: $PgDumpExecutable" }
    $dumpPath = Join-Path $backupPath 'database.dump'
    $oldPassword = $env:PGPASSWORD
    try {
        $env:PGPASSWORD = $database.Password
        & $pgDump.Source --format=custom --no-owner --no-privileges `
            "--host=$($database.Host)" "--port=$($database.Port)" `
            "--username=$($database.Username)" "--file=$dumpPath" $database.Database
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $dumpPath)) {
            throw 'PostgreSQL backup failed. The release was not deployed.'
        }
    } finally {
        $env:PGPASSWORD = $oldPassword
    }

    if (-not $SkipDependencyInstall) {
        if ($resolvedWheelhouse) {
            & $venvPython -m pip install --disable-pip-version-check `
                --no-index "--find-links=$resolvedWheelhouse" `
                -r (Join-Path $releasePath 'requirements.txt')
        } else {
            & $venvPython -m pip install --disable-pip-version-check `
                -r (Join-Path $releasePath 'requirements.txt')
        }
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    }

    $hadSmsEnvFile = Test-Path -LiteralPath 'Env:SMS_ENV_FILE'
    $oldSmsEnvFile = $env:SMS_ENV_FILE
    $hadEnvironment = Test-Path -LiteralPath 'Env:ENVIRONMENT'
    $oldEnvironment = $env:ENVIRONMENT
    try {
        $env:SMS_ENV_FILE = $environmentPath
        $env:ENVIRONMENT = 'production'
        Push-Location $releasePath
        try {
            & $venvPython -m alembic upgrade head
            if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
        } finally {
            Pop-Location
        }
        $schemaVersion = Get-DatabaseSchemaVersion `
            -PythonExecutable $venvPython -WorkingDirectory $releasePath `
            -CaptureDirectory $backupPath
    } finally {
        if ($hadSmsEnvFile) { $env:SMS_ENV_FILE = $oldSmsEnvFile }
        else { Remove-Item -LiteralPath 'Env:SMS_ENV_FILE' -ErrorAction SilentlyContinue }
        if ($hadEnvironment) { $env:ENVIRONMENT = $oldEnvironment }
        else { Remove-Item -LiteralPath 'Env:ENVIRONMENT' -ErrorAction SilentlyContinue }
    }

    $previousTarget = $null
    if (Test-Path -LiteralPath $currentPath) {
        $currentItem = Get-Item -LiteralPath $currentPath -Force
        if (-not ($currentItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "The current path exists but is not a junction: $currentPath"
        }
        $previousTarget = $currentItem.Target
        if ($previousTarget -is [array]) { $previousTarget = $previousTarget[0] }
    }
    Set-CurrentRelease -CurrentPath $currentPath -TargetPath $releasePath

    try {
        Start-Service -Name $ServiceName
        $appPort = Read-DotEnvValue -Path $environmentPath -Name 'APP_PORT'
        if (-not $appPort) { $appPort = '8993' }
        $healthUrl = "http://127.0.0.1:$appPort/login"
        $deadline = [DateTime]::UtcNow.AddSeconds($HealthTimeoutSeconds)
        $healthy = $false
        do {
            Start-Sleep -Seconds 2
            try {
                $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 5
                $healthy = $response.StatusCode -eq 200
            } catch {
                $healthy = $false
            }
        } while (-not $healthy -and [DateTime]::UtcNow -lt $deadline)
        if (-not $healthy) { throw "Health check failed: $healthUrl" }
    } catch {
        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
        if ($previousTarget) {
            Set-CurrentRelease -CurrentPath $currentPath -TargetPath $previousTarget
            Start-Service -Name $ServiceName
        }
        throw (
            "Release startup failed and the previous application release was restored. " +
            "The database remains at the newer schema version. $($_.Exception.Message)"
        )
    }

    [ordered]@{
        version = $releaseInfo.version
        deployed_utc = [DateTime]::UtcNow.ToString('o')
        previous_release = $previousTarget
        release_path = $releasePath
        backup_path = $backupPath
        database_schema = $schemaVersion
    } | ConvertTo-Json | Set-Content -LiteralPath (
        Join-Path $root 'deployment.json'
    ) -Encoding UTF8

    Write-Host "Release $($releaseInfo.version) deployed successfully."
    Write-Host "Backup: $backupPath"
} catch {
    if (
        $serviceStoppedByDeployment -and
        $serviceWasRunning -and
        (Get-Service -Name $ServiceName).Status -eq
            [ServiceProcess.ServiceControllerStatus]::Stopped
    ) {
        Start-Service -Name $ServiceName -ErrorAction SilentlyContinue
    }
    if (
        (Test-Path -LiteralPath $releasePath) -and
        -not (Test-Path -LiteralPath $currentPath)
    ) {
        Remove-Item -LiteralPath $releasePath -Recurse -Force
    }
    throw
}
