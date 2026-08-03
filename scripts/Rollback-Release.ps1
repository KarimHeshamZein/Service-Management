[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')]
    [string]$Version,

    [string]$InstallRoot = 'C:\ServiceManagement',
    [string]$ServiceName = 'ServiceManagementSystem'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath($InstallRoot)
$currentPath = Join-Path $root 'current'
$targetPath = Join-Path (Join-Path $root 'releases') $Version

if (-not (Test-Path -LiteralPath (Join-Path $targetPath 'release.json'))) {
    throw "Installed release not found: $targetPath"
}
$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $service) { throw "Windows service '$ServiceName' was not found." }
if (Test-Path -LiteralPath $currentPath) {
    $currentItem = Get-Item -LiteralPath $currentPath -Force
    if (-not ($currentItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "The current path exists but is not a junction: $currentPath"
    }
}

Stop-Service -Name $ServiceName -Force
if (Test-Path -LiteralPath $currentPath) {
    Remove-Item -LiteralPath $currentPath -Force
}
New-Item -ItemType Junction -Path $currentPath -Target $targetPath | Out-Null
Start-Service -Name $ServiceName

Write-Host "Application release changed to $Version."
Write-Warning (
    'This command does not downgrade PostgreSQL. Confirm that the selected ' +
    'application release is compatible with the current database schema.'
)
