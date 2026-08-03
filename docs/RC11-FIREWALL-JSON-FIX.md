# Install RC11 and verify a port-only change

RC11 fixes Windows PowerShell 5.1 decoding when no managed firewall rules are
configured. The Console now sends a stable object containing a `rules` property,
so zero, one and multiple rules retain their exact counts on supported Windows
computers.

Repair preserves the PostgreSQL database, users, records, photos, backups,
passwords, fixed LAN address and other machine settings.

## Install RC11

1. Recover the current service on `http://127.0.0.1:8997` by clicking **Start**
   if necessary.
2. Close the Service Management Console.
3. Copy `service-management-offline-1.1.0-rc11.zip` and its `.sha256` file to
   `D:\AfaqySetup`.
4. Extract the ZIP into a new `D:\AfaqySetup\1.1.0-rc11` folder.
5. Double-click `Setup-ServiceManagement.cmd` and approve UAC.
6. Select **Repair existing installation**.
7. Enter `D:\ServiceManagement` and application port `8997`.
8. Complete Repair and reopen the Service Console.

## Verify

1. On the **Service** tab, enter application port `8995`.
2. Click **Check port**.
3. If available, click **Apply port**.
4. Confirm **Open application** opens `http://127.0.0.1:8995`.
5. Change back to `8997` through the same Service-tab controls if desired.

Do not use the Network tab for a port-only change because it also reapplies
adapter, fixed-IP, gateway, DNS and firewall settings.

