[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')]
    [string]$Version,

    [Parameter(Mandatory = $true)]
    [string]$PythonInstallerPath,
    [Parameter(Mandatory = $true)]
    [string]$PostgreSqlInstallerPath,
    [Parameter(Mandatory = $true)]
    [string]$DotNetInstallerPath,
    [Parameter(Mandatory = $true)]
    [string]$WinSwPath,

    [string]$WheelBuilderPython = '.venv\Scripts\python.exe',
    [string]$OutputDirectory = 'dist'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Resolve-RequiredPeFile {
    param([string]$Path, [string]$Label)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Label was not found: $Path"
    }
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    if ([IO.Path]::GetExtension($resolved) -ine '.exe') {
        throw "$Label must be an .exe file."
    }
    $stream = [IO.File]::Open(
        $resolved,
        [IO.FileMode]::Open,
        [IO.FileAccess]::Read,
        [IO.FileShare]::Read
    )
    $reader = New-Object IO.BinaryReader($stream)
    try {
        if ($stream.Length -lt 64 -or $reader.ReadUInt16() -ne 0x5A4D) {
            throw "$Label is not a valid Windows PE executable."
        }
        $stream.Position = 0x3C
        $peOffset = $reader.ReadInt32()
        if ($peOffset -lt 0 -or ($peOffset + 4) -gt $stream.Length) {
            throw "$Label is not a valid Windows PE executable."
        }
        $stream.Position = $peOffset
        if ($reader.ReadUInt32() -ne 0x00004550) {
            throw "$Label is not a valid Windows PE executable."
        }
    } finally {
        $reader.Dispose()
        $stream.Dispose()
    }
    return $resolved
}

function Resolve-ProjectPath {
    param([string]$ProjectRoot, [string]$Path)
    $candidate = if ([IO.Path]::IsPathRooted($Path)) {
        $Path
    } else {
        Join-Path $ProjectRoot $Path
    }
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        throw "Required file was not found: $candidate"
    }
    return (Resolve-Path -LiteralPath $candidate).Path
}

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$outputRoot = if ([IO.Path]::IsPathRooted($OutputDirectory)) {
    [IO.Path]::GetFullPath($OutputDirectory)
} else {
    [IO.Path]::GetFullPath((Join-Path $projectRoot $OutputDirectory))
}
$pythonInstaller = Resolve-RequiredPeFile $PythonInstallerPath 'Python installer'
$postgresInstaller = Resolve-RequiredPeFile $PostgreSqlInstallerPath 'PostgreSQL installer'
$dotNetInstaller = Resolve-RequiredPeFile $DotNetInstallerPath '.NET Framework installer'
$winSwExecutable = Resolve-RequiredPeFile $WinSwPath 'WinSW executable'
$pythonInstallerVersion = [Diagnostics.FileVersionInfo]::GetVersionInfo($pythonInstaller)
if (
    $pythonInstallerVersion.FileMajorPart -ne 3 -or
    $pythonInstallerVersion.FileMinorPart -ne 11
) {
    throw 'PythonInstallerPath must point to a Python 3.11 Windows installer.'
}
if ($pythonInstallerVersion.OriginalFilename -in @('python.exe', 'pythonw.exe', 'py.exe')) {
    throw 'PythonInstallerPath points to a Python runtime executable, not an installer.'
}
$builderPython = Resolve-ProjectPath $projectRoot $WheelBuilderPython

$pythonFactsOutput = & $builderPython -c `
    'import sys; print(sys.version_info[0], sys.version_info[1], sys.maxsize)'
$pythonFactsExitCode = $LASTEXITCODE
$pythonFactsText = $pythonFactsOutput | Select-Object -First 1
if ($pythonFactsExitCode -ne 0 -or -not $pythonFactsText) {
    throw 'The wheel-builder Python executable could not be inspected.'
}
$pythonFacts = $pythonFactsText.Trim() -split '\s+'
if ($pythonFacts.Count -ne 3) {
    throw 'The wheel-builder Python executable returned an invalid version response.'
}
if ([int]$pythonFacts[0] -ne 3 -or [int]$pythonFacts[1] -ne 11) {
    throw 'WheelBuilderPython must use Python 3.11 so it matches the offline target.'
}
if ([Int64]$pythonFacts[2] -le [Int32]::MaxValue) {
    throw 'WheelBuilderPython must be a 64-bit Python installation.'
}

$stagingRoot = Join-Path ([IO.Path]::GetTempPath()) (
    'service-management-offline-' + [Guid]::NewGuid().ToString('N')
)
$bundleRoot = Join-Path $stagingRoot 'bundle'
$applicationRoot = Join-Path $bundleRoot 'application'
$prerequisitesRoot = Join-Path $bundleRoot 'prerequisites'
$bootstrapRoot = Join-Path $bundleRoot 'bootstrap'
$bootstrapScripts = Join-Path $bootstrapRoot 'scripts'
$wheelhouseRoot = Join-Path $bundleRoot 'wheelhouse'
$archivePath = Join-Path $outputRoot "service-management-offline-$Version.zip"

try {
    foreach ($directory in @(
        $bundleRoot,
        $applicationRoot,
        $prerequisitesRoot,
        $bootstrapScripts,
        $wheelhouseRoot,
        $outputRoot
    )) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }

    & (Join-Path $PSScriptRoot 'New-ReleasePackage.ps1') `
        -Version $Version -OutputDirectory $applicationRoot
    if ($LASTEXITCODE -ne 0) { throw 'The application release package could not be created.' }
    $releasePackage = Join-Path $applicationRoot "service-management-$Version.zip"
    if (-not (Test-Path -LiteralPath $releasePackage -PathType Leaf)) {
        throw "Application release package was not created: $releasePackage"
    }

    Copy-Item -LiteralPath $pythonInstaller `
        -Destination (Join-Path $prerequisitesRoot 'python-3.11-amd64.exe')
    Copy-Item -LiteralPath $postgresInstaller `
        -Destination (Join-Path $prerequisitesRoot 'postgresql-windows-x64.exe')
    Copy-Item -LiteralPath $dotNetInstaller `
        -Destination (Join-Path $prerequisitesRoot 'dotnet-framework-offline.exe')
    Copy-Item -LiteralPath $winSwExecutable `
        -Destination (Join-Path $prerequisitesRoot 'WinSW-net461.exe')

    Copy-Item -LiteralPath (Join-Path $projectRoot '.env.example') `
        -Destination $bootstrapRoot
    foreach ($scriptName in @(
        'Install-Server.ps1',
        'Deploy-Release.ps1',
        'Install-ServiceConsoleShortcuts.ps1',
        'Launch-ServiceConsole.ps1',
        'Uninstall-Server.ps1'
    )) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $scriptName) `
            -Destination $bootstrapScripts
    }
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Install-Offline.ps1') `
        -Destination $bundleRoot
    Copy-Item -LiteralPath (Join-Path $projectRoot 'Setup-ServiceManagement.cmd') `
        -Destination $bundleRoot
    Copy-Item -LiteralPath (Join-Path $projectRoot 'Setup-ServiceManagement.ps1') `
        -Destination $bundleRoot
    Copy-Item -LiteralPath (Join-Path $projectRoot 'docs\OFFLINE_INSTALL.md') `
        -Destination $bundleRoot

    & $builderPython -m pip download --disable-pip-version-check `
        --only-binary=:all: --platform win_amd64 --implementation cp `
        --python-version 311 --abi cp311 --dest $wheelhouseRoot `
        -r (Join-Path $projectRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) {
        throw 'Python dependencies could not be downloaded for CPython 3.11 64-bit Windows.'
    }
    if (-not (Get-ChildItem -LiteralPath $wheelhouseRoot -Filter '*.whl' -File)) {
        throw 'The offline wheelhouse contains no Python wheels.'
    }

    @"
# Third-party software in this offline bundle

The operator supplied these vendor installers to the bundle builder. Verify each
source file against its vendor-published checksum before building the bundle.

- Python: Python Software Foundation license — https://www.python.org/downloads/windows/
- PostgreSQL: PostgreSQL License — https://www.postgresql.org/download/windows/
- .NET Framework: Microsoft license terms — https://dotnet.microsoft.com/download/dotnet-framework
- WinSW: MIT License — https://github.com/winsw/winsw

The generated checksums.sha256 protects the files after the bundle is built; it
does not replace verification against each vendor's published checksum.
"@ | Set-Content -LiteralPath (Join-Path $bundleRoot 'THIRD_PARTY_NOTICES.md') `
        -Encoding UTF8

    $inputMetadata = @(
        @{ Name = 'Python'; Source = $pythonInstaller; Bundled = 'prerequisites/python-3.11-amd64.exe' },
        @{ Name = 'PostgreSQL'; Source = $postgresInstaller; Bundled = 'prerequisites/postgresql-windows-x64.exe' },
        @{ Name = '.NET Framework'; Source = $dotNetInstaller; Bundled = 'prerequisites/dotnet-framework-offline.exe' },
        @{ Name = 'WinSW'; Source = $winSwExecutable; Bundled = 'prerequisites/WinSW-net461.exe' }
    ) | ForEach-Object {
        $signature = Get-AuthenticodeSignature -LiteralPath $_.Source
        [ordered]@{
            name = $_.Name
            source_filename = [IO.Path]::GetFileName($_.Source)
            bundled_path = $_.Bundled
            sha256 = (Get-FileHash -LiteralPath $_.Source -Algorithm SHA256).Hash.ToLowerInvariant()
            signature_status = [string]$signature.Status
            signer = if ($signature.SignerCertificate) {
                $signature.SignerCertificate.Subject
            } else { '' }
        }
    }
    [ordered]@{
        product = 'Service Management System offline deployment bundle'
        version = $Version
        created_utc = [DateTime]::UtcNow.ToString('o')
        target = 'CPython 3.11, Windows x64'
        vendor_inputs = @($inputMetadata)
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (
        Join-Path $bundleRoot 'bundle.json'
    ) -Encoding UTF8

    $manifestLines = Get-ChildItem -LiteralPath $bundleRoot -File -Recurse |
        Where-Object { $_.Name -ne 'checksums.sha256' } |
        Sort-Object FullName |
        ForEach-Object {
            $relativePath = $_.FullName.Substring($bundleRoot.Length + 1).Replace('\', '/')
            $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            "$hash  $relativePath"
        }
    $manifestLines | Set-Content -LiteralPath (Join-Path $bundleRoot 'checksums.sha256') `
        -Encoding ASCII

    if (Test-Path -LiteralPath $archivePath) {
        Remove-Item -LiteralPath $archivePath -Force
    }
    Compress-Archive -Path (Join-Path $bundleRoot '*') -DestinationPath $archivePath
    $archiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.
        ToLowerInvariant()
    "$archiveHash  $([IO.Path]::GetFileName($archivePath))" |
        Set-Content -LiteralPath "$archivePath.sha256" -Encoding ASCII
    Write-Host "Offline deployment bundle created: $archivePath"
    Write-Host "Copy checksum: $archivePath.sha256"
    Write-Host 'Target: CPython 3.11, 64-bit Windows.'
} finally {
    if (
        (Test-Path -LiteralPath $stagingRoot) -and
        $stagingRoot.StartsWith(
            [IO.Path]::GetTempPath(),
            [StringComparison]::OrdinalIgnoreCase
        )
    ) {
        Remove-Item -LiteralPath $stagingRoot -Recurse -Force
    }
}
