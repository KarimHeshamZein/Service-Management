# Install the RC6 repair

RC6 corrects Repair mode so a newer bundled application release replaces the
older installed release. The repair preserves the PostgreSQL database, users,
records, photos, backups, passwords and machine configuration.

## Steps

1. Close the Service Management Console.
2. Copy `service-management-offline-1.1.0-rc6.zip` and its `.sha256` file to
   `D:\AfaqySetup`.
3. Extract the ZIP into a new `D:\AfaqySetup\1.1.0-rc6` folder.
4. Double-click `Setup-ServiceManagement.cmd` and approve UAC.
5. Select **Repair existing installation**.
6. Enter `D:\ServiceManagement` as the installation folder and `8997` as the
   application port.
7. Complete the repair and close Setup.
8. Reopen **Service Management Console**.

## Verify

1. The Network tab must show application port `8997`.
2. **Open application** must open `http://127.0.0.1:8997`.
3. Use **Check port** before testing a different port.
4. Apply an unused test port, wait for the health check, and then change back to
   `8997`.

Repair creates a deployment backup before changing the installed release. It
does not create another Administrator or application database.

