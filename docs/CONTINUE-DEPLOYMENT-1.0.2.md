# Continue deployment with version 1.0.2

Use this shorter guide after the version 1.0.1 deployment stopped at the Alembic schema-version check.

Your PostgreSQL database, role, password and application `.env` are already configured. Do not create them again and do not delete `D:\ServiceManagement`.

## Step 1: Copy the corrected files

Copy these two files from the development computer to the target computer:

```text
service-management-offline-1.0.2.zip
service-management-offline-1.0.2.zip.sha256
```

Place them in:

```text
D:\Deployment\
```

## Step 2: Verify the package

Open PowerShell and run:

```powershell
Get-FileHash -LiteralPath 'D:\Deployment\service-management-offline-1.0.2.zip' -Algorithm SHA256
```

Confirm that the displayed hash is:

```text
b3b21f7c4edab7edd418a1abf55a69bf66088aa2aa1e38b4eaf856afff1ea0fa
```

Uppercase and lowercase do not matter. Stop and copy the ZIP again if the hash is different.

## Step 3: Extract version 1.0.2

1. Open `D:\Deployment` in File Explorer.
2. Right-click `service-management-offline-1.0.2.zip`.
3. Select **Extract All**.
4. Extract it into:

```text
D:\Deployment\service-management-offline-1.0.2\
```

Confirm this file exists after extraction:

```text
D:\Deployment\service-management-offline-1.0.2\Install-Offline.ps1
```

Do not extract the package inside `D:\ServiceManagement` and do not extract it over version 1.0.1.

## Step 4: Run the corrected installer

1. Search Windows for **PowerShell**.
2. Right-click **Windows PowerShell** and select **Run as administrator**.
3. Run these commands one at a time:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
Set-Location 'D:\Deployment\service-management-offline-1.0.2'
.\Install-Offline.ps1 -InstallRoot 'D:\ServiceManagement' -Port 8993
```

Messages saying that Python, PostgreSQL, directories, the virtual environment, `.env`, or the Windows service already exist are expected.

## Step 5: Type READY

When the installer displays:

```text
Type READY after the application role and database exist
```

type:

```text
READY
```

Then press Enter.

The database is already migrated. Alembic may display informational messages without running new upgrade steps. This is expected.

## Step 6: Create the first Administrator

When prompted, enter:

1. The Administrator's full name.
2. The Administrator username.
3. A password containing at least 8 characters.
4. The same password again.

The password does not appear while you type. This is normal.

## Step 7: Wait for completion

Wait until PowerShell displays:

```text
Offline installation completed.
```

Do not close PowerShell before this message appears.

## Step 8: Open the application

On the target computer, open a browser and visit:

```text
http://localhost:8993
```

Log in using the Administrator account created in Step 6.

## Step 9: Confirm the Windows service if needed

If the website does not open, run this command in Administrator PowerShell:

```powershell
Get-Service -Name 'ServiceManagementSystem'
```

The expected status is:

```text
Running
```

If it is not running, copy the complete PowerShell output before changing or deleting anything. Remove any visible password before sharing the output.

## Step 10: Clean up old deployment files

Only after version 1.0.2 works and you can log in, you may delete these temporary deployment files:

```text
D:\Deployment\service-management-offline-1.0.0\
D:\Deployment\service-management-offline-1.0.1\
```

Do not delete:

```text
D:\ServiceManagement\
```
