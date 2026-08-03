# Clean production installation of RC12

Use this procedure only when the data from the previous installation is not
needed. It permanently deletes the application database, users, records,
uploaded photos, backups and configuration.

PostgreSQL itself remains installed and can be reused by the RC12 installer.

## 1. Close the application

Close the Afaqy Service Management Console and any browser windows displaying
the application.

## 2. Open an elevated PowerShell window

1. Open the Windows Start menu.
2. Search for **PowerShell**.
3. Right-click **Windows PowerShell**.
4. Select **Run as administrator**.
5. Approve the Windows security prompt.

## 3. Permanently remove the previous installation

Run this command:

```powershell
& "D:\ServiceManagement\Uninstall-ServiceManagement.ps1" `
  -InstallRoot "D:\ServiceManagement" `
  -RemovePersistentData
```

When prompted, type this exact confirmation:

```text
DELETE SERVICE MANAGEMENT DATA
```

Wait until PowerShell reports that the application and all persistent data were
removed. Do not manually delete `D:\ServiceManagement` before running the
uninstaller because that could leave the Windows service registered.

## 4. Prepare RC12

Copy these two files to the production computer and keep them together:

```text
service-management-offline-1.1.0-rc12.zip
service-management-offline-1.1.0-rc12.zip.sha256
```

Create this folder:

```text
D:\AfaqySetup\1.1.0-rc12
```

Extract the RC12 ZIP into that folder.

## 5. Install RC12

1. Open `D:\AfaqySetup\1.1.0-rc12`.
2. Right-click `Setup-ServiceManagement.cmd` and select **Run as
   administrator**.
3. Select **New installation**.
4. Follow the installer prompts.
5. Use `D:\ServiceManagement` as the installation folder.
6. Enter the application port you want to use.
7. Complete the installation.

## 6. Verify the installation

1. Open the Afaqy Service Management Console.
2. Confirm the Windows service status is **Running**.
3. Click **Open application**.
4. Create the first Administrator when the installer or setup flow requests it.
5. Log in and confirm that the dashboard opens.

Keep the RC12 ZIP and checksum file in a safe location for future repair or
reinstallation.
