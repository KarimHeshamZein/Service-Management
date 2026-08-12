# Service Management System — Project Handoff

Updated: 2026-08-12

This file is the portable context for continuing development on another PC or
with another Codex account. It is committed with the source. A new agent must
also read `AGENTS.md`, `CLAUDE.md`, and `README.md` completely before acting.
For a step-by-step Windows setup after copying the project folder, follow
`NEW_PC_SETUP.md`. To have Codex execute that setup, use the complete prompt in
`NEW_PC_CODEX_PROMPT.md`.

## Quick resume prompt

Give the next Codex session this instruction:

> Continue development of the Service Management System. Before doing anything,
> read AGENTS.md, CLAUDE.md, README.md, and PROJECT_HANDOFF.md completely. Run
> `git status --short --branch`, `git log -5 --oneline --decorate`, and
> `alembic heads`. Treat the Current handoff in CLAUDE.md and PROJECT_HANDOFF.md
> as authoritative. Preserve .env, databases, uploads, dist artifacts,
> D:\ServiceManagement, and the unrelated root index.html. Treat main as
> integration-only: never develop or commit directly on it. Before any approved
> change, update main safely and create a new descriptive feature/fix/docs
> branch from it; push that branch and merge only through a pull request after
> approval and testing. Report the state and propose a plan before editing.

## Repository and branch

- GitHub: `https://github.com/KarimHeshamZein/Service-Management.git`
- Primary integration branch: `main`; never develop or commit directly on it.
- Every task must use a new descriptive `feature/*`, `fix/*`, or `docs/*` branch
  created from the latest safely fast-forwarded `main`, then merge through a
  GitHub pull request after approval and testing.
- Hierarchical reporting was merged to `main` in `d80aba9`; the commit
  containing this refreshed file may be newer and is the latest handoff state.
- The root `index.html` is an unrelated original Camera Installation Planner
  source file. Its functionality has already been integrated into
  `app/static/camera-planner.html`; do not add, edit, or delete the root file.
- Offline deployment ZIPs are intentionally ignored because they are about
  510 MB each.

## Product purpose

The application is a FastAPI/PostgreSQL field-service evidence and quotation
system. Administrators manage master data and deployment settings. Technical
users submit installation and maintenance evidence and may receive Pricing
access. Customers can only view records, reports, and protected media for their
assigned Projects.

It currently records completed work. It does not yet implement work orders,
scheduling, dispatch, contracts, stock control, notifications, or a task-status
workflow. Those remain future scope unless the user explicitly requests them.

## Technology and architecture

- Python 3.11+
- FastAPI with server-rendered Jinja2 templates
- SQLAlchemy 2.0 and PostgreSQL
- Alembic-only production schema management
- Vanilla JavaScript and CSS; no npm or frontend build
- Pillow-protected uploads and thumbnails
- ReportLab PDFs with bundled Arabic font/shaping support
- Pytest regression suite using isolated test databases/uploads

Core locations:

- `app/models.py` — ORM entities
- `app/routers/` — authorization-protected routes
- `app/templates/` — HTML interface
- `app/static/js/app.js` and `app/static/css/app.css` — frontend behavior
- `app/pricing_pdf.py` — quotation PDF
- `app/quotation_planner.py` — planner validation
- `app/static/camera-planner.html` — embedded offline planner
- `app/maintenance_items.py` — unified service-item resolution
- `alembic/versions/` — schema history
- `scripts/New-OfflineBundle.ps1` — full offline deployment ZIP

## Current implemented state

### Project hierarchy and saved service reports

- The hierarchical reporting work is merged into `main` and approved.
- The existing Project model and URLs are preserved as Main Projects.
- Main Projects now have optional description, start date, and end date.
- Additive Sub Projects organize assignments to the existing global Site
  catalog; no parallel Site or customer system was introduced.
- Existing Customer-to-Project assignments remain the authorization boundary
  and automatically cover descendant Sub Projects and Sites.
- The Project page is a searchable Main Project → Sub Project → Site hierarchy
  with customer-user names, record counts, metadata, Sub Project controls, and
  Site assignment controls.
- Existing databases receive a `General` Sub Project under every Main Project,
  containing every previously selectable Site. Fresh development seeding builds
  the same hierarchy.
- Installation, Maintenance, and Preventive Maintenance entry use one selected
  Main Project → Sub Project → Site scope. Saved reports explicitly aggregate
  selected authorized records across one or many hierarchy branches.
- Saved reports retain their own number, name, report date, fixed creator,
  separately selected Team Leader, technicians, record links, and hierarchy/
  customer snapshots. Customer access requires every linked Main Project to be
  assigned to that Customer user.
- All three Data Entry workflows now use browser-entered per-Site tables instead
  of requiring technicians to download, fill, and upload an Excel workbook.
  Historical confirmed Excel snapshots remain readable as a report fallback.
- Before/after evidence accepts ordered descriptions shown on record pages and
  in saved report PDFs.

### Pricing and quotations

- Pricing Items are the shared item catalog for quotations and service entry.
- Items have protected images, thumbnails, SAR/USD pricing, optional related
  items, active status, and a service-entry flag.
- User-managed item categories can be created and renamed. Existing and new
  items may be assigned or left Uncategorized. Categories in use cannot be
  deleted. Item searches include category names.
- Quotation and Data Entry item pickers show searchable image cards grouped by
  category.
- Quotation main items are numbered sequentially in the form, saved detail, and
  PDF.
- Any quotation line may be an alternative to another line. Multiple lines may
  point to the same primary item. All quantities and prices remain visible and
  independent. Self-links and circular links are rejected.
- Saved quotations retain immutable project, seller, item, price, currency, and
  image snapshots.
- Required manpower, transportation, and calculated installation charges are
  retained. Mixed-currency quotations intentionally have no aggregate total.
- Site-survey layout images may be uploaded when creating/editing a quotation.
- Multiple post-purchase invoice proof images may be selected and uploaded in
  one action. Pending-selection warnings appear only after files are selected.

### Camera installation planner

- Embedded inside Create/Edit Quotation and stored with the quotation.
- Supports camera types and plan-width controls.
- Supports smart barriers, generators, solar poles, solar panels, guard rooms,
  white/black metal poles, signs, and front/side tree-pole variants.
- Cameras can be grouped/mounted on solar poles.
- The saved quotation and PDF include the rendered plan and equipment schedule.
- Planner assets are local/offline; no external frontend dependency is required.

### Service entry

- New Installation accepts active Pricing Items marked for service entry and
  retains the searchable image-card picker. Preventive Maintenance and
  Maintenance intentionally have no Item selector; their work cards begin with
  Service Performed and do not create an installed-asset link.
- Grouped multi-item records retain per-item results, notes, and evidence.
- Each Installation Site has an add/remove-row device table with Item/Device
  Name, Model, Serial Number, IMEI, SIM Serial Number, SIM Type, immutable
  Main/Sub/Site scope labels, and Remarks. Selecting an Installation Item
  prefills its row name/model; entered identifiers become part of the saved
  installation/asset snapshot.
- Each Preventive Maintenance and Maintenance Site has the exact browser table
  `No / Item / Quantity / Notes`. These independent rows do not link assets.
- All three entry pages support multiple Site sections across different Main/Sub
  Projects under one parent record number. Every Site section contains its own
  devices/services, before/after evidence, and its own browser data table. Installation Site
  sections additionally retain their Project-matched quotation snapshot;
  Preventive Maintenance and Maintenance do not link to quotations.
  Add another item/service operates inside a Site; Add another Site creates
  another complete section. The atomic save produces one record/ID for the full
  visit.
- Optional report data tables use browser-entered rows and are separated by a
  single-line `MAIN PROJECT | ... SUB PROJECT | ... SITE | ...` header.
  Historical Excel-imported snapshots remain a fallback. The report picker
  supports inclusive From/To submission-time filtering down to seconds.
- Preventive Maintenance and Maintenance PDF cards intentionally omit Model,
  Serial number, and Maintenance notes. They retain Service, Result, Issue
  found, Recommendations, and photo evidence. Installation PDFs are unchanged.
- Completed records remain controlled snapshots with append-only revision audit
  behavior as documented in `CLAUDE.md`.

### Authentication and interface

- Login retains browser password-manager-compatible autocomplete attributes.
- Login includes an accessible Show password / Hide password control.
- The shared application shell provides Quick Create, icon-led accordion
  navigation, a persistent desktop top bar, consistent controls, and mobile-safe
  list tables. Field-service entry uses anchored four-step navigation with
  browser data tables and persistent submit actions. Quotation
  Create/Edit uses anchored sections and a persistent Save action.
- English and Arabic catalogs are maintained; user-entered Arabic is supported
  in PDFs.

## Database state

Current single Alembic head on `main`:

`c8e4f2a91d73`

Recent migrations:

1. `d2e7a4c91b63_add_quotation_line_alternatives.py`
2. `f3a8d7c52e14_add_pricing_item_categories.py`
3. `c4d8e2f71a90_add_project_hierarchy.py`
4. `e9b4c7a21d36_add_saved_service_reports.py`
5. `b7e5d8c41f20_add_entry_device_data_snapshots.py`
6. `f2a6c9d14e73_mark_excel_imported_items.py`
7. `a3f8d1c62b04_add_item_site_scope_snapshots.py`
8. `d5b9e2a74c16_add_addressee_price_history_audit.py`
9. `e7c2a91bd460_make_entry_identifiers_optional.py`
10. `c8e4f2a91d73_add_browser_entry_data_rows.py`

Always run `alembic upgrade head` after pulling and before starting updated
application code. Never run migrations against a development or deployed
database without explicit user permission. Normal startup never creates schema
objects.

## Latest verification

- The old full-suite baseline was `356 passed, 1 warning`; do not treat that
  count as current because the suite has grown.
- Latest browser-entry/migration/report focused gate: `11 passed, 1 warning`.
- Latest offline release-workflow gate: `20 passed, 1 warning`.
- Latest maintenance PDF field-removal gate: `1 passed, 1 warning`, followed by
  a successful visual render inspection.
- The warning is Starlette's existing TestClient/httpx deprecation warning.
- `python -m compileall -q app alembic/versions` passed.
- `node --check app/static/js/app.js` passed.
- `git diff --check` passed before commit.
- After the approved local migration/restart, authenticated HTTP checks returned
  200 for Projects, all three service-entry forms, and all three new saved-report
  creation screens on port 8999.
- The current focused quotation addressee, price-history, audit, and Alembic
  gate is `9 passed, 1 warning`. The local database is migrated to
  `d5b9e2a74c16`, and `/login` returns HTTP 200 on port 8999.
- Source and local development database head `c8e4f2a91d73` supports optional
  serial/warranty/notes, browser-entered per-Site tables, and complete
  report-tree expansion across a record's hierarchy scopes. Port 8999 was
  restarted and returned HTTP 200 after the approved migration.

## Latest offline deployment artifact

- Version: `1.1.0-rc33`
- Local ignored filename: `dist/service-management-offline-1.1.0-rc33.zip`
- SHA-256:
  `f494123c624279313dba1613c46367c39790e6485a8f1fccf894d564450b1906`
- Size: `535146924` bytes (about 510 MB)
- Outer and embedded ZIP CRCs passed. The package reports Alembic head
  `c8e4f2a91d73`, its PDF source matches the repository, and `.env`, databases,
  uploads, `dist` history, and root `index.html` are absent.

The ZIP is not in GitHub source history. Copy it separately if it is needed on
the other PC. Building another full offline bundle also requires the ignored
Windows prerequisite installers under `tmp/phase7-prereqs/` or equivalent
paths supplied to `scripts/New-OfflineBundle.ps1`.

## Development setup on another PC

1. Install Git, Python 3.11 64-bit, and PostgreSQL.
2. Clone the repository and enter it:

   ```powershell
   git clone https://github.com/KarimHeshamZein/Service-Management.git
   Set-Location Service-Management
   ```

3. Read the four instruction/context files named at the top of this document.
4. Create and activate a virtual environment, then install requirements:

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   ```

5. Create a local `.env` from `.env.example`; use a new strong `SECRET_KEY` and
   the correct local PostgreSQL URL. Do not commit `.env`.
6. Create the database, then run `alembic upgrade head`. Use `python seed.py`
   only for a new disposable development database.
7. Run `python -m pytest -q` before changing code.
8. Start locally with `python run.py`, or use Uvicorn with the desired port.

The database and upload directory are not stored in Git. If the exact local
development data must move to the new PC, transfer it as a deliberate PostgreSQL
backup plus upload-directory copy; never copy or overwrite production data as
part of an ordinary source checkout.

## Deployment safety

- Preserve `.env`, PostgreSQL data, uploads, backups, and current/previous
  versioned releases during updates.
- Treat `D:\ServiceManagement` as external installation state.
- Use the verified installer/update scripts; do not manually copy source over a
  production release.
- Application rollback never automatically downgrades PostgreSQL.
- The Service Console is the supported writer for machine settings, service,
  firewall, fixed LAN IP, and backup configuration.
- Never put production secrets or deployment ZIPs into Git.

## Recommended future roadmap

If the user chooses to expand from evidence management into full field-service
management, the recommended order is:

1. Quotation lifecycle and immutable revisions
2. Work orders separated from final evidence records
3. Customer asset registry with warranty and QR labels
4. Purchasing and inventory movement
5. Preventive-maintenance contracts and recurring work generation
6. Configurable inspection checklists and customer signatures
7. Scheduling, dispatch, SLA dashboards, and notifications
8. Mobile offline mode

Do not introduce this scope automatically. Investigate and obtain explicit user
approval for each phase.

## Non-negotiable working rules

- Read first, report a concrete plan, then edit after authorization.
- Keep `main` integration-only. Never implement, edit tracked files, or create
  development commits directly on it. Create a fresh task branch from the
  latest `main`, push that branch, and merge through a reviewed pull request.
- Never force-push `main` or bypass its GitHub protection.
- Preserve the user's dirty worktree and unrelated files.
- Use `apply_patch` for source edits.
- Use Alembic for every schema change.
- Enforce authorization in FastAPI dependencies, not templates.
- Preserve immutable quotation and service-record snapshots.
- Run focused tests and the full suite for product changes.
- Installer changes require repeatable end-to-end installer/repair testing.
- Do not change the fixed stack or add dependencies without permission.
