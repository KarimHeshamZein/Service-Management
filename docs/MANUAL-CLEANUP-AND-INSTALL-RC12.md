# Manual cleanup and clean RC12 installation

Use this procedure when `D:\ServiceManagement` was deleted manually and the
installed uninstaller is no longer available.

This procedure permanently deletes the previous Service Management database,
users, records, uploaded photos, backups and configuration. Use it only when
yesterday's application data is not needed.

## 1. Remove the remaining Windows components

1. Open the Windows Start menu.
2. Search for **PowerShell**.
3. Right-click **Windows PowerShell**.
4. Select **Run as administrator**.
5. Approve the Windows security prompt.
6. Run:

```powershell
$service = Get-Service -Name "ServiceManagementSystem" -ErrorAction SilentlyContinue

if ($service) {
    Stop-Service -Name "ServiceManagementSystem" -Force -ErrorAction SilentlyContinue
    sc.exe delete "ServiceManagementSystem"
}

Unregister-ScheduledTask `
    -TaskName "ServiceManagementSystem Database Backup" `
    -Confirm:$false `
    -ErrorAction SilentlyContinue

Get-NetFirewallRule `
    -DisplayName "SMS Local HTTP","SMS Public HTTP" `
    -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule `
        -ErrorAction SilentlyContinue

Remove-Item `
    -LiteralPath "$env:ProgramData\ServiceManagementSystem" `
    -Recurse -Force `
    -ErrorAction SilentlyContinue

Remove-Item `
    -LiteralPath "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\Afaqy" `
    -Recurse -Force `
    -ErrorAction SilentlyContinue

Remove-Item `
    -LiteralPath "$env:PUBLIC\Desktop\Service Management Console.lnk" `
    -Force `
    -ErrorAction SilentlyContinue
```

Restart Windows so the deleted service is completely released.

## 2. Remove the previous application database

After restarting, open **PowerShell as Administrator** again and run:

```powershell
$pgBin = Get-ChildItem `
    -Path "$env:ProgramFiles\PostgreSQL" `
    -Filter "dropdb.exe" `
    -File -Recurse |
    Sort-Object FullName -Descending |
    Select-Object -First 1 |
    ForEach-Object DirectoryName

& "$pgBin\dropdb.exe" `
    --host=127.0.0.1 `
    --port=5432 `
    --username=postgres `
    --if-exists `
    --force `
    service_management

& "$pgBin\psql.exe" `
    --host=127.0.0.1 `
    --port=5432 `
    --username=postgres `
    --dbname=postgres `
    --command='DROP ROLE IF EXISTS service_management;'
```

Enter the PostgreSQL Administrator password when requested. The password is not
displayed while typing.

## 3. Extract RC12 again

Create this folder:

```text
D:\AfaqySetup\1.1.0-rc12
```

Extract the entire RC12 ZIP into that folder. Confirm these files are together
in the folder:

```text
Setup-ServiceManagement.cmd
Setup-ServiceManagement.ps1
Install-Offline.ps1
```

Confirm these folders are also present:

```text
application
bootstrap
prerequisites
wheelhouse
```

## 4. Start the installer without a disappearing window

Open **PowerShell as Administrator** and run:

```powershell
Set-Location "D:\AfaqySetup\1.1.0-rc12"

Get-ChildItem -Recurse -File |
    Unblock-File -ErrorAction SilentlyContinue

powershell.exe `
    -NoProfile `
    -ExecutionPolicy Bypass `
    -File ".\Setup-ServiceManagement.ps1"
```

When the graphical installer opens, select **New installation** and follow the
prompts.

If setup fails, leave PowerShell open and copy the complete displayed error. Do
not delete any additional files after the failure.
