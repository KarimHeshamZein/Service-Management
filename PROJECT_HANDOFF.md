# Service Management System — Project Handoff

Updated: 2026-08-09

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
> D:\ServiceManagement, and the unrelated root index.html. Report the state and
> propose a plan before editing.

## Repository and branch

- GitHub: `https://github.com/KarimHeshamZein/Service-Management.git`
- Primary branch: `main`
- The commit containing this file is the latest approved application state.
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

- Work is on `feature/hierarchical-installation-reports` pending final user review.
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
- Installation Reports provide an `.xlsx` template and preview/confirm import.
  Confirmed device rows become Installed Assets; imported device data can be
  included or omitted from the report PDF.
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

- New Installation, Preventive Maintenance, and Maintenance accept all active
  Pricing Items marked for service entry, not only previously installed units.
- Every item selector uses the searchable image-card picker.
- Grouped multi-item records retain per-item results, notes, and evidence.
- All three entry workflows provide a direct-download eleven-column Excel
  template, validated preview, and signed confirmation. The columns are Item /
  Device Name, Model, Serial Number, IMEI, SIM Serial Number, Sim Type, Main
  Project, Sub Project, Site, Remarks, and Status. Phone Number is not part of
  the workbook. Status is calculated by Excel as `Valid` when columns A-J are
  complete and `Invalid` when anything is missing;
  it is not a service-result input and has no dashboard Validation column.
  Valid/Invalid use green/red formatting. Location/Site text, IMEI, and SIM
  Serial Number are accepted as entered without scope or format warnings.
- Installation imports create Installed Assets. Maintenance imports update a
  matched asset only after the approved conflict confirmation; unmatched rows
  remain immutable record snapshots. Saved report PDFs can include these entry
  snapshots.
- All three entry pages support multiple Site sections across different Main/Sub
  Projects under one parent record number. Every Site section contains its own
  devices, before/after evidence, and Excel preview/import. Installation Site
  sections additionally retain their Project-matched quotation snapshot;
  Preventive Maintenance and Maintenance do not link to quotations.
  Add another device operates inside a Site; Add another Site creates another
  complete section. The atomic save produces one record/ID for the full visit.
- Report Device Data tables contain only explicitly Excel-imported snapshots
  and are separated per Main Project. The report record picker supports
  inclusive From/To submission-time filtering down to seconds.
- Completed records remain controlled snapshots with append-only revision audit
  behavior as documented in `CLAUDE.md`.

### Authentication and interface

- Login retains browser password-manager-compatible autocomplete attributes.
- Login includes an accessible Show password / Hide password control.
- The shared application shell provides Quick Create, icon-led accordion
  navigation, a persistent desktop top bar, consistent controls, and mobile-safe
  list tables. Field-service entry uses anchored four-step navigation with an
  expanded Excel section and persistent submit actions. Quotation
  Create/Edit uses anchored sections and a persistent Save action.
- English and Arabic catalogs are maintained; user-entered Arabic is supported
  in PDFs.

## Database state

Current single Alembic head on the feature branch:

`e7c2a91bd460`

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

Always run `alembic upgrade head` after pulling and before starting updated
application code. Never run migrations against a development or deployed
database without explicit user permission. Normal startup never creates schema
objects.

## Latest verification

- Full suite: `356 passed, 1 warning`
- Focused entry/report suite: `8 passed, 1 warning`
- Entry/i18n/migration gate: `110 passed, 1 warning`
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
- Source and local development database head `e7c2a91bd460` supports optional
  serial/warranty/notes, collapsed Excel entry panels, and complete report-tree
  expansion across a record's hierarchy scopes. Port 8999 was restarted and
  returned HTTP 200 after the approved migration on 2026-08-10.

## Latest offline deployment artifact

- Version: `1.1.0-rc28`
- Local ignored filename: `dist/service-management-offline-1.1.0-rc28.zip`
- SHA-256:
  `3ff83476bade9611524dbc94bafc2eae80aefbed976039c1b0732e301625fa9f`
- Size: `534702194` bytes (about 510 MB)
- Payload validation confirmed all three recent migrations and new templates are
  present. `.env`, databases, uploads, `dist`, and root `index.html` are absent.

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
- Preserve the user's dirty worktree and unrelated files.
- Use `apply_patch` for source edits.
- Use Alembic for every schema change.
- Enforce authorization in FastAPI dependencies, not templates.
- Preserve immutable quotation and service-record snapshots.
- Run focused tests and the full suite for product changes.
- Installer changes require repeatable end-to-end installer/repair testing.
- Do not change the fixed stack or add dependencies without permission.
