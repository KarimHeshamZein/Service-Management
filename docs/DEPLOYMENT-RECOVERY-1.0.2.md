# Deployment recovery guide for version 1.0.2

Use this guide on the target Windows computer after the version 1.0.0 installation stopped during database migrations.

The failed installation did not damage the database. Keep `D:\ServiceManagement` and continue with the corrected version 1.0.2 package.

## Before you begin

You need:

- Windows Administrator access to the target computer.
- Access to pgAdmin on the target computer.
- The corrected `service-management-offline-1.0.2.zip` package.
- The `service-management-offline-1.0.2.zip.sha256` checksum file.

Do not:

- Run the old version 1.0.0 installer again.
- Delete `D:\ServiceManagement`.
- Share the PostgreSQL password with anyone.

## Step 1: Copy version 1.0.2 to the target computer

From the development computer, copy these two files to the target computer:

```text
service-management-offline-1.0.2.zip
service-management-offline-1.0.2.zip.sha256
```

For example, place them in:

```text
C:\Deployment\
```

## Step 2: Verify the package checksum

1. Open PowerShell on the target computer.
2. Run:

```powershell
Get-FileHash -LiteralPath 'C:\Deployment\service-management-offline-1.0.2.zip' -Algorithm SHA256
```

3. Confirm that the displayed hash is exactly:

```text
b3b21f7c4edab7edd418a1abf55a69bf66088aa2aa1e38b4eaf856afff1ea0fa
```

Uppercase and lowercase letters do not matter.

Stop if the hash is different. Copy the package again before continuing.

## Step 3: Change the exposed PostgreSQL password

The previous PostgreSQL password appeared in the installation error. Replace it before continuing.

1. Open **pgAdmin**.
2. Connect to the PostgreSQL server.
3. Expand **Servers**.
4. Expand **PostgreSQL 16**.
5. Expand **Login/Group Roles**.
6. Right-click `service_management`.
7. Select **Properties**.
8. Open the **Definition** tab.
9. Enter the new password in **Password** and **Confirm password**.
10. Click **Save**.

For this recovery, use a unique random password containing at least 24 letters and numbers. Do not use spaces or symbols. This avoids URL-encoding mistakes while still providing a strong password.

Keep the new password available temporarily. You need it in the next step.

## Step 4: Update the application database password

1. Search Windows for **Notepad**.
2. Right-click **Notepad** and select **Run as administrator**.
3. In Notepad, select **File → Open**.
4. Open:

```text
D:\ServiceManagement\shared\.env
```

You may need to change the file filter from **Text Documents** to **All Files**.

5. Find the line beginning with `DATABASE_URL=`.
6. Replace that whole line with the following, inserting the new password:

```dotenv
DATABASE_URL=postgresql://service_management:YOUR_NEW_PASSWORD@localhost:5432/service_management
```

Example structure only:

```text
postgresql://username:password@server:port/database
```

Do not change `SECRET_KEY` or any other setting.

7. Save the file and close Notepad.

## Step 5: Extract version 1.0.2

1. In File Explorer, open `C:\Deployment`.
2. Right-click `service-management-offline-1.0.2.zip`.
3. Select **Extract All**.
4. Extract it into a new folder such as:

```text
C:\Deployment\service-management-offline-1.0.2\
```

Do not extract it over the old version 1.0.0 folder.

After extraction, confirm this file exists:

```text
C:\Deployment\service-management-offline-1.0.2\Install-Offline.ps1
```

## Step 6: Run the corrected installer

1. Search Windows for **PowerShell**.
2. Right-click **Windows PowerShell** and select **Run as administrator**.
3. Run these commands one at a time:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
Set-Location 'C:\Deployment\service-management-offline-1.0.2'
.\Install-Offline.ps1 -InstallRoot 'D:\ServiceManagement' -Port 8993
```

The installer will detect and reuse the components installed during the first attempt. It may report that Python, PostgreSQL, directories, the virtual environment, configuration, or Windows service already exist. This is expected.

## Step 7: Confirm the database exists

The installer will display:

```text
Type READY after the application role and database exist
```

Type:

```text
READY
```

Then press Enter.

The installer will verify PostgreSQL, install the corrected release, run the database migrations, and start the Windows service.

## Step 8: Create the first Administrator

Near the end, the installer will ask for the first Administrator account.

Enter:

1. The Administrator's full name.
2. The Administrator username.
3. A password containing at least 8 characters.
4. The same password again when asked to confirm it.

The password will not appear while you type. This is normal.

Store this Administrator password securely.

## Step 9: Confirm installation completed

Wait for this message:

```text
Offline installation completed.
```

Do not close PowerShell while the installer is still working.

## Step 10: Test the application on the target computer

Open a browser on the target computer and visit:

```text
http://localhost:8993
```

Log in using the Administrator account created in Step 8.

Confirm that:

- The login succeeds.
- The dashboard opens.
- The Settings tab is visible.
- The Users tab is visible.

## Step 11: Test the Windows service

If the website does not open:

1. Press `Windows + R`.
2. Enter `services.msc`.
3. Press Enter.
4. Find **ServiceManagementSystem**.
5. Confirm its status is **Running**.

You can also check it from an Administrator PowerShell window:

```powershell
Get-Service -Name 'ServiceManagementSystem'
```

The expected status is:

```text
Running
```

## Step 12: Test access from another computer

After local access works, open a browser on another computer on the same network and visit:

```text
http://TARGET_COMPUTER_IP:8993
```

Replace `TARGET_COMPUTER_IP` with the target computer's LAN address.

To display the LAN addresses on the target computer, run:

```powershell
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' }
```

Configure the Windows Firewall and deployment network settings if remote access does not work while `http://localhost:8993` does work.

## If the corrected installer stops again

Do not delete the installation directory or PostgreSQL database.

Copy the complete red PowerShell error text and record which step failed. Passwords can appear inside database URLs, so remove or cover any password before sharing the output.
