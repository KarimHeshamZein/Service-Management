# UI/UX and business-logic review

## Batch 1 — 2026-10-06

Scope: application map, Pricing Items/category hierarchy, and directly related
selection, permissions, search, and move behavior. This is not an assessment of
the whole application's quality. Implementation is not authorized.

Reviewed baseline: working tree at `3df505a` on
`feature/department-workspaces`, including the user's existing uncommitted
three-level category and quotation-description work. Documentation was saved on
`docs/ui-ux-review-batch-1`, branched from that current state to preserve the
reviewed work. No commits, staging, push, application edits, migration, service
restart, or changes to existing databases/uploads were performed.

Read `CLAUDE.md`, `README.md`, and `PROJECT_HANDOFF.md`. Older statements about
two-level categories and Department default permissions are superseded by the
current code and the latest CLAUDE handoff. Older handoff test counts are not
verification results from this review.

Progress and proposed implementation phases: [separate tracker](ui-ux-improvement-plan.md).

Batch 2 was added on 2026-10-07 below. Its access and data-preservation findings
take priority over the initial Batch 1 implementation order. Batch 1 evidence
remains a dated record; none of its proposed changes has been implemented.

## Assessment of the reviewed area

The catalogue can remain on the existing stack and schema. The main friction is
in locating destinations, separating ordinary editing from transfers, recovering
from errors, and explaining permission effects. Removing hierarchy levels would
not fix the confirmed failures below.

There are four high-impact functional findings (CAT-001 through CAT-004), followed
by practical workflow improvements. Existing strengths include server-side
authorization, cycle/depth checks, immutable quotation snapshots, and rejection
of transfers that would split shared purchase documents. Preserve those controls.

Preliminary direction: retain optional three-level folders and existing IDs;
repair category editing and scoped navigation first; make access wording truthful;
then offer one clear destination picker and atomic multi-item moves. No rewrite,
visual redesign, flattening migration, or automatic data reorganization is proposed.

## Application map and representative workflows

This map comes from the shared navigation (`app/templates/base.html:25`), router
registration (`app/main.py:74`), targeted route inspection, and architecture docs.
Rows marked mapped have not received a deep workflow review.

| Area | Representative workflow and relationships | Batch 1 coverage |
| --- | --- | --- |
| Sign-in, account recovery, language, workspace | Sign in; select Department; navigate through permission-aware sidebar/Quick Create; switch English/Arabic | Mapped; authentication used only with disposable users |
| Dashboard | Review summary then open work/records | Mapped |
| Projects and master data | Main Project → Sub Project → assigned Site; Project team/customer access; photo guidance; services | Mapped |
| Data Entry | Installation selects Project-matched quotation and service-enabled Pricing Item; maintenance/preventive work captures services/evidence; multi-Site entry, drafts and optional imports | Mapped; item-picker dependency inspected |
| Records and assets | Find installation/preventive/maintenance evidence; inspect/edit controlled records and asset history | Mapped |
| Reports | Filter records; select saved-report evidence; preview/download PDF; customer-scoped access | Mapped; snapshot dependencies inspected |
| Pricing Items | Department → category folders → Items; create/edit/deactivate; related items and price history; recategorize/transfer | Deep code review and targeted isolated HTTP/ORM probes |
| Quotations and planner | Project and addressee → select main/related items → quantities/prices/charges → planner/evidence → saved snapshot/PDF/package | Category selection and snapshot boundary only |
| Purchase Documents | Shared invoice/quotation → attach files and multiple main/related items → browse/search/price analysis | Category browser and transfer dependency only |
| Data Sheet | Item → files/current recommendation → PDF/ZIP; optional quotation snapshot | Category browser and transfer dependency only |
| Wiring Diagrams | Independent category library → diagram/files → preview/download | Mapped; independent from Pricing categories |
| Store | Independent item catalogue → warehouse receipt/issue/transfer → custody/return → reports/reversal | Mapped |
| Product Evaluations | Request → decision → receive serial-numbered device → assign/start/finish repeat evaluation → reports; optional Pricing prefill | Mapped |
| Tasks and notifications | Assign/reassign → status/comments → notification opens relevant workspace | Mapped |
| Users, Departments, permissions | Membership → direct actions and module scopes → selected Projects/Categories/Items/Warehouses | Pricing scope inspected; wider model pending |
| Logs and operational settings | Search activity/technician work; inspect/export; read-only deployment status; separate local Service Console | Mapped; installer operations excluded from this batch |

## How the category model actually works

- A category has a nullable parent and belongs to one Department. Maximum depth
  is two edges: Main Category → Subcategory → Sub-subcategory. Items may be
  assigned directly at any level, or be Uncategorized. Related Items belong to
  a main Item and inherit its folder context; they are not another category level.
  Evidence: `app/pricing_categories.py:8`, `app/models.py:1972`, `:2271`.
- Folder counts include descendants, while ordinary opened-folder item rows are
  direct children. Searching an opened Items folder includes descendants.
  Evidence: `app/routers/pricing.py:371`, `:601`.
- Add Main Item defaults to the opened category. Recategorization is inside the
  complete item Edit form. The category picker starts from roots, opens each
  level, and requires “Select this Category,” then “Save main item.”
- Reparenting a category is in Manage categories → Category level → Save.
  It preserves the branch and IDs. The backend excludes self/descendant parents,
  cross-Department parents, and moves whose resulting subtree exceeds three levels.
  Evidence: `app/routers/pricing.py:349`, `:868`.
- An Administrator can transfer one Item or an entire category branch to another
  Department. A single Item becomes Uncategorized. A transferred category becomes
  a root; its descendants stay attached. There is no target-folder selection in
  these transfers and no arbitrary multi-item move endpoint.
- Category deletion requires no direct Items and no child categories. Moving
  contents is therefore necessary before deleting a populated folder.
  Evidence: `app/routers/pricing.py:935`.

The three-level test uses Cameras → Hikvision → Hikvision Cameras/Access Control
(`tests/test_pricing.py:939`). This proves supported behavior, not a measured
business requirement. The usefulness of depth, and whether brand/type should
instead become filters, needs a small representative taxonomy and user examples.
Do not flatten existing data based on this review alone.

### Representative effort, derived from controls rather than timed user tests

From the sidebar, a deepest-folder Item requires Department selection and three
folder openings. Once the Item is visible, moving it to another deepest folder
requires Manage → Choose category → three folder openings → Select this Category
→ Save main item (seven actions). Save returns to the overview. Repeating this
for many Items compounds both navigation and full-form editing. Search can shorten
item discovery, but the destination picker itself has no search.

## Findings

Severity: High blocks a common operation or materially misleads access decisions;
Medium causes repeated friction or avoidable mistakes; Low is an optimization
without demonstrated operational impact. “Confirmed in code” may include isolated
HTTP/ORM reproduction; it never means observed in a real browser.

### CAT-001 — Category Save/Delete depend on an unrelated Department field

- **Area/classification/severity:** Items → Manage categories; functional defect;
  High. Administrators with more than one active Department cannot submit an
  ordinary rename/reparent or deletion while the Department destination is blank.
- **Reproduction:** Open Manage categories with two active Departments. Rename a
  category and click Save without selecting a target Department. The same form
  contains a required, initially empty `target_department_id`. Save and Delete do
  not bypass validation; Move alone has `formnovalidate`.
- **Evidence/status:** Confirmed in code and generated HTML, not browser-observed.
  `app/templates/pricing_items.html:54–68`; the probe confirmed the required select
  and absence of `formnovalidate` on Save. Category edit does not use that field
  (`app/routers/pricing.py:869`). The individual Item transfer is already a separate
  form (`app/templates/pricing_items.html:239`).
- **Recommendation/benefit:** Separate category edit, transfer, and deletion
  submissions. Ordinary Save must require only fields it actually uses.
- **Tradeoffs/data:** Small template change; no migration. Retain CSRF, server
  validation, branch checks, and transfer confirmation. Browser verification is
  necessary because TestClient does not execute native form validation.

### CAT-002 — Selected access to a nested category creates an unreachable folder

- **Area/classification/severity:** Pricing scoped navigation; functional defect;
  High. Users can have authorized Items that are absent from the root browser.
- **Reproduction:** Grant a Technical user Selected Pricing scope and only the
  leaf Outdoor under Security/Cameras. `/pricing/items` returns 200 without a
  Security folder link. `/pricing/items?category=<Outdoor>` returns 200 and the
  authorized Item. Its Back destination Cameras returns 404.
- **Evidence/status:** Confirmed in code and isolated HTTP/ORM reproduction.
  `app/database.py:103–147` includes ancestors for individually granted Items,
  but not ancestors of granted Categories; `app/routers/pricing.py:694` constructs
  roots from visible categories with null parents. Back uses saved parent IDs
  (`app/templates/pricing_items.html:167–184`).
- **Recommendation/benefit:** Include navigation-only ancestors for granted
  Categories, as for individually granted Items. Render a continuous path without
  widening access to sibling or ancestor Items.
- **Tradeoffs/data:** No migration expected. Test nested grants, direct grants,
  Own scope, and managers with partially visible branches; fixing navigation must
  not accidentally authorize editing previously hidden ancestors.

### CAT-003 — “Selected users only” does not restrict Department-scope readers

- **Area/classification/severity:** Category access configuration; functional
  defect in the UI/business-rule contract; High. The screen suggests a restriction
  that the current permission model does not enforce.
- **Reproduction:** Set Outdoor visibility to “Selected users only” and grant
  user A. A different Technical user with All Department Pricing scope can still
  retrieve the folder and its Item.
- **Evidence/status:** Confirmed in code and isolated HTTP reproduction.
  `app/templates/pricing_items.html:46–63`,
  `app/routers/pricing.py:838–928`, `app/database.py:134–157`.
  Department scope deliberately permits all category/item rows regardless of
  `visibility`; the same category-grant table is also edited by User Roles &
  Permissions (`app/routers/departments.py:566`).
- **Recommendation/benefit:** Align the category screen with the approved direct
  per-user model. Prefer explaining selected-scope grants or linking to the
  authoritative permissions page. Do not call them an exclusive restriction.
- **Tradeoffs/data:** This is not evidence that the backend violates the intended
  All Department policy. Adding a new deny rule would be a material policy change.
  Preserve existing grants and legacy visibility values until the next permission
  review determines the exact UI and compatibility behavior.

### CAT-004 — A branch transfer can fail with HTTP 500 on an Item-name collision

- **Area/classification/severity:** Category → Move to Department; functional
  defect; High. A valid-looking operation ends in a generic failure.
- **Reproduction:** Department A contains Security/Outdoor → Camera Alpha, model
  A. Department B already has Camera Alpha, model A, but no Security root. Transfer
  Security to B. The isolated POST returned 500; the original category and Item
  remained in A.
- **Evidence/status:** Confirmed in code and isolated HTTP/ORM reproduction.
  Branch transfer checks only the destination root-category name before moving
  all Items (`app/routers/pricing.py:970–1014`). The database enforces Item
  Department/name/model uniqueness (`app/models.py:2329`). Single-item transfer
  already checks its Item collision (`app/routers/pricing.py:1280`).
- **Recommendation/benefit:** Preflight all descendant Item conflicts and report
  exact conflicting Items/paths; handle a concurrent uniqueness conflict with
  rollback and an actionable response. Never merge same-named Items automatically.
- **Tradeoffs/data:** No migration expected. Preserve atomicity and existing
  identifiers, documents, snapshots, and access grants when any conflict occurs.

### CAT-005 — No multi-item move, despite recovery advice to move Items together

- **Area/classification/severity:** Item reorganization and shared-document
  transfers; usability problem; Medium.
- **Example:** Move ten selected Items from several folders. Each needs its own
  full Edit submission. Two Items sharing one purchase document cannot transfer
  independently; the error advises moving them together, but only a whole category
  branch provides that operation. Regrouping them into a temporary branch is an
  indirect workaround that can itself change selected-category access.
- **Evidence/status:** Confirmed in code. Item table has no row-selection/bulk-move
  controls (`app/templates/pricing_items.html:196–239`); routes accept one Item or
  one category (`app/routers/pricing.py:970`, `:1262`). Shared-document protection
  is in `:538–569`; existing test source covers refusal
  (`tests/test_departments_and_tasks.py:468–523`, not rerun in this batch).
- **Recommendation/benefit:** First add same-Department multi-item recategorization
  using a selected-ID set and one destination. Later add Administrator transfer of
  an explicit group, with shared-document dependency preview.
- **Tradeoffs/data:** Keep all-or-nothing mutation, explicit selection counts, and
  permission rechecks. Never silently add other Items to a transfer or split a
  shared document. Cross-Department work depends on Batch 2.

### CAT-006 — Destination selection is slow and fragmented

- **Area/classification/severity:** Item/category moves and discovery; usability
  problem; Medium.
- **Example:** A same-Department Item move is hidden in full Edit; its picker always
  opens at roots and has no search. A branch move uses a flat Category level select.
  Department transfer uses another control and cannot choose a destination folder.
  Full path text and one-level Back exist, but ancestors are not clickable breadcrumbs.
- **Evidence/status:** Confirmed in code. `app/templates/pricing_items.html:4`,
  `:58`, `:167`, `:231`, `:288–333`; `app/static/js/app.js:680–694` resets the
  picker to roots on every opening. Items navigation always opens Department
  folders (`app/templates/base.html:82`, `pricing_department_folders.html:14`).
- **Recommendation/benefit:** A dedicated Move action with searchable destination
  paths, current-folder starting position, clickable ancestors, and an explicit
  source → destination summary. Offer direct access to the active Department with
  an obvious workspace switcher; validate this shortcut with users.
- **Tradeoffs/data:** Preserve folder browsing, keyboard operation, RTL, and backend
  depth/cycle checks. Differentiate navigation from committing a move. No automatic
  flattening; cross-Department target-folder support is a later structural phase.

### CAT-007 — Validation failures and successful edits discard working context

- **Area/classification/severity:** Item/category forms; usability problem; Medium.
- **Reproduction:** Submit an Item edit with a changed description and invalid
  price. The response redirects to `/pricing/items`; the new description is gone.
  Ordinary successful edits also return to the overview rather than the edited
  Item's folder/search. Native input validation does not cover server-only errors,
  such as a duplicate name/model or invalid upload content.
- **Evidence/status:** Confirmed in code and isolated HTTP reproduction using an
  invalid price. `app/routers/pricing.py:1030–1120`, `:1122–1235`, `:869–931`.
- **Recommendation/benefit:** Re-render the submitted form with field errors and
  preserved text/category, open its panel, and keep a validated local return
  context. After success, show the destination and affected Item with a clear message.
- **Tradeoffs/data:** File inputs cannot simply be repopulated; explain reselection
  or use a separately reviewed retention mechanism. Do not introduce draft storage
  for this small form without evidence. Restrict return URLs to safe local paths.

### CAT-008 — Category search scope differs between related screens

- **Area/classification/severity:** Items, Purchase Documents, Data Sheet, pickers;
  usability problem; Medium.
- **Reproduction:** Place matching Camera Items in Security and Other. Search
  Camera with `category=Security`: Items returns only the Security descendant,
  while Purchase Documents' shared browser returns both. Searching Security from
  the Items root does not find the Camera in Security/Cameras/Outdoor, because
  only its immediate category name participates in the match.
- **Evidence/status:** Confirmed in code and isolated ORM probes: Item IDs `[1]`
  versus document-card IDs `[1, 2]`; ancestor-name Items search returned `[]`.
  `app/routers/pricing.py:640–672`, `purchase_documents.py:159–182`,
  `technical_documents.py:57–58`. Quotation picker matches full paths
  (`app/templates/pricing_quotation_form.html:93`); service picker groups/searches
  immediate category names (`app/templates/partials/service_item_picker.html:9–14`).
- **Recommendation/benefit:** Explicit “This folder and subfolders / All folders”
  scope and consistent full-path matching in catalogue screens. Label descendant
  search results appropriately instead of “Items directly in this Category.”
- **Tradeoffs/data:** Global results must remain within authorized resource and
  Department scope. Decide whether related-item matches appear as separate rows;
  do not duplicate or reparent related Items to make search consistent.

### CAT-009 — Read-only users are offered editable forms that return 403

- **Area/classification/severity:** Items → Manage and Related Items; usability
  problem; Medium. Users spend effort on actions they cannot complete.
- **Reproduction:** Sign in with Pricing view/All Department scope and no manage
  permission. Open an Item's Manage panel: the edit form and Save are present.
  Posting the form returns 403.
- **Evidence/status:** Confirmed in code and isolated rendered-HTML/HTTP probes.
  `app/templates/pricing_items.html:210–274` renders edit forms outside the manage
  condition; `app/routers/pricing.py:1128`, `:1461` enforce management permission.
- **Recommendation/benefit:** A read-only Details/history panel for viewers; render
  editable fields/Save only for authorized managers, including Related Items.
- **Tradeoffs/data:** Retain server checks. Do not hide useful history or weaken
  authorization to make an already-visible Save button work. No migration.

### CAT-010 — Transfer confirmation omits access and linked-resource consequences

- **Area/classification/severity:** Cross-Department transfer; usability problem;
  Medium, with permission implications.
- **Example:** Confirm a category transfer expecting a location change. Its main
  and related Items, attached purchase documents where wholly contained, technical
  documents, and recommendations move Department. Category and individual Item
  grants are cleared. A child category becomes a root. The prompt mentions only
  the category/subcategories/Items.
- **Evidence/status:** Confirmed in code, not a live transfer UI observation.
  `app/routers/pricing.py:538–593`, `:1000–1010`, `:1293`;
  `app/i18n/en.py:1822–1824`. Same-Department recategorization also changes access
  for Selected-category users because access follows the current hierarchy.
- **Recommendation/benefit:** Preflight source/destination paths, item/descendant
  counts, linked-document effects, blocked shared links, and grant removal. Require
  explicit confirmation and return a destination link and meaningful audit context.
- **Tradeoffs/data:** Keep grant clearing conservative until the permission model
  is reviewed; never silently copy source users into another Department. No undo
  promise until restoration of grants and linked resources is designed. Batch 2
  must verify quotation edit and document download behavior after transfer.

### CAT-011 — Catalogue management loads more data than its initial view needs

- **Area/classification/severity:** Items page scalability; optional improvement;
  Low pending measurement.
- **Example:** Open the root overview with a large catalogue. Although it displays
  folders, context construction fetches Items, related Items, price histories,
  quotation history, a second active catalogue, and all category parent candidates.
  Search results are unpaginated and have no status filter or user-selected sort.
- **Evidence/status:** Confirmed in code for unbounded loading and controls;
  slow response is a hypothesis requiring validation.
  `app/routers/pricing.py:601–757`, `app/templates/pricing_items.html:128–196`.
- **Recommendation/benefit:** Measure representative data first. If needed, load
  folder counts only at overview, fetch history on demand, and paginate results with
  name/status sorting and filters. This can reduce both page weight and clutter.
- **Tradeoffs/data:** Pagination must not make bulk selection ambiguous. Avoid a
  framework change; preserve stable query parameters, authorized counts, and locale
  behavior. No schema/index change is justified without a query plan/measurement.

## Linked-data and safeguard assessment

| Operation | Confirmed behavior | Implication for changes |
| --- | --- | --- |
| Same-Department Item recategorization | Updates category reference through full Edit; IDs remain | Preserve prices, service flags, images and grant semantics in a dedicated move endpoint |
| Category reparent | Reuses category/descendant IDs; validates cycle and full subtree depth | Keep server validation even if UI hides invalid destinations; concurrent/partially scoped edits need future tests |
| Department Item/branch transfer | Moves owned resources; clears selection grants; rejects purchase documents with links outside the group | Preview dependency closure; no partial move or implicit expansion |
| Saved quotation | Separate item/name/description/price/image snapshots (`models.py:2927`, `pricing.py:1852`, `:1973`) | A catalogue move need not rewrite history; post-transfer editing still depends on available source Items and needs Batch 2 verification |
| Technical recommendation | Current PDF uses current category path (`technical_documents.py:50`, `:147`); quotation package has recommendation/file snapshots (`pricing.py:2482–2534`) | Distinguish current library output from saved package; preserve historical package contents |
| Installation | Active service-enabled Pricing Items resolve through legacy device IDs (`maintenance_items.py:35–75`) | Preserve IDs and compatibility rows; category depth is not an installation identity requirement |
| Category deletion | Nonempty/parent categories refused | Retain protection; clarify move-first guidance and destination choices |

No complete report/PDF, media, installation, or quotation-edit regression was run.
Snapshot preservation above is a code-level assessment, not an end-to-end guarantee.

## Verification record and gaps

Used an in-memory Python harness via the repository virtual environment and a new
PostgreSQL database `sms_review_a49ad5ae70354360`. It created disposable schema/data,
two Departments and three users, used FastAPI TestClient plus ORM/helper probes,
then dropped that exact database and removed its temporary upload directory.
Environment values were process-local; dotenv loading was suppressed for the harness.
Application source and test files were unchanged. No existing database was reset.

| Probe | Result |
| --- | --- |
| Cycle and fourth-level parent candidates | Rejected; valid leaf reparent accepted by validator |
| Category Edit HTML with two Departments | Required transfer destination also belongs to ordinary Save |
| Leaf-only selected-category grant | Missing root link; leaf GET 200; parent GET 404 |
| “Selected users only” vs All Department viewer | Other viewer still sees Item |
| Colliding Item inside branch transfer | HTTP 500; source category/Item preserved |
| Invalid item edit | Redirect to root; submitted description absent |
| Viewer edit controls and mutation | Edit form present; POST 403 |
| Same search and category in two browsers | Items `[1]`; document cards `[1, 2]` |
| Items search by ancestor name | No matching descendant Item |

These are targeted diagnostic probes, not a full pytest pass. The standard test
fixture hardcodes `service_management_test` and drops its schema before tests
(`tests/conftest.py:16`, `:79`), so it was not run against that existing database.
The only warning in the harness was the existing Starlette/httpx deprecation warning.

The browser skill was read and a connection attempted; the tool failed before
bootstrap (`missing field sandboxPolicy`). Consequently no finding is labeled
“observed in UI.” Native validation behavior in CAT-001 still needs browser
reproduction; generated HTML and code establish the conflicting requirement.

Native dialog semantics, labels, focus restoration on selection, responsive folder
CSS, and reduced-motion rules exist (`pricing_items.html:288`, `app.js:723`,
`app.css:1198`, `:1607`). Their presence does not establish accessibility. Pending:
keyboard Escape/Close/focus sequence, screen reader names/errors, zoom, touch,
320/375px layouts, Arabic RTL/long paths, contrast, and large-catalogue latency.

Open business questions for later review: which real taxonomy needs three levels;
whether most moves stay within a Department; intended management rights over
navigation-only ancestors; whether Category access should be removed from this
screen under the direct-user design; expected treatment of shared documents and
quotation editing after a transfer. These are decision inputs, not assumptions.

## Priorities and next batch

1. Quick repairs: isolate category forms and remove impossible viewer edits
   (CAT-001, CAT-009).
2. Scoped navigation and truthful access controls (CAT-002, CAT-003).
3. Branch-transfer conflict handling (CAT-004), before encouraging larger moves.
4. Same-Department destination/search/error recovery and bulk recategorization
   (CAT-005–008); preserve existing depth and IDs.
5. After dependency review, cross-Department preflight and grouped transfers
   (CAT-005, CAT-010).
6. Measure before optimizing loading/pagination (CAT-011).

All are proposals; phase details and approval gates are in the tracker.
Next review batch: **Pricing permissions and document/quotation dependencies**—
review direct access settings, selected grants, Purchase Documents/Data Sheet
ownership, and existing-quotation editing after catalogue moves. Bound it to those
dependencies; leave pricing arithmetic/planner redesign, Store, and field-service
entry for later batches. Stop here until the user instructs continuation.

## Batch 2 — Pricing access and document/quotation dependencies, 2026-10-07

### Scope and outcome

The user authorized the next review batch, not implementation. Reviewed direct
Pricing actions/scopes, nested and individual grants, the two grant-editing
surfaces, document access and shared links, and quotation behavior after a
Department transfer. Existing code was inspected only as needed for these
dependencies. No repeat of the broad application map or Batch 1 navigation audit.

The working tree still contains the existing product changes over `3df505a`.
Review documents continue on `docs/ui-ux-review-batch-2`, branched from the Batch 1
review state without discarding that work. Only the report and tracker were edited.

**Assessment:** access boundaries and preservation of hidden relationships need
attention before adding larger moves. A scoped catalogue manager can broaden their
own Category grant. Ordinary saves can remove grants, shared-document Item links,
or quotation package snapshots that were not visibly selected for removal.
Transfers themselves preserve saved quotation lines and package files in the
tested case, but subsequent editing is not fully compatible with the new location.

Seven new findings follow. All have code evidence and isolated runtime probes;
none is browser-observed. These findings do not establish the behavior of every
permission combination, full document lifecycle, or quotation calculation.

### Permission/dependency map

| Resource/action | Current enforcement | Consequence |
| --- | --- | --- |
| Pricing Item/Category reads | Active Department plus Pricing scope: None, Own, Selected or Department (`app/database.py:100–190`) | Selected uses category descendants and individually granted Items; individual-Item ancestors become readable for navigation |
| Category create/edit and grant changes | `pricing_items.manage` plus the readable Category lookup (`app/routers/pricing.py:805`, `:869`) | Same permission handles catalogue content and Category grants; no separate Administrator check for those grants |
| User Roles grant editing | Administrator-only; root categories rendered; all submitted user's category/item grants replaced (`app/routers/departments.py:335–417`, `:559–598`) | Nested Category grants exist but are absent from this form |
| Purchase Documents/Data Sheet | Independent view/manage action gate, then their module scope; Selected uses the Item set resolved from **Pricing scope** (`app/database.py:193–234`) | Document-only access and a Selected document scope do not behave independently of Pricing |
| Shared purchase document | Any visible linked Item can make the whole document readable in Selected scope | Whole-file disclosure and changes to shared links need an explicit policy, not assumptions about per-Item isolation |
| Department transfer | Administrator-only; moves main/related Items, wholly contained purchase documents, technical files and recommendations; clears grants | Source workspace loses live library access; target workspace gains it according to its permissions |
| Quotation read/PDF/package | Quotation permission and Project/creator check; saved line/file snapshots | A transferred source Item need not prevent reading saved output |
| Quotation Edit | Rebuilds every submitted line from an active Item in the current scoped catalogue | Even an unrelated header edit depends on current Item access |
| Quotation technical selection Save | Deletes previous snapshots and copies selected currently visible sources | Hidden or moved sources can disappear from the saved package |

The direct-user model remains the proposed authority. Do not interpret the
legacy Category `visibility` field as a deny rule; CAT-003 already demonstrated
that All Department readers are intentionally not constrained by that field.

### B2-001 — A scoped catalogue manager can grant themselves a larger subtree

- **Area/classification/severity:** Pricing Category access; functional defect;
  High, authorization boundary. Limited same-Department access can be expanded
  through a content-management route.
- **Reproduction:** Give a Technical user `pricing_items.manage`, Selected scope,
  and only an individual Item in Root/Granted leaf. Put another Item in
  Root/Other leaf. The individual grant exposes Root for navigation. POST Root's
  Edit form with `visibility=selected_users` and that user's own ID in
  `category_user_ids`. The POST returns 303; the previously hidden sibling Item
  becomes visible on the next request. No Administrator role was used.
- **Evidence/status:** Confirmed in code and isolated HTTP/ORM probes. The route
  checks only `pricing_items.manage`, loads the visible ancestor, and replaces
  its grants (`app/routers/pricing.py:875–928`). Ancestor visibility comes from
  `app/database.py:109–147`. Matching controls are offered under Manage categories
  (`app/templates/pricing_items.html:54–63`).
- **Recommendation/benefit:** Separate access administration from catalogue
  editing. Default to Administrator-only grant mutations and navigation-only
  ancestor access. Check mutation authority server-side, including forged requests.
- **Tradeoffs/dependencies/data:** Requires an explicit policy for managers who
  can edit a selected Item but not its enclosing branch. No migration is needed
  merely to restrict the route; preserve existing grants and ordinary authorized
  Item edits. Do not fix by hiding ancestors needed for CAT-002 navigation.

### B2-002 — Ordinary saves erase grants that are absent or unrelated to the edit

- **Area/classification/severity:** User Roles and Manage categories; functional
  defect; High. Existing authorized access disappears without an explicit removal.
- **Reproduction A:** Grant a user a leaf Category, then open User Roles and save
  the unchanged visible membership/permission controls. The form contains no leaf
  checkbox. The POST returned 303 and the user's leaf grant was removed.
- **Reproduction B:** Assign a root Category through User Roles while its legacy
  visibility value remains `department`. Rename that Category, submitting the
  unchanged `department` visibility. The existing user grant is cleared.
- **Evidence/status:** Confirmed in code and isolated HTTP/ORM probes.
  `app/routers/departments.py:359–364` selects roots only;
  `:559–580` deletes/rebuilds all grants. `app/templates/user_access.html:25`
  can only render those roots. Category Edit unconditionally clears grants at
  `app/routers/pricing.py:910` and restores them only for `selected_users`.
- **Recommendation/benefit:** One authoritative grant editor with complete paths
  for every supported level; ordinary name/parent edits must not alter access.
  Preserve grants not explicitly changed, and distinguish removal from omission.
- **Tradeoffs/dependencies/data:** Coordinate with B2-001 and CAT-003. Existing
  grants must be retained; do not normalize legacy visibility by deleting them.
  A concurrency-aware save should not overwrite another administrator's changes.
  No schema migration is assumed for the first repair.

### B2-003 — Manage access with None scope does not preserve newly created Items

- **Area/classification/severity:** Pricing permissions → create/reopen Item;
  functional defect; High. A successful creation can disappear from its creator.
- **Reproduction:** Give a Technical user `pricing_items.manage` and Pricing
  scope None. Create a valid Item. The POST returned 303 and the row existed with
  that creator, but searching for its exact name returned no Item row.
- **Evidence/status:** Confirmed in code and isolated HTTP/ORM reproduction with
  database-generated IDs. The permissions page promises Create access preserves
  own work (`app/templates/user_access.html:6`). `module_scope()` provides a
  None-to-Own fallback (`app/access_control.py:174`), but library ORM filtering
  reads raw scope values from `app/deps.py:72` / `app/database.py:100–170`.
- **Recommendation/benefit:** Resolve effective scope consistently for libraries
  and Project-linked modules, including the approved own-work guarantee. State
  clearly whether a setting means no access or no access to other users' work.
- **Tradeoffs/dependencies/data:** Do not broaden to all Department data. Audit
  adjacent creation/management modules before applying a shared resolver change.
  Preserve explicit permission denials; test None, Own and Selected independently.
  No migration expected; broader module behavior remains outside this batch.

### B2-004 — Document permissions have an unexplained dependency on Pricing scope

- **Area/classification/severity:** Purchase Documents and Data Sheet; usability
  problem with business-rule ambiguity; Medium. Administrators cannot reliably
  predict usable access from the document module's controls alone.
- **Reproduction A:** Grant document view + All Department document scope, but no
  Pricing scope. Both document home pages are reachable, but their Item detail
  routes return 404. Direct download of an existing authorized document returns
  200. Thus a user may be allowed a document yet cannot reach it through its Item.
- **Reproduction B:** Give Pricing All Department and document Selected scope,
  with zero explicit Item/Category grants. Download of a document on another Item
  still returns 200 because Selected documents inherit the full visible Pricing set.
- **Evidence/status:** Confirmed in code and isolated HTTP probes.
  `app/database.py:134–157`, `:193–234`;
  `app/routers/purchase_documents.py:70`, `:124`, `:268`, `:613`;
  `app/routers/technical_documents.py:30–68`, `:123`.
  `app/templates/user_access.html:21–39` does not explain this derived scope.
- **Recommendation/benefit:** Choose and document one policy. Prefer letting each
  document module resolve its own scope over the shared selected-resource list,
  with limited Item identity/navigation where needed, without granting Pricing
  prices or editing. Alternatively, retain inheritance but label it explicitly and
  prevent unusable combinations in the permission editor.
- **Tradeoffs/dependencies/data:** This is not classified as a confirmed unauthorized
  download: inheritance is explicit in current code, while the intended independent
  policy requires approval. One linked Item currently exposes an entire shared
  supplier file; approval must address that document-level disclosure boundary.
  Never expand Pricing permissions automatically as a UI workaround.

### B2-005 — Saving a shared purchase document can remove an inaccessible Item link

- **Area/classification/severity:** Purchase Documents → Edit; functional defect;
  High, preservation of shared relationships.
- **Reproduction:** A supplier document links Item A and Item B. Give a manager
  Selected Pricing access to A only and Selected purchase-document access plus
  manage. GET Edit contains both saved link IDs, but its permitted picker catalogue
  contains only A. The browser initializer keeps only entries in that catalogue.
  Submit the resulting visible selection while changing the supplier name. The
  POST returned 303; the database retained A's link and deleted B's link.
- **Evidence/status:** Confirmed in code plus isolated HTML/HTTP/ORM probes.
  The probe derived the submission from the actual rendered catalogue and saved
  JSON using the same membership filter; it did not execute a browser click.
  `app/static/js/app.js:2901–2908`, `:2921–2924`, `:2953–2976` filter and sync the
  selection. `app/routers/purchase_documents.py:216–248` supplies all saved links,
  while `:415–450` treats absent links as deletions. Authorization allows access
  through any visible linked Item (`app/database.py:203–209`).
- **Recommendation/benefit:** Preserve opaque links outside the editor's scope;
  distinguish explicit, authorized removal from missing form data. A conservative
  first repair can make shared documents with inaccessible links read-only and
  explain how an Administrator can change them.
- **Tradeoffs/dependencies/data:** Do not reveal hidden Item names/prices just to
  make the form round-trip. Decide whole-document management rights separately
  from per-Item link rights. No file was deleted in this reproduction, but the
  missing association removes the document from B's history. Keep transactionality.

### B2-006 — Moving an Item blocks unrelated edits to its existing quotation

- **Area/classification/severity:** Existing quotation → Edit after transfer;
  functional defect; High, compatibility with catalogue reorganization.
- **Reproduction:** Save a quotation with two Items and then transfer one Item
  to another Department. In the original Department, open quotation Edit and
  change only Notes, retaining both lines. The POST returns 422:
  `line_0_item_id: Choose an active main item.` Existing notes remain unchanged.
  Quotation detail and PDF remain accessible.
- **Evidence/status:** Confirmed in code and isolated HTTP/ORM probes.
  `_existing_quote_form` retains the source ID (`app/routers/pricing.py:2923`),
  but the picker uses only the current active scoped catalogue (`:1701`). Edit
  rebuilds every line (`:3018`) and `_build_quote_lines` rejects missing scoped
  source Items (`:1807–1817`). No special path preserves an unchanged saved line.
- **Recommendation/benefit:** Permit unchanged snapshot lines when editing
  unrelated fields; require current catalogue authorization only when adding,
  replacing or explicitly refreshing a line. Display an unavailable/moved-source
  explanation using the already-authorized quotation snapshot.
- **Tradeoffs/dependencies/data:** Do not bypass Department filtering or reveal
  the destination catalogue. Price, description, image and related-line retention
  need an explicit edit contract. Existing snapshot columns may suffice; any
  revision-history redesign is outside this proposal. Broader quote editing is
  the proposed next review batch.

### B2-007 — Saving visible technical selections drops hidden quotation snapshots

- **Area/classification/severity:** Quotation detail → Technical package;
  functional defect; High, historical package content can disappear unexpectedly.
- **Reproduction:** Save two Data Sheet snapshots and one recommendation in a
  quotation. Transfer the first Item and its live sources to another Department.
  The saved package still downloads both original PNG files unchanged. The
  selection form now renders only the second Item's source. Save that visible,
  already-selected source. Attachments change from three rows to one; the old
  snapshot files are removed, including the moved Item's retained copy.
- **Evidence/status:** Confirmed in code and isolated HTTP/ORM/file probes.
  `app/templates/pricing_quotation_detail.html:69–72` renders current source
  choices rather than a complete saved-attachment list.
  `app/routers/pricing.py:2482–2514` deletes all previous rows, rebuilds from
  visible sources, commits, then deletes all previous snapshot files.
- **Recommendation/benefit:** Display saved attachments independently of current
  library availability. Reconcile explicit add/remove/replace actions; retain
  snapshots by default even when the source moved, was deleted, or became hidden.
  Separate refreshing current sources from saving a selection.
- **Tradeoffs/dependencies/data:** Authorize removal through quotation rights,
  additions through the approved source-document policy, and never infer deletion
  from an absent checkbox. Keep old files until replacement commits successfully.
  Avoid exposing current source metadata outside its scope. No migration assumed.

### Transfer safeguards and compatibility verified in this batch

| Check | Result | Limit |
| --- | --- | --- |
| Main Item with Related Item and wholly contained purchase document transferred | All relevant Department IDs changed to target, including technical file and recommendation | One isolated successful single-Item transfer; branch success remains Batch 1 code/existing-test evidence |
| Item compatibility device reference | Same device FK before/after | Does not certify every installed-asset/service-record view |
| Individual Item grant after transfer | Removed as current code intends | Category grant transfer policy and restoring grants still need a decision |
| Source vs destination live document downloads | Source 404; target 200 for purchase file and Data Sheet | Tested with Administrator switching workspaces |
| Quotation saved lines | Source ID, name, description and price unchanged by transfer | A later full Edit still hits B2-006 |
| Quotation detail/PDF/package immediately after transfer | HTTP 200; both saved PNG members had unchanged SHA-256 values | PDF layout and byte-for-byte PDF identity not asserted |
| Failed post-transfer quote edit | 422 with specific Item error; original notes unchanged | Input retention/visual behavior requires browser testing |
| Subsequent technical selection Save | Reproduced B2-007 loss of hidden snapshots | Transfer alone did not cause the loss |

The whole-document transfer blocker reviewed in Batch 1 remains important: do
not split a supplier document by moving one linked Item. B2-005 now shows why the
suggestion to “separate that document first” also needs careful permission and
preservation rules before it can be recommended as an easy recovery workflow.

### Verification log and remaining gaps

Used process-local settings, suppressed dotenv loading, temporary upload directories,
synthetic PNG files and newly created PostgreSQL schemas through the ORM. No schema
change or migration was run on an existing database. Every named scratch database
below was removed in a `finally` cleanup; temporary file directories were removed.

- `sms_review_c6e109e04b1f4c82`: grants, scoped management, document dependencies
  and shared-link probes. Those results completed. An initial own-Item creation
  probe used explicit seed IDs without advancing the sequence and returned 500;
  that result is a fixture artifact and is excluded from product findings.
- `sms_review_495ae78fa79943d0`: corrected own-Item creation with generated IDs
  returned 303 and confirmed invisibility; successful transfer, line preservation,
  related-resource Department IDs and saved PNG hashes checked. The harness then
  attempted JSON parsing without the route's required `camera-planner` request
  header and stopped; subsequent checks were not claimed from that run.
- `sms_review_7f2db571c48d47e9`: fixture setup stopped on a missing required Project
  address. No product behavior was assessed from that run.
- `sms_review_a324ec90490647fd`: corrected quotation follow-up completed: 422
  Item error, preserved notes, source/destination file access, missing moved-source
  checkbox, and three-to-one attachment loss after saving visible selections.

These are diagnostic probes, not a pytest suite pass. Existing tests and
application code were not edited. The standard fixed test database was not used.
The existing Starlette/httpx deprecation warning appeared in the probes.

The browser connection was retried and again failed before bootstrap with
`missing field sandboxPolicy`. Browser, mobile/RTL, focus, screen-reader, native
form validation, and visual PDF checks remain pending. No test of real user data
or deployed installations was performed.

Open decisions: catalogue management versus access administration; preserving
unseen grants during concurrent saves; independent document scopes versus explicit
inheritance; whole supplier-file disclosure when one Item is selected; exact
quotation snapshot retention/refresh behavior. Concurrent mutation and combinations
outside the tested matrix are verification gaps, not verified defects.

### Updated priorities and proposed Batch 3

1. **Before larger moves:** close self-granting and protect existing grants/shared
   links/saved attachments (B2-001, B2-002, B2-005, B2-007).
2. Repair scope consistency and quotation edit compatibility (B2-003, B2-004,
   B2-006), alongside the small Batch 1 form/conflict repairs.
3. Resume destination/search/bulk-move improvements only after those boundaries
   are defined and regression-tested. Keep all migrations/data reorganization
   out of scope unless separately approved.

Tracker phases P0, P2, P7 and P8 expand the prior roadmap; all are unapproved.
Proposed next review batch: **Quotation create/edit lifecycle and error recovery**,
covering saved versus current Item/related-item data, prices/currencies/charges,
alternatives, deactivation/deletion compatibility, planner save boundaries and
export behavior. Keep it to quotations; do not start Store or service-entry review
in the same run. Batch 2 stops here until the next instruction.

## Batch 3 — 2026-10-07: quotation lifecycle and error recovery

Scope: creation/editing, saved versus current main/related Item content, numeric
validation, charges, alternatives, planner submission and export boundaries.
Baseline remains the user's dirty working tree at `3df505a`; documentation is on
`docs/ui-ux-review-batch-3`. Only the two review documents changed. No implementation,
existing-data mutation, migration, service restart, staging or packaging occurred.

### Findings at a glance

| ID | Classification | Severity | Finding | Evidence status |
| --- | --- | --- | --- | --- |
| B3-001 | Functional/data preservation | High | Ordinary Edit refreshes saved catalogue and Project content | HTTP/ORM reproduced; image/company effects traced in code |
| B3-002 | Functional/data preservation | High | Inactive related Item disappears from saved quote after Edit | HTTP/ORM reproduced with submission derived from current frontend logic |
| B3-003 | Functional/validation consistency | Medium | Server accepts fractional quantities that the form disallows | HTTP/ORM reproduced; HTML/JS constraints inspected |
| B3-004 | Usability/error recovery | Medium | Async errors discard field/row association and appear under planner | Keyed HTTP error reproduced; presentation traced in JS |
| B3-005 | Functional/resilience | Medium | Optional planner readiness blocks saving; unanswered requests have no bounded recovery | Confirmed control flow; browser fault injection pending |

There are now 23 findings across three batches. These are review findings, not
implemented fixes. Browser bootstrap remains unavailable (`missing field
sandboxPolicy`); no interaction, accessibility or visual PDF pass is claimed.

### B3-001 — A notes-only edit refreshes saved source content

Reproduction: create a quote using a main Item and Project; change that Item's
name/model/description and the Project's name/address in the disposable database.
Before editing, saved values remain original. Submit the same quote values with
only Notes changed. The route returns 200 JSON success, and saved Project name,
address, Item name/model/description now contain the new source values. The saved
price override remains 120.00, so price retention does not imply full snapshot retention.

Evidence: `_existing_quote_form` (`app/routers/pricing.py:2923`) passes source IDs
and commercial fields, `_build_quote_lines` (`:1789`) reconstructs current source
content, and Edit (`:3079`) clears/replaces saved lines. `_apply_quote_header`
(`:2183`) also refreshes Project/contact/company fields. `_snapshot_line_images`
(`:1973`) and post-commit cleanup show the same current-source replacement policy
for images; image/company mutation was not separately runtime-probed in this batch.

Impact: an unrelated edit changes the meaning and customer-facing content of an
existing offer without an explicit refresh action. This narrows Batch 1's snapshot
strength: saved content is insulated from source changes until ordinary Edit.
It complements B2-006, where inaccessible sources prevent the edit altogether.

Recommendation: preserve unchanged saved content by default, including Project,
contact, company and Item snapshots; provide an explicit refresh/replace action
with a before/after summary. Tradeoff: historical wording can differ from current
catalogue data, so label the saved version clearly. New/replaced Items still need
current authorization and validation. P8 should define this policy before editing code.

### B3-002 — Deactivating a related Item can silently remove its priced row

Reproduction: save a quote with one selected accessory (2 × 15 SAR), then deactivate
that accessory. Its saved related line still exists. Edit serializes only the
currently active related choices; submit the resulting selection with the other
values unchanged. HTTP 200 succeeds, related snapshot count falls from one to zero,
and the sampled single-currency computed amount falls from 910.00 to 880.00.
The HTTP submission was constructed from the inspected JS behavior; this was not
a browser click-through.

Evidence: `_catalogue_payload` (`app/routers/pricing.py:403`) excludes inactive
related Items; `renderRelatedItems` (`app/static/js/app.js:914`) creates controls
only from that payload. `_existing_quote_form` drops related entries whose source
ID is null, while the Edit route replaces all saved lines. Deletion therefore has
an additional code-level loss path; only deactivation was runtime-reproduced here.

Impact: a historical priced accessory disappears without an explicit Remove action.
If other active choices remain, the user may first be required to select or skip
them; that does not preserve the inactive saved row.

Recommendation: render saved related lines independently of current catalogue
availability, mark unavailable sources, and reconcile explicit additions/removals
against saved IDs. Tradeoff: unchanged historical content must remain editable
without allowing arbitrary new selections from inaccessible sources. Include
related-line identity, alternatives and amounts in P8 preservation acceptance.

### B3-003 — Quantity rules differ between server and form

Reproduction: submit a valid Edit with main quantity 1.5 and workers 1.5. It succeeds;
the main quantity persists as 1.50. Main/worker/transport/day HTML fields and related
quantity JS specify minimum 1 and step 1. A fractional saved value is consequently
inconsistent with native form validity on reopening. Native browser blocking has
not been exercised in this environment.

Evidence: `quantity` (`app/pricing.py:37`) allows 0.01 upward and rounds to two decimal
places; form constraints are at `pricing_quotation_form.html:58`, `:110`, `:116`,
`:122`, and related control creation at `app/static/js/app.js:963`.

Recommendation: decide quantities per business unit (devices, workers, days,
transport), then use the same rules and wording in client/server validation.
Tradeoff: fractions may be legitimate for some units. Do not blanket-round or
rewrite existing quotations; define an explicit compatibility policy first. P9.

### B3-004 — Async validation loses the location of each error

Reproduction: submit an invalid main quantity. The server returns 422 with
`line_0_quantity: Enter a quantity greater than zero.` The normal planner-integrated
save path maps the error object's values into one message, discarding its keys.
It scrolls to the planner alert rather than marking/focusing the affected line.
With multiple Items, identical messages no longer identify which row needs repair.

Evidence: `renderQuotationErrors` (`app/static/js/app.js:1405`),
`showPlannerSubmitError` (`:1385`) and the JSON handling immediately below.
The template has inline errors for server-rendered responses, but that does not
repair the asynchronous path. Runtime evidence confirms keyed errors and preserved
database state; visual/focus behavior is code-derived and awaits browser verification.

Recommendation: retain error keys, annotate the matching field and Item section,
provide an accessible linked summary, focus the first affected control, and reserve
the planner alert for planner errors. Preserve entered fields/files and translate
dynamic messages. Tradeoff: dynamic line indexes and removed rows need robust
mapping with a form-level fallback. Reuse established entry-form patterns where
appropriate without assuming that their implementation fits quotation rows. P9.

### B3-005 — Saving depends on planner readiness without timeout recovery

Reproduction procedure for browser verification: block the planner iframe or prevent
its ready message, then try saving a quotation without a plan. The submit handler
prevents submission and reports that the planner is loading. Alternatively, allow
ready but suppress the matching export result/error: submit buttons remain disabled.
The source contains no export timeout or fetch cancellation/recovery deadline.

Evidence: the iframe is always present (`pricing_quotation_form.html:129`);
`app/static/js/app.js:1452–1494` gates every save on readiness/export and only unlocks
on a handled response/error. A pending HTTP fetch has the same unbounded-wait gap.
This is confirmed control flow, not a measured production outage or browser repro.

Recommendation: add a bounded wait, clear retry/reconnect status and recovery that
retains the form. Distinguish an empty optional plan, unchanged saved plan, explicit
removal and a failed export. Tradeoff: bypassing planner export by submitting empty
state could erase an existing plan because `_apply_plan` replaces its contents;
safe recovery must preserve saved state explicitly. Never blindly retry an uncertain
create response without duplicate protection. P9, coordinated with P8.

### Controls retained, probes and remaining coverage

- Single-currency arithmetic probe: main 2 × 120 + accessory 2 × 15 + transport
  2 × 20 + installation 2 × (3 workers × 100) = 910.00 SAR. Manpower is the
  installation daily-rate input and is not added twice by `quotation_totals`.
- Saved price override survived source metadata refresh. Invalid NaN quantity
  returned 422 and retained the previously saved 1.50 quantity. Direct numeric
  helpers rejected zero quantity, NaN, negative price and Infinity.
- Code inspection found currency validation and currency labels per priced row.
  Detail/PDF render separate row amounts; this review does not recommend adding
  a mixed-currency grand total. Discount/VAT are currently forced to zero by the
  header builder; their absence from the UI is not treated as a defect.
- Alternative validation rejects self-reference, missing targets and cycles in
  `_build_quote_lines`; these guards were inspected, not newly runtime-tested.
- Planner validation checks state/file consistency and rejects missing preview or
  required background. Message handling checks origin, iframe source and request ID.
  Empty-plan create/Edit succeeded in the HTTP probe. Stateful planner export,
  image replacement, slow network and session expiry still need browser coverage.
- Detail and PDF endpoints returned 200 after the sampled edits. PDF visual layout,
  bilingual long content, mixed currencies and alternative presentation are not
  certified by those status checks. Invoice/site-survey attachment lifecycle,
  deletion dependencies and concurrent edits remain outside this batch's probes.

The diagnostic harness used only scratch database `sms_review_a32c48f1b1454524`,
process-local settings with dotenv loading suppressed, and a temporary upload
directory. Cleanup dropped that exact database in `finally` and removed temporary
files. No test files changed and no full/fixed-database suite ran. The existing
Starlette/httpx deprecation warning appeared. This is diagnostic evidence, not a
pytest pass count.

### Updated priorities and proposed Batch 4

Keep P0 access/link/package preservation first. Promote P8 quotation snapshot
preservation alongside it before larger transfer workflows; B3-001/002 add confirmed
content/price loss to the earlier editability concern. P9 covers the smaller
validation and planner recovery changes after policy decisions. All remain unapproved.

Proposed next bounded batch: **Purchase Documents and Data Sheet lifecycle**—create,
edit, file validation/replacement, preview/download/export, shared-link deletion,
recommendation changes and error recovery. Reuse Batch 2 scope/link findings without
repeating their probes unless new evidence warrants it. Stop here; continuing the
review does not authorize implementation.

## Batch 4 — 2026-10-07: Purchase Documents and Data Sheet lifecycle

Scope: create/edit validation, file storage and correction, preview/download/ZIP,
recommendation saves, deletion feedback and price-analysis filtering. Prior scope
and hidden-link findings B2-004/005/007 remain applicable and were not reprobed.
Baseline is the same dirty tree at `3df505a`, with documentation on
`docs/ui-ux-review-batch-4`. Only these review documents changed.

### Findings at a glance

| ID | Classification | Severity | Affected workflow | Verification |
| --- | --- | --- | --- | --- |
| B4-001 | Functional defect | High | Arabic Item names break Data Sheet recommendation PDF and package ZIP | HTTP reproduced; header encoding cause confirmed |
| B4-002 | Functional defect | Medium | Overlong Data Sheet title causes 500 and orphan upload | HTTP/storage/ORM reproduced |
| B4-003 | Usability problem | Medium | Document validation discards unsaved form values | HTTP/HTML reproduced; frontend inspected |
| B4-004 | Functional defect | Medium | Missing stored files produce inconsistent 404/500 downloads | HTTP reproduced with disposable missing-file fixtures |
| B4-005 | Usability problem | Low | Correcting an uploaded file requires broader deletion/recreation | Confirmed routes/templates; corrected-file append reproduced |
| B4-006 | Usability problem | Medium | Destructive effects are implicit in recommendation Save and shared-document Delete | Blank-save deletion reproduced; shared-delete code confirmed |

Total: 29 findings. All implementation remains unapproved. Browser runtime was
retried and failed with `missing field sandboxPolicy`; no browser walkthrough,
keyboard/RTL check or visual PDF result is claimed.

### B4-001 — Arabic Item names break technical exports

Create a Data Sheet and recommendation for an ASCII-named Item: recommendation
PDF and package ZIP both return 200. Rename the disposable Item to include Arabic
characters and repeat: both return 500. Ordinary file preview/download works for
the initial upload. This prevents common bilingual Item names from using the
combined technical-information export, even when the stored files are valid.

Evidence: `app/routers/technical_documents.py:151` and `:157` interpolate raw Item
names into `Content-Disposition` response headers. A direct response-construction
probe confirmed `UnicodeEncodeError` from Latin-1 header encoding. ZIP member names
are separately cleaned, so archive member sanitization does not solve this header.

Recommendation: use one safe download-header helper with a quoted ASCII fallback
and correctly encoded UTF-8 filename support; handle quotes and control characters
too. Preserve the original display name in the UI. No data rewrite or migration is
needed. Verify Arabic/mixed-script/punctuation names across recommendation PDF and
ZIP downloads. Visual Arabic PDF typography remains a separate verification gap.

### B4-002 — Long Data Sheet title leaves a file behind after failed Save

Upload a valid PNG with a 181-character title through the Data Sheet form. The
request returns 500, no new TechnicalDocument row is saved, but one new PNG remains
under the disposable upload directory. A successful prior row remains intact.
The title input has no maximum, so this does not require bypassing its HTML rules.

Evidence: `app/models.py:3225` limits title to 180 characters;
`technical_document_item.html:6` has no maxlength. `upload_documents`
(`app/routers/technical_documents.py:72`) stores files before commit and catches
only `PurchaseDocumentError`, not database failures. The database constraint and
exception coverage explain the reproduced failure and orphaned file.

Recommendation: validate title length before file writes, align frontend limits,
and clean newly written files on database failure with a recoverable form error.
Keep existing saved files untouched. Test both overlong input and a simulated
commit failure. Avoid broad orphan deletion: reviewing/reconciling existing storage
would require its own explicitly approved scope. No migration is needed for this fix.

### B4-003 — Validation sends users back to a reset form

Purchase Documents: change supplier and submit an invalid date. The POST redirects
to Edit, which reloads saved values; the submitted supplier is absent from the
returned input. Data Sheet: enter title/notes and upload a valid PNG plus an invalid
PNG. The route redirects to the Item page; the entered title/notes are not restored.
File selections also cannot be repopulated by that fresh server-rendered page.

Evidence: `_save_document` (`app/routers/purchase_documents.py:344`) flashes joined
errors and redirects; `_form_context` (`:216`) reconstructs only saved/default data.
Data Sheet upload (`technical_documents.py:72`) similarly redirects on rejection.
The purchase form JS (`app/static/js/app.js:3033`) synchronizes Item selection on
submit but does not implement the quotation-style async validation recovery.

Impact: a single invalid field/file can require re-entering supplier/date, Item
selections/prices or descriptive text, then selecting files again. This increases
repeat work for documents linked to many Items. Existing saved data is not changed
by the sampled validation failures.

Recommendation: retain submitted values, identify the exact bad field/file and
keep browser file selections where feasible through in-place validation responses.
For a non-JS fallback, preserve text/selection values and explicitly request file
reselection. Do not store large files or sensitive form contents in signed cookies.
Coordinate shared-link preservation with B2-005 before rebuilding selection state.

### B4-004 — Missing storage is handled inconsistently

In the disposable environment only, remove the stored file after a successful
upload. Data Sheet preview, direct download and Item package return 500. Purchase
preview and individual-file download return 404, but whole-document download
returns 500 (tested with two files, one missing).

Evidence: `resolve_technical_file` (`app/technical_documents.py:36`) raises a safe
domain exception when a file is absent. Its callers in `technical_documents.py`
routes `:115`, `:123`, `:157` do not translate that exception. Purchase preview and
individual download catch it (`purchase_documents.py:607`, `:624`), while whole
download (`:658`) does not. Single-file whole download has the same uncaught path
in code, though the missing-file runtime sample used the multi-file branch.

Recommendation: provide a consistent unavailable-file response and an actionable
message without exposing filesystem paths. Preserve metadata so an operator can
investigate. Package export must either clearly fail with the missing-file list or
explicitly identify an approved partial package; never silently omit files. Physical
restoration and investigation of real storage remain out of this review's scope.

### B4-005 — There is no bounded file-correction action

Purchase Edit allows adding files but lists existing files only as download links.
Uploading a corrected version appends it: the probe changed the file count from
one to two, retaining the incorrect version. The router exposes only whole-document
Delete, not individual-file removal/replacement. At the 20-file ceiling, even
appending another correction is blocked. Data Sheet offers upload/delete but no
title/notes edit or explicit replacement action.

Evidence: `purchase_document_form.html:16–17`, `_save_document` file extension at
`app/routers/purchase_documents.py:408`, router inventory and
`technical_document_item.html:6–7`. No claim is made that file correction must
overwrite history; that retention policy has not been decided.

Recommendation: offer a small, permission-checked correction workflow—metadata
editing, and explicit file removal or superseding/replacement under an agreed
retention rule. Explain effects on every linked Item. Keep at least one valid file
on a purchase document, and preserve separately copied quotation attachments.
Tradeoff: immutable revisions may be appropriate for supplier evidence but add
storage and UI complexity. Start with a policy decision; versioning/schema work is
not preapproved. Until then, clarify that Edit adds files rather than replaces them.

### B4-006 — Destructive effects need explicit wording

Data Sheet: save an existing recommendation, clear its text and click ordinary
Save changes. The record is deleted; this was reproduced. The help says to write
the current approved recommendation and gives no explanation that blank Save
removes it (`app/i18n/en.py:1782`). There is no explicit Remove control/confirmation.

Purchase Documents: Delete is shown on each Item's document card. The generic
confirmation says only “Delete?”, while the route deletes the shared document and
all its files, affecting every linked Item (`purchase_document_item.html:16`,
`app/routers/purchase_documents.py:725`). A shared-item count is visible, but the
confirmation does not explain the global effect. This branch is code-confirmed,
not a new runtime deletion probe; deleting a shared object may be intentional.

Recommendation: separate recommendation removal from routine Save, or clearly
explain and confirm empty-save removal. Distinguish “unlink from this Item” from
“delete document for all linked Items”, showing authorized impact before destructive
confirmation. Do not disclose inaccessible Item identities or infer new delete
permissions. Coordinate B2-005/P0 so a partial visible Item list never authorizes
global link removal. No migration is assumed for wording and explicit actions.

### Retained controls and verification limits

- Valid synthetic PNG upload, preview, direct download and technical package
  returned successful responses; valid purchase create/preview/download did too.
- A two-file Data Sheet batch with a bad second file left no newly stored PNGs:
  the existing domain-validation cleanup worked. B4-002 concerns database failures.
- File helpers enforce file-type/content checks, nonempty files, a 20 MB per-file
  limit, generated storage keys and root containment. PDF validation rejects
  encrypted/empty/unreadable documents. Purchase documents cap total files at 20;
  the Data Sheet route does not apply that same count cap. Large-package resource
  limits need measurement, not an unmeasured performance defect claim.
- Purchase analysis code groups prices by currency, avoids percentage division by
  zero and applies the same supplier/type/date filters to page and export queries
  (`purchase_documents.py:498`, `:529`, `:687`). Malformed/reversed date-filter UX
  and representative price charts remain manual verification tasks.
- Mutation routes retain CSRF and manager permission checks; the current permission
  code is the baseline, not older Administrator-only deletion descriptions. Broader
  permission-matrix certification remains open. B2's scope/shared-link issues remain.
- Technical recommendations are one current value; full revision history is not
  a required new feature. Existing quotation technical snapshots are a separate
  preservation concern already tracked in B2-007.

One diagnostic harness used scratch database `sms_review_a0d4486d3eee4595`, disabled
dotenv loading process-locally, and used a temporary upload directory. Missing-file
simulation removed only explicitly checked paths inside that temporary directory.
The exact database was dropped in `finally`; a subsequent read-only query confirmed
its absence. Temporary files, including the reproduced orphan, were removed. No
existing database/upload, test/source/configuration file or Windows service changed.
No pytest suite ran; the existing Starlette/httpx deprecation warning appeared.

Remaining verification: PDF visual fidelity, malicious/corrupt PDF edge cases,
duplicate submission/retry, concurrent edits, keyboard/label associations, mobile
and Arabic RTL, large packages, and complete deletion/cascade/quotation-snapshot
integration. Successful response codes do not certify those behaviors.

### Priorities and proposed Batch 5

Keep P0/P8 preservation repairs ahead of structural workflow changes. P10 adds
bounded export/upload/error-recovery fixes (B4-001–004). P11 covers file correction
and clear destructive effects (B4-005/006) after retention/shared-link decisions.
All proposals are unapproved; existing storage cleanup is explicitly not included.

Next proposed batch: **Projects, Sub Projects, Sites and Project-team setup**,
covering creation, selection, editing/deactivation/deletion, relationships and the
setup steps that feed field work. Photo-guidance configuration may be included
where directly dependent; defer installation entry/import/drafts to its own batch.
Batch 4 stops here pending the next instruction.

## Batch 5 — 2026-10-07: Project hierarchy and team setup

Scope: Main Projects, Sub Projects, global Sites, team selection, setup permissions,
validation/search recovery, deletion fallback and the Photo Guidance entry point.
Field-entry workflows and full photo-profile editing are deferred. Baseline remains
the dirty tree at `3df505a`; documentation branch is `docs/ui-ux-review-batch-5`.
Only review documents changed; no implementation was authorized.

### Model and everyday workflow

A Main Project is stored in the legacy `sites` table. Creating one automatically
creates a `General` Sub Project with no Site assignments. Administrators maintain
global Site names separately at `/sites`; a Project editor assigns them to Sub
Projects. Sites can be reused across Sub Projects. This is an assignment hierarchy,
not the Pricing folder tree, and should retain its existing identities.

Project-team membership is the shared selected-Project list for several modules;
module permissions/scopes still govern actions and visibility. The table has one
membership per Project/user, including one represented Department and a free-text
role. Department scope includes Projects represented by a team membership in that
Department; Selected uses the current user's membership. Own currently relies on
the role string described in B5-002. Customer assignments are separate.

### Findings at a glance

| ID | Classification | Severity | Affected workflow | Verification |
| --- | --- | --- | --- | --- |
| B5-001 | Functional defect/access control | High | Team manager can mutate a hidden Project's team and self-grant visibility | HTTP/ORM reproduced |
| B5-002 | Functional defect/access model | High | Editable role wording determines Own Project access | HTTP/ORM reproduced |
| B5-003 | Usability problem/permission mismatch | Medium | Non-admin Project editor sees Photo Guidance action that returns 403 | Rendered HTML/HTTP reproduced |
| B5-004 | Usability problem/search recovery | Medium | No-match Project search removes search and Clear controls | Rendered HTML reproduced |
| B5-005 | Usability problem/form recovery | Medium | Invalid Project edits lose entered values and editing context | HTTP/HTML reproduced; redirects traced |
| B5-006 | Functional defect/validation | Medium | Site Edit accepts overlong name until database failure | HTTP/ORM reproduced |

There are now 35 findings. Evidence below is HTTP/ORM/code, not browser interaction.
The browser runtime failure documented in earlier batches remains unresolved.

### B5-001 — Team mutations omit the Project scope check

Give a Technical user `projects.view`, `projects.edit`, `projects.create` and
`projects.manage_team`, with Selected Project scope and membership in Project A.
Project B is absent from their page. A direct Edit POST for B returns 403. Posting
the same user's valid membership to B's team route returns 303; B then appears in
their Project list. In an independent follow-up fixture, removing B's existing
other team member also succeeds while B remains hidden to the actor.

Evidence: `app/routers/admin.py:295` and `:368` check the module-level team permission
but not `project_access_allowed`; normal Project Edit (`:405`) does check it.
`Site` and team membership are not automatically narrowed to that selected list
by these database lookups. `visible_project_ids` (`app/access_control.py:186`)
then honors the inserted membership.

Impact: a scoped manager can broaden their own selected list or revoke someone
else's membership outside their visible Projects. Effects can reach other modules
that use the shared selection, subject to their own permissions/scopes; those
downstream combinations were not runtime-tested in this batch.

Recommendation: require authority over the target Project before either team
mutation; define whether adding cross-Department members needs additional authority.
Do not treat possession of a global action bit as authority over every Project.
If global team administration is intentional, give it an explicit separate policy
and UI. Preserve existing memberships during the repair. Also replace the Project
team summary's misleading “Only selected users can access” wording: Department
scope and Administrator access are not limited to that displayed list.

### B5-002 — A role label doubles as ownership

With Own Project scope, a user whose team role is `Project creator` sees A.
Save that user's role as `Team Leader`: A disappears on the next page load.
Setting their role on B to the literal `Project creator` makes B visible under Own.
The latter probe also traversed B5-001, so it is not claimed as a separate bypass
after that endpoint is fixed. The role-to-ownership coupling itself remains a
defect even when an authorized Administrator changes the role.

Evidence: `visible_project_ids` compares `ProjectTeamMember.project_role` to the
exact English string at `app/access_control.py:214`. Creation writes that label
(`app/routers/admin.py:280`); the ordinary team-save handler overwrites it with
free text (`:324`). The form presents it as a descriptive Project role and suggests
`Team Leader`, without warning that the text affects visibility.

Recommendation: represent creator identity independently of editable/localized
role wording. Keep Own access stable through role edits; decide how removal of
membership affects it. Historical creator attribution cannot safely be inferred
from arbitrary current role labels alone. This may require an approved Alembic
migration, an evidence-based backfill and explicit handling of ambiguous records.
Do not automatically promote current `Project creator` labels into trusted history.

### B5-003 — Photo Guidance advertises an unavailable management action

The non-admin editor above sees `/projects/{id}/photo-guidance` in the rendered
Project page. Following it returns 403. The template gates the card with
`can('projects.edit')`, while `app/routers/photo_guidance.py:132` requires Admin.
Evidence: Photo Guidance block in `app/templates/projects.html` and HTTP probe.

Recommendation: match the entry-point visibility to the existing Administrator-only
policy and, where helpful, explain who configures guidance. Do not broaden backend
permissions merely to make the link work. If delegation is desired, design that
permission explicitly. This is a small template/policy alignment fix; no migration
is expected. Verify both Admin and Technical editor experiences.

### B5-004 — Empty search looks like an empty application

On a database with Projects, request `/projects?q=NoMatchReview123`. The response
has neither the search input nor Clear link and says `No Main Projects yet`.
The user must navigate away/back or edit the URL to search again. Browser back
remains possible; this is a missing in-page recovery action, not a complete trap.

Evidence: `/projects` filters its list before rendering (`admin.py:167`);
`projects.html` wraps the search form in `{% if projects %}` and uses the creation
empty state for the alternate branch. Matching hierarchy links also omit `q`, so
opening a result drops the search context (code-confirmed).

Recommendation: render search/reset independently of results, distinguish no
matches from no accessible Projects, and preserve the query on result navigation
when useful. Do not reveal hidden Projects through counts or empty-state wording.
Verify no-match, no-access, first-use and matching-result states. No schema changes.

### B5-005 — Project validation loses the work needed for correction

Edit a Project name/address and set an end date before its start. POST redirects
with an error; the subsequent page has saved values, not the submitted name/address.
Create/Sub Project validation has the same flash-and-redirect design in code.
Some redirects preserve `project_id`, while successful Project Edit and several
error paths return simply to `/projects`, whose selected detail defaults to the
first Project. Edit sections are rendered closed rather than reopened at the error.

Evidence: `admin.py:405–470`, date validator at `:98`, selected-Project fallback
at `:192`, and the Project/Sub Project forms in `projects.html`. The invalid-date
value loss was reproduced; focus and disclosure interaction await browser checks.

Recommendation: keep submitted values and the current Project/Sub Project context,
show field-specific errors and reopen/focus the affected form. On success, remain
on the edited object. Reuse existing form-recovery patterns without adding drafts
to these short forms unless real usage warrants it. Preserve historical record
snapshots and current permission checks. No migration expected.

### B5-006 — Site Edit can fail with an ordinary long name

Submit a 121-character name to an existing global Site. The response is 500 and
the saved name remains unchanged. The Edit input has no maxlength, whereas Site
Create has maxlength 120. The server checks only presence and duplicates before
commit, against a 120-character database column.

Evidence: `app/templates/work_sites.html` Edit input;
`app/routers/admin.py:744`; `app/models.py:747`. Main Project scalar-field lengths
and team-role length similarly rely on frontend/database limits rather than full
server validation; those additional failure paths were not runtime-probed.

Recommendation: validate bounded fields on the server, align Create/Edit controls,
and return a recoverable field error with input intact. Retain database constraints
as the final guard and handle duplicate races without a generic error page.
Test boundary lengths and Unicode values; do not truncate existing data or expand
schema limits just to avoid validation. No migration expected for the bounded fix.

### Retained safeguards, gaps and cleanup

- Creation returned 303 and created `General` with zero assigned Sites. Assigning
  a Site and then submitting an empty selection both returned 303; zero assignments
  persisted. The existing Deselect all workflow is consistent with that rule.
- A Project referenced by a disposable quotation survived Delete as an inactive
  Project. An unreferenced Project was removed. `_delete_or_deactivate` uses the
  database's restrictive references before falling back to deactivation. This
  does not certify every service-record/Sub Project/Site dependency or cascade.
- Normal hidden-Project Edit returned 403, distinguishing the team-route omission
  from an application-wide absence of Project authorization.
- Code validates Sub Project ownership on edits/assignment, rejects nonexistent
  Site IDs, checks date ordering and case-insensitive duplicate names, and reserves
  Project/Sub Project toggle/delete and global Site management for Administrators.
- Photo-profile value limits and description de-duplication were inspected;
  profile CRUD, field-entry use, copied descriptions and guidance deletion remain
  pending for the field-entry batch. No broad photo-guidance completion is claimed.
- Global Site reuse, assigning inactive Sites, and one represented Department per
  team member need task-based policy review before redesign. Full-list hierarchy
  loading and repeated Site checklists may become costly, but no latency problem
  was measured. Mobile, Arabic RTL, keyboard/focus and screen-reader checks remain open.

Probe `sms_review_7778c7f949dd40f2` completed the six findings and basic setup checks;
its final quotation fixture omitted required `vat_rate`, so the deletion portion
stopped before assessment. That fixture error is excluded from product findings.
Follow-up `sms_review_5135746051384379` corrected the fixture and verified hidden
team removal plus referenced/unreferenced Project deletion. Both databases were
dropped in `finally`; temporary upload directories were removed. Settings were
process-local with dotenv suppressed. Email delivery was disabled in the probe;
no messages were sent to real users. No full suite, source/test/config edit,
existing-data mutation, migration or service restart occurred.

### Priorities and proposed Batch 6

P12 closes team mutation scope and defines durable creator semantics; prioritize
it alongside P0/P8 preservation and access repairs. P13 contains the small setup
permission/search/form fixes. The creator backfill and any access-policy changes
need a concrete approved plan before implementation.

Next proposed batch: **Installation entry and saved-record editing**, including
Project/Sub Project/Site and quotation selection, device/evidence entry, drafts,
validation and directly related photo guidance. Keep Excel imports as a follow-up
if necessary to stay bounded; defer Maintenance and Preventive Maintenance.
Batch 5 stops here pending the next instruction.

## Batch 6 — 2026-10-07: Installation entry, additions and drafts

Scope: entry and saved-edit authorization paths, hierarchy/quotation selection,
evidence validation, append behavior, draft identity and completion cleanup.
Photo-guidance selection and normal edit transactions were traced; full browser
editing, imports and the entire asset/report lifecycle remain open. Baseline is
the same dirty tree at `3df505a`; branch `docs/ui-ux-review-batch-6` contains only
review-document changes. No application implementation was authorized.

### Findings at a glance

| ID | Classification | Severity | Affected workflow | Verification |
| --- | --- | --- | --- | --- |
| B6-001 | Functional defect/access control | High | Create endpoint appends to saved records despite explicit Edit denial | HTTP/ORM reproduced |
| B6-002 | Functional defect/access control | High | Installation submission accepts a Project outside the user's selected scope | HTTP/ORM reproduced |
| B6-003 | Functional defect/data preservation | High | Same entry draft overwrites work across Department workspaces | HTTP/ORM reproduced; key construction inspected |
| B6-004 | Functional defect/data preservation | High | Preflight-rejected submit can mark a draft for later deletion | Code-confirmed; isolated JS marker/condition probe; full browser repro pending |

Total: 39 findings. No browser or full Installation workflow certification is
claimed. The previously recorded browser runtime failure remains unresolved.

### B6-001 — Appending is authorized as Create rather than Edit

Create an Installation as Admin. A Technical user can view its Project and has
`records.create_installation`, but is explicitly denied `records.edit`. The normal
record Edit page returns 403. Submit a valid new device to `/installations/submit`
with `append_record_id` pointing to that saved Installation: HTTP 201 succeeds,
the original record number is returned, and saved work-item count increases from
one to two. The target record belongs to Admin, not the submitting Technical user.

Evidence: `app/routers/installations.py:391` requires Create, then `_load_record`
checks visibility for `append_record_id` at `:399–406`; it does not require Edit.
The append branch (`:1016`) adds devices/data rows, replaces participants and
invalidates linked reports. Normal Edit explicitly requires `records.edit`
(`:1491`). GET `submit?append_to=...` has the same Create-only gate at `:188`.

Recommendation: authorize an append as mutation of the target record, with Edit
permission plus record/Project access. Keep new-record creation separate. Define
whether editors need Create permission to add a device through the shared helper;
normal Edit currently delegates additions back to that helper. Test both directions
of the permission matrix. Preserve revision logging, report invalidation and one
transaction; no migration is expected for the authorization repair.

### B6-002 — Submitted hierarchy IDs bypass the visible Project restriction

The same user has Selected record scope for Project A only. Project B does not
appear as a Project option. Submit a valid Installation naming B, its assigned
Site, and its existing quotation number, using a service-enabled Item visible in
the active Department. HTTP 201 succeeds and an Installation with B's Project ID
is persisted. This probe stays within one Department; it does not claim that the
Department boundary was bypassed.

Evidence: `active_project_hierarchy` (`app/project_hierarchy.py:12`) narrows picker
choices. `validate_entry_scopes` (`app/entry_scopes.py:26`) instead loads submitted
Project IDs, validates activity/relationships, and does not check the user's
Project authority. The Installation submit handler does not add that missing check.
Quotation matching validates identity/Project relationship, not permission to
create evidence under that Project. Author access to own records makes this more
than a hidden picker issue: unauthorized Project evidence becomes durable.

Recommendation: enforce current record-creation Project scope for every submitted
Site section before file writes or mutations, including appended sections. Reuse
one server-side authorization rule for picker and validation while preserving
separate quotation identifier access for technicians. Do not grant commercial
quotation access merely to permit reference selection. Test a mixed allowed/denied
multi-Site request for atomic rejection. Shared validators affect other entry
types, so inspect those call sites before applying a broad change.

### B6-003 — Draft identity omits Department and independent entry sessions

Save a draft on `/installations/submit` in Department A. Switch the same user to B:
`/drafts/current` returns A's payload. Save B's entry, switch back to A, and read:
only B's payload remains. Both saves return 200; this overwrites the first draft
instead of retaining separate workspace work. No cross-user disclosure is claimed.

Evidence: `app/static/js/app.js:2103` constructs the key from pathname plus optional
append target. `app/routers/drafts.py:141` upserts by user/key only. The local photo
key adds user ID at JS `:2402`, but no workspace or draft-instance identity. Two
independent Create tabs likewise target the same key by construction; that browser
scenario was not separately run. The nominal 20-draft limit does not give users
20 independent new Installations when all use this one pathname key.

Recommendation: give each new entry a durable draft-instance ID, bind it to the
workspace and user, and restore through an explicit draft URL/context. Use the same
identity for text and cached files. Define safe handling of legacy page-key drafts;
never automatically overwrite or assign ambiguous old drafts to a Department.
This may require an approved schema/backfill or compatibility design. Keep server
authorization on final Save; restoration itself must not grant resource access.

### B6-004 — Draft cleanup infers success from leaving the form

The autosave submit listener sets `sms-finalizing-draft` and related sessionStorage
markers before the later asynchronous submit listener runs preflight validation.
If preflight finds an incomplete device, the later handler returns without sending
a request and does not clear those markers. Navigating afterward to a non-entry
page, such as Records, meets the global cleanup condition. It requests draft
deletion and deletes locally cached files under that draft prefix even though no
Installation was saved.

Evidence: marker listener `app/static/js/app.js:2453`, page-change cleanup `:2469`,
and preflight return in the later submit handler around `:2575`. The entry/edit
forms use `novalidate`, so native constraint validation does not prevent this
listener sequence. An isolated Node probe executed the actual marker listener
with mocks and confirmed the later `/records` cleanup condition becomes true.
It did not run a browser, delete a real draft, or certify DOM/event behavior.
The server and local-file delete calls are confirmed in the inspected cleanup body.

Recommendation: delete a draft only after explicit successful server Save, bound
to the correct user/workspace/draft instance. Clear any pending state on preflight
failure; navigation alone is not success. Retain drafts on validation errors,
cancel/navigation and uncertain network results. Verify cached-photo survival too.
Do not fix this solely by moving the marker: completion still needs authoritative
success and correct identity, coordinated with B6-003.

### Positive controls and remaining review coverage

- Wrong-Project quotation returned 422 with a keyed quotation error. Invalid PNG
  evidence returned 422; neither attempt created a record. Corrected resubmission
  returned 201. Reusing the token returned 422 and the final record count remained
  one. These checks support existing validation/token safeguards, not the missing
  Project authorization check.
- Code enforces active services/Items, service-enabled Items, duplicate serial
  rejection, device-count/text limits, valid Sub Project/Site relationships and
  Project-matched photo profiles (`app/photo_guidance_profiles.py:22`). Profile
  absence is allowed. Full guidance visibility/enablement and photo-description
  browser behavior remain pending.
- Normal Edit traces saved identity, photo changes, asset detachment, revision
  creation and linked-report invalidation. Appended edits roll back when the shared
  creation path rejects additions. Those complex paths were not all runtime-tested;
  complete removal/multi-Site/photo-mirror regressions remain open.
- Draft endpoints constrain user/key, size and retention; text lives server-side,
  while selected photos are cached in that browser. Final entry remains separately
  validated. Concurrent saves, offline restore, session expiry, failed discard,
  storage quota errors and photo availability messaging need targeted browser work.
- Field labels, error focus, keyboard use, mobile camera behavior, Arabic RTL and
  long-form task effort cannot be certified by HTTP success. Excel import preview,
  confirmation and asset matching are deliberately deferred to Batch 7.

Diagnostic databases `sms_review_840aed4ca1434e59` (authorization/draft probes) and
`sms_review_9dc3ebcf53884932` (negative controls/corrected submission) used synthetic
users/evidence, process-local settings with dotenv suppressed and temporary upload
directories. Both were dropped in `finally`; temporary files were removed. The
Node probe ran from stdin with mocked storage and wrote no application files.
No fixed test database or full suite was used. Existing data, source/tests/config,
services and installations were untouched. Existing Starlette/httpx deprecation
warning appeared; no pytest pass count is claimed.

### Priorities and proposed Batch 7

P14 addresses Installation mutation/Project authorization; P15 addresses draft
preservation and explicit successful-completion cleanup. Both join the existing
high-priority access/data-preservation work. Check shared entry callers before
reusing a repair across modules; do not expand permissions to hide a validation gap.

Next proposed batch: **Installation Excel import, preview/confirmation and asset
mapping**, including imported versus browser-entered device data and correction
compatibility. Keep Maintenance/Preventive Maintenance full workflows separate.
Batch 6 stops here pending the next instruction.

## Batch 7 — 2026-10-07: Installation import and device-data mapping

Scope: current entry UI versus retained Excel endpoints, template scope, preview
validation and final mapping of imported/browser-entered rows into assets.
Baseline remains the dirty tree at `3df505a`; documentation branch is
`docs/ui-ux-review-batch-7`. No source, test, configuration or existing data changed.

The current Installation form uses `partials/entry_data_table.html`; it does not
include `partials/entry_device_import.html`. The latter and its JS still exist,
as do downloadable templates, preview endpoints and final signed-token support.
Consequently, endpoint probes below do not imply a currently reachable Excel UI.
This is a useful distinction from the older README description of Data Entry import.

### Findings at a glance

| ID | Classification | Severity | Affected workflow | Verification |
| --- | --- | --- | --- | --- |
| B7-001 | Usability/documentation inconsistency | Medium | Documented Excel workflow has no current entry-page controls | Rendered HTML and template references confirmed |
| B7-002 | Functional defect/access control | High | Downloaded template includes hidden Project names | Scoped HTTP/workbook-content probe |
| B7-003 | Functional defect/data consistency | High | Workbook location labels are accepted without matching selected scope | Preview and final-save HTTP/ORM reproduced |
| B7-004 | Functional defect/workflow validation | Medium | Preview accepts more devices than final Save permits | 21-row preview succeeds; final Save rejects |
| B7-005 | Functional defect/data integrity | High | Independent table rows overwrite asset metadata by position | HTTP/ORM reproduced with and without import |

Total: 44 findings. No browser, Excel desktop interaction, workbook rendering or
visual-layout pass is claimed. Spreadsheet checks inspect the application's own
generated workbook and synthetic request fixtures; no workbook is a deliverable.

### B7-001 — The documented import workflow is absent from entry

GET `/installations/submit` returns browser-table controls but no
`data-entry-device-import` controls. The template endpoint still returns 200.
Repository references show the import partial is not included by the current entry
templates, while README still describes template/preview/confirmation as Data Entry.

Evidence: `app/templates/installation_entry.html:75`,
`partials/entry_device_import.html`, `app/entry_device_imports.py:89`, and the README
Reports extension description. This may reflect an intentional transition to direct
entry; the review cannot infer the intended product policy from dormant code.

Recommendation: decide whether Excel import remains supported. If yes, expose one
clear entry point after the validation/mapping issues below are fixed. If retired,
align documentation and explicitly define compatibility for retained clients and
signed previews. Do not simply reinsert the partial: its `applyRows` changes the
existing device-card count/selection on Preview, so evidence preservation and an
explicit apply/replace decision need review. No automatic endpoint removal is proposed.

### B7-002 — Template reference lists disclose out-of-scope Projects

Use the Batch 6-style Technical user with Selected record scope for Project A only.
The Project B name is absent from their entry picker. Download the Installation
template: its hidden `Lists` worksheet contains B's name. A hidden worksheet is
part of the downloaded file, not an authorization boundary.

Evidence: `_active_main_project_names` and `_active_sub_project_names`
(`app/entry_device_imports.py:60`, `:71`) query all active rows rather than authorized
Project IDs. `device_template` (`:89`) inserts these lists into the workbook.
Main Project disclosure was reproduced; Sub Project name disclosure follows the
same code path but was not separately isolated in the fixture.

Recommendation: build reference lists from the same effective entry scope as the
picker, including authorized parent-child relationships. Keep template, preview
and final-submit checks consistent; B6-002/P14 covers final mutation authority.
The endpoints also use general record-submitter eligibility rather than a distinct
entry-kind action check; review that policy without accidentally breaking legitimate
edit/import use. No migration is expected. Do not broaden visibility for convenience.

### B7-003 — Preview accepts conflicting workbook Project/Site labels

Select valid Project A/General/Gate on the request, but upload a row whose Main
Project/Sub Project/Site cells say `Wrong Main`, `Wrong Sub`, `Wrong Site`.
Preview returns 200, `ok: true`, no errors and a signed token. Final Save succeeds
using the selected Project/Site. The previewed labels therefore do not reliably
describe the hierarchy that will be saved.

Evidence: `validate_device_workbook` (`app/device_import.py:225`) requires a nonempty
Site label but does not compare the workbook's location strings to the selected
hierarchy. It assigns `row.site_id = site.id` at `:308`. The preview signs the request's
selected IDs and the original row strings; final submission validates those IDs,
not agreement between the displayed row labels and them. Without browser-table
replacement, `location_name` also draws from the imported free-text Site label in
the create code; that specific persisted variant was code-traced, not separately probed.

Recommendation: choose one source of truth. Either reject mismatched worksheet
hierarchy fields with row-specific errors or explicitly map/confirm every row to
the selected scope and display the effective destination. Do not silently accept
an entire workbook intended for another location. Preserve historical IDs and
snapshots; existing inconsistent data needs a separately approved audit, not an
automatic corrective rewrite. Multi-site workbook support would be additional scope.

### B7-004 — Successful preview cannot guarantee an admissible row count

A synthetic 21-device workbook passes preview and receives a token. Submit its
21 matching device rows: final Save returns 422, `Add at most 20 devices to one
record.` The parser allows up to 1,000 rows, while Installation final entry caps
devices at 20 across the record. Multiple individually valid previews can also
exceed the record-wide limit (code-derived; not separately submitted).

Evidence: `MAX_IMPORT_ROWS` in `app/device_import.py:34`; Installation
`MAX_DEVICES_PER_RECORD` at `app/routers/installations.py:97` and validation `:454`.
The retained client applies preview rows before final validation, with no explicit
record-wide limit in that import application path.

Recommendation: surface and enforce the same effective capacity before applying
preview rows, accounting for other Site sections. Offer explicit splitting only
if the user wants it; never silently truncate or increase record limits without
evidence about photos/performance. Template instructions should state the operative
limit. Existing records require no migration for this repair.

### B7-005 — Positional table mapping changes the wrong device's metadata

Import a Camera with serial `XL-ONE`, IMEI `EXCEL-IMEI` and SIM serial
`EXCEL-ICCID`. In the independent browser table, enter an `Unrelated router`, model
`OTHER`, serial `TABLE-OTHER`, with `TABLE-IMEI`/`TABLE-ICCID`. Final Save returns 201.
The asset remains Camera/XL-ONE but now contains TABLE-IMEI; the work item does too,
while the saved table retains the unrelated router identity. The import's metadata
has been overwritten without verifying that the rows describe the same device.

A separate ordinary submission without an import also succeeds with mismatched
table/device identities. Reusing its table IMEI/SIM serial for another record
reaches a database uniqueness error and returns 500. Rollback preserves just the
first asset; duplicate data was not committed. This is a missing actionable
prevalidation path, not proof that uniqueness enforcement is absent.

Evidence: `parse_entry_data_rows` (`app/entry_data_tables.py:25`) validates independent
text rows but no device identity link. The Installation route matches table and
work item by `(scope_position, local position)` (`:991–1014`), then overwrites IMEI,
SIM details and remarks after import identifier validation. Frontend item-change
prefill (`app/static/js/app.js:384`) does not establish a durable identity link or
prevent independently editing/removing table rows. Saved Edit later replaces table
rows separately (`installations.py:1883`), another compatibility path needing tests.

Recommendation: either treat the table as independent evidence with no asset
mutation, or link rows explicitly to device instances and validate the relationship.
Agree precedence for Excel versus table values and show any proposed replacements.
Run identifier checks on the final resolved values before writes, retaining DB
constraints for races. Test removing/reordering rows, duplicate models and edits.
Stable links may require an approved migration; positional historical data cannot
be safely reconciled automatically. This is the highest data-integrity priority
from the batch and applies to the currently visible browser-table workflow.

### Controls, cleanup and remaining work

Code retains `.xlsx` format/header validation, a 5 MB compressed/50 MB expanded
limit, available-Item matching, duplicate workbook identifiers and current-asset
revalidation. Preview tokens are signed, expire after two hours and bind entry kind
and selected hierarchy IDs. These are useful controls; they do not validate the
later positional overwrite. Workbook `Status` means all A–J cells are filled, not
that server validation passed; optional blank fields can show Invalid despite an
accepted preview. That wording deserves review if import is restored.

The application-generated workbook was read as an XLSX ZIP. Synthetic row XML was
inserted in memory for request probes, without changing source or existing files.
Scratch database `sms_review_41fe4e94002842ea` covered template scope, location
mismatch, 21-row acceptance/rejection and mixed import/table persistence.
`sms_review_a42ad53ecbf246bb` covered ordinary table mapping and duplicate rollback;
the expected uniqueness failure was logged by the application's existing handler.
Both were dropped in `finally`, with temporary upload directories removed.
Process-local settings suppressed dotenv. No fixed test database/full suite,
migration, real-user mutation, service restart or packaged artifact was involved.

Remaining: browser preview/apply/reset and warning presentation; formula/text
identifier fidelity in actual Excel; long-cell validation; token expiry/replay and
concurrent assets; imported metadata on saved Edit; large-workbook resources;
complete Maintenance import matching/overwrite confirmation; bilingual layout and
accessibility. Current import UI absence prevents claiming a user click-through.

### Priorities and proposed Batch 8

P16 addresses explicit device/table identity and final-value validation first.
P17 defines the supported import workflow and aligns template scope, preview
destinations and capacity; coordinate it with P14 rather than reopening access.
Neither phase is approved. Do not automatically repair historical asset metadata.

Next proposed batch: **Maintenance and Preventive Maintenance entry/editing**,
focusing on installed-asset selection, results/evidence, imported metadata overwrite,
record permissions and draft dependencies. Reuse shared findings instead of
retesting Installation paths. Batch 7 stops here pending the next instruction.

## Batch 8 — 2026-10-07: Maintenance and Preventive Maintenance entry

Scope: current create and append forms, Project/Site scope, Service and evidence
validation, photo guidance, and retained Excel-import final-submit behavior. This
batch also checked the user-facing form structure in templates. It did not certify
the saved Edit lifecycle or visually test either form. Implementation is not
authorized.

Both forms now present Service work cards and a separate Site data table. An Admin
created one normal record of each kind in disposable data (201). The server retains
required evidence-photo checks, keyed field errors and duplicate-submit tokens.
The common jump bar calls its Service section “Items” (`nav.pricing.items`), which
may make the task sequence less clear; confirm wording with users and in both
languages during the pending browser pass. An asset-specific service-history
requirement also needs a product decision: current new cards use a Service, not an
Installed Asset. The absence of an asset selector is not treated as a defect by
itself.

### B8-001 — Hidden Project photo guidance is exposed during field entry

Severity: high (cross-Project information disclosure). A scoped user whose Project
picker excluded Project B still received B’s Photo Guidance Profile name as an
`<option>` in both Maintenance entry forms. Calling
`GET /photo-guidance?project_id=<B>&profile_id=<B profile>&work_site_id=<B site>`
as that user returned 200 with `enabled: true` and B’s Before alert. The endpoint
also returns After alerts and descriptions when present; those fields were
code-traced, not separately asserted in the probe.

Evidence: `profile_choices` in `app/photo_guidance_profiles.py:11` selects every
profile without user or Project filtering. Both entry contexts pass that list to
their templates, whose profile options include names and Project IDs
(`app/templates/preventive_maintenance_entry.html:11`,
`app/templates/general_maintenance_entry.html:9`).
`app/routers/photo_guidance.py:310` checks submitter eligibility, setting and
Site/Profile association, but not the caller’s Project access. The disposable
Project A/B HTTP/HTML probe observed the hidden name and alert.

Recommendation: scope profile choices and the guidance read endpoint to the same
effective Project authority as entry creation. Reject inaccessible IDs without
revealing names or guidance text. Keep project/profile/site relationship checks,
and test Admin plus Selected/Own/None users on both entry pages and direct URLs.
Check how existing records tied to later-hidden Projects should be displayed before
altering saved-record access. No migration is expected for the initial read guard.

### B8-002 — Retained maintenance import tokens cannot match current Service cards

Severity: medium (incomplete retained workflow; support decision required). Neither
current Maintenance form includes the import partial or an Installed Asset selector,
yet both submit handlers still accept a signed `device_import_token`. In a bounded
probe, a correctly signed preview-format token for a matching Project/Site and one
device row reached final validation, then both endpoints returned 422 at
`installed_device_id_0`: “This item no longer matches the Excel preview. Preview
the file again.” The token was constructed through the application's serializer;
an end-to-end preview-button path was not claimed.

Evidence: current Service forms in
`app/templates/preventive_maintenance_entry.html` and
`app/templates/general_maintenance_entry.html` have no
`partials/entry_device_import.html`. The routes set `selected_item` to `None` for
the Service entries and then require it to match the imported device
(`app/routers/maintenance.py:435`, `app/routers/general_maintenance.py:388`).
The resulting error asks for a preview path that these pages do not offer. This
also limits confidence in retained clients or tokens from older entry versions.

Recommendation: decide whether Excel import is supported for Service-based
Maintenance. If supported, define explicit asset/service matching and show the
preview, confirmation and recovery controls with consistent final validation.
If retired, make the route contract and user documentation truthful, and reject
legacy import requests with an actionable message. Preserve existing records and
token/asset safety while changing behavior; do not silently map workbook rows to
unrelated Service cards. Coordinate with B7-001–005/P16–P17.

### Shared findings confirmed in both Maintenance workflows

- **B6-001/P14 — append authorization:** a user with Create permission and an
  explicit Edit denial received 403 on normal saved Edit, yet `append_record_id`
  POST returned 201 and increased the Admin record’s work-item count from one to
  two for each kind. Both submit routes require Create and use record visibility
  for append lookup, without enforcing target Edit authority. Participants and
  report/revision consequences follow the append path; those side effects were
  code-traced rather than individually asserted in this probe.
- **B6-002/P14 — Project mutation scope:** the same user’s Project picker omitted
  Project B, yet a forged otherwise-valid B hierarchy POST created a record under
  B (201) for each kind. `validate_entry_scopes` confirms active hierarchy
  relationships but does not check the actor's Project grant. This is confirmed
  for Installation and both Maintenance entry kinds; P14 must cover all three.
- **B6-003/B6-004/P15 — drafts:** both forms use the shared draft client. The
  Batch 6 overwrite and premature-cleanup evidence applies as a code dependency,
  but no new Maintenance-specific multi-tab browser run was made here.

### Verification limits, cleanup and next area

The main reproductions used fresh disposable PostgreSQL databases and temporary
uploads, with dotenv loading suppressed in the probe process. Successful scratch
databases were `sms_review_a43520d7affa439f` (authorization, hidden Project and
import submission) and `sms_review_093f2643f7a64fae` (profile disclosure). They
were dropped in `finally`, and temporary uploads removed. Two earlier setup probes
stopped because their test user lacked the intended Create grants; they contribute
no finding. A separate disabled-profile fixture was inconclusive and is excluded.
No deployed database, existing uploads, service, source file or test was changed.

Browser bootstrap remained unavailable, so no visual layout, responsive, keyboard,
screen-reader, focus, camera, Arabic RTL or full user click-through claim is made.
Saved Edit/multi-Site removal, linked report invalidation, photo-mirror behavior,
concurrent submission and existing-asset service history remain open. The next
proposed batch is **Records and Installed Assets**: listing/detail/edit authority,
asset history, search/filter/sort/pagination and destructive actions. Batch 8
stops here pending the next instruction.

## Batch 9 — 2026-10-07: Records, evidence access and asset navigation

Scope: unified and type-specific record lists, detail/edit/delete entry points,
search/filter/pagination behavior, media authorization, and the current Installed
Asset presentation. No source implementation is authorized. The review inspected
the three record routers, `record_views.py`, and list/detail templates; it did
not perform a full saved-Edit or destructive-action regression.

The unified list uses a bounded, stable date/ID ordered page across all three
types. Type-specific lists also paginate and offer more filters. Detail routes
check record visibility, Edit routes require `records.edit`, and Delete routes
require `records.delete` plus CSRF. Installation deletion blocks an asset
referenced by a Maintenance record and removes linked generated reports only after
the record passes its checks. The detail templates warn Admins about linked
reports before deletion. Those are useful controls; deletion and asset cascade
were code-traced, not run against a full dependency fixture in this batch.

### B9-001 — Type-specific lists disagree with mixed-Project detail access

Classification: functional access/consistency defect. Severity: high. A
disposable Maintenance record had Project A as its primary Project and a work
item in Project B. A Customer assigned only A matched the type-specific list's
visibility predicate (one record), while the unified Records predicate excluded
it (zero) and the detail loader returned 403. An Admin filtering the type-specific
list by B got zero, while the shared record-view Project-B predicate matched
one. The All Records page itself currently exposes only text/type filters. The SQL
and loader results were observed in a disposable database; the exact page HTML
was not opened in a browser. The type-specific list renders the record number,
Project/Site, service and result, so the mismatch can expose a mixed record's
summary and leads to a dead-end detail link.

Evidence: each type-specific list grants non-Admin visibility from submitter or
primary `site_id` only (`app/routers/maintenance.py:837`,
`app/routers/general_maintenance.py:738`, `app/routers/installations.py:1149`).
Their Project filters also compare primary `site_id` (`maintenance.py:884`,
`general_maintenance.py:766`, `installations.py:1200`). In contrast, shared
`app/record_views.py:299–465` excludes an inaccessible work-item Project and
finds Project matches in work items; all three detail loaders require access
to every work-item Project (for non-creators). The isolated general-Maintenance
case reproduced both differences; Installation/Preventive are code-confirmed
analogues, not separately seeded.

Recommendation: centralize the effective record visibility and Project-filter
predicates for unified, type-specific, detail and export views. Define how a
creator's own mixed-Project record remains visible after grant changes. Match
counts, rows, links and media access; avoid fixing only the template. Do not
display partial details without an explicit redaction policy. No migration is
expected for predicate alignment, but tests need multi-Project records,
Customers, Selected/Own technicians, creators and revoked grants.

### B9-002 — Evidence-photo URLs omit the Records View action check

Classification: functional permission defect. Severity: high. In a disposable
HTTP probe, a Technical user explicitly denied `records.view` but assigned the
record's Project received 403 at the Preventive record detail URL and 200 with
the exact evidence bytes at `/media/photo/<id>`. This requires a known photo ID;
the Project access check still applied, so this is not evidence of cross-Project
photo access. The probe overrode only the authenticated user and database
dependencies, not the route logic; browser/session behavior remains untested.

Evidence: detail routes call `require_permission(..., "records.view")` before
`_load_record`, while the media routes in `app/routers/maintenance.py:1722–1790`,
`app/routers/general_maintenance.py:1436`, and
`app/routers/installations.py:2074–2140` use `get_current_user` and `_load_record`
without that action permission. `_load_record` checks creator/Project
visibility, not `records.view`. The Preventive media path was HTTP-confirmed;
other media handlers were code-confirmed.

Recommendation: require an effective record-evidence read permission on all
record photo routes, consistent with detail access for Technical users and
Customer assignments. Preserve legitimate creator access only where the
permission policy explicitly grants it. Test known photo IDs after `records.view`
revocation, across all three entry types and both item/legacy photo endpoints.
The change needs no migration but must not break authorized report rendering.

### B9-003 — Detail pages advertise Edit to users who cannot edit

Classification: usability problem. Severity: low. All three detail templates
show Edit whenever `user.can_submit_records` is true, which includes any
Technical user. The corresponding GET Edit routes require `records.edit` and
return 403 for users denied that action. A read-only Technical user therefore
sees a promising action that cannot open. This is code-confirmed; no visual or
keyboard interaction was performed.

Evidence: `app/templates/installation_detail.html:15`,
`app/templates/maintenance_detail.html:15`, and
`app/templates/general_maintenance_detail.html:4` versus the `records.edit`
guards at `app/routers/installations.py:1482`,
`app/routers/maintenance.py:1154`, and
`app/routers/general_maintenance.py:979`. Keep backend guards.

Recommendation: render Edit only when the user has the effective Edit action and
target-record authority; if an authorized user can see but not edit a specific
record, explain that state rather than link to 403. Check role, Department and
Project grant combinations. No migration; focused template/HTTP and browser
checks suffice.

### B9-004 — Invalid list filters silently become broad results

Classification: usability and query-contract problem. Severity: medium. On the
type-specific lists, a malformed Project/Site/device ID is retained in `filters`
and makes `has_filters` true, but `entity_id` returns `None` and no condition is
added. An unknown numeric `device_id` or one without a linked
catalogue ID is also ignored. Invalid dates are parsed to `None` and ignored,
while an invalid Result resets to blank. A bookmarked or hand-edited filtered URL
can therefore show all accessible records under a misleading applied-filter
state. A stale but valid numeric Project/Site ID instead produces an empty set;
that is a separate recovery case. This is code-confirmed; no HTTP/browser filter
round trip was performed.

Evidence: `app/routers/installations.py:1122–1339`,
`app/routers/maintenance.py:810–1023`, and
`app/routers/general_maintenance.py:714–867` use the same conditional pattern.
Their templates show an Apply/Clear state based on the raw `filters` values.

Recommendation: validate every supplied filter, show an actionable invalid or
stale selection, and never silently broaden a search. A valid but now
inaccessible Project should not reveal its name; choose an empty result or a
neutral error. Normalize the URL and on-page controls together. Test malformed,
deleted, inaccessible and reversed-date inputs plus pagination links. No
migration; reuse one filter parser if it reduces the three-route drift.

### Asset-history and verification limits

`InstalledDevice` has an installation owner and optional Maintenance links, but
there is no dedicated Installed Asset list/detail/history route in the inspected
routers or navigation. Installation details show a device table; current new
Maintenance forms are Service-based and save no asset link (Batch 8). This does
not establish that every service visit must attach an asset. Decide whether users
need a per-serial lifetime view before adding another screen or changing the
data model. If required, define how legacy unlinked Service records and edited
identifiers appear without inventing matches. B7-005/P16 asset identity must be
settled first. No asset migration or backfill is proposed by this review.

The mixed-Project query probe used `sms_review_250de0c69e70413f`; the photo
HTTP probe used `sms_review_b8b3184f4bbf45eb`. Both fresh PostgreSQL databases
were dropped in `finally`, and temporary upload directories removed. Earlier
setup attempts failed before yielding evidence and were also cleaned. No
development/deployed database, existing upload, service or application source was
changed. In-app browser bootstrap remained unavailable, so responsive, Arabic
RTL, keyboard, focus, screen-reader and visual search/error states are pending.
Full saved Edit, delete/report/asset-cascade, photo cache, sorting requirements,
large-data performance and concurrency remain unverified.

Prioritize B9-001/B9-002 as P19 access parity; B9-003/B9-004 fit a smaller P20
record-action/filter UX phase. Both phases are proposals only. The next proposed
batch is **Saved and filtered Reports**: selection, Customer scope, report
regeneration and PDF usability. Batch 9 stops here pending the next instruction.

## Batch 10 — 2026-10-07: Saved reports, filtered exports and PDF

Scope: standard filtered Records PDF, three saved-report list/create/detail/PDF
routes, selection and time-filter behavior, report invalidation on source edits,
and one small rendered Maintenance PDF. This is a code and isolated-probe review,
not a full Customer or multilingual acceptance test. No implementation is
authorized.

The standard export reuses the same scoped Records query as its preview and caps
output at `max_pdf_records`, returning an actionable 422 if too many records
match. Saved-report creation rechecks selected IDs against authorized record
views, enforces a record count cap, and uses a locked counter for numbering.
Details and PDF downloads revalidate linked record visibility. A disposable
single-record Maintenance report saved with 303 and downloaded with 200; its
four-page English PDF had eight native bookmarks. Rendered pages showed a clear
cover, contents/index, record detail and approvals, with no clipping in that
sample. Larger/photo-heavy, Arabic, physical print and interactive link behavior
remain unverified.

### B10-001 — Report filters lose selection context and broaden on error

Classification: usability/validation-recovery defect. Severity: medium. The
record-number/time filter is a separate GET form above the report creation POST
form. Applying it reloads the page, so any entered report name, date, Team Leader,
technicians or record selections are not submitted with the filter. When Save
fails, the POST URL has no filter query and `_report_form_context` rebuilds the
full record tree, although submitted field values and record IDs are retained.
Invalid time input also shows an error while loading the full unfiltered tree.
This can make a user think the intended filter still governs the choices.

Evidence: `app/templates/structured_report_form.html:7–24` contains separate
GET/POST forms with no shared draft state; `app/routers/structured_reports.py:132`
parses the time query, `:274` builds the tree from the request query, and `:577`
returns the same context after validation errors. In disposable HTTP checks, a
`record_number=NO-MATCH` GET hid the sample record (200); an invalid `from_at`
GET displayed it (200); a failed POST redisplayed it (422). Actual partially
completed browser form state was code-traced, not visually tested.

Recommendation: keep filters and report-entry state together across Apply,
validation and retry, or make record selection a deliberate staged step with
drafted form values. Invalid time ranges should not silently present all
records as selectable. Preserve selected IDs by stable record identity when
the visible tree changes and show any selections outside the current view.
No migration is expected; test filtered selection, failed Save, browser Back,
multiple Site branches and both languages before changing the interaction.

### B10-002 — Report actions are shown without their action permissions

Classification: usability problem. Severity: low. The saved-report list shows
Create to every Technical user via `can_submit_records`, even if
`reports.create` is denied; its GET route then returns 403. The saved-report
detail always shows Preview and Download, although both routes require
`reports.download`. The shared Records page likewise always displays Export PDF,
while `/reports/pdf` requires `reports.download` for internal users. These are
code-confirmed permission/UI mismatches, not observed browser clicks. Backend
guards remain effective.

Evidence: `app/templates/structured_reports_list.html:8`,
`app/templates/structured_report_detail.html:9`,
`app/templates/records.html:12–17`; route guards in
`app/routers/structured_reports.py:562`, `:754`, `:808` and
`app/routers/reports.py:75`. The latter page is shared by `/records` and
`/reports`, so both entry points need the same action presentation.

Recommendation: gate each action with its effective permission and show a
useful read-only state where appropriate. Keep server authorization intact.
Check direct users with View but no Create/Download, Customer access and
Department switches in focused HTTP/template plus browser checks. No migration.

### B10-003 — Successful result is red in detailed report PDF

Classification: visual/semantic usability defect. Severity: low. In the rendered
four-page sample, the cover summarizes one Successful result in green, but the
same item's “Completed successfully” label on the detail page is bright red.
The contradictory cue can make a successful visit look like a failure at a
glance. This was observed in the PNG rendering, with text extraction confirming
the label. It is not a large-report or print-color test.

Evidence: `app/structured_report_pdf.py:244` defines `card_status` with `RED`
unconditionally; `_device_card` applies it to every item's result at `:1318`.
The style is also used by the attention card, where red may be appropriate.

Recommendation: map detail status color from the result tone and reserve a
distinct warning/error cue for attention items. Keep text labels and contrast
so meaning does not depend on color. Review all four results, grayscale print
and accessible contrast before release. No data or schema change.

### B10-004 — Editing a source record removes full reports without a clear warning

Classification: data-loss/feedback problem. Severity: high. A material saved
Edit to any of the three source-record types calls `delete_linked_reports`,
which deletes the entire generated report containing that record. The Edit form
does not identify linked reports or warn before Save, and its success message
only says the record updated. The source detail's linked-report warning is shown
to Admins for the Delete context, not to a Technical editor. Append flows add a
post-save message, but still do not supply a pre-save impact review. The deletion
path was confirmed in code; full Edit with an existing report was not executed
in this batch.

Evidence: `app/saved_report_deletion.py:27`; Edit call sites at
`app/routers/installations.py:1929`, `app/routers/maintenance.py:1601`, and
`app/routers/general_maintenance.py:1336`. The shared
`app/templates/record_edit.html` has no linked-report context or warning. The
normal success flashes at the end of all three Edit routes omit the deleted
report count. This affects complete report packages, including other records
in the same report, not only the edited one.

Recommendation: show the exact linked-report count/numbers and consequence
before committing a material Edit, then report the outcome and a regeneration
path. Decide whether superseded reports should be retained as invalidated
historical artifacts instead of deleted; that larger policy could require a
migration and access/version design. Keep current atomic deletion until an
approved replacement avoids misleading stale PDFs. Test no-op/failed/successful
Edit, mixed-record reports, append, creator/Customer views and transaction
rollback before changing lifecycle behavior.

### Shared access dependency, scale and cleanup

Batch 9's B9-001/P19 mixed-Project mismatch also affects saved-report lists:
`_reports_for_user` initially checks each link's primary Project ID or creator,
while `_load_report` rechecks complete source-record visibility and may return
404 after a list row is shown. This is code-confirmed extension, not a new ID;
repair report list/detail parity with P19. Saved-report lists load every report
and its links/technicians before Python-side filtering and have no search or
pagination. That is a concrete discoverability gap and scale risk, but no
representative volume/latency was measured; evaluate it before specifying a
pagination design. The record-selection tree similarly loads all authorized
records, so large-data task timing remains open.

Isolated form checks used fresh database `sms_review_393802b9e99d4ce9`;
create/download and PDF rendering used `sms_review_0f18097eba0d48c5`.
Both databases were dropped in `finally`, temporary uploads removed, and the
generated PDF/PNGs deleted after visual inspection. No existing data, service,
application source or test was changed. Browser form, RTL, keyboard/focus,
Customer assignment, report revocation, PDF links, large report and physical
print checks remain pending. The next proposed batch is **Store and custody**:
receipts, issues, transfers, returns, reversals and reporting. Batch 10 stops
here pending the next instruction.
