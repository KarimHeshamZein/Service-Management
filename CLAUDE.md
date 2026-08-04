# CLAUDE.md

Service Management System — a maintenance evidence portal. Read `README.md` for
full architecture, entities and known limitations. This file is the short version
plus the rules that aren't inferable from the code.

## Working agreement

1. **Read → report → fix.** Investigate and report findings first. Do not edit
   files during a review or research phase.
2. **Wait for explicit approval** before making changes. State what you intend to
   change and why, then stop.
3. **Ask before adding any dependency.** The dependency list is deliberately small.
4. **Run `python -m pytest` before and after every change.**

## Stack — do not change

FastAPI · Jinja2 server-rendered templates · SQLAlchemy 2.0 · PostgreSQL ·
Alembic · bcrypt · Pillow · ReportLab.

No npm, no build step, no frontend framework, no microservices. Frontend is
hand-written CSS plus vanilla JS in `app/static/`. If a task seems to call for
React or a bundler, say so and stop — don't introduce one.

## Commands

```bash
pip install -r requirements.txt
cp .env.example .env          # then generate a SECRET_KEY
python seed.py                # create schema + sample data
python seed.py --reset        # wipe database and uploads, reload
python reset_admin_password.py # interactive local Administrator recovery
python run.py                 # http://localhost:8993 by default
python -m pytest              # full regression suite
python -m pytest -k <name>    # single test
.\scripts\New-ReleasePackage.ps1 -Version 1.1.0 # build production release ZIP

# Database migrations
alembic upgrade head                              # apply pending migrations (run before restarting app)
alembic revision --autogenerate -m "description" # generate migration after editing models.py
alembic downgrade -1                              # roll back one migration
alembic current                                   # show current migration version in the database
```

Dev logins: `admin` / `admin123` · `omar@afaqy.local` / `Leader@12345`

## Layout

```
app/config.py      settings from env vars only
app/models.py      ORM entities
app/deps.py        auth + role dependencies  <-- authorization lives here
app/security.py    bcrypt, sessions, CSRF, single-use form tokens
app/uploads.py     image validation, storage, path safety
app/helpers.py     record numbering, timezone display, render()
app/routers/       auth · dashboard · maintenance · installations · records · reports · settings · admin
app/templates/     server-rendered pages + partials/macros.html
tests/             4 files; test_acceptance_workflow.py is the end-to-end scenario
```

## Invariants — breaking these breaks the product

- **Submitted records are controlled and audited.** Administrators and Technical
  users may edit results, notes, issue/recommendation or handover text,
  participants and photos. Record identity, submitter, timestamps and Project/
  Site scope stay immutable. Every edit writes an append-only `record_revisions`
  entry in the same transaction. Only Administrators may permanently delete a
  record and its stored photos.
- **Authorization is enforced in FastAPI dependencies**, never in templates.
  Hiding a nav link is cosmetic. Every protected route goes through
  `get_current_user`, `require_admin`, `require_catalog_manager` or
  `require_record_submitter`.
- **Deployment Settings are Administrator-only and read-only.** The page shows
  sanitized runtime, network, database, backup and legacy-audit status. The local
  elevated Service Console is the only supported machine-settings writer and
  performs validated atomic `.env`, service, adapter and firewall changes.
- **Scheduled database backups are installed through Windows Task Scheduler.**
  The Service Console stores the enabled flag, interval days, retained-dump count, absolute
  backup directory, `pg_dump.exe` path, upload-snapshot flag and separate upload
  retention count. The downloaded elevated installer reads `DATABASE_URL` and
  `UPLOAD_DIR` from `.env` at runtime, never embeds credentials, writes compressed
  dumps followed by same-timestamp upload snapshots, prunes each by its own
  retention and records a status that the read-only Settings page checks for failures and
  staleness. Upload snapshots use NTFS hardlinks for unchanged immutable files
  and copy new files or files that cannot be linked.
- **Production releases preserve persistent state.** Versioned Windows releases
  use `scripts/Deploy-Release.ps1`, a shared `.env` and uploads directory,
  PostgreSQL/upload backups, Alembic upgrades and a bounded health check.
  Application rollback never automatically downgrades PostgreSQL.
- **Roles are enforced server-side.** Administrators have full access. Technical
  users can submit and edit records and create/edit catalog data, but cannot
  delete or deactivate catalog rows or reach user management. Customers can only reach Records,
  Reports and protected media belonging to Projects assigned through
  `customer_project_assignments`.
- **Pricing has an additional per-user permission.** Administrators always have
  full Pricing access. Only Technical users with `pricing_access` may reach
  Pricing routes; they may create/edit items and quotations but cannot delete,
  activate/deactivate, or change Pricing settings. Customers never receive
  Pricing access. Enforce this through `require_pricing_access`.
- **Quotations are snapshot-based.** Saved quotations retain Project, seller,
  main-item, related-item, unit-price and per-line currency snapshots. Catalogue or Pricing-setting
  changes never rewrite an existing quotation. Monetary calculations use
  `Decimal` with two-decimal rounding. Main and related prices may be overridden
  per quotation without changing the catalogue. Mixed SAR/USD quotations intentionally
  have no aggregate total. Every quotation includes manpower, transportation and
  installation charge snapshots. Transportation quantity is editable. Installation
  price per day is workers multiplied by price per worker; the informational manpower
  row is not counted a second time. A main item with
  active optional items must either select at least one or explicitly store one
  skip decision for the entire optional set.
- **New service records require a Project-matched quotation reference.** Store
  both the nullable FK and quotation-number snapshot so older records remain
  compatible and quotation deletion does not erase the historical identifier.
  All submitters may select the ID without gaining Pricing access. Only
  Administrators and Pricing-authorized Technical users may see it later or
  explicitly include it in a standard report PDF. Never include it in record
  search, customer output or technician audit reports.
- **Pricing item images use protected upload storage.** Each main Pricing item
  may have one validated image and thumbnail. Only Pricing-authorized users may
  fetch it. Each saved quotation copies the selected main-item image into a
  quotation-line snapshot so later catalogue replacement/removal cannot rewrite
  the quotation detail or PDF. Replacing quotation lines and deleting catalogue
  items or quotations cleans up the corresponding stored files.
- **`maintenance_records` carries snapshot columns** (`site_name`,
  `customer_name`, `site_address`, `service_name`, `team_leader_name`) alongside
  the FKs, so history survives renames and deactivation. Any new record type must
  follow the same pattern.
- **Item and device history is snapshot-based.** Pricing Items are the only
  user-managed equipment catalogue. Active items marked for service entry are offered
  on New Installations. Each Pricing Item maintains a hidden one-to-one `device_catalog`
  compatibility row so new installations can create an `installed_devices` row without
  rewriting historical foreign keys.
  Maintenance records attach a `maintenance_record_devices` snapshot so later
  catalog changes never rewrite historical evidence.
- One installation or preventive-maintenance visit may group up to 20 device
  work items under the same Project, Site and participants. Each device item
  owns its result, notes and photos; installation items also own handover notes,
  while maintenance items own issues and recommendations. Additive child tables
  preserve compatibility with older record formats.
- **Projects, Sites, services, Pricing Items and users are hard-deleted only when
  unused.** If protected by historical references, an Administrator's delete
  action deactivates the row instead. Enforced with `ON DELETE RESTRICT`.
- The user-facing administration term is **Project**, managed at `/projects`.
  It is backed by the legacy `sites` table for compatibility; new and edited
  projects mirror Project Name into both legacy name columns.
- **Sites** are a separate global one-field catalog (`work_sites`) managed at
  `/sites`, with names such as Gate 1, Gate 2 and Gate 3. Installation entry
  selects Project, Site, Service and Device in that order.
- **Timestamps come from the server clock** (`models.utcnow()`). Never trust a
  client-supplied `submitted_at`, `submitted_by_id` or `record_number`.
- **Uploads are validated three ways** — extension, magic bytes, Pillow decode —
  stored under generated UUIDs outside the static root, and served only through
  the permission-checked `/media/photo/{id}` route.
- **Storage is UTC**; the display offset is a config value, default +03:00.
- **HTML language is user-selectable.** Authenticated preferences live on the
  user row; anonymous pages use the signed session. Catalogs are plain Python
  dictionaries under `app/i18n/`, English is the fallback, user-entered data and
  stored enum values are never translated, and PDF labels remain English. User-entered
  Arabic is shaped and rendered with the bundled Noto Sans Arabic font.
- **Normal startup never creates schema objects.** Alembic owns application
  schema changes. Only the destructive development seed workflow may call
  `Base.metadata.create_all()`.
- **Public password recovery is Administrator-only.** It requires a separately
  verified recovery email and configured SMTP. Reset tokens are hashed,
  single-use and expire after 15 minutes. Technical and Customer passwords are
  reset only by an authenticated Administrator from Users.

## Scope

**Preventive Maintenance**, **Maintenance**, **New Installations**, **Reports**
and **Pricing** are implemented. Records and Reports share the same normalized
Search and Record Type filters. Reports export the full matching set as an
access-controlled PDF with work details and available evidence photos.
Administrators also have a Technician Activity report with user, date, Project
and record-type filters. It audits led and assisted visits, device outcomes,
evidence totals and append-only record edits, with an optional-photo PDF export.
The graphical offline installer handles prerequisites, PostgreSQL bootstrap,
migrations, first-Administrator creation, service registration and shortcuts.
Administrators use the local elevated Service Console for public/LAN access on
one application port, optional fixed LAN IP, PostgreSQL, backups and verified
updates. Uvicorn binds to `0.0.0.0`; IP-specific Windows Firewall rules control
exposure without a port-proxy layer. Generated operations contain no database
password or application secret.
Pricing includes imaged reusable main and optional related items, searchable
Project quotations, editable price and SAR/USD currency snapshots, required
manpower/transportation/installation charges, explicit optional-item decisions,
configurable validity/company/charge defaults and PDF export. Mixed-currency
quotations show line totals only, never a misleading aggregate total.

Explicitly out of scope by design — do not add without being asked: scheduling,
task assignment, calendars, start/stop actions, approval workflows,
notifications, configurable permission matrices, and task status workflows.
Workers who accompany the submitter are selected from active Technical user
accounts. The submitter is excluded from the selector, submitted IDs are
validated server-side, and participants retain both their account ID and a
historical name snapshot.

## Conventions

- Validation errors re-render the form with an `errors` dict keyed by field name;
  the AJAX path returns the same dict as JSON plus a fresh `form_token`.
- User-facing copy: sentence case, active voice, no apologies. Errors say what
  happened and what to do.
- New pages go through `helpers.render()` so CSRF, flash messages and the current
  user land in the template context.
- Every state-changing POST requires a valid CSRF token.
