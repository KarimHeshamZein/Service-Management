# CLAUDE.md

Service Management System — a maintenance evidence portal. Read `README.md` for
full architecture, entities and known limitations. This file is the short version
plus the rules that aren't inferable from the code.

## Current handoff — 2026-08-12

- `main` is now an integration-only branch. Never implement, edit tracked
  files, or create development commits directly on it. Before each approved
  task, safely fast-forward `main`, create a new descriptive `feature/*`,
  `fix/*`, or `docs/*` branch, commit and push only that branch, and merge it
  through a GitHub pull request after approval and testing. Never force-push
  `main` or bypass its protection.

- Browser-entered per-Site service data
  tables are implemented for Installation, Preventive Maintenance, and
  Maintenance. Installation uses the detailed device columns; both maintenance
  workflows use the approved `No / Item / Quantity / Notes` layout. Rows can be
  added and removed in each Site section. Maintenance entry no longer selects
  or links a catalogue/installed Item; each service/photo card is headed by the
  selected Service Performed.
- Saved report PDFs keep the optional Include device data checkbox and append
  the browser-entered tables at the end, separated by Main Project, Sub Project,
  and Site. Historical confirmed Excel snapshots remain a report fallback. The
  current PDF table render was visually checked with no clipping or overlap.
- New migration `c8e4f2a91d73` creates the three browser data-row tables and
  makes maintenance item catalogue/model references optional. It has passed the
  full Alembic upgrade/downgrade/metadata-drift gate against the scratch test
  database. With approval, a pre-migration dump was created at
  `tmp/phase2-dev-backups/service_management-before-c8e4f2a91d73-20260811-172621.dump`,
  the local database was migrated to `c8e4f2a91d73`, and the application was
  restarted successfully on port 8999. `/login` returned HTTP 200.
- Focused gate for this pending feature: `11 passed, 1 warning`.
  `python -m compileall -q app` and `git diff --check` pass (only existing
  line-ending notices).

- The approved hierarchical service-report feature is implemented on
  `feature/hierarchical-installation-reports`. The existing Project entity is
  the Main Project, with optional description/start/end dates, additive Sub
  Projects, and scoped assignments to the existing Site catalog.
- The `/projects` management page now provides a searchable expandable
  Main Project → Sub Project → Site hierarchy, customer-user visibility,
  metadata editing, Sub Project management, and server-validated Site
  assignments. Existing Project/Site IDs, URLs, customer assignments, and
  service-record authorization remain unchanged.
- The hierarchy tree now uses connected compact rows with localized `Main` and
  `Sub` level badges, Site markers, a selected Main Project state, anchor links
  to Sub Project controls, and a reference-style project detail/statistics
  layout.
- Installation, normal-maintenance, and preventive-maintenance entry support
  one parent record/number containing multiple Main Project → Sub Project →
  Site sections. Each Site section is a complete work area with its own devices,
  before/after evidence and one Excel import, while shared
  personnel remain at parent-record level. The UI provides Add another device
  inside each Site and Add another Site below the complete sections. Saved
  customer-facing reports
  can explicitly combine authorized records across one or many Main Projects,
  Sub Projects, and Sites. Created By is fixed to the authenticated user while
  Team Leader and technicians are selected separately.
- Installation, Maintenance, and Preventive Maintenance entry each provide a
  direct-download Excel template, validated preview, and explicit confirmation.
  The technician workbook uses the exact eleven approved device columns. New
  Installation rows create Installed Assets; maintenance rows update a matched
  asset only under the approved conflict rules and otherwise remain record
  snapshots. Saved report PDFs can include the device snapshots captured at
  entry. Before/after evidence supports ordered descriptions.
- The workbook Status column is formula-driven: blank for unused rows, `Valid`
  only when columns A-J are complete, otherwise `Invalid`. The template columns
  are Item / Device Name, Model, Serial Number, IMEI, SIM Serial Number, Sim
  Type, Main Project, Sub Project, Site, Remarks, and Status; Phone Number was
  removed. Status has no dropdown,
  is not mapped to the service-result controls, and the dashboard preview no
  longer shows a separate Validation column. Valid is green and Invalid is red
  in both Excel and the preview. Excel Location/Site text, IMEI, and SIM Serial
  Number are stored as entered without the former scope/format rejection.
- The approved usability pass adds an application-wide desktop top bar with
  Quick Create, icon-led accordion navigation that keeps one group open, clearer
  shared form/table styling, and mobile-safe tables. Installation, Maintenance,
  and Preventive Maintenance now have sticky four-step navigation, an expanded
  Excel section, anchored sections, and persistent submit controls.
  Quotation Create/Edit has equivalent section navigation and persistent Save.
  Entry forms provide repeatable, self-contained Site cards; devices are nested
  directly inside their Site instead of using a separate assignment dropdown.
- Saved-report Device Data includes only confirmed Excel rows, never ordinary
  Data Entry fallback values, and renders a separate table for each selected
  Main Project. Report creation has inclusive From/To submission filters with
  second precision in the configured display timezone.
- Migration `c4d8e2f71a90` creates the hierarchy and backfills `General` Sub
  Projects. Migration `e9b4c7a21d36` attaches records/assets to Sub Projects and
  creates saved reports, report links/counters, photo metadata, and imported
  device fields. Migration `b7e5d8c41f20` adds device-data snapshots to all
  three service item tables. Migration `f2a6c9d14e73` adds the explicit Excel
  source marker and best-effort historical backfill. Migration `a3f8d1c62b04`
  adds immutable hierarchy/quotation snapshots to every service item so one
  parent record can safely contain multiple Sites. The current single Alembic
  head before the current pending migration was `d5b9e2a74c16`. Migration `d5b9e2a74c16` adds quotation addressee
  snapshots, immutable catalogue price history, and the append-only audit log.
- The full post-change regression result is `356 passed, 1 warning`. The focused
  entry/report suite is `8 passed, 1 warning`, and the broader entry/i18n/
  migration gate was `110 passed, 1 warning`; after the Status correction, the
  three entry/i18n/report suites pass `112 passed, 1 warning`.
- Per the user's request, the usability pass used focused tests instead of the
  full suite: `12 passed, 1 warning` for rendering/navigation/i18n plus `4
  passed, 1 warning` for the four affected submission workflows. Authenticated
  live checks returned HTTP 200 for 15 representative tabs on port 8999.
- The latest focused change gate is `93 passed, 1 warning` for all affected
  entry/report workflows plus `1 passed, 1 warning` for the Alembic round-trip
  and ORM drift check. Authenticated live checks returned HTTP 200 for all three
  entry pages and the second-precision report filter.
- With explicit approval, the local development database was backed up and
  migrated to `b7e5d8c41f20`, and the application was restarted on port `8999`
  on 2026-08-09. The live `/login` endpoint returned HTTP 200. The pre-migration
  dump is under `tmp/phase2-dev-backups/` and is ignored local state. The latest
  pre-`b7e5d8c41f20` dump is
  `service_management-before-b7e5d8c41f20-20260809-134910.dump`.
- With approval, the local development database was migrated to
  `f2a6c9d14e73` and the application restarted successfully on port `8999`.
- With approval, the local development database was migrated to
  `a3f8d1c62b04`; focused nested-site/report/migration gates passed (`10 passed`
  and `13 passed`, each with the existing warning), and authenticated live
  checks returned HTTP 200 for all three nested entry pages on port `8999`.
- Quotation Create/Edit can optionally address the quotation to the Project
  contact, an active Customer assigned to that Project, or a custom person.
  Name, title, email, and phone are snapshotted and printed on the detail/PDF.
  Pricing Items now retain catalogue edits as immutable price history and show
  quoted snapshot prices separately. Administrators have a filterable combined
  Audit Log covering mutations, authentication, and sensitive downloads; it
  records actor/request/change metadata without passwords or upload contents.
- Catalogue and quoted-price graphs now render interactive points. Hover,
  keyboard focus, click, or touch shows the formatted price and date; quoted
  points also show the quotation number. This applies to main and related items.
- Structured report selection and saved-report detail trees now expand one
  atomic record across every saved Main/Sub/Site section; repeated choices stay
  synchronized as one record ID. Excel import panels are collapsed by default
  on all three Data Entry workflows. Serial number, installation warranty date,
  and workflow notes are optional when creating records. Migration
  `e7c2a91bd460` supplies the required nullable serial schema and removes the
  legacy non-empty note constraints.
- The source and local development database Alembic head is `e7c2a91bd460`.
  With approval, the migration was applied and port 8999 restarted successfully
  on 2026-08-10. The focused gate passed `12 passed, 1 warning`; live inspection
  confirmed nullable serials and all saved hierarchy branches in the latest
  installation report tree.
- With approval, the local development database was migrated to
  `d5b9e2a74c16` and the app restarted on port `8999`. The focused new-feature
  and migration gate passed `9 passed, 1 warning`; the broader affected gate
  passed `78` tests with one pre-existing customer top-bar expectation failure.
  Live `/login` returned HTTP 200.

- The complete portable continuation guide is `PROJECT_HANDOFF.md`. A new Codex
  session must read it after this file and `README.md`.
- The approved application state includes the quotation installation planner,
  quotation site-survey and invoice proof uploads, expanded planner equipment,
  unified image-card item selection across quotations and Data Entry, whole-unit
  quantity steps, quotation line numbering and multi-alternative relationships,
  Pricing Item categories, and a login Show/Hide password control.
- The previous approved Main-branch Alembic head was `f3a8d7c52e14`. Its recent chain is
  `a6c1e9b42f70` (catalog items in maintenance) → `d2e7a4c91b63` (quotation
  alternatives) → `f3a8d7c52e14` (Pricing Item categories).
- The previous Main-branch regression baseline was `343 passed, 1 warning`.
  The feature branch raises the verified baseline to `356 passed, 1 warning`; the
  warning remains the existing Starlette TestClient/httpx deprecation warning.
- Saved-report PDFs normalize invisible formatting characters, retain complete
  uncropped evidence images in equal frames, and center English/Arabic photo
  notes. Record editing now provides thumbnail cards for existing photos,
  editable notes, removal controls, and per-photo previews/notes for new uploads
  across Installation, Maintenance, and Preventive Maintenance. Administrators
  can delete a generated report alone, while deleting a source service record
  also removes every complete generated report containing it.
- Quotation selection is now Installation-only. New Preventive Maintenance and
  Maintenance records store no quotation link, including multi-Site entries.
  Administrator quotation deletion preserves all service records; it retains
  the historical Installation quotation number while clearing legacy
  Maintenance/Preventive links and fake number snapshots. Saved report PDFs now
  label each device's service, result, model, serial, workflow notes, Installation
  warranty/handover details, or Maintenance issue/recommendations as applicable.
  The report ends with manual-signature placeholders for Customer Representative,
  Afaqy Representative, and Project Manager. The focused gate passed `10 passed,
  1 warning`, and both the device-detail and approvals pages were rendered and
  visually inspected without an intervening blank page.
- The Pricing Quotations list now exposes Administrator-only View/Edit/Delete
  row actions plus checkbox selection, Select All for the visible page, and one
  confirmed bulk-delete action. Single and bulk deletion share the same
  service-record-preserving implementation and bulk deletion has an explicit
  Audit Log event. The focused pricing/i18n gate passed `27 passed, 1 warning`;
  port 8999 was restarted and `/login` returned HTTP 200.
- Saved-report creation now filters submissions by a full or partial Record ID,
  independently or together with the second-precision From/To fields. The
  shared Reports search also stays within the Reports tab and explicitly
  supports record numbers. Generated PDFs process each device as one complete
  sequence: its Installation or Maintenance details, then its own Before/After
  evidence beginning on a fresh page, before the next device starts. Record
  context is repeated at each device/evidence boundary without an intervening
  blank page. Main/Sub/Site hierarchy headings use a compact font and reduced
  padding so normal device details fit with them on one page. Each Record banner
  and its device details are kept as one layout block; oversized notes can flow
  onward without orphaning the banner. Evidence pages start directly with
  `PHOTO EVIDENCE` and the device name and do not duplicate the Record banner.
  The focused report/search/i18n gate
  passed `30 passed, 1 warning`, and the compact normal, long-note, single-device,
  and six-page multi-device layouts were rendered and inspected.
- The latest verified offline installer is `1.1.0-rc33`. Its ignored files are
  `dist/service-management-offline-1.1.0-rc33.zip` and the adjacent checksum.
  The ZIP is `535146924` bytes and its SHA-256 is
  `f494123c624279313dba1613c46367c39790e6485a8f1fccf894d564450b1906`.
  The focused release-workflow gate passed `20 passed, 1 warning`; both outer
  and embedded application ZIP CRC checks passed, the package reports Alembic
  head `c8e4f2a91d73`, the packaged PDF source matches the current source, and
  protected data/root `index.html` are excluded.
- The local development server was verified at port `8999`, but a new PC must
  configure its own `.env`, PostgreSQL database, uploads, and port.
- The root `index.html` remains an unrelated untracked original planner file.
  Its integrated application copy is `app/static/camera-planner.html`. Preserve
  the root file and never stage it.
- Preserve `.env`, databases, uploads, `dist`, ignored installer prerequisites,
  and `D:\ServiceManagement`. None belongs in ordinary source commits.

## Previous handoff — 2026-08-04

- The latest source release is committed on `main` at `bfdb305` and pushed to
  `origin/main` (`KarimHeshamZein/Service-Management`). A documentation-only
  handoff commit may follow it.
- The latest tested offline installer is `1.1.0-rc22`. Its ignored local files
  are `dist/service-management-offline-1.1.0-rc22.zip` and the adjacent
  `.zip.sha256` file. The ZIP is about 532 MB and cannot be stored in ordinary
  GitHub source history. Its SHA-256 is
  `7df76e79a67eb8a36f329f7230f3eaeb027bac4901d62d07026e60edbe2bb21e`.
- RC22 fixes Repair mode's final release switch. PowerShell previously used
  `Remove-Item` on the `current` directory junction, which requested interactive
  confirmation inside the hidden setup worker. `Set-CurrentRelease` now verifies
  that `current` is a junction and removes only that junction with
  `[IO.Directory]::Delete`; it never traverses or removes the targeted release.
- The repair path has an isolated Windows/PostgreSQL end-to-end regression test.
  It creates a temporary database and install root, performs a real `pg_dump`,
  runs real Alembic migration, backs up uploads and `.env`, replaces the real
  junction, preserves the previous release, and simulates only Windows service
  control and the HTTP health response because the development session is not
  elevated. The focused result after the RC22 fix was
  `20 passed, 1 warning in 25.62s` for `tests/test_release_workflow.py`.
- The complete test suite was not rerun after the last deployment-only fix at the
  user's request to keep iteration fast. Run it before the next product release.
- Recent shipped work also includes Arabic PDF font/shaping support, mixed
  quotation currencies, calculated installation labour, transportation quantity,
  Pricing Items as the single service-entry equipment catalog, browser password
  manager support, and Service Console/firewall corrections for LAN access.
- The development/test installation used during installer troubleshooting was
  under `D:\ServiceManagement`, commonly on application port `8995`. Treat that
  as external machine state, not repository configuration. Never modify or remove
  it unless the user explicitly asks.
- `index.html` in the repository root is currently an unrelated, untracked
  "Camera Installation Planner" file. Preserve it and do not stage, edit, or
  delete it unless the user explains that it belongs to this project.

### Resume checklist

1. Read this file and `README.md`, then run `git status --short --branch` and
   `git log -3 --oneline --decorate`.
2. Confirm the requested work and report the proposed change before editing.
3. If the current branch is `main`, safely update it and create a new task
   branch before editing any tracked file. Never develop directly on `main`.
4. Preserve ignored deployment bundles, local `.env`, databases, uploads, and
   the external Windows installation.
5. Use Alembic for every schema change; never run migrations against the
   development or deployed database without explicit permission.
6. For installer work, add or update a repeatable repair/install regression and
   test the exact packaged payload before asking the user to try another RC.

## Working agreement

1. **Read → report → fix.** Investigate and report findings first. Do not edit
   files during a review or research phase.
2. **Wait for explicit approval** before making changes. State what you intend to
   change and why, then stop.
3. **Never develop on `main`.** Create a fresh task branch from the latest
   safely fast-forwarded `main`; merge it through a pull request.
4. **Ask before adding any dependency.** The dependency list is deliberately small.
5. **Run `python -m pytest` before and after every change.**

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
- **New Installation records require a Project-matched quotation reference.**
  Preventive Maintenance and Maintenance are independent from quotations. Store
  both the nullable FK and quotation-number snapshot for Installation so older records remain
  compatible and quotation deletion does not erase the historical Installation identifier.
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
