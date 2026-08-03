# Service Console manual verification

Run this checklist on an elevated disposable Windows installation after the
automated test suite passes.

1. Open the Desktop shortcut. Approve UAC and confirm a second console instance
   is refused.
2. On **Service**, start, stop and restart the service. Check port availability,
   change to a free port, verify the health check and open the application.
3. Confirm recent logs are readable and contain no database URL, password or
   secret key.
4. On **Network**, select the safe test adapter. Test the profile. Apply only
   with console access available because Remote Desktop may disconnect. Verify
   the exact local/public firewall rules, then exercise rollback.
5. On **Database**, test a deliberately invalid candidate and confirm nothing
   changes. Test the real candidate, save it and verify application health.
6. On **System**, review version, firewall and backup state. Run a backup, update
   the backup schedule and export diagnostics. Confirm diagnostics are redacted.
7. Select a release ZIP and its SHA-256 manifest. Confirm a wrong checksum is
   refused, then install a verified update through `Deploy-Release.ps1`.
8. Restart Windows and confirm delayed automatic service startup and LAN access.
