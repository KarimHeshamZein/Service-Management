# First deployment guide

This is the technician guide for the first installation on a normal Windows
computer. The target may be offline.

## Before you begin

Prepare three strong passwords:

1. **PostgreSQL Administrator password** for the local `postgres` database
   account.
2. **Application database password** for the restricted `service_management`
   account that setup creates.
3. **Application Administrator password** for the first website login.

These are different accounts. Store all three passwords securely. Do not use
development passwords such as `admin123` in production.

## Install

1. Copy `service-management-offline-<version>.zip` to the Windows computer.
2. Right-click the ZIP, choose **Extract All**, and open the extracted folder.
3. Double-click `Setup-ServiceManagement.cmd`.
4. Select **Yes** in the Windows Administrator prompt.
5. Keep **New installation** selected.
6. Choose the installation folder, normally `C:\ServiceManagement`.
7. Choose the application port, normally `8993`, then click **Next**.
8. Enter the PostgreSQL server and passwords. For a local database, keep
   `127.0.0.1`, port `5432`, administrator `postgres`, database
   `service_management`, and database user `service_management`.
9. Enter the first application Administrator’s name, username and password.
10. Review the summary and click **Install**.

Setup checks the package before it runs anything. Missing .NET and Python are
installed automatically. If PostgreSQL is missing, its official setup window
opens:

- keep the default installation and data folders;
- keep PostgreSQL Server, pgAdmin and Command Line Tools;
- enter the same postgres password used in the Afaqy wizard;
- use the same port, normally `5432`;
- leave the locale at its default; and
- clear **Launch Stack Builder** at the end.

Return to the Afaqy window after PostgreSQL finishes. The remaining work is
automatic: database creation, migrations, Windows service registration,
Administrator creation and shortcuts.

## Verify the installation

1. Open `http://localhost:8993` (replace `8993` if you selected another port).
2. Log in with the Administrator created in setup.
3. Confirm Projects, Sites, Devices, Users, data entry, Records and Reports open.
4. Open **Service Management Console** from the Desktop.
5. On **Service**, confirm the service is running and the health check succeeds.
6. On **System**, configure and run a backup.

## Configure LAN or public access

Open the Desktop **Service Management Console** shortcut and approve UAC.

- **Service** changes the single application port and tests the application.
- **Network** selects the LAN adapter, DHCP/fixed address, local/public address
  and allowed remote networks. Applying a fixed address can disconnect Remote
  Desktop, so keep console access available.
- **Database** tests and saves PostgreSQL connection changes.
- **System** manages scheduled backups, logs, diagnostics and updates.

The application listens on `0.0.0.0` using one port. Windows Firewall restricts
which local address and remote network may reach it. There is no Windows
`portproxy`, so an address assigned after boot works without restarting a proxy.
Public access remains HTTP:

```text
http://PUBLIC_IP:APP_PORT
http://LAN_IP:APP_PORT
```

## Repair or resume

If installation is interrupted, run `Setup-ServiceManagement.cmd` again with
the same values. Setup resumes from its last safe completed stage. For an
already completed installation, select **Repair existing installation**. Repair
checks prerequisites, reinstalls dependencies, verifies migrations, recreates
shortcuts and restarts the service.

Setup state and its redacted log are stored outside the verified bundle at:

```text
C:\ProgramData\ServiceManagementSystem\Installer\
```

## Uninstall

Open **Afaqy → Uninstall Service Management** from the Start menu. Normal
uninstall removes the service and application code but preserves PostgreSQL,
uploads, backups, `.env` and machine configuration.

Permanent removal is deliberately not in the shortcut. An Administrator must
run the installed uninstaller with `-RemovePersistentData` and type the exact
confirmation shown. PostgreSQL software itself remains installed.

## Restore drill

Follow [PRODUCTION_UPDATES.md](PRODUCTION_UPDATES.md#restore-a-backup-pair). Test
the restore procedure before production use and after changing backup storage.
