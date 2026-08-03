# Repair port management — 1.1.0-rc5

Use this repair when the application is installed in `D:\ServiceManagement`
and currently opens on port `8997`. Repair preserves the PostgreSQL database,
accounts, records, uploaded photos, backups and existing configuration.

## Install the repair

1. Copy `service-management-offline-1.1.0-rc5.zip` and its `.sha256` file into
   `D:\AfaqySetup`.
2. Extract the ZIP into a new `1.1.0-rc5` folder. Do not extract over an older
   release-candidate folder.
3. Double-click `Setup-ServiceManagement.cmd` and approve UAC.
4. Select **Repair existing installation**.
5. Enter `D:\ServiceManagement` as the installation folder and `8997` as the
   application port.
6. Complete the repair.

## Verify the repair

1. Open **Service Management Console** and approve UAC.
2. Confirm **Open application** opens `http://127.0.0.1:8997`.
3. On the Service tab, enter an unused test port and click **Check port**.
4. Click **Apply port** and allow up to 30 seconds for the health check.
5. Confirm **Open application** uses the new port.
6. Change the application back to port `8997` and verify it again.

The application listens on `0.0.0.0`; it does not claim an adapter address.
Windows owns and assigns each LAN address, and the application becomes reachable
on it when the network interface is ready.

