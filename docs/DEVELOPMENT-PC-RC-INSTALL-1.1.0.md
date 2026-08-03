# Development PC installation test — 1.1.0-rc3

Follow this guide after restarting the development PC. This is a disposable
release-candidate test, not the production installation.

## 1. Confirm port 8993 is free

Open PowerShell and run:

```powershell
Get-NetTCPConnection -LocalPort 8993 -State Listen -ErrorAction SilentlyContinue
```

The command should return nothing. If it displays a listener before installation,
stop and investigate that listener before continuing.

## 2. Prepare the installer

The release candidate consists of these two files:

```text
C:\Users\karimAi\Desktop\Islam\service-management-system\service-management-system\dist\service-management-offline-1.1.0-rc3.zip
C:\Users\karimAi\Desktop\Islam\service-management-system\service-management-system\dist\service-management-offline-1.1.0-rc3.zip.sha256
```

Create this temporary folder:

```text
D:\AfaqySetup
```

Copy both files into it.

## 3. Verify the ZIP

Open PowerShell and run:

```powershell
Set-Location D:\AfaqySetup

$expected = ((Get-Content `
  .\service-management-offline-1.1.0-rc3.zip.sha256) -split '\s+')[0]

$actual = (Get-FileHash `
  .\service-management-offline-1.1.0-rc3.zip `
  -Algorithm SHA256).Hash

$actual -eq $expected
```

The result must be:

```text
True
```

If it says `False`, do not continue.

## 4. Extract the installer

Right-click the ZIP and select **Extract All**.

Extract it into:

```text
D:\AfaqySetup\1.1.0-rc3
```

Do not run setup from inside the ZIP viewer.

Do not extract RC3 over an old RC1 or RC2 folder. Use the new `1.1.0-rc3` folder
so Windows cannot mix files from different verified bundles.

## 5. Start setup

Inside the extracted folder, double-click:

```text
Setup-ServiceManagement.cmd
```

Then:

1. Approve the Windows Administrator prompt.
2. If SmartScreen appears, select **More info → Run anyway**.
3. Wait for the graphical Afaqy Setup window.

## 6. Enter the installation options

Select:

```text
Action:              New installation
Installation folder: D:\ServiceManagement
Application port:    8993
```

Choose **New installation** again. RC2 successfully created and verified the
isolated database and role but stopped before creating the application folder.
RC3 will safely resume from the saved `database_created` stage and will not try
to recreate the database.

Do not use `C:\ServiceManagement`; it already contains preserved backup data.

Click **Next**.

## 7. Enter the PostgreSQL information

Enter:

```text
Server:                    127.0.0.1
Port:                      5432
Postgres administrator:    postgres
Postgres password:         Your existing postgres password

Application database:      service_management_rc1
Application database user: service_management_rc1
Application DB password:   Create a new strong test password
Confirm DB password:       Enter the same password again
```

The PostgreSQL Administrator password is the password selected when PostgreSQL
was installed.

PostgreSQL is already installed on this development PC, so its separate vendor
installation window should not appear.

Click **Next**.

## 8. Create the first application Administrator

Enter:

```text
Full name:        RC Test Administrator
Username:         admin.rc1
Password:         Create a strong password
Confirm password: Enter the same password again
```

The password must contain at least eight characters.

Click **Next**.

## 9. Install

Review the summary and click **Install**.

Do not close the window while setup is working. Setup will:

1. verify the package and vendor executables;
2. create the test PostgreSQL role and database;
3. configure `D:\ServiceManagement`;
4. install Python dependencies;
5. apply Alembic migrations;
6. install the Windows service;
7. create the first application Administrator; and
8. create the Desktop and Start-menu shortcuts.

When setup reports that installation completed, click **Close**.

## 10. Test the application

Open:

```text
http://localhost:8993
```

Log in using:

```text
Username: admin.rc1
Password: The application Administrator password entered during setup
```

Confirm that the dashboard opens.

## 11. Test the Service Console

Open **Service Management Console** from the Desktop and approve UAC.

On the **Service** tab:

1. Confirm that the service shows **Running**.
2. Run the health check.
3. Click **Stop** and confirm the website stops.
4. Click **Start** and confirm the website returns.
5. Click **Restart** and run the health check again.

## 12. Test changing the application port

In the Service Console:

1. Change the port from `8993` to `8994`.
2. Click **Check Port**.
3. Apply the change.
4. Open `http://localhost:8994` and confirm the application loads.
5. Change the port back to `8993`.
6. Open `http://localhost:8993` and confirm the application loads.

## 13. Test a backup

In the Service Console's **System** tab:

1. Configure this backup directory:

   ```text
   D:\ServiceManagement\backups\scheduled
   ```

2. Enable database and upload backups.
3. Run **Backup Now**.
4. Confirm the backup folder contains a matching pair:

   ```text
   service-management-YYYYMMDD-HHMMSS.dump
   uploads-YYYYMMDD-HHMMSS\
   ```

The timestamps must match.

## 14. Test automatic startup after another reboot

Restart Windows again.

After signing in:

1. Do not start the application manually.
2. Wait approximately one minute.
3. Open `http://localhost:8993`.
4. Confirm the application loads.
5. Open the Service Console and confirm the service is running.

## 15. Stop point

Do not configure a fixed LAN IP yet. First confirm that installation, login,
Service Console controls, port changes, backup creation and automatic startup
all pass.

Record any failed step and its exact error message before attempting repairs.
