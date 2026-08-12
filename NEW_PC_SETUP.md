# New PC Development Setup — Windows

Updated: 2026-08-12

For an automated setup, copy the prompt from `NEW_PC_CODEX_PROMPT.md` into the
first Codex session on the new PC. Codex will perform the steps in this guide and
pause only for required credentials, administrator approval, or an existing
database decision.

Use this guide after copying the complete folder:

`C:\Users\karimAi\Desktop\Islam\service-management-system`

to the new Windows PC. This creates a brand-new development database. It does
not move the old PC's PostgreSQL records, and it does not modify a deployed
`D:\ServiceManagement` installation.

## 1. Install the required software

Install these applications on the new PC:

1. Git for Windows
2. Python 3.11, 64-bit
3. PostgreSQL
4. Codex

For the simplest development/test setup, configure the local PostgreSQL
superuser as:

- User: `postgres`
- Password: `postgres`
- Host: `localhost`
- Port: `5432`

The automated test configuration currently expects this local development
password. Use it only on a development PC with PostgreSQL restricted to the
local machine. Do not use this password in production.

Restart Windows after installing PostgreSQL if its service does not start
automatically.

## 2. Paste and locate the repository

Paste the copied `service-management-system` folder wherever you want it on the
new PC. The copied structure currently contains an outer folder and the actual
repository inside it.

Open PowerShell and enter the inner folder—the folder containing `AGENTS.md`,
`CLAUDE.md`, `README.md`, and `requirements.txt`:

```powershell
Set-Location 'C:\Users\YOUR-NEW-USERNAME\Desktop\Islam\service-management-system\service-management-system'
Get-ChildItem AGENTS.md, CLAUDE.md, README.md, PROJECT_HANDOFF.md
```

Replace `YOUR-NEW-USERNAME` and the preceding path if you pasted the folder
somewhere else.

If all four files are displayed, you are in the correct directory.

## 3. Verify the copied Git repository

Run:

```powershell
git status --short --branch
git remote -v
git log -5 --oneline --decorate
```

The expected remote is:

`https://github.com/KarimHeshamZein/Service-Management.git`

The merged feature baseline on `main` is:

`d80aba9` (`Merge pull request #1 from feature/hierarchical-installation-reports`)

The documentation may have a newer commit. After pulling, use the current
`origin/main` tip and confirm it contains `d80aba9`.

The copied root `index.html` may appear as an untracked file. That is expected.
It is the preserved original planner source and must not be committed, edited,
or deleted.

Connect GitHub on the new PC, then synchronize safely:

```powershell
git switch main
git fetch origin
git pull --ff-only origin main
```

If Git reports local changes other than the expected untracked `index.html`,
stop and inspect them before pulling.

`main` is integration-only. Do not develop or commit directly on it. For each
approved feature, fix, or documentation task, first update `main`, then create
a descriptive task branch:

```powershell
git switch main
git fetch origin
git pull --ff-only origin main
git switch -c feature/short-description
```

Use `fix/short-description` for a bug fix or `docs/short-description` for a
documentation-only change. Commit and push that branch with
`git push -u origin <branch-name>`, then merge it through a GitHub pull request
after review and testing. Never force-push or develop directly on `main`.

## 4. Recreate the Python virtual environment

A copied `.venv` is tied to paths and software on the old PC. Do not use it.

If the copied `.venv` exists, move it to the parent folder so it remains
recoverable temporarily without appearing as an untracked repository file:

```powershell
if (Test-Path -LiteralPath '.venv') {
    Move-Item -LiteralPath '.venv' -Destination '..\.venv-from-old-pc'
}
```

Create and activate a new environment:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Verify that the project environment is active:

```powershell
python --version
python -c "import fastapi, sqlalchemy, psycopg2; print('Python dependencies are ready.')"
```

The Python version should be 3.11.x and the import command should finish
without an error.

If PowerShell blocks `Activate.ps1`, run this once in the current PowerShell
window, then activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## 5. Create three fresh PostgreSQL databases

The project uses separate databases so tests never touch development data:

1. `service_management` — the local application
2. `service_management_test` — the ordinary pytest suite
3. `service_management_migrations_test` — Alembic round-trip tests

### Recommended method: pgAdmin

1. Open pgAdmin.
2. Connect to the local PostgreSQL server.
3. Expand **Servers → PostgreSQL → Databases**.
4. Right-click **Databases** and choose **Create → Database**.
5. Create `service_management` with owner `postgres`.
6. Repeat for `service_management_test`.
7. Repeat for `service_management_migrations_test`.

### Alternative method: PostgreSQL command line

Change `16` below if a different PostgreSQL version is installed:

```powershell
& 'C:\Program Files\PostgreSQL\16\bin\createdb.exe' -U postgres -h localhost -p 5432 service_management
& 'C:\Program Files\PostgreSQL\16\bin\createdb.exe' -U postgres -h localhost -p 5432 service_management_test
& 'C:\Program Files\PostgreSQL\16\bin\createdb.exe' -U postgres -h localhost -p 5432 service_management_migrations_test
```

Enter the local PostgreSQL password when prompted.

## 6. Create a clean development `.env`

Do not rely on the copied old-PC `.env`. Move it outside the repository
temporarily, then create a fresh one:

```powershell
if (Test-Path -LiteralPath '.env') {
    Move-Item -LiteralPath '.env' -Destination '..\.env-from-old-pc'
}
Copy-Item -LiteralPath '.env.example' -Destination '.env'
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copy the generated random value. Open `.env` in a text editor and set at least:

```dotenv
SECRET_KEY=PASTE-THE-GENERATED-RANDOM-VALUE-HERE
ENVIRONMENT=development
APP_HOST=0.0.0.0
APP_PORT=8999
APP_RELOAD=true
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/service_management
UPLOAD_DIR=./data/uploads
PUBLIC_BASE_URL=http://127.0.0.1:8999
```

Leave SMTP fields empty for local development unless password-recovery email is
being tested.

Never commit `.env`. After the new setup works, securely delete the parent
folder's `.env-from-old-pc` because it may contain secrets from the previous PC.

### Optional clean upload directory

If the copied folder contains old development uploads and you want a completely
fresh environment, rename the directory before starting:

```powershell
if (Test-Path -LiteralPath 'data\uploads') {
    Rename-Item -LiteralPath 'data\uploads' -NewName 'uploads-from-old-pc'
}
```

The application will create a new upload directory when needed. Do not perform
this step if the copied images still need to be examined.

## 7. Apply the database migrations

With `.venv` activated and PostgreSQL running:

```powershell
alembic heads
alembic upgrade head
alembic current
```

The expected single migration head/current revision is:

`c8e4f2a91d73`

Do not use `Base.metadata.create_all()` or manually create application tables.
Alembic owns the normal schema.

## 8. Load fresh development sample data

Run:

```powershell
python seed.py
```

This adds development users, Projects, Sites, service types, Pricing Items, and
sample records to the new development database.

Default development logins include:

- Administrator: `admin` / `admin123`
- Technical: `omar@afaqy.local` / `Leader@12345`
- Technical: `yousef@afaqy.local` / `Leader@12345`

These accounts are for local development only.

Do not run `python seed.py --reset` unless you intentionally want to destroy the
new development database and its uploads. Never run the seed command against a
production database.

## 9. Run the automated tests

Run the complete suite before editing the application:

```powershell
python -m pytest -q
```

Test counts increase as features are added, so do not compare against the old
`356 passed` baseline. Run the complete suite and report its actual result. The
existing Starlette TestClient/httpx deprecation warning is expected. Recent
focused gates include 20 passing release-workflow tests and 11 passing
browser-entry/migration/report tests.

If tests report that `service_management_test` or
`service_management_migrations_test` does not exist, return to step 5. If they
report password authentication failure, confirm the local PostgreSQL `postgres`
password and test connection settings.

## 10. Start the development application

Run:

```powershell
python run.py
```

Open:

`http://127.0.0.1:8999`

Keep the PowerShell window open while the server is running. Press `Ctrl+C` to
stop it.

If port 8999 is already in use, change `APP_PORT` and `PUBLIC_BASE_URL` together
in `.env`, then restart the application.

## 11. Start the new Codex session

Open Codex in the repository folder and give it this prompt:

> Continue development of the Service Management System. Before doing anything,
> read AGENTS.md, CLAUDE.md, README.md, PROJECT_HANDOFF.md, and NEW_PC_SETUP.md
> completely. Run `git status --short --branch`,
> `git log -5 --oneline --decorate`, `alembic current`, and `alembic heads`.
> Treat the Current handoff in CLAUDE.md and PROJECT_HANDOFF.md as authoritative.
> Preserve .env, databases, uploads, dist artifacts, D:\ServiceManagement, and
> the unrelated root index.html. Treat main as integration-only: never develop,
> edit tracked files, or commit directly on main. For every task, first update
> main with a safe fast-forward, create a new descriptive feature/fix/docs branch
> from it, commit and push only that branch, and merge through a pull request
> after my approval and the required tests. Report the project state and wait
> for my next task before editing.

The different Codex account will not have the old conversation history, but the
committed handoff files provide the necessary project context and safety rules.

## 12. Files that do not need to be restored

- The old `.venv` — recreate it as described above.
- The old PostgreSQL database — this guide creates a fresh one.
- `D:\ServiceManagement` — not required for source development.
- The external source-image folder — required planner assets are committed.
- Old test caches such as `.pytest_cache` and `__pycache__`.

The RC33 deployment ZIP under `dist` is optional for development. Keep it only
if the new PC will also be used to deploy the application.

## 13. Reproduce the full offline deployment ZIP

This is optional for development. A Git clone alone cannot reproduce the full
offline ZIP because these large vendor installers are intentionally ignored:

- Python 3.11 Windows x64 installer
- PostgreSQL Windows x64 installer
- .NET Framework offline installer
- WinSW executable

Copy `tmp\phase7-prereqs` from the old PC, or extract the `prerequisites`
directory from the latest verified offline ZIP. When asked to package, Codex
must use `scripts\New-OfflineBundle.ps1`, run
`tests\test_release_workflow.py`, create the adjacent `.sha256`, and validate
both the outer and embedded ZIPs. The latest verified reference is
`service-management-offline-1.1.0-rc33.zip`; use the next RC number unless a
specific version is requested.

## Troubleshooting checklist

### `python` or `py` is not recognized

Reinstall Python 3.11 and enable the installer option that makes the Python
launcher available, then reopen PowerShell.

### `No module named psycopg2`

Activate `.venv` and rerun:

```powershell
python -m pip install -r requirements.txt
```

### PostgreSQL connection refused

Open Windows Services and confirm the PostgreSQL service is running. Confirm
host `localhost` and port `5432` in `.env`.

### PostgreSQL password authentication failed

Confirm that `.env` contains the password configured for the local `postgres`
role. The current automated tests expect `postgres` for the test databases.

### Application reports missing tables or columns

Run:

```powershell
alembic upgrade head
alembic current
```

Confirm the current revision is `c8e4f2a91d73`.

### Port 8999 is already occupied

Find the listener:

```powershell
Get-NetTCPConnection -LocalPort 8999 -State Listen
```

Either stop the known development process or choose a different unused
development port in `.env`. Do not terminate an unknown process.
