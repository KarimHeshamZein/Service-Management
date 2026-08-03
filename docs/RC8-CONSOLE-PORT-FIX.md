# Install RC8 and change the application port

RC8 makes the protected production `.env` authoritative when the Windows
service restarts. This allows the Service Console to change the application port
even when the service wrapper inherited an older `APP_PORT` value.

The repair preserves the PostgreSQL database, users, records, photos, backups,
passwords, fixed LAN address and other machine settings.

## Install RC8

1. Confirm the current application opens on `http://127.0.0.1:8997`.
2. Close the Service Management Console.
3. Copy `service-management-offline-1.1.0-rc8.zip` and its `.sha256` file to
   `D:\AfaqySetup`.
4. Extract the ZIP into a new `D:\AfaqySetup\1.1.0-rc8` folder.
5. Double-click `Setup-ServiceManagement.cmd` and approve UAC.
6. Select **Repair existing installation**.
7. Enter installation folder `D:\ServiceManagement` and application port
   `8997`.
8. Complete Repair and reopen the Service Console.

## Change the port from the Console

1. Open the **Service** tab. Do not use the Network tab for a port-only change.
2. Enter `8995` under **Application port**.
3. Click **Check port**.
4. If it is available, click **Apply port** and wait for the health check.
5. Click **Open application** and confirm it opens
   `http://127.0.0.1:8995`.
6. Repeat these steps to return to `8997` if desired.

The Network tab exposes the same application port but also reapplies adapter,
fixed-IP, gateway, DNS and firewall configuration. Use it only when those
network settings also need to change.

