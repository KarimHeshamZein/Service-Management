# Install RC10 and verify the Console port change

RC10 corrects the final Windows ACL rights comparison used when the Service
Console updates the protected production `.env`. Windows stores a Read allow
rule with the Synchronize bit included (`0x120089`); RC10 verifies that exact
normalized value.

Repair preserves the PostgreSQL database, users, records, photos, backups,
passwords, fixed LAN address and other machine settings.

## Install RC10

1. Recover the current service on `http://127.0.0.1:8997` by clicking **Start**
   if necessary.
2. Close the Service Management Console.
3. Copy `service-management-offline-1.1.0-rc10.zip` and its `.sha256` file to
   `D:\AfaqySetup`.
4. Extract the ZIP into a new `D:\AfaqySetup\1.1.0-rc10` folder.
5. Double-click `Setup-ServiceManagement.cmd` and approve UAC.
6. Select **Repair existing installation**.
7. Enter `D:\ServiceManagement` and application port `8997`.
8. Complete Repair and reopen the Service Console.

## Verify

1. On the **Service** tab, enter application port `8995`.
2. Click **Check port**.
3. If available, click **Apply port**.
4. Confirm **Open application** opens `http://127.0.0.1:8995`.
5. Change back to `8997` the same way if desired.

Do not use the Network tab for a port-only change because it also reapplies
adapter, fixed-IP, gateway, DNS and firewall settings.

