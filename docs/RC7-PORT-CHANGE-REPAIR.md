# Install the RC7 port-change repair

RC7 fixes the Service Console's **Apply port** workflow. It preserves the
database, accounts, records, photos, backups, passwords and network settings.

## Install

1. If the service is stopped, click **Start** in the current Console and verify
   `http://127.0.0.1:8997` opens.
2. Close the Service Management Console.
3. Copy `service-management-offline-1.1.0-rc7.zip` and its `.sha256` file to
   `D:\AfaqySetup`.
4. Extract the ZIP into a new `D:\AfaqySetup\1.1.0-rc7` folder.
5. Double-click `Setup-ServiceManagement.cmd` and approve UAC.
6. Select **Repair existing installation**.
7. Enter `D:\ServiceManagement` and application port `8997`.
8. Complete Repair and reopen the Service Console.

## Test the port change

1. On the Service tab, enter `8995` and click **Check port**.
2. If the port is available, click **Apply port**.
3. Wait for Windows service startup and the HTTP health check to finish.
4. Confirm **Open application** opens `http://127.0.0.1:8995`.
5. Repeat the process to change back to `8997` if that is the desired production
   port.

The corrected workflow explicitly stops the Windows service, waits for the
Stopped state, starts it, waits for the Running state, and then verifies the new
HTTP endpoint.

