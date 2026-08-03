# Offline installation quick guide

Use this package on 64-bit Windows 10/11 Pro or Enterprise, or Windows Server
2016 or newer. Internet access is not required.

1. Copy `service-management-offline-<version>.zip` to the target computer.
2. Extract the complete ZIP to a temporary folder. Do not run it inside the ZIP
   viewer.
3. Double-click `Setup-ServiceManagement.cmd`.
4. Approve the Windows Administrator prompt.
5. Follow **Next → Next → Install**.

Setup verifies every bundled checksum and checks each vendor executable against
the Authenticode details recorded in `bundle.json`. It installs missing .NET,
Python, PostgreSQL and WinSW components. Python is silent; the official
PostgreSQL window remains visible so its administrator password never appears in
a process command line. If that window appears, use the same postgres password
and port entered in the Afaqy setup wizard. Do not install Stack Builder.

The wizard then creates the application database, applies Alembic migrations,
creates the first Administrator, installs the automatic Windows service, and
adds **Service Management Console** shortcuts to the Desktop and Start menu.
Passwords are held only in memory and sent to the Python bootstrap process over
standard input. They are never written to setup state or logs.

Setup progress and resumable state are stored under:

```text
C:\ProgramData\ServiceManagementSystem\Installer\
```

If setup is interrupted, run the same CMD file again and enter the same values.
Choose **Repair existing installation** for a completed installation. Setup
refuses an unknown non-empty destination folder.

After installation, open `http://localhost:<port>`. Use the local elevated
Service Console—not the website—to change the application port, LAN/public
firewall profile, fixed adapter address, PostgreSQL connection or backup task.
The website Settings page is status-only.

Public access is HTTP and is not encrypted. Restrict allowed remote networks and
prefer a VPN until real HTTPS termination is deployed.
