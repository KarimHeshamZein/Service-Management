[CmdletBinding()]
param(
    [string]$InstallRoot = 'C:\ServiceManagement'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script as Windows Administrator.'
}

$root = [IO.Path]::GetFullPath($InstallRoot)
$pythonWindowed = Join-Path $root '.venv\Scripts\pythonw.exe'
$workingDirectory = Join-Path $root 'current'
if (-not (Test-Path -LiteralPath $pythonWindowed -PathType Leaf)) {
    throw "The production Python launcher was not found at $pythonWindowed"
}
if (-not (Test-Path -LiteralPath (Join-Path $workingDirectory 'console\__main__.py'))) {
    throw "The Service Console was not found in $workingDirectory"
}

$launcherSource = Join-Path $PSScriptRoot 'Launch-ServiceConsole.ps1'
if (-not (Test-Path -LiteralPath $launcherSource -PathType Leaf)) {
    throw "The Service Console launcher was not found at $launcherSource"
}
$programDataRoot = Join-Path $env:ProgramData 'ServiceManagementSystem'
$launcherPath = Join-Path $programDataRoot 'Launch-ServiceConsole.ps1'
New-Item -ItemType Directory -Path $programDataRoot -Force | Out-Null
Copy-Item -LiteralPath $launcherSource -Destination $launcherPath -Force

# The shortcut must reach this launcher before elevation, so Users receive only
# read/execute access while Administrators and SYSTEM retain full control.
$systemSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')
$administratorsSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')
$usersSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-32-545')
$launcherAcl = [Security.AccessControl.FileSecurity]::new()
$launcherAcl.SetOwner($administratorsSid)
$launcherAcl.SetAccessRuleProtection($true, $false)
foreach ($sid in @($systemSid, $administratorsSid)) {
    $launcherAcl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
        $sid,
        [Security.AccessControl.FileSystemRights]::FullControl,
        [Security.AccessControl.AccessControlType]::Allow
    ))
}
$launcherAcl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
    $usersSid,
    [Security.AccessControl.FileSystemRights]'ReadAndExecute, Synchronize',
    [Security.AccessControl.AccessControlType]::Allow
))
Set-Acl -LiteralPath $launcherPath -AclObject $launcherAcl

$shell = New-Object -ComObject WScript.Shell
$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$arguments = (
    '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' +
    $launcherPath + '" -InstallRoot "' + $root + '"'
)
$locations = @(
    [Environment]::GetFolderPath('CommonDesktopDirectory'),
    (Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\Afaqy')
)
foreach ($location in $locations) {
    New-Item -ItemType Directory -Path $location -Force | Out-Null
    $shortcutPath = Join-Path $location 'Service Management Console.lnk'
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $powershell
    $shortcut.Arguments = $arguments
    $shortcut.WorkingDirectory = $programDataRoot
    $shortcut.Description = 'Manage the Afaqy Service Management System'
    $shortcut.Save()
}

$uninstaller = Join-Path $root 'Uninstall-ServiceManagement.ps1'
if (Test-Path -LiteralPath $uninstaller -PathType Leaf) {
    $uninstallShortcut = $shell.CreateShortcut((Join-Path $locations[1] 'Uninstall Service Management.lnk'))
    $uninstallShortcut.TargetPath = 'powershell.exe'
    $uninstallShortcut.Arguments = (
        '-NoProfile -ExecutionPolicy Bypass -File "' + $uninstaller +
        '" -InstallRoot "' + $root + '"'
    )
    $uninstallShortcut.WorkingDirectory = $root
    $uninstallShortcut.Description = 'Safely uninstall the Afaqy Service Management System'
    $uninstallShortcut.Save()
}

Write-Host 'Service Console shortcuts installed.'
