[CmdletBinding()]
param(
    [string]$InstallRoot = 'C:\ServiceManagement',
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')]
    [string]$ServiceName = 'ServiceManagementSystem',
    [ValidateRange(1, 65535)]
    [int]$Port = 8993,
    [ValidateSet('New', 'Repair')]
    [string]$Mode = 'New',
    [string]$DatabaseAdminHost = '127.0.0.1',
    [ValidateRange(1, 65535)]
    [int]$DatabaseAdminPort = 5432,
    [string]$DatabaseAdminName = 'postgres',
    [string]$DatabaseAdminUsername = 'postgres',
    [Security.SecureString]$DatabaseAdminPassword,
    [string]$DatabaseName = 'service_management',
    [string]$DatabaseUsername = 'service_management',
    [Security.SecureString]$DatabasePassword,
    [string]$AdministratorFullName = '',
    [string]$AdministratorUsername = '',
    [Security.SecureString]$AdministratorPassword,
    [switch]$InitializeNewDatabase
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Test-BundleChecksums {
    param([string]$BundleRoot)
    $manifestPath = Join-Path $BundleRoot 'checksums.sha256'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw "Offline bundle checksum manifest not found: $manifestPath"
    }
    $rootPrefix = $BundleRoot.TrimEnd('\') + '\'
    $listedPaths = New-Object 'Collections.Generic.HashSet[string]' `
        ([StringComparer]::OrdinalIgnoreCase)
    foreach ($line in Get-Content -LiteralPath $manifestPath) {
        if ($line -notmatch '^([0-9a-fA-F]{64})  (.+)$') {
            throw "The checksum manifest contains a malformed line: $line"
        }
        $expectedHash = $Matches[1]
        $relativePath = $Matches[2].Replace('/', '\')
        $targetPath = [IO.Path]::GetFullPath((Join-Path $BundleRoot $relativePath))
        if (-not $targetPath.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "The checksum manifest contains an unsafe path: $relativePath"
        }
        if (-not (Test-Path -LiteralPath $targetPath -PathType Leaf)) {
            throw "Offline bundle file is missing: $relativePath"
        }
        $actualHash = (Get-FileHash -LiteralPath $targetPath -Algorithm SHA256).Hash
        if ($actualHash -ine $expectedHash) {
            throw "Offline bundle checksum failed: $relativePath"
        }
        [void]$listedPaths.Add($relativePath)
    }
    $unlisted = Get-ChildItem -LiteralPath $BundleRoot -File -Recurse |
        Where-Object { $_.FullName -ne $manifestPath } |
        Where-Object {
            $relativePath = $_.FullName.Substring($BundleRoot.Length + 1)
            -not $listedPaths.Contains($relativePath)
        } |
        Select-Object -First 1
    if ($unlisted) {
        $relativePath = $unlisted.FullName.Substring($BundleRoot.Length + 1)
        throw "Offline bundle contains an unverified file: $relativePath"
    }
    Write-Host 'Offline bundle checksums verified.'
}

function Get-DotNetFrameworkRelease {
    $path = 'HKLM:\SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full'
    try {
        return [int](Get-ItemPropertyValue -LiteralPath $path -Name Release)
    } catch {
        return 0
    }
}

function Get-Python311Executable {
    $candidates = New-Object Collections.Generic.List[string]
    $launcher = Get-Command 'py.exe' -ErrorAction SilentlyContinue
    if ($launcher) {
        try {
            $launcherOutput = & $launcher.Source -3.11 -c 'import sys; print(sys.executable)' `
                2>$null
            $launcherExitCode = $LASTEXITCODE
            $launcherPython = $launcherOutput | Select-Object -First 1
            if ($launcherExitCode -eq 0 -and $launcherPython) {
                $candidates.Add($launcherPython.Trim())
            }
        } catch {}
    }
    foreach ($registryRoot in @(
        'HKLM:\SOFTWARE\Python\PythonCore',
        'HKLM:\SOFTWARE\WOW6432Node\Python\PythonCore'
    )) {
        if (Test-Path -LiteralPath $registryRoot) {
            Get-ChildItem -LiteralPath $registryRoot -ErrorAction SilentlyContinue |
                Where-Object { $_.PSChildName -like '3.11*' } |
                ForEach-Object {
                    $installPath = Join-Path $_.PSPath 'InstallPath'
                    try {
                        $root = (Get-Item -LiteralPath $installPath).GetValue('')
                        if ($root) { $candidates.Add((Join-Path $root 'python.exe')) }
                    } catch {}
                }
        }
    }
    $candidates.Add((Join-Path $env:ProgramFiles 'Python311\python.exe'))
    foreach ($candidate in $candidates) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        try {
            $factsOutput = & $candidate -c `
                'import sys; print(sys.version_info[0], sys.version_info[1], sys.maxsize)' `
                2>$null
            $factsExitCode = $LASTEXITCODE
            $factsText = $factsOutput | Select-Object -First 1
            if ($factsExitCode -ne 0 -or -not $factsText) { continue }
            $facts = $factsText.Trim() -split '\s+'
            if (
                $facts.Count -eq 3 -and
                [int]$facts[0] -eq 3 -and [int]$facts[1] -eq 11 -and
                [Int64]$facts[2] -gt [Int32]::MaxValue
            ) {
                return (Resolve-Path -LiteralPath $candidate).Path
            }
        } catch {}
    }
    return $null
}

function Get-PostgreSqlTools {
    $psql = Get-Command 'psql.exe' -ErrorAction SilentlyContinue
    $pgDump = Get-Command 'pg_dump.exe' -ErrorAction SilentlyContinue
    if ($psql -and $pgDump) {
        return [ordered]@{ Psql = $psql.Source; PgDump = $pgDump.Source }
    }
    $postgresRoot = Join-Path $env:ProgramFiles 'PostgreSQL'
    if (Test-Path -LiteralPath $postgresRoot -PathType Container) {
        $versions = Get-ChildItem -LiteralPath $postgresRoot -Directory |
            Sort-Object {
                try { [Version]$_.Name } catch { [Version]'0.0' }
            } -Descending
        foreach ($version in $versions) {
            $candidatePsql = Join-Path $version.FullName 'bin\psql.exe'
            $candidatePgDump = Join-Path $version.FullName 'bin\pg_dump.exe'
            if (
                (Test-Path -LiteralPath $candidatePsql -PathType Leaf) -and
                (Test-Path -LiteralPath $candidatePgDump -PathType Leaf)
            ) {
                return [ordered]@{ Psql = $candidatePsql; PgDump = $candidatePgDump }
            }
        }
    }
    return $null
}

function ConvertFrom-SecureValue {
    param([Security.SecureString]$SecureValue)
    if (-not $SecureValue) { return '' }
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

function Write-InstallerProgress {
    process {
        # Write native setup output to the host stream so it remains visible but
        # cannot become part of a function's returned data value.
        Write-Host ([string]$_)
    }
}

function Test-VendorSignatures {
    param([string]$BundleRoot)
    $metadataPath = Join-Path $BundleRoot 'bundle.json'
    try { $metadata = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json }
    catch { throw 'Offline bundle metadata is missing or unreadable.' }
    foreach ($vendor in @($metadata.vendor_inputs)) {
        $path = Join-Path $BundleRoot ([string]$vendor.bundled_path).Replace('/', '\')
        $signature = Get-AuthenticodeSignature -LiteralPath $path
        if ([string]$signature.Status -cne [string]$vendor.signature_status) {
            throw "Vendor signature status changed after packaging: $($vendor.name)."
        }
        $signer = if ($signature.SignerCertificate) {
            $signature.SignerCertificate.Subject
        } else { '' }
        if ($signer -cne [string]$vendor.signer) {
            throw "Vendor signer changed after packaging: $($vendor.name)."
        }
        if ($signature.Status -notin @('Valid', 'NotSigned')) {
            throw "Vendor signature is not trustworthy: $($vendor.name)."
        }
    }
    Write-Host 'Vendor signatures match the verified bundle metadata.'
}

function Write-InstallerState {
    param([string]$Path, [Collections.IDictionary]$Value)
    $directory = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $temporary = Join-Path $directory ('.state-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    try {
        $Value | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $temporary -Encoding UTF8
        Move-Item -LiteralPath $temporary -Destination $Path -Force
    } finally {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    }
}

function Get-ReleasePackageVersion {
    param([string]$PackagePath)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($PackagePath)
    try {
        $manifest = $archive.Entries |
            Where-Object { $_.FullName -eq 'release.json' } |
            Select-Object -First 1
        if (-not $manifest) {
            throw 'The application release package does not contain release.json.'
        }
        $reader = [IO.StreamReader]::new($manifest.Open())
        try { $release = $reader.ReadToEnd() | ConvertFrom-Json }
        finally { $reader.Dispose() }
    } finally {
        $archive.Dispose()
    }
    $version = [string]$release.version
    if ($version -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$') {
        throw 'The application release package contains an invalid version.'
    }
    return $version
}

function Assert-InstallationTarget {
    param([string]$Root, [string]$Mode, [string]$StatePath)
    $resolved = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    $state = $null
    if (Test-Path -LiteralPath $StatePath -PathType Leaf) {
        try { $state = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json }
        catch { throw 'Installer state is unreadable. Repair it before continuing.' }
    }
    $known = $state -and ([string]$state.install_root).TrimEnd('\') -ieq $resolved
    $nonEmpty = (Test-Path -LiteralPath $resolved -PathType Container) -and
        (Get-ChildItem -LiteralPath $resolved -Force | Select-Object -First 1)
    if ($Mode -eq 'New' -and $nonEmpty -and -not $known) {
        throw 'The installation folder is not empty and is not a known installation. Choose an empty folder.'
    }
    if ($Mode -eq 'New' -and $known -and $state.status -eq 'complete') {
        throw 'This installation is already complete. Choose Repair instead.'
    }
    if ($Mode -eq 'Repair' -and -not $known) {
        throw 'Repair requires an installation recorded by this setup program.'
    }
    return $state
}

function Initialize-BootstrapRuntime {
    param(
        [string]$PythonExecutable,
        [string]$ReleasePackage,
        [string]$Wheelhouse,
        [string]$RuntimeRoot
    )
    $source = Join-Path $RuntimeRoot 'source'
    $python = Join-Path $RuntimeRoot '.venv\Scripts\python.exe'
    $stagedSource = Join-Path $RuntimeRoot (
        'source-refresh-' + [Guid]::NewGuid().ToString('N')
    )
    try {
        New-Item -ItemType Directory -Path $stagedSource -Force | Out-Null
        Expand-Archive -LiteralPath $ReleasePackage -DestinationPath $stagedSource
        if (-not (Test-Path -LiteralPath (Join-Path $stagedSource 'bootstrap_cli.py'))) {
            throw 'The setup bootstrap source is incomplete.'
        }
        if (Test-Path -LiteralPath $source) {
            Remove-Item -LiteralPath $source -Recurse -Force
        }
        Move-Item -LiteralPath $stagedSource -Destination $source
    } finally {
        Remove-Item -LiteralPath $stagedSource -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        & $PythonExecutable -m venv (Join-Path $RuntimeRoot '.venv') 2>&1 |
            Write-InstallerProgress
        if ($LASTEXITCODE -ne 0) { throw 'The setup bootstrap environment could not be created.' }
    }
    & $python -m pip install --disable-pip-version-check --no-index `
        "--find-links=$Wheelhouse" -r (Join-Path $source 'requirements.txt') 2>&1 |
        Write-InstallerProgress
    if ($LASTEXITCODE -ne 0) { throw 'The setup bootstrap dependencies could not be installed.' }
    return [ordered]@{ Python = $python; Cli = Join-Path $source 'bootstrap_cli.py' }
}

function Invoke-BootstrapCommand {
    param(
        [Collections.IDictionary]$Runtime,
        [string]$Command,
        [Collections.IDictionary]$Payload
    )
    $json = $Payload | ConvertTo-Json -Depth 6 -Compress
    $output = $json | & $Runtime.Python $Runtime.Cli $Command 2>$null
    $exitCode = $LASTEXITCODE
    $json = $null
    try { $result = ($output | Select-Object -Last 1) | ConvertFrom-Json }
    catch { throw 'The database bootstrap operation returned an unreadable response.' }
    if ($exitCode -ne 0 -or -not $result.ok) {
        $message = @($result.errors.PSObject.Properties.Value) | Select-Object -First 1
        if (-not $message) { $message = 'The database bootstrap operation failed.' }
        throw [string]$message
    }
    return $result
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script as Windows Administrator.'
}

$bundleRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
Test-BundleChecksums -BundleRoot $bundleRoot
Test-VendorSignatures -BundleRoot $bundleRoot
$installerRoot = Join-Path $env:ProgramData 'ServiceManagementSystem\Installer'
$statePath = Join-Path $installerRoot 'state.json'
$resolvedInstallRoot = [IO.Path]::GetFullPath($InstallRoot)
$previousState = Assert-InstallationTarget -Root $resolvedInstallRoot -Mode $Mode `
    -StatePath $statePath

function Read-CapturedText {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return '' }
    $content = Get-Content -LiteralPath $Path -Raw
    if ($null -eq $content) { return '' }
    return ([string]$content).Trim()
}

function Invoke-AlembicUpgrade {
    param(
        [string]$PythonExecutable,
        [string]$WorkingDirectory,
        [string]$CaptureDirectory
    )
    New-Item -ItemType Directory -Path $CaptureDirectory -Force | Out-Null
    $captureId = [Guid]::NewGuid().ToString('N')
    $stdoutPath = Join-Path $CaptureDirectory "alembic-repair-$captureId.stdout"
    $stderrPath = Join-Path $CaptureDirectory "alembic-repair-$captureId.stderr"
    try {
        $process = Start-Process -FilePath $PythonExecutable `
            -ArgumentList @('-m', 'alembic', 'upgrade', 'head') `
            -WorkingDirectory $WorkingDirectory -WindowStyle Hidden `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath -Wait -PassThru
        $stdout = Read-CapturedText -Path $stdoutPath
        $stderr = Read-CapturedText -Path $stderrPath
        if ($stdout) { Write-Host $stdout }
        if ($stderr) { Write-Host $stderr }
        if ($process.ExitCode -ne 0) {
            $detail = if ($stderr) { " $stderr" } elseif ($stdout) { " $stdout" } else { '' }
            throw "Repair could not verify database migrations.$detail"
        }
    } finally {
        Remove-Item -LiteralPath $stdoutPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $stderrPath -Force -ErrorAction SilentlyContinue
    }
}

$resumeStep = if ($previousState) { [string]$previousState.last_completed_step } else { '' }
if ($Mode -eq 'New') {
    if (-not $InitializeNewDatabase) {
        throw 'A new installation requires explicit new-database initialization.'
    }
    foreach ($required in @(
        @{ Name = 'database Administrator password'; Value = $DatabaseAdminPassword },
        @{ Name = 'application database password'; Value = $DatabasePassword },
        @{ Name = 'Administrator full name'; Value = $AdministratorFullName.Trim() },
        @{ Name = 'Administrator username'; Value = $AdministratorUsername.Trim() },
        @{ Name = 'Administrator password'; Value = $AdministratorPassword }
    )) {
        if (-not $required.Value) { throw "Enter the $($required.Name)." }
    }
}
Write-InstallerState -Path $statePath -Value ([ordered]@{
    status = 'running'; mode = $Mode; install_root = $resolvedInstallRoot
    service_name = $ServiceName
    last_completed_step = if ($resumeStep) { $resumeStep } else { 'bundle_verified' }
    updated_utc = [DateTime]::UtcNow.ToString('o')
})
$prerequisitesRoot = Join-Path $bundleRoot 'prerequisites'
$pythonInstaller = Join-Path $prerequisitesRoot 'python-3.11-amd64.exe'
$postgresInstaller = Join-Path $prerequisitesRoot 'postgresql-windows-x64.exe'
$dotNetInstaller = Join-Path $prerequisitesRoot 'dotnet-framework-offline.exe'
$winSwExecutable = Join-Path $prerequisitesRoot 'WinSW-net461.exe'
$wheelhouse = Join-Path $bundleRoot 'wheelhouse'
$installServer = Join-Path $bundleRoot 'bootstrap\scripts\Install-Server.ps1'
$deployRelease = Join-Path $bundleRoot 'bootstrap\scripts\Deploy-Release.ps1'
$releasePackages = @(Get-ChildItem -LiteralPath (Join-Path $bundleRoot 'application') `
    -Filter 'service-management-*.zip' -File)
if ($releasePackages.Count -ne 1) {
    throw 'The offline bundle must contain exactly one application release ZIP.'
}
$bootstrapRuntimeRoot = Join-Path $installerRoot 'bootstrap-runtime'

# WinSW requires .NET Framework 4.6.1 (release 394254) or newer.
if ((Get-DotNetFrameworkRelease) -lt 394254) {
    Write-Host 'A compatible .NET Framework was not found. Starting the bundled installer.'
    $dotNetProcess = Start-Process -FilePath $dotNetInstaller `
        -ArgumentList '/passive', '/norestart' -Wait -PassThru
    if ($dotNetProcess.ExitCode -eq 3010) {
        Write-Host 'The .NET Framework installation requires a restart. Restart Windows, then run this script again.'
        exit 3010
    }
    if ($dotNetProcess.ExitCode -ne 0 -or (Get-DotNetFrameworkRelease) -lt 394254) {
        throw 'A compatible .NET Framework could not be installed.'
    }
} else {
    Write-Host 'Compatible .NET Framework already installed; skipped.'
}

$pythonExecutable = Get-Python311Executable
if (-not $pythonExecutable) {
    Write-Host 'Python 3.11 64-bit was not found. Starting the bundled installer.'
    $pythonProcess = Start-Process -FilePath $pythonInstaller -ArgumentList @(
        '/quiet',
        'InstallAllUsers=1',
        'PrependPath=1',
        'Include_pip=1',
        'Include_launcher=1',
        'Include_tcltk=1',
        'Include_test=0'
    ) -Wait -PassThru
    if ($pythonProcess.ExitCode -ne 0) {
        throw "Python installation failed with exit code $($pythonProcess.ExitCode)."
    }
    $pythonExecutable = Get-Python311Executable
    if (-not $pythonExecutable) {
        throw 'Python installation completed, but Python 3.11 64-bit was not found.'
    }
} else {
    Write-Host "Python 3.11 64-bit already installed; skipped: $pythonExecutable"
}

& $pythonExecutable -c 'import tkinter; print(tkinter.TkVersion)'
if ($LASTEXITCODE -ne 0) {
    throw 'Python tkinter is unavailable. Repair Python 3.11 with Tcl/Tk support, then run the installer again.'
}
Write-Host 'Python tkinter support verified.'

$postgresTools = Get-PostgreSqlTools
if (-not $postgresTools) {
    Write-Host 'PostgreSQL was not found. Starting the bundled vendor installer.'
    Write-Host 'Complete the visible PostgreSQL setup and remember the postgres password and port.'
    $postgresProcess = Start-Process -FilePath $postgresInstaller -Wait -PassThru
    if ($postgresProcess.ExitCode -ne 0) {
        throw "PostgreSQL installation failed or was cancelled with exit code $($postgresProcess.ExitCode)."
    }
    $postgresTools = Get-PostgreSqlTools
    if (-not $postgresTools) {
        throw 'PostgreSQL setup completed, but psql.exe and pg_dump.exe were not found.'
    }
} else {
    Write-Host "PostgreSQL tools already installed; skipped: $($postgresTools.Psql)"
}
Write-InstallerState -Path $statePath -Value ([ordered]@{
    status = 'running'; mode = $Mode; install_root = $resolvedInstallRoot
    service_name = $ServiceName
    last_completed_step = if ($resumeStep -in @(
        'database_created', 'server_configured', 'deployed', 'admin_created'
    )) { $resumeStep } else { 'prerequisites_ready' }
    updated_utc = [DateTime]::UtcNow.ToString('o')
})

if ($Mode -eq 'New' -and $resumeStep -notin @(
    'database_created', 'server_configured', 'deployed', 'admin_created'
)) {
    $runtime = Initialize-BootstrapRuntime -PythonExecutable $pythonExecutable `
        -ReleasePackage $releasePackages[0].FullName -Wheelhouse $wheelhouse `
        -RuntimeRoot $bootstrapRuntimeRoot
    $plainAdminPassword = ConvertFrom-SecureValue $DatabaseAdminPassword
    $plainDatabasePassword = ConvertFrom-SecureValue $DatabasePassword
    try {
        [void](Invoke-BootstrapCommand -Runtime $runtime `
            -Command 'create-role-database' -Payload ([ordered]@{
                admin = [ordered]@{
                    host = $DatabaseAdminHost; port = $DatabaseAdminPort
                    database = $DatabaseAdminName; username = $DatabaseAdminUsername
                    password = $plainAdminPassword
                }
                application = [ordered]@{
                    database = $DatabaseName; username = $DatabaseUsername
                    password = $plainDatabasePassword
                }
            }))
    } finally {
        $plainAdminPassword = $null
        $plainDatabasePassword = $null
    }
    Write-Host 'The application PostgreSQL role and database were created.'
    $resumeStep = 'database_created'
    Write-InstallerState -Path $statePath -Value ([ordered]@{
        status = 'running'; mode = $Mode; install_root = $resolvedInstallRoot
        service_name = $ServiceName; last_completed_step = $resumeStep
        updated_utc = [DateTime]::UtcNow.ToString('o')
    })
}

& $installServer -InstallRoot $resolvedInstallRoot -ServiceName $ServiceName `
    -WinSwPath $winSwExecutable -PythonExecutable $pythonExecutable -Port $Port `
    -DatabaseHost $DatabaseAdminHost -DatabasePort $DatabaseAdminPort `
    -DatabaseName $DatabaseName -DatabaseUsername $DatabaseUsername `
    -DatabasePassword $DatabasePassword
if ($LASTEXITCODE -ne 0) { throw 'Server installation did not complete.' }
$resumeStep = if ($resumeStep -in @('deployed', 'admin_created')) {
    $resumeStep
} else { 'server_configured' }
Write-InstallerState -Path $statePath -Value ([ordered]@{
    status = 'running'; mode = $Mode; install_root = $resolvedInstallRoot
    service_name = $ServiceName; last_completed_step = $resumeStep
    updated_utc = [DateTime]::UtcNow.ToString('o')
})

$currentPath = Join-Path $resolvedInstallRoot 'current'
$venvPython = Join-Path $resolvedInstallRoot '.venv\Scripts\python.exe'
$bundledReleaseVersion = Get-ReleasePackageVersion `
    -PackagePath $releasePackages[0].FullName
$installedReleaseVersion = ''
$installedManifest = Join-Path $currentPath 'release.json'
if (Test-Path -LiteralPath $installedManifest -PathType Leaf) {
    try {
        $installedReleaseVersion = [string](
            Get-Content -LiteralPath $installedManifest -Raw | ConvertFrom-Json
        ).version
    } catch {
        throw 'The installed release manifest is unreadable. Repair cannot continue safely.'
    }
}
$repairSameRelease = (
    $Mode -eq 'Repair' -and
    (Test-Path -LiteralPath $currentPath -PathType Container) -and
    $installedReleaseVersion -ceq $bundledReleaseVersion
)
if ($Mode -eq 'New' -and $resumeStep -in @('deployed', 'admin_created') -and
    (Test-Path -LiteralPath $currentPath -PathType Container)) {
    Write-Host 'Application release already deployed; resumed at the next setup step.'
} elseif ($repairSameRelease) {
    & $venvPython -m pip install --disable-pip-version-check --no-index `
        "--find-links=$wheelhouse" -r (Join-Path $currentPath 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Repair could not reinstall application dependencies.' }
    $oldSmsEnvFile = $env:SMS_ENV_FILE
    $oldEnvironment = $env:ENVIRONMENT
    try {
        $env:SMS_ENV_FILE = Join-Path $resolvedInstallRoot 'shared\.env'
        $env:ENVIRONMENT = 'production'
        Invoke-AlembicUpgrade -PythonExecutable $venvPython `
            -WorkingDirectory $currentPath -CaptureDirectory (
                Join-Path $resolvedInstallRoot 'shared\runtime-temp'
            )
    } finally {
        $env:SMS_ENV_FILE = $oldSmsEnvFile
        $env:ENVIRONMENT = $oldEnvironment
    }
    Restart-Service -Name $ServiceName -Force
    Write-Host "Release $bundledReleaseVersion dependencies and migrations were repaired."
} else {
    if ($Mode -eq 'Repair') {
        Write-Host (
            "Repair is installing bundled release $bundledReleaseVersion " +
            "over installed release $installedReleaseVersion."
        )
    }
    Write-Host (
        'Verifying dependencies and deploying the application. This can take ' +
        'several minutes. Do not close Setup.'
    )
    & $deployRelease -ReleasePackage $releasePackages[0].FullName `
        -InstallRoot $resolvedInstallRoot -ServiceName $ServiceName `
        -PythonExecutable $pythonExecutable -PgDumpExecutable $postgresTools.PgDump `
        -WheelhousePath $wheelhouse
    if ($LASTEXITCODE -ne 0) { throw 'Application deployment did not complete.' }
}
$resumeStep = if ($resumeStep -eq 'admin_created') { $resumeStep } else { 'deployed' }
Write-InstallerState -Path $statePath -Value ([ordered]@{
    status = 'running'; mode = $Mode; install_root = $resolvedInstallRoot
    service_name = $ServiceName; last_completed_step = $resumeStep
    updated_utc = [DateTime]::UtcNow.ToString('o')
})

if ($Mode -eq 'New' -and $resumeStep -ne 'admin_created') {
    $plainAdministratorPassword = ConvertFrom-SecureValue $AdministratorPassword
    $hadSmsEnvFile = Test-Path -LiteralPath 'Env:SMS_ENV_FILE'
    $oldSmsEnvFile = $env:SMS_ENV_FILE
    $hadEnvironment = Test-Path -LiteralPath 'Env:ENVIRONMENT'
    $oldEnvironment = $env:ENVIRONMENT
    try {
        $env:SMS_ENV_FILE = Join-Path $resolvedInstallRoot 'shared\.env'
        $env:ENVIRONMENT = 'production'
        $adminRuntime = [ordered]@{
            Python = $venvPython
            Cli = Join-Path $currentPath 'bootstrap_cli.py'
        }
        [void](Invoke-BootstrapCommand -Runtime $adminRuntime -Command 'create-admin' `
            -Payload ([ordered]@{
                full_name = $AdministratorFullName
                username = $AdministratorUsername
                password = $plainAdministratorPassword
            }))
    } finally {
        $plainAdministratorPassword = $null
        if ($hadSmsEnvFile) { $env:SMS_ENV_FILE = $oldSmsEnvFile }
        else { Remove-Item -LiteralPath 'Env:SMS_ENV_FILE' -ErrorAction SilentlyContinue }
        if ($hadEnvironment) { $env:ENVIRONMENT = $oldEnvironment }
        else { Remove-Item -LiteralPath 'Env:ENVIRONMENT' -ErrorAction SilentlyContinue }
    }
    $resumeStep = 'admin_created'
    Write-InstallerState -Path $statePath -Value ([ordered]@{
        status = 'running'; mode = $Mode; install_root = $resolvedInstallRoot
        service_name = $ServiceName; last_completed_step = $resumeStep
        updated_utc = [DateTime]::UtcNow.ToString('o')
    })
}

$installedUninstaller = Join-Path $resolvedInstallRoot 'Uninstall-ServiceManagement.ps1'
Copy-Item -LiteralPath (Join-Path $bundleRoot 'bootstrap\scripts\Uninstall-Server.ps1') `
    -Destination $installedUninstaller -Force
$shortcutInstaller = Join-Path $bundleRoot 'bootstrap\scripts\Install-ServiceConsoleShortcuts.ps1'
& $shortcutInstaller -InstallRoot $resolvedInstallRoot
if ($LASTEXITCODE -ne 0) { throw 'Service Console shortcuts could not be installed.' }

Write-InstallerState -Path $statePath -Value ([ordered]@{
    status = 'complete'; mode = $Mode; install_root = $resolvedInstallRoot
    service_name = $ServiceName; last_completed_step = 'complete'
    updated_utc = [DateTime]::UtcNow.ToString('o')
})

Write-Host ''
Write-Host 'Offline installation completed.'
Write-Host "Open http://localhost:$Port and log in with the Administrator you created."
Write-Host 'Use the local Service Console for network, service and backup settings.'
