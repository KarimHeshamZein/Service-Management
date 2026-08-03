# Production installation, updates and recovery

Production keeps configuration, uploads, backups and PostgreSQL data outside
versioned application releases. Installing a new release does not replace them.

## First installation

Use the offline graphical package described in
[FIRST_DEPLOYMENT_GUIDE.md](FIRST_DEPLOYMENT_GUIDE.md): extract the ZIP,
double-click `Setup-ServiceManagement.cmd`, approve UAC, and follow the wizard.
The wizard creates the PostgreSQL role/database and first Administrator. It is no
longer necessary to edit `.env`, type `READY`, run Alembic, create a service or
download scripts from the website.

The production layout is:

```text
C:\ServiceManagement\
|-- .venv\
|-- current\                 Junction to the active release
|-- releases\
|-- shared\
|   |-- .env                 Authoritative protected environment
|   |-- machine-settings.json
|   |-- runtime-temp\
|   `-- uploads\
|-- backups\
|-- logs\
|-- ServiceManagementSystem.exe
|-- ServiceManagementSystem.xml
|-- Uninstall-ServiceManagement.ps1
`-- deployment.json
```

WinSW runs `serve.py` as `NT AUTHORITY\LocalService`, supplies the absolute
`SMS_ENV_FILE`, and starts automatically with delayed-start recovery. Uvicorn
binds `0.0.0.0:APP_PORT`; exact local-address and remote-network firewall rules
provide the network boundary. No `portproxy` or `iphlpsvc` dependency exists.

```text
Executable:        C:\ServiceManagement\.venv\Scripts\python.exe
Arguments:         serve.py
Working directory: C:\ServiceManagement\current
Service account:   NT AUTHORITY\LocalService
SMS_ENV_FILE=C:\ServiceManagement\shared\.env
```

The production launcher listens on `0.0.0.0` using `APP_PORT` from that protected
environment file.

## Local Service Console

Open **Service Management Console** from the Desktop or Start menu and approve
UAC. It is the only supported machine-settings writer:

- service start/stop/restart, port changes and health checks;
- DHCP/fixed LAN settings and IP-scoped firewall profiles;
- tested PostgreSQL connection changes;
- backup scheduling and immediate backups;
- redacted diagnostics; and
- verified release updates.

The web `/settings` page is Administrator-only, sanitized and read-only. It
shows runtime/network/database/backup status and the preserved legacy audit; it
does not apply Windows changes or generate privileged scripts.

## Release updates

Build the application ZIP on the development computer:

```powershell
.\scripts\New-ReleasePackage.ps1 -Version 1.1.0
```

Copy both the release ZIP and its SHA-256 value to the server. In the Service
Console, open **System → Install update package**, select the ZIP and checksum,
then install. The console verifies SHA-256 and invokes `Deploy-Release.ps1`; it
does not reproduce deployment logic.

The deployment script:

1. validates the release and persistent configuration;
2. stops the service;
3. creates a PostgreSQL and upload safety backup;
4. installs requirements;
5. runs `alembic upgrade head`;
6. switches the `current` junction;
7. starts the service and checks `/login`; and
8. records the version, backup and schema in `deployment.json`.

If application startup fails, it restores the previous code junction. It never
automatically downgrades PostgreSQL. After every update, verify login, data entry,
record search, photos, PDFs, backup status and LAN access.

## Application rollback

Application rollback changes code only:

```powershell
.\scripts\Rollback-Release.ps1 `
  -Version 1.0.0 `
  -InstallRoot C:\ServiceManagement `
  -ServiceName ServiceManagementSystem
```

It does not downgrade the database. Releases intended for rollback must retain
database compatibility through additive Alembic migrations.

## Scheduled backups

Configure scheduled backups from the local Service Console. Each successful run
writes a PostgreSQL custom-format dump followed by the same-timestamp upload
snapshot:

```text
service-management-20260803-020000.dump
uploads-20260803-020000\
```

Snapshots iterate the current upload source. A file removed from production is
not resurrected into the next snapshot; older snapshots retain their historical
copy. Unchanged immutable UUID files use NTFS hardlinks to the previous snapshot,
and new files or hardlink failures use copies. Pruning occurs only after the new
dump and snapshot verify successfully.

Copying a hardlink snapshot off the server with a tool that does not preserve
hardlinks creates an independent full-size copy. This is expected. Keep the dump
and its matching `uploads-` folder together.

## Restore a backup pair

Restoration replaces production evidence and requires explicit approval. First
copy the matching dump and upload folder onto a local or trusted backup volume.
Then open Windows PowerShell as Administrator:

```powershell
Set-Location C:\ServiceManagement\current

.\scripts\Restore-Backup.ps1 `
  -DumpPath 'E:\SMS-Backups\service-management-20260803-020000.dump' `
  -UploadsSnapshot 'E:\SMS-Backups\uploads-20260803-020000' `
  -InstallRoot 'C:\ServiceManagement'
```

The tool performs all non-destructive checks before stopping the service:

- `pg_restore --list` proves the custom dump is readable;
- dump/snapshot timestamps must match;
- upload snapshots may not contain reparse points; and
- the backup Alembic revision must exactly equal the installed revision.

The exact-version requirement prevents an accidental schema downgrade. If the
revisions differ, deploy the matching application version and plan a controlled
migration; do not bypass the guard.

After verification, type `RESTORE SERVICE MANAGEMENT`. The tool stops the
service, creates a fresh pre-restore safety dump, restores PostgreSQL, stages and
swaps the uploads directory, starts the service and checks `/login`. On failure
it attempts to restore the safety dump and original uploads before restarting.

For an intentional database-only restore, omit `-UploadsSnapshot` and specify
`-DatabaseOnly`. This can leave photo references inconsistent, so use it only
when the backup was deliberately database-only and the consequences are known.

### Restore drill

Before production and at least after any backup-location change:

1. create a record with a recognizable test photo;
2. run a backup from the Service Console;
3. record the matching dump/snapshot names;
4. make a second disposable change;
5. run `Restore-Backup.ps1` with the pair;
6. confirm the first record/photo exists and the later disposable change does
   not;
7. confirm login, reports and protected media; and
8. record the drill date and safety-dump path.

## Uninstall

The Start-menu uninstaller is non-destructive: it removes the service and code
while preserving the database, uploads, backups, `.env` and machine settings.

Permanent deletion requires an elevated PowerShell session:

```powershell
C:\ServiceManagement\Uninstall-ServiceManagement.ps1 `
  -InstallRoot C:\ServiceManagement `
  -RemovePersistentData
```

It requires typing `DELETE SERVICE MANAGEMENT DATA`. If the database cannot be
removed, filesystem data is preserved. PostgreSQL server software is never
uninstalled automatically.

## Migration rules

- Commit one Alembic revision for every schema change.
- Test a clean database and an upgrade from the previous release.
- Prefer additive nullable/defaulted columns and new tables.
- Never run `seed.py` or `seed.py --reset` in production.
- Never remove old schema in the same release that stops using it.
- Verify a database/upload backup and restore drill before destructive cleanup.
