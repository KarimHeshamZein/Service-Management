# New PC Codex Setup Prompt

Copy everything inside the prompt block below and send it as the first message
to Codex on the new PC after pasting the project folder.

```text
Set up the Service Management System as a fresh local development environment
on this Windows PC and continue until it is running and verified.

The copied project is somewhere inside the service-management-system folder.
Find the actual repository root by locating the directory that contains
AGENTS.md, CLAUDE.md, README.md, PROJECT_HANDOFF.md, NEW_PC_SETUP.md,
requirements.txt, app/, alembic/, and tests/. Work only from that repository.

Before changing anything:

1. Read AGENTS.md completely.
2. Read CLAUDE.md completely.
3. Read README.md completely.
4. Read PROJECT_HANDOFF.md completely.
5. Read NEW_PC_SETUP.md completely.
6. Run and report:
   - git status --short --branch
   - git log -5 --oneline --decorate
   - git remote -v
   - alembic heads, if the current Python environment can run it
7. Treat the Current handoff in CLAUDE.md and PROJECT_HANDOFF.md as
   authoritative.

Objective:

- Create a brand-new local development database. Do not transfer or connect to
  an old or production database.
- Recreate the Python 3.11 virtual environment and install requirements.
- Create a fresh development .env with a newly generated SECRET_KEY.
- Use application port 8999.
- Create and use these local PostgreSQL databases:
  - service_management
  - service_management_test
  - service_management_migrations_test
- Apply all Alembic migrations to the new service_management database.
- Load development sample data with python seed.py.
- Run the complete pytest suite.
- Start the application on 0.0.0.0:8999 and verify it through
  http://127.0.0.1:8999.

Authorization for this setup:

- You are explicitly authorized to create or replace a .venv inside this copied
  repository.
- You are explicitly authorized to create a new .env from .env.example and
  generate a new local SECRET_KEY.
- You are explicitly authorized to create only the three new local development
  PostgreSQL databases listed above.
- You are explicitly authorized to run alembic upgrade head only against the
  newly created local service_management database.
- You are explicitly authorized to run python seed.py only against that new
  local development database.
- You are explicitly authorized to start and restart the local development
  server on port 8999.
- You may install missing Python packages into the new .venv.
- Ask before performing any machine-wide installation or action that requires
  Windows administrator elevation.

Safety requirements:

- Do not access, modify, migrate, delete, or stop anything under
  D:\ServiceManagement.
- Do not connect to or modify any production/deployed database, Windows service,
  firewall rule, scheduled task, backup, or external installation.
- Preserve the unrelated root index.html. Do not stage, edit, move, or delete
  it.
- Preserve dist ZIPs, uploads, copied backups, installer prerequisites, and all
  user files.
- Do not commit or push .env, databases, uploads, dist, tmp, .venv, logs, or
  secrets.
- Do not run python seed.py --reset.
- Do not edit application source merely to make this PC work. Diagnose setup
  problems first. If a genuine source change appears necessary, stop, explain
  the evidence, and ask for approval.
- Use PowerShell path-safe commands and verify exact targets before moving or
  deleting anything.

Setup procedure:

1. Inspect the PC for Git, 64-bit Python 3.11, PostgreSQL, and the PostgreSQL
   command-line tools. Report what is installed.
2. If Git, Python 3.11, or PostgreSQL is missing, explain exactly what is
   missing and ask for approval before installing it. Prefer installers already
   copied under tmp/phase7-prereqs when they are valid and appropriate.
3. Verify the copied Git repository and configured origin. If authentication is
   available, fetch origin and fast-forward main only when that will not
   overwrite local work. Never stage the unrelated index.html.
4. If a copied .venv exists, do not use it. Move it outside the repository to a
   clearly named old-PC backup after verifying the destination, then create a
   new .venv with Python 3.11.
5. Activate the new .venv and install requirements.txt. Verify imports for
   fastapi, sqlalchemy, and psycopg2.
6. If a copied .env exists, move it outside the repository to a protected
   old-PC backup after verifying the destination. Copy .env.example to .env,
   generate a strong random SECRET_KEY, and configure:
   - ENVIRONMENT=development
   - APP_HOST=0.0.0.0
   - APP_PORT=8999
   - APP_RELOAD=true
   - DATABASE_URL=postgresql://postgres:postgres@localhost:5432/service_management
   - UPLOAD_DIR=./data/uploads
   - PUBLIC_BASE_URL=http://127.0.0.1:8999
7. Confirm PostgreSQL is local and its service is running. The current tests use
   postgres/postgres on localhost:5432. If that local credential does not work,
   do not change the PostgreSQL password silently; ask me for the credential or
   permission to align the local development role.
8. Create only service_management, service_management_test, and
   service_management_migrations_test if they do not already exist. If any
   already exists, inspect it and ask before dropping, resetting, or reusing it.
9. Run alembic heads and require exactly one head. Run alembic upgrade head
   against the new service_management database, then run alembic current. The
   expected handoff revision is f3a8d7c52e14 unless the repository contains a
   newer committed migration.
10. Run python seed.py once. Confirm the development Administrator exists
    without exposing password hashes or secrets.
11. Run python -m compileall -q app alembic/versions and
    node --check app/static/js/app.js when Node is available. Node is optional;
    do not install Node merely for this vanilla-JavaScript project.
12. Run python -m pytest -q. The handoff baseline is 343 passed with one existing
    Starlette TestClient/httpx deprecation warning. Report the actual result.
13. Start the application with the new .venv on 0.0.0.0:8999. Use a hidden
    background process only after tests pass. Keep stdout/stderr in ignored tmp
    logs.
14. Verify:
    - port 8999 is listening from the expected Python process;
    - GET /login returns HTTP 200;
    - login contains the Show password control;
    - development Administrator login works;
    - /dashboard returns HTTP 200 after login;
    - /pricing/items returns HTTP 200 and contains category management;
    - /pricing/quotations/new returns HTTP 200 and contains the grouped item
      picker and alternative-item selector.
15. Run git status --short --branch again. Confirm only expected ignored/local
    setup files and the preserved untracked root index.html remain; no secret or
    generated file may be staged.

Communication requirements:

- Send concise progress updates while working and do not leave me without an
  update for more than 60 seconds.
- Take reasonable action within the authorization above instead of asking about
  routine setup choices.
- Pause only for a genuinely blocking credential, administrator approval,
  existing-database decision, or source-code issue.
- At the end, report the repository commit, Python version, database names,
  Alembic revision, test result, running PID/port, verified URLs, and any manual
  action still required.
```

## Expected pauses

Even with this prompt, Codex may need you to approve or provide:

- Windows administrator elevation for installing Python or PostgreSQL
- The local PostgreSQL password if it is not `postgres`
- GitHub browser/device authentication before fetching or pushing
- A decision if any of the three database names already contains data

Those pauses protect existing machine data. After you answer them, tell Codex to
continue the same setup task.

