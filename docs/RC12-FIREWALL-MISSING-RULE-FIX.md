# Install RC12 and verify a port-only change

RC12 fixes the remaining Windows Firewall failure during a port change. The
Console now enumerates the firewall rules that actually exist and filters that
list for its managed rules. A managed rule that has not been created yet is a
normal state and no longer makes PowerShell return an error.

Repair preserves the PostgreSQL database, users, records, photos, backups,
passwords, fixed LAN address and other machine settings.

## Install RC12

1. If the current service is stopped, open the Service Console and click
   **Start** to recover it on `http://127.0.0.1:8997`.
2. Close the Service Management Console.
3. Copy `service-management-offline-1.1.0-rc12.zip` and its `.sha256` file to
   `D:\AfaqySetup`.
4. Extract the ZIP into a new `D:\AfaqySetup\1.1.0-rc12` folder.
5. Double-click `Setup-ServiceManagement.cmd` and approve UAC.
6. Select **Repair existing installation**.
7. Enter `D:\ServiceManagement` and application port `8997`.
8. Complete Repair and reopen the Service Console.

## Verify

1. On the **Service** tab, enter application port `8995`.
2. Click **Check port**.
3. If the port is available, click **Apply port**.
4. Confirm the service status returns to **Running**.
5. Confirm **Open application** opens `http://127.0.0.1:8995`.
6. Change back to `8997` with the same Service-tab controls if desired.

Do not use the Network tab for a port-only change because it also reapplies
adapter, fixed-IP, gateway, DNS and firewall settings.
