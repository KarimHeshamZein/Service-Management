# Service Management System — Project Handoff

Updated: 2026-08-31

## Pending review: direct user permissions and resource scopes

Work remains on `feature/department-workspaces`. Permissions are now assigned
directly to each User inside each Department; Department defaults no longer
grant or deny access. Internal User creation requires an active Department and
then opens User Roles & Permissions. That page controls Department memberships,
the primary Department, direct action permissions, view scopes (None, Own,
Selected, All Department), selected Projects, Pricing Categories/Items, and
Warehouses. Create permission always preserves access to the user's own work.
The shared selected-Project list scopes Projects, records, reports, quotations,
and Tasks, but each module still needs its own permission. Project Team only
maintains that selected list; its old per-project capability toggles are gone.
Store custody choices are limited to active Technical users in the current
Department.

Migration `d4f9c2a61b30` is the single head. With approval, the development
database was backed up to
`tmp/phase2-dev-backups/service_management-before-d4f9c2a61b30-20260831-140631.dump`,
migrated to the head, passed `alembic check`, and restarted successfully on
`127.0.0.1:8999`. Administrator live checks passed for Login, Users, and User
Roles & Permissions. No ZIP was built. Full isolated regression: `449 passed, 9 warnings`. Alembic round-trip/schema drift:
`6 passed`. Python compilation, JavaScript syntax, all Jinja templates, and
`git diff --check` pass.

## Superseded design note: Department workspaces, permissions, Projects and Tasks

Work is on `feature/department-workspaces`. Internal users may belong to several
Departments and choose one active workspace; Administrators can enter every
active Department. A permission matrix supplies Department defaults and
per-user allow/deny overrides for every major module/action. Department-owned
Pricing, documents, wiring, Store, Product Evaluations and Tasks are centrally
isolated, while Pricing Categories can be restricted to selected Department
users. Existing data/users migrate into General.

Projects are shared only through explicit cross-Department team memberships
with separate record, report, quotation and task capabilities. The task board
supports assignment/reassignment, Project, priority, due time, status, comments,
in-app notifications and optional SMTP delivery. Project-team additions notify
the user. Notifications switch to the relevant workspace before opening their
target. Department, permission, Project-team and task mutations write detailed
Logs Report context. The screens use card layouts and one-open-at-a-time
accordions to reduce page clutter.

Migration `c1e8a4f72d90` is the single head and passed the isolated six-test
Alembic round trip/schema check. With approval, the development database was
backed up to
`tmp/phase2-dev-backups/service_management-before-c1e8a4f72d90-20260830-171325.dump`,
migrated to `c1e8a4f72d90`, passed `alembic check`, and restarted successfully on
port `8999`; `/login` returned HTTP 200. No ZIP has been performed. Focused passing gates:
auth `39`, Departments/Tasks `9`, reports `30`, maintenance `59`,
installations/admin `64`, Pricing/Store/documents/evaluations `55`, and
i18n/logs/Departments `38`.

## Pending review: Product Evaluations and Testing

Create Order now contains an independent device request, Admin approval, receipt,
assignment and repeat-evaluation workflow. Serial Number identifies the physical
device for later search; every test session retains its assigned user, timing,
results, five ratings, decision, evidence and PDF, while a combined PDF shows the
full device history. Sales and After Sales may be internal users or free-text
external names. Add to Pricing Items only pre-fills the existing item form and
does not link the records. Migration `b9d4f6a21c80` is the single head and passes
the isolated round trip. It was applied to the development database after backup
`tmp/phase2-dev-backups/service_management-before-b9d4f6a21c80-20260829-133829.dump`
and passes `alembic check`. Focused gates: workflow `2 passed`, migrations `6
passed`, and i18n `24 passed`.

## Pending review: Wiring Diagrams

Pricing now includes an independent Wiring Diagrams library with separate Main
and Subcategory folders, optional free-text Project name and notes, multiple
validated PDF/image files, combined preview, individual downloads and ZIP
download. Pricing access permits viewing; a separate permission permits
Technical-user management; only Administrators delete complete diagrams. Its
migration is `a8c5e2f41d70`, applied after a local backup and verified through a
downgrade/upgrade round trip and `alembic check`.

## Pending review: Store and Data Sheet modules

Store is a separate inventory ledger with Main/Branch warehouses, independent
items, multi-item purchases/issues/transfers, Technical-user custody, strict
non-negative balances, immutable movements with reasoned reversal, scoped
action permissions, and on-screen/PDF/Excel reports. Pricing now has a
folder-first Data Sheet library for Main and Related Items, multiple validated
files, branded recommendation PDF, Technical Package ZIP, and optional immutable
quotation snapshots. Migration `f2b7c4d91e63` is applied after backup
`tmp/phase2-dev-backups/service_management-before-f2b7c4d91e63-20260827-102015.dump`;
its downgrade/upgrade round trip and ORM drift check pass. Focused gates: `26
passed` for Store/Data Sheet/i18n and `95 passed` for existing
Pricing/Purchase/Admin/i18n behavior.

## Pending review: actionable Create/Edit validation

Installation, Preventive Maintenance, and Maintenance now treat a browser-added
row as an attempted addition even when its Service was left blank. The Edit
workflow therefore stays on the same record and reports the exact missing field
instead of redirecting with `No changes were made`. A client preflight marks the
field and its Site/service cards in red, shows a contextual English/Arabic reason,
focuses the first problem, and retains the entered fields and selected photos for
correction. Server-side validation remains the final authority and keeps the
saved record atomic. The focused Edit/Append/Autosave gate is `16 passed, 1
warning`; JavaScript syntax and Python compilation pass. No migration or restart
was performed, and browser visual verification is still pending because the
in-app browser connection was unavailable.

## Pending review: shared Purchase Documents and price analysis

Pricing now includes Purchase Documents directly beneath Items. It uses the
same Main Category/Subcategory folders and item images. One purchase invoice or
supplier quotation may contain multiple validated files and link to multiple
Main or Related Items selected across folders without storing duplicate files.
Each linked Item has an independent optional unit price and currency; Item pages
filter the archive and provide hoverable, currency-separated trends plus an
in-tool PDF analysis export. Combined PDF preview, individual download, ZIP
download, role controls, detailed audit events, and safe orphan cleanup are
covered by focused tests. Migration `c6a4e8f21d90` is created but has not been
applied to the development database, and the service has not been restarted.
The focused cross-feature gate is `42 passed, 1 warning`; compile, JavaScript
syntax, migration round-trip/metadata drift, and diff checks pass. In-app
browser visual verification was unavailable in this session.

## Pending review: isolated customer-report redesign Part 1

Administrators now see an `Open design preview` action beside the unchanged
official PDF actions. The isolated Part 1 PDF contains only a redesigned cover
and executive summary built from the saved report's real data. It uses the
existing horizontal AFAQY logo plus a light AFAQY watermark on both pages and is
clearly marked as a non-final design preview. The official renderer and routes
are untouched. No dependency, database, or migration change was made. The
focused access/PDF/i18n gate is `25 passed, 1 warning`; both pages were rendered
to PNG and visually inspected.

## Pending review: Pricing Item folder assignment

Add/Edit Pricing Item uses a shared Category folder picker instead of a flat
dropdown. It shows every Main Category as a folder, opens one Main Category to
show its smaller teal Subcategory folders, and provides Back, direct Main
Category selection, and Uncategorized. The selected path is shown on the form
and is persisted only when Create/Save is submitted; editing therefore uses the
same UI to move an existing Item between folders. No migration is required. The
full Pricing gate is `41 passed, 1 warning`; the focused hierarchy/i18n gate is
`25 passed, 1 warning`, and JavaScript syntax passes.

## Pending review: two-level Pricing categories

Pricing supports Main Categories with one level of smaller teal Subcategory
folders. Existing Categories remain Main Categories. In Items, a Main Category
shows its Subfolders first and its directly assigned items below; a Subcategory
shows only its own items. Create Quotation uses the same hierarchy in a compact
picker with one-level Back navigation. Migration e7c3a1b95d42 adds only a
nullable self-reference and does not move existing data. The focused Pricing
and Alembic round-trip/ORM-drift gate is 42 passed, 1 warning. The development
database was backed up to
`tmp/phase2-dev-backups/service_management-before-e7c3a1b95d42-20260825-133148.dump`,
migrated to `e7c3a1b95d42`, and restarted successfully on port 8999 on
2026-08-25. All three existing Categories and all four Pricing Items were
verified after migration.

## Pending Pricing Items category browser

Pricing Items now opens with responsive folder-style Category cards rather than
rendering every item in one long table. Opening a Category displays only its
items; Back to categories returns to the folder grid, and Uncategorized has its
own folder. Searches work across all Categories from the overview and remain
scoped when started inside a Category. Existing management and price-history
features remain intact. Create Quotation uses the same folder-first navigation
inside its item-selection dialog, including Back to categories and cross-folder
search. No migration is required. The focused Pricing/i18n gate is `64 passed,
1 warning`; the quotation-picker gate is `27 passed, 1 warning`.

## Pending unified Logs Report

Work now continues on `feature/logs-report`. Administrators have one
Management -> Logs Report page combining application/user audit searches and
Technician Activity. Both views remain blank until the Administrator supplies a
search criterion and selects Search. Activity filters use second-precision
display-time bounds and can export the complete match to PDF or Excel;
Technician Activity retains PDF and adds a three-sheet Excel export. The old
Audit Log and Technician Activity navigation entries were removed and their
page URLs redirect to the new location. Change history is no longer rendered on
Installation, Preventive Maintenance, or Maintenance record details; revisions
remain stored and are available only through Logs Report. No migration is
required. The focused gate is `45 passed, 37 deselected, 1 warning`, plus
`9 passed, 1 warning` for record-detail visibility.

## Pending long-entry autosave and Edit correction

Work now continues on `fix/record-edit-autosave-drafts`. Installation,
Preventive Maintenance, and Maintenance Create/Edit forms autosave private
server-side drafts for seven days, retain selected photos in same-browser
IndexedDB, expose a Data Entry -> My drafts page, and renew the authenticated
session every four minutes. Edit-table clones preserve their saved Site position,
fixing the observed `Table row ... is not assigned to a valid Site` rejection.
Failed additions keep the original record unchanged.

Migration `d8f4a6c21e90` adds `entry_drafts`. The focused workflow, access, i18n,
and Alembic gate is `169 passed, 1 warning`. Source validation is green. With
approval, the development database was backed up to
`tmp/phase2-dev-backups/service_management-before-d8f4a6c21e90-20260823-165434.dump`,
migrated to `d8f4a6c21e90`, and restarted on port 8999. Authenticated HTTP checks
passed for Preventive Maintenance, My drafts, and the draft API.

## Pending Photo Guidance Profiles feature

The current `feature/project-photo-guidance-profiles` worktree redesigns Photo
Guidance as independent, named, Main-Project-scoped profiles such as `Solar
Solution`. Profiles no longer select or depend on Pricing Items or Installed
Assets. Each device/service card in Installation, Preventive Maintenance, and
Maintenance Create/Edit has one optional profile selector. Before/After alerts
and reusable descriptions guide the technician, while only the final editable
photo description is saved as evidence and printed in reports.

Alembic revision `b4e8d3c71a26` migrates the older item-linked rules into named
profiles and adds nullable saved-profile references to all three work-item types.
The migration and focused workflow gate pass. With approval, the development
database was backed up to
`tmp/phase2-dev-backups/service_management-before-b4e8d3c71a26-20260819-032403.dump`,
migrated to `b4e8d3c71a26`, and restarted on port 8999 with reload disabled.
Authenticated HTTP checks passed for the profile-management page and all three
data-entry pages.

The same branch also changes newly created Main Projects so their automatic
`General` Sub Project begins without Site assignments. Each Sub Project has a
`Deselect all Sites` action followed by the existing explicit Save action. A
global Back control appears on all authenticated pages with safe Dashboard/All
Records fallback. No migration was required; the focused gate is `62 passed, 1
warning`, and port 8999 was restarted and checked successfully.

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
- Pending on `feature/full-record-editing`, saved report PDFs add large-report
  navigation: clickable hierarchical contents, a searchable Record & Device
  Index, Report Information, per-Site Service Data Tables, Approvals, native
  viewer bookmarks down to devices, and Back to contents links. ReportLab uses
  multi-pass layout so displayed page references stay accurate.
- Customer reports now lead with a compact executive summary and omit the
  Technician list. A clickable Items Requiring Attention section is generated
  only when a result/issue/recommendation needs review; fully successful reports
  show a short no-actions message. Footers say Confidential, and manual
  approvals collect Name, Job title, Signature, and Date.
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
- Grouped multi-item records retain per-item results and evidence. Installation
  retains its notes; maintenance workflows collect optional Issue Found and
  Recommendations without a separate Maintenance Notes input. Historical notes
  stay stored.
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
- Add another item/service, Add another Site, and Add row use an idempotent
  shared JavaScript initializer. Static CSS/JavaScript URLs carry a content
  fingerprint so deployments do not reuse an obsolete cached form script.
- Optional report data tables use browser-entered rows and are separated by a
  single-line `MAIN PROJECT | ... SUB PROJECT | ... SITE | ...` header.
  Historical Excel-imported snapshots remain a fallback. The report picker
  supports inclusive From/To submission-time filtering down to seconds.
- Saved report PDF `Created at` and record `Performed by ... on` timestamps are
  converted from stored UTC to the configured display timezone, matching the
  Records interface. Saved reports render on download, so downloading again is
  sufficient; previously downloaded PDF files remain unchanged.
- Preventive Maintenance and Maintenance PDF cards intentionally omit Model and
  Serial number. They retain Service, Result, photo evidence, and any non-empty
  historical Maintenance Notes, Issue Found, and Recommendations rows; empty
  optional labels are not printed. Installation PDFs are unchanged.
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

- Version: `1.1.0-rc43`
- Local ignored filename: `dist/service-management-offline-1.1.0-rc43.zip`
- The authoritative SHA-256 is stored in the adjacent ignored
  `service-management-offline-1.1.0-rc43.zip.sha256` file. Its value is
  `07dd093a7e493c5683bc008959d0811e333424f8cc946c9363152e6de91fb55e`.
- Size: 510.57 MB (`535373941` bytes).
- The focused Pricing and release-workflow gate passed `61 passed, 1 warning`.
  Outer and embedded ZIP CRCs passed. The package includes Alembic migration
  `e7c3a1b95d42`, and `.env`, databases,
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
