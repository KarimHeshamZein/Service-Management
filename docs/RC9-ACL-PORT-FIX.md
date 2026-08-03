# Install RC9 and verify Console port changes

RC9 fixes Windows ACL verification for protected `.env` updates. PowerShell
returns a file owner as text; RC9 converts that account text to a Windows SID
before checking the exact protected permissions.

This repair preserves the PostgreSQL database, users, records, photos, backups,
passwords, fixed LAN address and all other machine settings.

## Install RC9

1. Confirm the application has been recovered on
   `http://127.0.0.1:8997`. If necessary, click **Start** in the current Service
   Console first.
2. Close the Service Management Console.
3. Copy `service-management-offline-1.1.0-rc9.zip` and its `.sha256` file to
   `D:\AfaqySetup`.
4. Extract the ZIP into a new `D:\AfaqySetup\1.1.0-rc9` folder.
5. Double-click `Setup-ServiceManagement.cmd` and approve UAC.
6. Select **Repair existing installation**.
7. Enter installation folder `D:\ServiceManagement` and application port
   `8997`.
8. Complete Repair and reopen the Service Console.

## Verify the port change

1. On the **Service** tab, enter `8995` under **Application port**.
2. Click **Check port**.
3. If available, click **Apply port** and wait for the health check.
4. Confirm **Open application** opens `http://127.0.0.1:8995`.
5. Change back to `8997` using the same controls if desired.

Use the Network tab only when adapter, fixed-IP, gateway, DNS or public-access
settings also need to change.

