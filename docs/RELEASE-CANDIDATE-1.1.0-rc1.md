# Release candidate 1.1.0-rc1 acceptance

## Package

```text
dist\service-management-offline-1.1.0-rc1.zip
dist\service-management-offline-1.1.0-rc1.zip.sha256
SHA-256: 8e831118e370b91db520869f7542cef6d7329c716ec594531d8c326407b12c9f
Alembic head: a6d1e7c93b52
```

The outer SHA-256, all 58 internal manifest entries and the nested release were
verified on 2026-08-03. The nested release contains no `.env`, tests, development
database, uploads or temporary files. Vendor metadata records valid signatures
for Python, PostgreSQL and .NET Framework. WinSW is unsigned and is protected by
the verified package hashes.

## Automated acceptance completed

- [x] Full suite after networking and environment work: 260 passed.
- [x] Full suite after config core: 277 passed.
- [x] Full suite after Service Console: 285 passed.
- [x] Full suite after read-only Web Settings: 285 passed.
- [x] Full suite after wizard/repair/uninstall: 288 passed.
- [x] Full suite after restore/docs: 290 passed.
- [x] All deployment PowerShell files parse.
- [x] Graphical launcher, repair, safe uninstall, restore and Service Console
  shortcuts are packaged.
- [x] Development `python run.py` process on port 8993 was stopped.

## Development-PC installation

Windows retained a stale `0.0.0.0:8993` listener for terminated PID `29892`.
The PID no longer exists in `Get-Process` or `tasklist`. Restart Windows before
the installation test so the stale kernel listener is cleared.

`C:\ServiceManagement` already contains an unrelated/preserved `backups` folder,
so the new installer correctly treats it as an unknown non-empty destination.
Use the currently empty `D:\ServiceManagement` for this disposable test.

The development PostgreSQL server already contains `service_management`,
`service_management_test` and `service_management_migrations_test`. To avoid any
development data, enter these test-only names in the wizard:

```text
Installation folder:       D:\ServiceManagement
Application port:          8993
Application database:      service_management_rc1
Application database user: service_management_rc1
Administrator username:    admin.rc1
```

Use new strong passwords. Do not reuse production credentials.

## Hands-on acceptance still required

These checks require UAC, interactive passwords, real Windows networking or a
reboot and therefore must be completed at the computer:

- [ ] Restart Windows and confirm port 8993 is free.
- [ ] Extract the RC ZIP and double-click `Setup-ServiceManagement.cmd`.
- [ ] Complete New installation with the disposable values above.
- [ ] Log in and reach `/dashboard` as `admin.rc1`.
- [ ] Service Console: stop, start, restart, health check and recent logs.
- [ ] Change to a free port and back; verify health after each change.
- [ ] Test database connection without saving a wrong candidate.
- [ ] Run a backup and verify the matching dump/upload snapshot.
- [ ] Run the documented restore drill with disposable data.
- [ ] Apply a fixed IP only on a safe adapter or VM; test rollback.
- [ ] Restart Windows; confirm automatic delayed service startup and LAN access.
- [ ] Install a test update through the Service Console and verify users,
  database, uploads and settings survive.
- [ ] Search logs and exported diagnostics for the test passwords and confirm no
  occurrence.

Do not rename this RC as the final production package until every hands-on item
passes. Do not install it on the production target first.
