[CmdletBinding()]
param(
    [string]$InstallRoot = 'C:\ServiceManagement'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Show-LaunchError {
    param([string]$Message)
    Add-Type -AssemblyName System.Windows.Forms
    [Windows.Forms.MessageBox]::Show(
        $Message,
        'Service Management Console',
        [Windows.Forms.MessageBoxButtons]::OK,
        [Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
}

try {
    $root = [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        $arguments = @(
            '-NoProfile',
            '-ExecutionPolicy', 'Bypass',
            '-WindowStyle', 'Hidden',
            '-File', ('"' + $PSCommandPath + '"'),
            '-InstallRoot', ('"' + $root + '"')
        )
        try {
            Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments `
                -Verb RunAs -WindowStyle Hidden | Out-Null
        } catch {
            Show-LaunchError 'Administrator approval was refused. The Service Console was not opened.'
            exit 1
        }
        exit 0
    }

    $pythonWindowed = Join-Path $root '.venv\Scripts\pythonw.exe'
    $workingDirectory = Join-Path $root 'current'
    $consoleEntry = Join-Path $workingDirectory 'console\__main__.py'
    if (-not (Test-Path -LiteralPath $pythonWindowed -PathType Leaf)) {
        throw "The production Python launcher was not found at $pythonWindowed. Run the installer in Repair mode."
    }
    if (-not (Test-Path -LiteralPath $consoleEntry -PathType Leaf)) {
        throw "The Service Console was not found at $consoleEntry. Run the installer in Repair mode."
    }

    Start-Process -FilePath $pythonWindowed `
        -ArgumentList @('-m', 'console', '--install-root', ('"' + $root + '"')) `
        -WorkingDirectory $workingDirectory | Out-Null
} catch {
    Show-LaunchError $_.Exception.Message
    exit 1
}
