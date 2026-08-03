# Repair the Service Console and configure backups — 1.1.0-rc4

Use this guide on the development computer where the application is already
installed in `D:\ServiceManagement` and opens on port `8997`. Repair preserves
the PostgreSQL database, uploads, configuration, accounts and passwords.

## 1. Prepare RC4

Copy these two files into `D:\AfaqySetup`:

```text
service-management-offline-1.1.0-rc4.zip
service-management-offline-1.1.0-rc4.zip.sha256
```

Extract the ZIP into a new folder:

```text
D:\AfaqySetup\service-management-offline-1.1.0-rc4
```

Do not extract it over the RC3 folder and do not delete `D:\ServiceManagement`.

## 2. Run Repair

Open the extracted RC4 folder and double-click:

```text
Setup-ServiceManagement.cmd
```

Approve the Windows Administrator prompt. In the setup window select:

```text
Action:              Repair existing installation
Installation folder: D:\ServiceManagement
Application port:    8997
```

Continue through the wizard and click **Install**. Repair uses the existing
database connection and Administrator account; it does not ask you to recreate
them.

## 3. Test the shortcut

Double-click **Service Management Console** on the Desktop and approve UAC. No
PowerShell command is required. Confirm the Console opens and the Service tab
shows the service as running.

## 4. Enable automatic backups

Open the Console's **System** tab. Under **Automatic backups**:

1. Tick **Enable scheduled backups**.
2. Enter how often to run it, such as `1` day.
3. Enter how many database backups to retain, such as `30`.
4. Keep **Include photo uploads** ticked.
5. Enter how many photo snapshots to retain, such as `7`.
6. Set the backup folder to `D:\ServiceManagement\backups\scheduled`.
7. Use **Browse...** beside `pg_dump.exe` and select the installed PostgreSQL
   backup tool, normally
   `C:\Program Files\PostgreSQL\16\bin\pg_dump.exe`.
8. Click **Save and install schedule**.
9. Click **Run Backup Now** once to create and verify the first backup.

Refresh the application's Administrator Settings page. It should report the
latest backup instead of saying automatic backups are disabled.

