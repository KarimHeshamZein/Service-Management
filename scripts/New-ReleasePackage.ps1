[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')]
    [string]$Version,

    [string]$OutputDirectory = 'dist'
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$outputRoot = if ([IO.Path]::IsPathRooted($OutputDirectory)) {
    [IO.Path]::GetFullPath($OutputDirectory)
} else {
    [IO.Path]::GetFullPath((Join-Path $projectRoot $OutputDirectory))
}
$stagingRoot = Join-Path ([IO.Path]::GetTempPath()) (
    'service-management-release-' + [Guid]::NewGuid().ToString('N')
)
$packageRoot = Join-Path $stagingRoot 'package'
$archivePath = Join-Path $outputRoot "service-management-$Version.zip"

$requiredPaths = @(
    'app',
    'console',
    'alembic',
    'alembic.ini',
    'requirements.txt',
    'bootstrap_cli.py',
    'run.py',
    'serve.py'
)
foreach ($relativePath in $requiredPaths) {
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $relativePath))) {
        throw "Required release path is missing: $relativePath"
    }
}

try {
    New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null

    $releasePaths = @(
        'app',
        'alembic',
        'docs',
        'scripts',
        'console',
        '.env.example',
        'alembic.ini',
        'CLAUDE.md',
        'README.md',
        'requirements.txt',
        'bootstrap_cli.py',
        'create_admin.py',
        'reset_admin_password.py',
        'run.py',
        'serve.py'
    )
    foreach ($relativePath in $releasePaths) {
        $source = Join-Path $projectRoot $relativePath
        if (Test-Path -LiteralPath $source) {
            Copy-Item -LiteralPath $source -Destination $packageRoot -Recurse -Force
        }
    }

    Get-ChildItem -LiteralPath $packageRoot -Directory -Recurse -Force |
        Where-Object { $_.Name -in @('__pycache__', '.pytest_cache') } |
        Sort-Object FullName -Descending |
        Remove-Item -Recurse -Force
    Get-ChildItem -LiteralPath $packageRoot -File -Recurse -Force |
        Where-Object { $_.Extension -in @('.pyc', '.pyo') } |
        Remove-Item -Force

    $python = Join-Path $projectRoot '.venv\Scripts\python.exe'
    $alembicHead = 'unknown'
    if (Test-Path -LiteralPath $python) {
        $headOutput = & $python -m alembic heads 2>$null
        if ($LASTEXITCODE -eq 0 -and $headOutput) {
            $alembicHead = (($headOutput | Select-Object -First 1) -split '\s+')[0]
        }
    }
    [ordered]@{
        product = 'Service Management System'
        version = $Version
        created_utc = [DateTime]::UtcNow.ToString('o')
        alembic_head = $alembicHead
    } | ConvertTo-Json | Set-Content -LiteralPath (
        Join-Path $packageRoot 'release.json'
    ) -Encoding UTF8

    if (Test-Path -LiteralPath $archivePath) {
        Remove-Item -LiteralPath $archivePath -Force
    }
    Compress-Archive -Path (Join-Path $packageRoot '*') -DestinationPath $archivePath
    Write-Host "Release package created: $archivePath"
} finally {
    if (
        (Test-Path -LiteralPath $stagingRoot) -and
        $stagingRoot.StartsWith([IO.Path]::GetTempPath(), [StringComparison]::OrdinalIgnoreCase)
    ) {
        Remove-Item -LiteralPath $stagingRoot -Recurse -Force
    }
}
