# Service Management System

A service evidence portal for a field service team. Technical users file installation and maintenance proof; Administrators manage the system; Customers read records for their assigned Projects.

**Maintenance, Preventive Maintenance, New Installations, Reports and Pricing are implemented.** Reports reuse the All Records filters and export the full matching evidence set as PDF. Administrators have both per-user Technician Activity reporting and a filterable append-only Audit Log for mutations, authentication, and sensitive downloads. Pricing provides the single imaged equipment/item catalogue, immutable catalogue price history, separate quoted-price snapshots, optional quotation addressees, mandatory charges, explicit optional-item decisions, search, and PDF export. Mixed-currency quotations intentionally show no aggregate total.

## What this system is not

It does not schedule, assign, approve, or track maintenance tasks. There are no calendars, no start/stop actions, no task statuses, no approval chains and no notifications. It records work that has already been done. Submitted records are permanently read-only — that is the point of an evidence portal.

---

## Technology stack

| Layer | Choice |
|---|---|
| Language | Python 3.11+ (developed on 3.12) |
| Web framework | FastAPI |
| Templates | Jinja2, server-rendered HTML |
| Database | PostgreSQL via SQLAlchemy 2.0 ORM and Alembic migrations |
| Auth | Signed session cookies (Starlette `SessionMiddleware`) + bcrypt password hashing |
| Images | Pillow — content validation and thumbnail generation |
| Frontend | Hand-written CSS and vanilla JavaScript. No build step, no npm |
| Tests | pytest + Starlette `TestClient` |

Chosen for a small maintainable app: one process, one dependency file, no microservices, no message queues, no frontend toolchain.

## Architecture

```
Browser ──form post / XHR──> FastAPI (single process)
                               │
                               ├─ SessionMiddleware      signed cookie: user_id, role, csrf token
                               ├─ Routers                auth · dashboard · maintenance · records · reports · settings · admin
                               ├─ Dependency guards      get_current_user / require_admin / require_record_submitter
                               ├─ SQLAlchemy ORM ──────> PostgreSQL
                               └─ Upload service ──────> data/uploads/YYYY/MM/<uuid>.jpg
                                                         served only via /media/photo/{id}
                                                         after an ownership check
```

Authorization lives in FastAPI dependencies, never in templates. Administrators have full access; Technical users cannot manage users or deactivate catalog data; Customers can only read records, reports and media for assigned Projects. Pricing is additionally controlled by a per-user permission: Administrators always have access, while each Technical account may be granted or denied access from Users.

The administration UI calls work locations **Projects** and manages them at
`/projects`. Each project has a project name, address or location, city, contact
person, contact number, optional description, and optional start/end dates. The
existing `sites` table remains the compatibility storage layer; for new and
edited projects its legacy `customer_name` value is kept equal to the project
name. Projects act as **Main Projects** and contain **Sub Projects**. Sub
Projects receive scoped assignments to the existing Site catalog, forming the
Main Project → Sub Project → Site hierarchy without changing existing Project
IDs or Customer Project assignments.

Installation, normal-maintenance, and preventive-maintenance entries may submit
multiple hierarchy branches under one atomic parent record and record number.
Each Site is a complete section with its own devices, before/after evidence,
and Excel import, while personnel are shared. Installation Site sections also
retain their Project-matched quotation snapshot. Device rows
retain immutable Main Project → Sub Project → Site snapshots, allowing device
location lookup without splitting one visit into separate records. Report
selection and saved-report detail expand the atomic record under every
contained hierarchy branch while keeping one synchronized record selection.
Customer-facing saved reports explicitly combine authorized
records from one or many Main Projects, Sub Projects, and Sites while retaining
their own report metadata and hierarchy/customer snapshots. Installation
Each Installation, Maintenance, and Preventive Maintenance Site entry can download,
preview, and confirm a validated Excel device workbook. Installation rows become
Installed Assets; all three entry types retain immutable device snapshots that
may optionally appear in the saved report PDF. PDF Device Data includes only
confirmed Excel rows and is separated by Main Project.

```
app/
  config.py       settings from environment variables
  database.py     PostgreSQL engine and session factory
  models.py       ORM entities
  security.py     bcrypt hashing, sessions, CSRF, single-use form tokens
  deps.py         authentication and role dependencies
  uploads.py      image validation, storage, thumbnails, path safety
  helpers.py      record numbering, timezone display, template rendering
  main.py         app factory, middleware, error handlers
  routers/        auth · dashboard · maintenance · records · reports · settings · admin
  templates/      11 pages + shared macros
  static/         app.css · app.js
seed.py           schema creation and development data
run.py            development server
tests/            PostgreSQL regression suite
```

## Database entities

```
users ──────────┬──< maintenance_records >──┬──< maintenance_participants
sites ──────────┤                           └──< maintenance_photos
service_types ──┤
                └──< installation_records >─┬──< installation_participants
                                            └──< installation_photos
pricing_items ── 1:1 compatibility ── device_catalog ──< installed_devices ──< maintenance_record_devices
work_sites ──< installation_record_sites >── installation_records
sites ──< sub_projects ──< sub_project_sites >── work_sites
service_reports ──< service_report_records >── installation/maintenance records
service_reports ──< installed_devices (optional confirmed Excel import)
record_counters               (backs PM-YYYY-NNNNN)
installation_record_counters  (backs NI-YYYY-NNNNN)
```

`maintenance_records` holds foreign keys **and** snapshot columns — `site_name`, `customer_name`, `site_address`, `service_name`, `team_leader_name`. The foreign keys give referential integrity; the snapshots mean history never changes when a site, service or person is later renamed or deactivated. Both are tested.

Deletes are blocked at the schema level: sites, service types and users referenced by a record use `ON DELETE RESTRICT`. Deactivate instead — inactive entries disappear from the submission form but stay intact in history.

Foreign keys are enforced by PostgreSQL, unique constraints cover record numbers, usernames, service names and site+customer pairs, and indexes cover every column the record list filters on.

---

## Setup

Requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # paste into SECRET_KEY
```

### Database setup

```bash
python seed.py            # create the schema and load development data
python seed.py --reset    # wipe the database and uploads, then reload
python reset_admin_password.py  # recover a forgotten Administrator password
```

The schema is managed by Alembic. Run `alembic upgrade head` after pulling model
changes and before restarting the application. `seed.py --reset` remains the
development-only command for wiping and reloading sample data.

### Administrator password recovery

Forgot-password email links are intentionally limited to active Administrator
accounts. Technical and Customer passwords remain resettable only by a logged-in
Administrator from the Users page.

Configure these values in `.env`:

```dotenv
PUBLIC_BASE_URL=https://service.example.com
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=service@example.com
SMTP_PASSWORD=use-an-app-password-or-provider-secret
SMTP_FROM_EMAIL=service@example.com
SMTP_STARTTLS=true
```

After SMTP is configured, log in as an Administrator, open **Users → Manage**,
save a recovery email and open its verification link. The login-page **Forgot
password?** flow becomes usable only after verification. Reset links are hashed
in storage, single-use, expire after 15 minutes and invalidate existing sessions.
The local `python reset_admin_password.py` command remains the emergency fallback.

### Run

```bash
python run.py             # http://localhost:8000
```

Or directly: `uvicorn app.main:app --reload`.

For a phone on the same network, the server already binds `0.0.0.0` — open `http://<your-machine-ip>:8000`.

### Tests

```bash
python -m pytest          # full PostgreSQL regression suite
python -m pytest -v       # per-test names
```

Tests use their own temporary database and upload directory, so running them never touches development data.

---

## Development accounts

| Role | Username | Password | Notes |
|---|---|---|---|
| Administrator | `admin` | `admin123` | Full access, including field-service data entry |
| Technical | `omar@afaqy.local` | `Leader@12345` | Has submitted records |
| Technical | `yousef@afaqy.local` | `Leader@12345` | Has submitted records |
| Technical | `hani@afaqy.local` | `Leader@12345` | **Deactivated** — proves inactive users cannot log in |

Running `seed.py` loads these development accounts regardless of `ENVIRONMENT`.
The login page lists them only when `ENVIRONMENT` is not `production`.
`seed.py` is excluded from production release packages and must not be copied to or
run on a production server. Change the accounts before using seeded data outside
local development.

## Environment variables

All settings come from the environment; see `.env.example`.

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | dev fallback | Signs the session cookie. **Required in production** — the app refuses to start without it |
| `ENVIRONMENT` | `development` | `production` enables strict startup checks and hides the dev account list |
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/service_management` | PostgreSQL connection URL |
| `UPLOAD_DIR` | `./data/uploads` | Where proof photos are stored |
| `MAX_UPLOAD_MB` | `8` | Per-photo size limit |
| `MAX_PHOTOS_PER_RECORD` | `10` | Photos per submission |
| `SESSION_MAX_AGE_SECONDS` | `43200` | Session lifetime (12 hours) |
| `SESSION_HTTPS_ONLY` | `false` | Set `true` behind TLS |
| `PAGE_SIZE` | `10` | Records per page |
| `MAX_PDF_RECORDS` | `250` | Maximum matching records permitted in one standard or technician-audit PDF |
| `DISPLAY_TZ_OFFSET_MINUTES` | `180` | Display offset. Storage is always UTC |
| `DISPLAY_TZ_LABEL` | `UTC+03:00` | Shown next to timestamps |
| `BCRYPT_ROUNDS` | `12` | Hashing cost. Tests drop it to 4 for speed |

## Windows HTTP deployment

The offline package provides `Setup-ServiceManagement.cmd`, a graphical elevated
installer that verifies the bundle, installs missing prerequisites, initializes
PostgreSQL, runs migrations, creates the first Administrator and installs the
Windows service and Service Console shortcuts. Installer state and redacted logs
live under `%ProgramData%\ServiceManagementSystem\Installer`, outside the
checksum-verified bundle, so a safe rerun can resume.

Machine configuration is performed from the local elevated **Service Management
Console**. It manages the service, the one application port, optional fixed LAN
adapter settings, IP-scoped firewall access, PostgreSQL connectivity, backups,
diagnostics and verified updates. The Administrator `/settings` page is
sanitized and read-only.

Uvicorn listens on `0.0.0.0` and Windows Firewall controls exact local-address
and permitted-remote-network access. There is no Windows portproxy layer. The
resulting endpoints are:

```text
http://PUBLIC_IP:APP_PORT
http://LAN_IP:APP_PORT
```

The Service Console configures recurring PostgreSQL backups: enable the schedule,
choose an interval in days, separate database/upload retention counts, an
absolute backup directory and `pg_dump.exe` path. The task writes a compressed database dump
followed by a same-timestamp upload snapshot, prunes each backup type by its own
retention limit and reports failures or stale status on the Settings page.
Unchanged immutable uploads are hardlinked from the preceding snapshot; new
files, and files on storage that cannot create hardlinks, are copied.

For versioned production updates, PostgreSQL/upload backups, Alembic upgrades,
health checks, and application rollback, follow
[`docs/PRODUCTION_UPDATES.md`](docs/PRODUCTION_UPDATES.md).
That runbook also covers the fully offline bundle built by
`scripts/New-OfflineBundle.ps1`, including vendor installers, WinSW, integrity
checks, a CPython 3.11 Windows wheelhouse and `scripts/Restore-Backup.ps1`.

The PostgreSQL field changes the application's connection target only.
PostgreSQL must already be listening on that host and port, and its firewall
port must not be exposed on the public NIC. Public HTTP is unencrypted; use the
permitted-remote-IP field or a VPN whenever possible.

## File upload handling

Files never land in the static directory. They go to `UPLOAD_DIR/YYYY/MM/` under a freshly generated UUID plus a canonical extension derived from the *detected* type. The uploaded filename is stored as display data only and is sanitised — it never influences a path.

Validation runs three gates before anything is written:

1. **Extension** must be `.jpg`, `.jpeg`, `.png` or `.webp`.
2. **Magic bytes** must match JPEG, PNG or WebP. A shell script renamed to `.jpg` fails here.
3. **Pillow decode** must succeed and its detected format must agree with the sniffed type.

Size is checked against `MAX_UPLOAD_MB` before decoding. If any file in a submission fails, the whole submission is rejected and every file already written for it is deleted — no orphans.

Serving goes through permission-checked media routes, which verify Administrator/Technical access or the Customer's assigned Project before resolving the file. A 480px thumbnail is generated at upload time and served with `?size=thumb`.

## Security summary

- bcrypt password hashing, cost 12. Hashes are never rendered or returned.
- Every page and endpoint behind an authentication dependency. Anonymous requests redirect to login with a validated same-origin `next` parameter.
- Authorization is enforced server-side per request, including Customer Project scope on record lists, details and photos.
- CSRF token required on every state-changing POST.
- Single-use form token blocks duplicate submissions; the submit button also locks during upload.
- Deactivating an account kills its live session on the next request.
- Identical error message for an unknown username and a wrong password, so accounts cannot be enumerated.
- Uploads validated by content, stored under generated names, path traversal blocked.
- Submission timestamps come from the server clock. Any `submitted_at`, `submitted_by_id` or `record_number` a client tries to post is ignored — tested.
- Internal exceptions render a generic error page; no stack traces or SQL reach the browser.
- `X-Content-Type-Options`, `X-Frame-Options` and `Referrer-Policy` set on every response.
- Secrets only from environment variables; `.env` is gitignored.

## Sample data

`python seed.py` loads 4 users (one deactivated), 6 sites across Riyadh, Dammam and Jeddah (one deactivated), 6 service types including Gate, Router and Camera Service (one deactivated), and 6 maintenance records covering all four results, with participants, issue descriptions, recommendations and generated proof photos.

The seeded photos are synthetic placeholder images generated by Pillow, not real site photography.

## Testing

356 tests across the PostgreSQL regression suite:

- `test_auth_and_access.py` — valid and invalid login, inactive users blocked, protected pages, role enforcement on GET and POST, session invalidation, nav hiding, hashes never exposed.
- `test_admin_management.py` — creating and editing sites, service types and users; deactivation removing them from the form; search; password reset; duplicate names; CSRF enforcement; admins cannot deactivate themselves.
- `test_maintenance.py` — successful submission, validation, secure uploads, role and Project visibility, immutable records, filters, snapshot integrity and dashboard statistics.
- `test_installations.py` — installation validation, NI numbering, grouped equipment evidence, secure photos, Customer Project visibility, immutable records and unified records.
- `test_acceptance_workflow.py` — the entire 22-step acceptance scenario in one test.
- `test_general_maintenance.py` — separate MA numbering, grouped per-device evidence, validation, search, permissions and secure photos.
- `test_database_migrations.py` — builds a separate scratch database through Alembic, checks ORM/schema drift, verifies downgrade/upgrade round trips and requires one migration head.
- `test_record_pagination.py` — mixed-type SQL pagination, bounded PDF exports,
  photo caps, technician SQL filters and multi-page Customer Project isolation.
- `test_reports.py` and `test_technician_audit.py` — filtered evidence PDFs and
  Administrator-only technician activity audits.
- `test_structured_reports.py` — saved hierarchy-aware reports, fixed creator
  identity, Team Leader selection, Customer authorization, three-workflow Excel
  preview and confirmation, asset conflict rules, device snapshots, evidence
  descriptions, and PDF output.
- `test_settings.py` — Settings authorization, validation, PostgreSQL testing,
  secret-free audit data, and generated Windows scripts.

- `test_pricing.py` — per-user access, protected item images and cleanup,
  main/related-item management, quotation price overrides, required charges,
  explicit optional-item selection or skip decisions, snapshots and
  calculations, historical quotation-image snapshots, validation, search,
  editing, deletion, and PDF content.

### Manual verification

The workflow was exercised against the running server at desktop and mobile widths. On narrow screens the sidebar becomes an off-canvas drawer behind a hamburger, tables switch to card layouts, and controls keep a 44px minimum touch target. **Not yet verified on physical hardware** — in particular, the `capture="environment"` camera path and iOS Safari's handling of `DataTransfer` for the file list should be checked on a real phone before field use.

---

## Assumptions

1. **Timestamps** are stored in UTC and displayed at a configurable offset, defaulting to +03:00 (Riyadh).
2. **The four maintenance results are fixed** by the specification, so they are an enum in code rather than a configurable table. Making them configurable would let someone rename a result out from under historical records.
3. **Administrator is a superset role.** Administrators can manage master data,
   submit installation and maintenance evidence, and review every record.
4. **Username doubles as email.** One field, validated for uniqueness case-insensitively, no separate email column.
5. **Participants are selected Technical users.** Installation, Preventive
   Maintenance and Maintenance forms list active Technical accounts other than
   the submitter. The backend validates account IDs and stores the selected
   display names as historical snapshots.
6. **Duplicate protection is session-scoped.** A single-use token is issued with each form and tracked in the session. It stops the double-tap and the browser back-and-resubmit; it does not deduplicate two genuinely separate submissions describing the same visit.
7. **Photos are proof, not a gallery.** No EXIF extraction, no GPS verification, no compression of the original.
8. **Single-server deployment.** Sessions live in the cookie and files on local disk, so horizontal scaling would need shared storage.

## Known limitations

- **Photo selections do not survive a validation error.** Browsers cannot repopulate a file input, so after a server-side validation error the Technical user must reselect photos.
- **No rate limiting on login.** There is no lockout or throttle after repeated failures. Put this behind a reverse proxy with rate limiting, or add `slowapi`, before exposing it publicly.
- **Sessions are cookie-based**, so there is no server-side "log out everywhere". Deactivating a user does end their session on the next request.
- **No pagination on the admin lists.** Sites, service types and users render in full. Fine at a few hundred rows; add pagination beyond that.
- **PostgreSQL is a required external service.** The application and test databases must be available before the app or test suite starts.
- **Uploads are stored unencrypted at rest** and are not virus-scanned. They are access-controlled but not scanned for malicious payloads.
- **Audit events are application-level.** The combined Administrator Audit Log
  records application mutations, authentication, and sensitive downloads, but
  direct database changes made outside the application are not observable.
- **Arabic UI support is implemented.** Language persistence, RTL layout, HTML pages
  and server messages use the English/Arabic catalogs. PDF labels stay English, while
  user-entered Arabic is shaped and rendered with an embedded Noto Sans Arabic font.

## Extension points

**New Installations** — implemented with its own controlled record,
participant, photo and counter tables. It reuses sites, service types, users,
upload validation and authorization. `/records` combines maintenance and
installation history without merging their database tables.

**Installation selection workflow** — Administrators manage Main Projects at
`/projects`, one-field Site names such as Gate 1 at `/sites`, and searchable
equipment under Pricing Items. Items marked available for service records appear in
New Installation entry. The form adds one or more Main Project, Sub Project,
Site, and quotation scopes, assigns each service item to one scope, then
registers each serialized unit
through a hidden legacy compatibility row. Project, Sub Project, Site, device,
model and serial are available to structured report selection.

**Reports** — `/reports` remains the read-only filtered preview over the same
normalized record set used by `/records`. `/reports/installation`,
`/reports/maintenance`, and `/reports/preventive-maintenance` contain saved,
customer-facing reports assembled from explicitly selected authorized records.
Saved reports use a fixed authenticated creator, separately selected Team
Leader/technicians, Main/Sub/Site grouping, staged evidence descriptions, and
downloadable PDFs. Report record selection supports inclusive From/To filters
with second precision. Excel template/preview/confirmation belongs to Installation,
Maintenance, and Preventive Maintenance Data Entry; saved reports may include
those captured device snapshots in their PDFs. `/reports/technician-audit`
remains Administrator-only.

Every new Installation record requires an existing quotation ID belonging to
the selected Project. Preventive Maintenance and Maintenance do not link to a
quotation. All Installation record submitters may select the identifier without
seeing prices. Only Administrators
and Pricing-authorized Technical users see it on record details or may opt to
include it in a standard Reports PDF; it is otherwise omitted from lists,
searches, customer views and audit exports.

**Audited corrections** — the specification asks for records to stay read-only, and they are. If corrections become necessary, do not add an edit form. Add a `record_corrections` table holding the record reference, the correcting user, a timestamp, a reason and the before/after values, and show corrections as an appended trail on the detail page. The original evidence stays untouched.
