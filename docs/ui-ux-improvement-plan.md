# UI/UX review coverage and improvement plan

Updated 2026-10-07. [Findings and evidence](ui-ux-logic-review.md).

Review authorization: Batches 1–10, completed to the code/isolated-probe extent
recorded below. Browser verification remains pending. Implementation authorization:
none. All implementation proposals are preliminary where dependencies remain open.

Legend: `[ ]` Pending; `[x]` Completed. Notes state blocked, in progress, or awaiting
verification. A mapped module is not a completed deep review.

## Review coverage — independent of implementation

- [x] Read repository instructions and current handoff.
- [x] Map application areas and representative workflows from navigation/routes.
- [x] Inspect category schema, depth rules, creation, editing and deletion.
- [x] Inspect single-Item recategorization, branch reparenting and Department moves.
- [x] Inspect absence of bulk moves and shared-purchase-document blocking behavior.
- [x] Inspect destination controls, folder paths, search, sorting and pagination.
- [x] Inspect Pricing category/item permission predicates and UI restrictions.
- [x] Trace directly related quotation, technical-document and service-item references.
- [x] Run bounded probes against a newly created, disposable PostgreSQL database.
- [x] Save Batch 1 findings, limitations, roadmap and next-batch scope.
- [ ] Browser walkthrough of category/item create, edit, move and error recovery.
  Note: blocked in this session by browser bootstrap tool failure; no screenshots.
- [ ] Category/item keyboard, screen-reader, mobile, zoom and Arabic RTL verification.
- [ ] Large-catalogue latency/query-count measurement and concurrency move checks.
- [ ] Validate hierarchy depth against representative user tasks/taxonomy.
- [x] Batch 2 code review of Pricing action/scope and Category-grant editing boundaries.
- [x] Batch 2 isolated probes of grant saves, scoped manager access and own-Item visibility.
- [x] Batch 2 inspect/probe document scope dependencies and shared purchase-link preservation.
- [x] Batch 2 inspect/probe transferred resource access, quotation Edit and saved package selection.
- [x] Save B2-001–007, revised priorities and proposed Batch 3; remove disposable data.
- [ ] Browser verification of Batch 2 permission saves, shared-document edits and quotation packages.
  Note: awaiting verification; browser bootstrap failed again. HTTP checks are not browser checks.
- [ ] Approve intended document-scope inheritance, shared-file disclosure and grant-edit authority.
- [ ] Full Pricing permissions matrix, concurrent grant saves/moves and service-asset consequences.
- [x] Batch 3 inspect quotation create/Edit, snapshots, calculations, alternatives and planner save path.
- [x] Reproduce metadata refresh, inactive related-line loss and quantity-rule mismatch in disposable data.
- [x] Check sampled arithmetic, numeric rejection, unchanged data after validation and detail/PDF HTTP responses.
- [x] Save B3-001–005, update P8/P9 and remove disposable data.
- [ ] Quotation browser/RTL/accessibility verification, planner fault injection and visual PDF review.
- [ ] Quotation mixed-currency/alternative runtime cases, concurrent edits, deletion and invoice/survey lifecycle.
- [x] Batch 4 code review of document creation/editing, file correction, recommendation and deletion flows.
- [x] Probe document uploads/downloads, title limits, invalid-form recovery and Arabic export headers.
- [x] Probe missing-file responses and failed-upload cleanup using disposable storage only.
- [x] Save B4-001–006, P10/P11 proposals and next-batch scope; confirm scratch cleanup.
- [ ] Document browser/keyboard/mobile/RTL and visual PDF/price-chart verification.
- [ ] Document full deletion/cascade/snapshot regression, concurrency, retries and large-package measurement.
- [x] Batch 5 inspect Project/Sub Project/Site setup, team scope and deletion fallback.
- [x] Probe hidden-Project team mutation, Own-role coupling and guidance action permissions.
- [x] Probe search/form recovery, Site name limits, default General and empty Site assignments.
- [x] Probe referenced/unreferenced Project deletion with disposable data; save B5-001–006/P12/P13.
- [ ] Full Project/Sub Project/Site dependency/cascade matrix, concurrency and customer assignments.
- [ ] Setup browser/mobile/RTL/accessibility checks and representative hierarchy loading measurements.
- [ ] Complete photo-guidance profile lifecycle and its field-entry interactions.
- [x] Batch 6 inspect Installation create/Edit/append authorization and hierarchy/evidence validation.
- [x] Reproduce append despite Edit denial and creation outside selected Project scope.
- [x] Reproduce cross-workspace draft overwrite and inspect completion cleanup with isolated JS probe.
- [x] Verify sampled wrong-quotation/invalid-photo rejection, corrected Save and duplicate-token rejection.
- [x] Save B6-001–004/P14/P15 and remove disposable data.
- [ ] Installation full multi-Site Edit/removal, asset/photo-mirror/report invalidation regressions.
- [x] Batch 7 inspect current import UI absence, retained template/preview/token and table mapping paths.
- [x] Probe hidden template Project names, workbook location mismatch and preview/final row limits.
- [x] Probe imported/browser-table overwrite, ordinary table identity mismatch and duplicate rollback.
- [x] Save B7-001–005/P16/P17 and remove disposable data.
- [ ] Browser import apply/reset, Excel identifier/formula fidelity and imported metadata on saved Edit.
- [ ] Import expiry/replay/concurrency, large-workbook behavior and complete matching/overwrite matrix.
- [ ] Browser preflight/draft cleanup, concurrent tabs/saves, offline/session recovery and cached-photo behavior.
- [ ] Installation keyboard/mobile/camera/RTL, error focus and representative long-entry task walkthrough.
- [x] Batch 8 inspect Maintenance and Preventive Maintenance current entry and append paths.
- [x] Probe both kinds for target Edit denial, hidden Project creation and import-token mismatch.
- [x] Probe hidden Photo Guidance names and direct guidance read; save B8-001–002/P18.
- [ ] Maintenance/Preventive saved Edit, full import decision, multi-Site and asset-history policy.
- [ ] Maintenance/Preventive browser, mobile, keyboard, camera and Arabic RTL verification.
- [x] Batch 9 inspect unified/type-specific list, detail, Edit, media and Delete routes.
- [x] Probe mixed-Project list/detail inconsistency and secondary-Project filtering.
- [x] Probe a denied-Records-View user against detail and known photo URL.
- [x] Save B9-001–004/P19/P20; remove disposable databases/uploads.
- [ ] Record full saved Edit and Delete/report/asset-cascade regression.
- [ ] Asset-history policy and legacy unlinked Maintenance-record treatment.
- [ ] Record browser search/filter, sort needs, mobile/keyboard/Arabic RTL verification.
- [x] Batch 10 inspect standard export and saved-report selection, access and lifecycle routes.
- [x] Probe filtered/invalid/failed report form states in disposable data.
- [x] Create/download/render one four-page English report and inspect its pages/bookmarks.
- [x] Save B10-001–004/P21–P23; remove disposable databases/uploads/PDFs.
- [ ] Full Customer/report-revocation matrix and source-Edit/report-deletion regression.
- [ ] Large/photo-heavy/Arabic PDF, keyboard, mobile, print and interactive-link verification.
- [ ] Saved-report list/search and large selection-tree timing with representative data.
- [ ] Store, warehouse/custody operations, reversals and reports.
- [ ] Product Evaluations lifecycle, repeat sessions, evidence and reports.
- [ ] Tasks, assignments, state transitions, comments and notifications.
- [ ] Wiring Diagrams library and its independent taxonomy.
- [ ] Full Users/Departments/permissions review outside Pricing dependencies.
- [ ] Authentication, recovery, language and session/error recovery.
- [ ] Dashboard, global navigation/discoverability and Quick Create task analysis.
- [ ] Logs Report and read-only operational settings; Service Console UX if requested.
- [ ] Cross-application terminology/layout/defaults/feedback/empty/loading-state comparison.
- [ ] Cross-application accessibility/responsiveness and duplicated-workflow assessment.

Do not mark the full catalogue UX review complete until its browser and accessibility
items are verified. Other modules are mapped, not certified.

## Batch log

| Batch | Scope | Evidence/result | Next action |
| --- | --- | --- | --- |
| 1, 2026-10-06 | Map and category/item deep code review | CAT-001–011; isolated HTTP/ORM/HTML probes; scratch DB removed; no source edits | User authorized Batch 2 on 2026-10-07 |
| 2, 2026-10-07 | Pricing access and document/quotation transfer dependencies | B2-001–007; isolated probes; cleanup confirmed; browser pending | User authorized continuation |
| 3, 2026-10-07 | Quotation create/edit lifecycle and error recovery | B3-001–005; HTTP/ORM and code evidence; scratch data removed; browser pending | User authorized continuation |
| 4, 2026-10-07 | Purchase Documents and Data Sheet lifecycle | B4-001–006; HTTP/ORM/storage probes and code evidence; scratch cleanup confirmed; browser blocked | User authorized continuation |
| 5, 2026-10-07 | Project/Sub Project/Site and team setup | B5-001–006; scoped HTTP/ORM/HTML probes; two scratch databases removed; browser pending | User authorized continuation |
| 6, 2026-10-07 | Installation entry/additions and drafts | B6-001–004; HTTP/ORM and isolated JS evidence; two scratch databases removed; full browser/edit coverage pending | User authorized continuation |
| 7, 2026-10-07 | Installation import and asset mapping | B7-001–005; template/HTTP/ORM probes; two scratch databases removed; browser pending | User authorized continuation |
| 8, 2026-10-07 | Maintenance/Preventive Maintenance entry and append | B8-001–002 plus B6-001/002 extension; isolated HTTP/HTML/code probes; scratch cleanup; browser and full Edit pending | User authorized continuation |
| 9, 2026-10-07 | Records, evidence access and asset navigation | B9-001–004; isolated SQL/loader and media HTTP probes; scratch cleanup; browser and full Edit/Delete pending | User authorized continuation |
| 10, 2026-10-07 | Saved reports and filtered PDF | B10-001–004; isolated form/create/PDF probes and four rendered pages; scratch cleanup; browser and full Customer/Edit pending | Stop and await user instruction |
| 11, proposed | Store and custody | Receipt, issue, transfer, return, reversal and reporting | Requires instruction to continue reviewing |

Batch 2 resolved several CAT-002/003/010 dependencies in code, but policy choices
remain unapproved. Batch 3 confirmed snapshot refresh and related-line loss on Edit,
plus quantity validation and recovery gaps. Full browser and export presentation
coverage remains open above. Batch 4 confirmed export-header, title/storage and
validation-recovery failures; file correction and destructive wording need policy
decisions. Batch 5 confirmed team mutation scope and role-based ownership failures,
plus setup permission/search/validation friction. Batch 6 confirmed Installation
authorization gaps and draft preservation problems. Batch 7 found a missing import
entry point, template disclosure, preview mismatches and unsafe table/asset mapping.
Batch 8 extended the Installation authorization findings to both Maintenance
workflows and found hidden guidance disclosure plus a retained import mismatch.
Batch 9 confirmed inconsistent mixed-Project lists and a photo-action permission
gap, plus Edit-link and filter recovery friction. Browser verification and untested
import/edit/delete combinations remain open above. Batch 10 confirmed report
filter-state loss, premature action links, a red Success PDF label and unannounced
linked-report deletion on source Edit.
Do not repeat completed category or transfer probes unless new evidence requires it.

Updated order: P0/P8/P12/P14/P15/P16/P18/P19/P21 access and data-preservation safeguards first;
then P10 bounded document failures, P1/P2/P3, P7 scope decisions and P9 validation/recovery.
P17 template disclosure should be repaired alongside P14; import UI policy precedes
restoring controls. P13/P20/P22 setup, record and report recovery can follow as
small fixes. P23 is a bounded PDF presentation correction.
P11 correction/deletion policy precedes its implementation. P4/P5 larger workflow
changes only afterward. P6 remains
measurement-led. Numbering is stable and does not imply approval or completion.

## Implementation phases — no work approved or completed

### P0 — Protect access grants, shared links and saved attachments

Findings: B2-001, B2-002, B2-005, B2-007; related CAT-003/CAT-010.
Priority: highest. Approval: none; each bounded repair needs a concrete approved plan.

Scope: separate Category access administration from content edits; preserve grants
outside explicit changes; prevent an incomplete visible document selection from
deleting hidden links; preserve quotation attachments independently of live sources.
Default policy proposal: Administrator-only grant changes, read-only navigation
ancestors, and explicit authorized removals. A conservative shared-document guard
can precede a richer per-link editing design.

Dependencies/risks: shared grant tables, legacy visibility, opaque hidden resources,
concurrent edits, whole-document versus per-Item authority, atomic file cleanup.
P2 navigation must not expand mutation rights. P5 cannot safely build larger moves
on destructive save behavior. Migration/compatibility: no migration expected for
initial guards/reconciliation; preserve IDs, existing grants/links and snapshots.
Any durable concurrency/version field requires an approved Alembic proposal.

Acceptance and checks:

- [ ] Selected manager cannot self-grant a root or edit other users' access via forged POSTs.
- [ ] Authorized Item management and read-only ancestor navigation continue working.
- [ ] User Roles displays complete nested paths; unchanged save retains all existing grants.
- [ ] Category rename/reparent does not alter grants; explicit revocation remains possible.
- [ ] A shared document editor cannot silently remove a link outside their authority.
- [ ] Hidden Item names/prices are not exposed merely to preserve their associations.
- [ ] Moved/deleted/hidden technical sources do not disappear from saved quotation packages on Save.
- [ ] Explicit attachment removal/replacement is authorized, clear and transactional.
- [ ] Simulate rejected/stale requests and storage/database failures; retain original data/files.
- [ ] Run focused access/shared-document/package regressions plus browser round-trips in both languages.
- [ ] Record verification and unresolved policy limits before marking any task complete.

### P1 — Repair category form boundaries and read-only controls

Findings: CAT-001, CAT-009. Priority: first, small bounded changes.
Approval: not requested/granted; concrete implementation plan must precede approval.

Scope: separate category edit/transfer/delete forms. Ordinary Save does not require
a Department; transfer does. Render Item/Related Item details and price history as
read-only when management permission is absent.

Dependencies/risks: verify all template conditionals and native browser validation,
including the one-Department case. Preserve backend permissions/CSRF.
Migration/compatibility: none expected; keep URLs and form field contracts where possible.

Acceptance and checks:

- [ ] Rename/reparent/save a category with two Departments and blank transfer destination.
- [ ] Delete an empty category without choosing a Department; populated category remains protected.
- [ ] Transfer validates its own destination and confirmation independently.
- [ ] View-only users retain details/history but see no editable Save controls.
- [ ] Forged edit requests still return 403; authorized managers still save successfully.
- [ ] Verify focused template/HTTP tests plus desktop/mobile English/Arabic browser actions.
- [ ] Report results and mark phase complete only after required verification.

### P2 — Restore scoped paths and align access wording with policy

Findings: CAT-002, CAT-003, B2-001, B2-002. Priority: high. Batch 2 evidence available;
exact access-policy/UI changes remain preliminary and require approval.
Approval: none.

Scope: navigation-only ancestors for nested Category grants; consistent Back/path
navigation; truthful explanation of selected grants. Proposed default is to retain
the direct-user/All Department policy, not introduce category-deny precedence.

Dependencies/risks: Category grant controls and User Roles modify the same table.
Exposing an ancestor for navigation must not authorize editing it or reveal sibling
Items; B2-001 confirms this is already a real mutation risk. P0 grant preservation
must accompany this phase. Own scope and partially visible branches need separate scenarios.
Migration/compatibility: no automatic deletion/rewrite of legacy visibility values
or grants. Any later schema cleanup requires a separate approved Alembic plan.

Acceptance and checks:

- [ ] Leaf-only and middle-category grants yield a traversable root-to-leaf path.
- [ ] Back and breadcrumbs never lead to unauthorized 404 ancestors within that path.
- [ ] Ancestor/sibling Items stay hidden; direct Item grants remain limited to those Items.
- [ ] Navigation-only ancestors cannot be renamed, moved or deleted without proper authority.
- [ ] All Department behavior and category labels agree; switching UI does not silently erase grants.
- [ ] Nested grants survive User Roles round-trip and root grants survive ordinary category renames.
- [ ] Test Admin, Selected, Own, None and All Department combinations in isolated sessions.
- [ ] Verify User Roles round-trip and English/Arabic permissions explanation in the browser.

### P3 — Make branch-transfer conflicts actionable and atomic

Findings: CAT-004. Priority: high; independent bounded backend repair.
Approval: none.

Scope: detect every descendant Item name/model collision before transfer, preserve
current case-insensitive collision policy, and handle a concurrent uniqueness failure
without a generic 500. Identify conflicts without silently merging records.

Dependencies/risks: shared-document blockers, duplicate category roots, and race
conditions. Existing source transaction must remain unchanged on rejection.
Migration/compatibility: no migration expected; preserve database uniqueness constraints.

Acceptance and checks:

- [ ] Reproduce CAT-004 with a duplicate in the destination; receive an actionable error.
- [ ] Root/subcategory/leaf Items, related Items, documents and grants remain unchanged on failure.
- [ ] Conflict-free branch transfer at any nesting depth preserves IDs and internal parent relationships.
- [ ] Concurrent collision rolls back and gives a recoverable response.
- [ ] Verify focused database/HTTP cases; manually verify the conflict message and retry path.

### P4 — Simplify same-Department organization and recovery

Findings: CAT-005 (same-Department part), CAT-006, CAT-007, CAT-008.
Priority: next workflow phase. Preliminary destination/search design pending browser review.
Approval: none.

Scope: dedicated single/multi-Item Move action; browsable authorized destination
folders; clickable ancestors; direct-Item Select All; preserve validation values
and return context. Related Items remain attached to their main Item. Category
branches may be nested at any depth, including across Departments, without
allowing cycles. A folder move explicitly chooses whether descendant Items follow
or become Uncategorized in their original Department. Folder deletion makes the
same Item choice before removing the selected branch.

Dependencies/risks: P2 scoped paths, selected-category access changes, selection
state after filtering, safe redirects, browser file restrictions. Reusing the
existing picker is preferred over creating a second hierarchy model.
Migration/compatibility: expected to use existing IDs/parent/category fields;
no flattening, price update, image replacement, or snapshot rewrite.

Acceptance and checks:

- [ ] Select Items across folders/search results and see an explicit selected count/list.
- [ ] Move a single Item and multiple Items without submitting unrelated price/detail fields.
- [ ] Cancel changes nothing; invalid or unauthorized member causes no partial move.
- [ ] Display permission consequences of changing category before committing.
- [ ] Reject self/descendant moves and duplicate sibling names on the server; allow deeper nesting.
- [ ] Search full paths consistently; distinguish direct items from descendant search results.
- [ ] After success show destination/affected Items; after error retain text/category and focus error.
- [ ] Explain necessary image reselection without claiming that browser files were retained.
- [ ] Test snapshots/related links unchanged and authorization preserved with forged IDs.
- [ ] Verify keyboard, Escape, focus, touch, narrow widths, long paths and Arabic RTL.

### P5 — Reviewable cross-Department group transfers

Findings: CAT-005 (cross-Department part), CAT-006 (target folder), CAT-010,
B2-004–007.
Priority: structural follow-up. Preliminary; blocked on approved policy plus P0,
P2/P3, P7 and P8. Batch 2 exposed preservation/compatibility failures to repair first.
Approval: none.

Scope: Administrator selects an explicit Item group or branch, chooses an authorized
Department and appropriate destination folder, reviews dependencies/access changes,
then commits atomically. Surface shared-document conflicts before mutation. Branch
destination must accommodate the entire subtree within the current depth limit.

Dependencies/risks: supplier documents shared across unrelated Items, technical files,
selected-user grants, quote edit source references, historical package downloads,
concurrent moves, and after-transfer source/destination visibility. Do not promise
undo or copy access grants automatically.
Migration/compatibility: existing relationships may suffice. Any new durable preview,
transfer record or rollback storage needs a separately reviewed migration proposal.
Never rewrite old quotations/service evidence to match catalogue location.

Acceptance and checks:

- [ ] Preview lists source/destination, descendants/Items, linked resources and cleared grants.
- [ ] Shared documents outside the explicit group block transfer and identify a recovery action.
- [ ] No implicit additional Items, file duplication, silent merge, or partial transfer.
- [ ] Submission revalidates permissions, depth, conflicts and dependency membership.
- [ ] Verify successful/failed transfers of main and related Items, documents and recommendations.
- [ ] Verify quotation detail/PDF/package, quote edit, and installed-asset identity after transfer.
- [ ] Verify source/destination access and informative audit evidence; link to destination afterward.
- [ ] Run focused affected-module regression and browser confirmations before completion.

### P6 — Measure and reduce catalogue loading cost

Finding: CAT-011. Priority: low until representative measurement.
Approval: none. Preliminary; no demonstrated latency regression yet.

Scope: record root/search/folder response size, query count and latency for a realistic
catalogue. Based on results, propose count-only overview, on-demand history and
paginated/filterable results. Agree a performance target before implementation.

Dependencies/risks: P4 selection semantics, authorized counts, stable sort, locale,
and large history rendering. Avoid optimizing a synthetic workload unlike real use.
Migration/compatibility: none assumed; justify any index with query evidence.

- [ ] Establish dataset size and agreed response/interaction targets with the user.
- [ ] Measure current behavior without touching real data.
- [ ] Present the smallest evidence-based optimization plan for approval.
- [ ] Implement only approved loading/filter/pagination changes.
- [ ] Verify bounded queries/results, stable selection, accurate permissions/counts and no lost actions.
- [ ] Repeat measurements and browser verification; record achieved targets.

### P7 — Make effective library scopes consistent and understandable

Findings: B2-003, B2-004. Priority: high for own-work guarantee; document policy
decision required before changing inherited Selected semantics. Approval: none.

Scope: one effective-scope calculation consistent with the approved own-work rule.
Define whether document Selected scope uses explicit shared grants independently
or inherits visible Pricing Items. Make permitted documents discoverable without
automatically granting commercial Pricing access, and explain dependencies in User Roles.

Dependencies/risks: per-module action gates, explicit denial precedence, shared files,
other libraries using the raw ORM scope, and price/image access. Preserve the
separation between navigable Item identity and permission to read prices/edit Items.
Migration/compatibility: no automatic scope/grant conversion or data migration;
if a policy transition changes existing access, present its impact before approval.

- [ ] Manage/Create with None scope can reopen own Items while other users' Items stay hidden.
- [ ] Test None/Own/Selected/Department and direct denials independently; no unintended broadening.
- [ ] Document-only access has a usable, authorized navigation/download path under approved policy.
- [ ] Selected document scope has a clearly stated, testable meaning when Pricing is None or All Department.
- [ ] Whole-file disclosure for documents shared with inaccessible Items follows the approved policy.
- [ ] Verify other affected library scope consumers before sharing a resolver change.
- [ ] Run focused permission/navigation/download checks and review English/Arabic configuration wording.

### P8 — Preserve quotation editability after catalogue changes

Findings: B2-006, B3-001, B3-002; coordinate B2-007 with P0.
Priority: high data-preservation/compatibility repair. Approval: none.
Batch 3 establishes the failure paths; snapshot refresh policy still needs agreement.

Scope: retain unchanged saved lines when an Item is moved/deactivated/hidden/deleted;
allow unrelated header edits; use current authorized sources only for explicit
add/replace/refresh actions. Clearly distinguish saved snapshots from current library data.

Dependencies/risks: optional related Items, alternatives, images/descriptions,
quantities/currencies/charges, historical price intent, deleted source IDs and planner
save behavior. Do not bypass Department or source-document permissions.
Migration/compatibility: existing snapshots likely suffice for unchanged-line edits;
no revision-history system or schema migration is preapproved.

- [ ] Notes-only edit succeeds after Item transfer while saved lines/images/attachments remain unchanged.
- [ ] Missing/deactivated/deleted source is explained without requiring replacement of an unchanged line.
- [ ] New or replaced lines still require authorized active catalogue Items and server validation.
- [ ] Related lines and alternatives preserve correct relationships and monetary values.
- [ ] Explicit refresh states which saved values will change; no silent description/image refresh.
- [ ] Notes-only edit preserves saved Project/contact/company details despite source changes.
- [ ] Inactive/deleted related Items remain as saved priced rows until explicitly removed.
- [ ] Verify saved main/related names, models, descriptions, images, quantities and price overrides.
- [ ] Invalid edits roll back and retain original quotation/package contents.
- [ ] Verify focused quote/transfer/PDF-package content regressions and browser error recovery.

### P9 — Align quotation validation and provide reliable save recovery

Findings: B3-003, B3-004, B3-005. Priority: medium; coordinate P8 snapshot/plan policy.
Approval: none. Browser reproduction and quantity business rules remain open.

Scope: consistent per-unit quantity rules, keyed inline errors and accessible summary,
bounded planner waits and recoverable save failures. Preserve entered values and
files. Explain loading/retry/session failures in English and Arabic.

Dependencies/risks: fractional existing data, dynamic line indexes, iframe messages,
single-use create tokens, uncertain network outcomes and existing plan retention.
Timeout recovery must not clear a saved plan or create a duplicate quotation.
Migration/compatibility: no migration assumed; do not silently round existing
quantities. A new durable save/retry identity needs a separate design if required.

- [ ] Agree which quantities allow fractions and align client/server limits and messages.
- [ ] Reopen existing fractional values without an unexplained blocked Save or data rewrite.
- [ ] Map async errors to exact main/related/charge fields and focus the first error.
- [ ] Provide a linked accessible summary and preserve inputs/files through correction.
- [ ] Simulate iframe not-ready, missing export response, rejected export and stalled HTTP.
- [ ] Recovery restores usable controls and preserves empty/unchanged/edited saved-plan intent.
- [ ] Handle expired sessions and uncertain save results without blind duplicate submission.
- [ ] Verify corrected resubmission, single-use token behavior and numeric/alternative guards.
- [ ] Check keyboard, mobile, Arabic RTL and planner/saved PDF content with focused regression.

### P10 — Repair document export, upload failure and form recovery

Findings: B4-001, B4-002, B4-003, B4-004. Priority: high for broken Arabic exports;
medium for validation/recovery. Approval: none.

Scope: safe Unicode download headers; matching title limits before file writes;
new-file cleanup on failed commits; preserved form values and keyed errors;
consistent missing-file handling for previews/downloads/packages.

Dependencies/risks: multi-file atomicity, browser file inputs, shared Item selection,
large response bodies and opaque storage identifiers. Retain B2-005 protections;
never silently export an incomplete package. Migration/compatibility: none expected.
Do not rewrite filenames/metadata or clean existing storage as part of these fixes.

- [ ] Arabic/mixed-script/quoted Item names download PDF and ZIP with safe usable filenames.
- [ ] Overlong title is rejected before writes, with submitted title/notes preserved.
- [ ] Database failure removes only newly created files and keeps existing records/files intact.
- [ ] Invalid purchase fields/files retain supplier/date/Item selections and per-Item prices.
- [ ] Errors identify their field/file; correction and resubmission preserve files where feasible.
- [ ] Missing files return an actionable consistent response without exposing filesystem paths.
- [ ] Package failures identify unavailable content; no silent partial-success download.
- [ ] Run focused upload/rollback/download checks and browser recovery in English/Arabic.

### P11 — Make document correction and destructive scope explicit

Findings: B4-005, B4-006; depends on B2-005/P0 shared-link preservation.
Priority: medium for destructive clarity; low for correction convenience.
Approval: none; retention and replace/supersede policy undecided.

Scope: clarify that purchase Edit appends files; propose metadata edit and targeted
file correction; make recommendation removal explicit; distinguish Item unlinking
from shared-document deletion and show authorized impact.

Dependencies/risks: source evidence retention, last-file rules, linked inaccessible
Items, management permissions, quotation copies and concurrency. Migration: none
assumed for wording/explicit actions; revisions or soft deletion require a separate
Alembic/data-retention proposal. No automatic historical cleanup or rewrite.

- [ ] Agree whether corrections remove, replace or supersede existing evidence.
- [ ] Correcting one file preserves the document's other files, prices and shared Item links.
- [ ] The 20-file cap and last-valid-file requirement remain consistent during correction.
- [ ] Data Sheet title/notes corrections do not require unintended content replacement.
- [ ] Blank recommendation Save cannot unexpectedly remove the current recommendation.
- [ ] Shared Delete explicitly states its global effect; unlink is a distinct authorized action.
- [ ] Impact messaging does not reveal hidden Item identities or imply unauthorized removal rights.
- [ ] Existing quotation copies survive source correction/deletion under the agreed snapshot policy.
- [ ] Verify permissions, confirmation/cancel, rollback/file cleanup and shared-link deletion cases.

### P12 — Bound Project-team authority and separate creator identity from role text

Findings: B5-001, B5-002. Priority: high. Approval: none.

Scope: enforce target-Project scope on team add/update/remove; define explicit
cross-Department team administration; make Own visibility independent of editable
role wording. Align team access explanations with actual module scope rules.

Dependencies/risks: shared Project selections across records/reports/quotations/tasks,
creator membership removal, multi-Department users, direct denials and historical
creator attribution. Migration/compatibility: route guards may need no migration;
durable creator identity may need Alembic and a reviewed backfill. Current role text
alone must not become trusted creator evidence. Ambiguous records require an
explicit resolution policy; no automatic access broadening or data rewrite.

- [ ] Hidden Project team add/update/remove fails without changing any membership.
- [ ] A manager cannot self-grant hidden Project visibility by posting a known ID.
- [ ] Authorized Project and Administrator team operations still work under agreed scope policy.
- [ ] Changing/localizing a role label does not change creator identity or Own visibility.
- [ ] Literal `Project creator` entered in free text cannot establish ownership.
- [ ] Agree membership-removal and represented-Department behavior for Own/Selected/Department scopes.
- [ ] Review reliable historical creator evidence and migration/backfill impact before schema work.
- [ ] Verify downstream selected-Project effects, cross-Department boundaries and direct denials.
- [ ] Correct team wording without implying membership overrides missing module permissions.
- [ ] Run focused authorization/compatibility checks and browser team-management verification.

### P13 — Repair Project setup navigation and validation recovery

Findings: B5-003, B5-004, B5-005, B5-006. Priority: medium; bounded usability fixes.
Approval: none.

Scope: match Photo Guidance action to Admin policy; keep search/reset visible for
empty results; preserve active Project and invalid form values; align bounded-field
validation across Site Create/Edit and related setup forms.

Dependencies/risks: no-access versus no-match states, role-specific controls,
disclosure/focus behavior, duplicate races and historical name snapshots.
Migration/compatibility: no migration expected. Preserve IDs, assignments and old
record snapshots; do not enlarge field limits or change permissions implicitly.

- [ ] Technical editor sees no action that implies authorized Photo Guidance management.
- [ ] Admin Photo Guidance remains reachable; its backend restriction stays enforced.
- [ ] No-match search keeps query/reset controls and distinguishes empty from inaccessible data.
- [ ] Search result links and edit success/error responses retain useful Project context.
- [ ] Invalid dates/duplicates retain input, reopen the correct form and identify/focus errors.
- [ ] Server rejects overlong Site/Project/team fields before commit; HTML limits match.
- [ ] Boundary and Unicode inputs produce actionable errors without truncation or 500 responses.
- [ ] Verify new General/empty Site assignments and delete-or-deactivate behavior remain intact.
- [ ] Check keyboard, small screens, Arabic RTL and focus with focused setup regression.

### P14 — Enforce field-entry mutation and Project authorization

Findings: B6-001, B6-002, confirmed across Installation and both Maintenance kinds
in Batch 8. Priority: high. Approval: none.

Scope: require target-record Edit authority for append; validate authorized Project
scope on every submitted section before writes, for all three entry kinds. Define
separate new-record and existing-record addition permissions rather than inheriting
the endpoint name.

Dependencies/risks: shared entry validators, record creator visibility, multi-Project
records, quotation identifier selection, participants, report invalidation and
audited transactions. Migration/compatibility: none expected for authorization;
legacy clients must still satisfy current permissions. No historical records are
automatically removed or reassigned. Coordinate P12 team-selection integrity.

- [ ] Create-only user with explicit Edit denial cannot append to Installation,
  Preventive Maintenance or Maintenance saved records.
- [ ] GET append entry and POST append apply the same target authorization.
- [ ] Define and verify Edit-only versus Create+Edit users adding devices to existing records.
- [ ] Hidden/unauthorized Project IDs fail for every entry kind even with otherwise
  valid Item/Service, Site and quotation references.
- [ ] Mixed authorized/unauthorized Site submissions reject atomically with no files/records changed.
- [ ] Authorized creation/addition preserves numbering, participants policy and revision/report behavior.
- [ ] Technicians can select permitted quotation identifiers without receiving commercial access.
- [ ] Test shared-validator callers before extending the repair to other entry types.
- [ ] Run focused permission/transaction regressions and browser picker/error recovery checks.

### P15 — Give drafts stable identity and delete only after confirmed Save

Findings: B6-003, B6-004. Priority: high. Approval: none.

Scope: distinguish user/workspace/entry-instance drafts and cached files; retain
independent work; clean up only the draft associated with an acknowledged successful
record save. Remove page-navigation inference as the success signal.

Dependencies/risks: legacy pathname keys, concurrent tabs and autosaves, workspace
switching, failed requests/discards, session expiry, IndexedDB quota and per-user
retention limits. Migration/compatibility: stable identity/workspace binding may
require an approved schema and legacy-draft transition. Never overwrite or silently
discard ambiguous old drafts. Cleanup repair can be planned separately if safe.

- [ ] Department A and B entries retain independent text and local photo sets.
- [ ] Two new Installation drafts can coexist with distinct explicit restore paths.
- [ ] Restoring a draft activates or clearly requests its correct workspace without broadening access.
- [ ] Preflight failure followed by Records/Cancel navigation retains server draft and cached photos.
- [ ] Server validation, interrupted upload and uncertain response do not trigger draft deletion.
- [ ] Confirmed Save cleans only the matching user/workspace/draft instance after success.
- [ ] Concurrent/in-flight autosave cannot recreate a finalized draft or overwrite newer work unnoticed.
- [ ] Verify legacy drafts, expired sessions, offline restore, failed discard and storage quota handling.
- [ ] Preserve non-destructive restore rules for saved evidence removals.
- [ ] Run focused endpoint/JS checks and real-browser multi-tab/workspace/evidence recovery tests.

### P16 — Make device-table identity and metadata precedence explicit

Finding: B7-005. Priority: high. Approval: none.

Scope: stop implicit asset mutation by row position. Choose independent evidence
tables or explicit device-instance links; resolve Excel/table metadata precedence,
then validate final identifiers before saving. Preserve database uniqueness guards.

Dependencies/risks: row order/removal, duplicate models, multi-Site records, installed
assets, work-item snapshots, imported metadata and later table edits. Migration:
explicit links may require Alembic and a reviewed compatibility policy. Historical
positional matches are ambiguous; no automatic metadata reconciliation is approved.

- [ ] A row naming another device cannot silently change the selected asset's metadata.
- [ ] Removing/reordering a table row cannot shift values onto a different device.
- [ ] Excel/table conflicts use agreed precedence with explicit replacement feedback.
- [ ] Validate final serial/IMEI/SIM identifiers after all input sources are resolved.
- [ ] Duplicate identifiers return actionable errors; races roll back records/assets/files atomically.
- [ ] Saved Edit follows the same identity rules and preserves historical evidence semantics.
- [ ] Verify duplicate models, multiple Sites, imported/plain entry and blank metadata cases.
- [ ] Review schema/backfill proposal separately if stable row links are required.
- [ ] Run focused mapping/rollback checks and browser row-edit/reorder workflows.

### P17 — Align the supported Excel workflow, scope and preview contract

Findings: B7-001, B7-002, B7-003, B7-004, B8-002. Priority: high for template disclosure and
destination mismatch; medium for discoverability/limits. Approval: none.

Scope: decide support versus retirement by entry kind; scope workbook reference
lists correctly; make preview show effective destinations; enforce final-entry
capacity before apply. For Maintenance kinds, reconcile retained asset import
tokens with current Service cards or reject them with actionable guidance. If
import is supported, expose it only with safe apply/replace behavior.

Dependencies/risks: P14 Project authorization, P16 metadata integrity, retained
clients/tokens, entered device evidence, multi-Site capacity and Excel validation
wording. Migration: none assumed for initial guards; do not remove endpoints or
change existing records implicitly. No workbook redesign or larger limits approved.

- [ ] Downloaded workbook contains only authorized Project/Sub Project references.
- [ ] Preview and final Save enforce intended entry-kind and target scope consistently.
- [ ] Conflicting workbook location labels reject or require explicit mapping to effective destinations.
- [ ] Preview accounts for the record-wide device limit and other Site sections.
- [ ] No silent truncation, device-card removal or evidence reassignment on Preview/Apply.
- [ ] Decide and document import support; align entry controls and README accordingly.
- [ ] Maintenance import submissions either match visible Service/asset choices
  through validated rules or clearly reject the unsupported legacy path.
- [ ] Clearly distinguish completeness Status, blocking errors and nonblocking warnings.
- [ ] Verify leading zeros/long identifiers, expired previews, changed catalogue data and duplicate races.
- [ ] Run targeted endpoint checks and real Excel/browser workflows before enabling the entry point.

### P18 — Scope Photo Guidance choices and reads to Project authority

Finding: B8-001. Priority: high. Approval: none.

Scope: apply the same effective Project access policy to field-entry profile
choices and direct guidance reads. Keep profile and Site relationship validation,
and define how a saved record displays guidance after a user's Project grant changes.

Dependencies/risks: shared guidance endpoint, Project/team grants, record creator
visibility, existing record history and entry forms for all record kinds. Avoid
revealing hidden Project/profile names in either HTML or error text. No migration
expected for initial read guards; preserve saved guidance associations.

- [ ] Selected/Own/None users see only authorized profiles in each applicable form.
- [ ] Direct GET with hidden Project/profile/Site IDs returns no guidance text.
- [ ] Admin and properly scoped technicians still see intended Before/After guidance.
- [ ] Forged form values do not bind a hidden Project's profile to a new record.
- [ ] Saved records retain evidence and show a deliberate result after grant changes.
- [ ] Verify isolated HTTP/HTML cases and browser English/Arabic picker/error behavior.

### P19 — Align record list, detail and evidence access

Findings: B9-001, B9-002; Batch 10 confirmed saved-report list/detail dependency.
Priority: high. Approval: none.

Scope: use one effective mixed-Project visibility policy across unified and
type-specific lists, Project filters, detail, saved-report lists and media.
Enforce the appropriate Records View action on evidence URLs while retaining
authorized Customer and explicit creator access. Counts and links must agree
with the detail outcome.

Dependencies/risks: three record kinds, shared Records/Reports selectors,
multi-Project visits, creator access after grant changes, saved report rendering,
photo thumbnails and private browser caching. Align P14's submitted-Project
mutation policy without broadening existing read grants. No migration expected;
preserve record and photo IDs. Historic mixed-Project records need a visibility
policy, not automatic splitting.

- [ ] A viewer assigned only Project A cannot see a non-owned A+B record summary
  in any list, filter result, count or media URL if detail is forbidden.
- [ ] A fully authorized viewer finds a multi-Project record by each included
  Project in unified and type-specific lists, with a working detail link.
- [ ] Saved-report list visibility matches report detail/PDF access after
  mixed-Project links and grant changes.
- [ ] Define and verify creator/Customer behavior after Project grant changes.
- [ ] Denying `records.view` blocks known photo IDs for Technical users in all
  legacy/item media routes, unless an explicitly defined creator rule applies.
- [ ] Authorized record pages, thumbnails and saved report evidence still load.
- [ ] Test all three kinds with pagination, scoped roles and revoked grants; run
  targeted HTTP/SQL checks and browser list-to-detail/photo walkthroughs.

### P20 — Make record actions and filters truthful

Findings: B9-003, B9-004. Priority: medium/low, bounded UX phase. Approval: none.

Scope: show Edit only when the user can edit that specific record; validate
type-specific search parameters before querying, retain an understandable
filter/error state and keep URL, controls, count and results aligned. Preserve
server-side Edit and Delete permission checks.

Dependencies/risks: Department action grants, record visibility, stale bookmarks,
deleted/inaccessible Project or device references, date ranges and pagination.
No migration expected; keep valid existing URLs working. Coordinate shared
filter parsing with P19 so access constraints cannot be bypassed.

- [ ] Read-only Technical users do not receive Edit links leading to 403.
- [ ] Edit-authorized users see the action only for records they can edit.
- [ ] Invalid numeric, stale or inaccessible Project/Site/device filters never
  silently broaden results or reveal inaccessible names.
- [ ] Malformed/reversed dates and invalid Results give clear correction paths.
- [ ] Corrected filters, Clear and pagination retain a truthful selected state.
- [ ] Verify focused route/template checks and English/Arabic browser filter,
  empty-state and keyboard/focus behavior.

### P21 — Make linked-report invalidation reviewable

Finding: B10-004. Priority: high. Approval: none.

Scope: before a material source-record Edit/append, show the linked saved reports
that the operation will invalidate, including reports containing other records.
Confirm the intended lifecycle policy, then give an explicit post-save outcome
and regeneration route. Keep no-op and failed saves non-destructive.

Dependencies/risks: three record types, saved report creator/Customer access,
source revisions, transactional rollback, files and generated PDF references.
Initial warning/feedback needs no migration. Retaining invalidated historical
reports would need a separate approved version/status/data migration and a
policy for who may download superseded PDFs. Do not silently restore or rewrite
deleted historical reports.

- [ ] Edit shows exact linked-report impact before Save to any authorized editor.
- [ ] No-op, validation failure and rolled-back Edit retain all linked reports.
- [ ] Successful material Edit/append reports which report numbers were removed
  or invalidated and how to regenerate them.
- [ ] A report containing multiple source records is handled as a whole with
  clear consequences for its other records and recipients.
- [ ] Admin/Technical/Customer report views agree with the approved lifecycle.
- [ ] Run focused transaction, concurrent Edit and multi-record report checks,
  then browser confirmation/recovery checks in English and Arabic.

### P22 — Preserve report selection and show permitted actions

Findings: B10-001, B10-002. Priority: medium. Approval: none.

Scope: retain entered report metadata and selected record IDs when filters are
applied or Save fails; prevent invalid time input from opening an unfiltered
selection tree. Gate Create, Preview, Download and Export controls by their
effective actions while preserving backend checks. Improve saved-report finding
only after measuring real list/tree volumes; no automatic redesign is proposed.

Dependencies/risks: multi-Site duplicate record cards, query string state,
large selections, stale IDs, Department switches, Customer access and PDF export
limit behavior. No migration expected. P19 must define source-record visibility
before reusing selectors across report pages.

- [ ] Apply/Clear and failed Save preserve report name, date, Team Leader,
  technicians and stable selected record IDs, with out-of-view choices visible.
- [ ] Invalid/reversed time input blocks or clearly isolates unfiltered choices.
- [ ] View-only users do not see Create/Preview/Download/Export controls that
  lead to a permission 403; authorized actions remain reachable.
- [ ] Standard export still caps matching records and retains search/type filters.
- [ ] Verify focused route/template/JS cases and browser Back, retry, keyboard,
  Arabic RTL and Customer action paths.

### P23 — Align PDF result color with status meaning

Finding: B10-003. Priority: low, bounded presentation fix. Approval: none.

Scope: use a result-aware status treatment on detailed report cards. Keep the
current text label, cover summary and navigation; reserve red for conditions
that actually need attention and maintain contrast without relying on color.

Dependencies/risks: shared `card_status` style also appears in the attention
section, PDF fonts and grayscale printing. No migration or data changes.

- [ ] All four result labels show a consistent tone on cover and detail pages.
- [ ] Attention cards remain distinct from successful work.
- [ ] Render representative English/Arabic PDFs with multiple pages/photos;
  inspect color, grayscale, clipping, contrast, bookmarks and text extraction.

## Continuation and approval rules

Review batch → saved findings/plan → stop. Approval to continue reviewing does not
authorize implementation. Each implementation phase requires a concrete phase plan
and explicit approval; routine work then continues within that approved scope.
Material scope changes or new data risks require a new decision.

For any approved implementation, preserve the dirty worktree and external state,
use `apply_patch`, use Alembic for schema changes, run focused proportionate checks,
and record what was actually verified. No phase checkbox above indicates an
implemented change. Do not rerun the whole suite for documentation-only updates.
