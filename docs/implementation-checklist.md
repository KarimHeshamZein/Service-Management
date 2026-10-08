# Implementation checklist

This is the short progress tracker for the UI/UX and business-logic improvements. The [review findings](ui-ux-logic-review.md) contain the evidence; the [detailed improvement plan](ui-ux-improvement-plan.md) contains acceptance criteria and dependencies. Phase IDs below refer to that plan. This order is a recommendation and can change when implementation reveals a dependency. The user chose focused testing per change and a full-suite run after the selected implementation scope is stable, replacing the repository's per-change full-suite cadence.

## Current position

- [x] Complete ten bounded review batches and record their findings.
- [x] Push the application and review checkpoint to GitHub (`feature/pre-improvement-checkpoint-2026-10-07`).
- [x] Prepare the first implementation slice and its acceptance checks below.
- [ ] Integrate the checkpoint into `main` through [PR #3](https://github.com/KarimHeshamZein/Service-Management/pull/3) before source implementation. GitHub requires one approving review; merge is pending that review.
- [ ] Agree on the first implementation slice: protect Pricing Category grants (P0, B2-001/B2-002).
- [ ] Implement and verify the first slice.

No improvement below is implemented yet. Browser, mobile, keyboard, and Arabic RTL verification from the review remain open. Add a PR/commit link and a brief verification note beside each item when it is finished. Check an item only when its behavior, regression tests, and relevant UI verification are complete; a partial repair stays unchecked.

## Priority 1 — access and preservation

Work in small, reviewable changes. Where one phase spans unrelated risks, its parts have separate checkboxes.

- [ ] **01 — P0:** Restrict Category grant changes to authorized administrators and preserve existing nested grants on unchanged saves.
- [ ] **02 — P14:** Enforce Edit permission for appending to saved Installation/Maintenance records and validate every submitted Project section.
- [ ] **03 — P19:** Make Records list, detail, and evidence access follow the same effective permissions and Project scope.
- [ ] **04 — P18:** Limit Photo Guidance choices and direct reads to authorized Projects.
- [ ] **05 — P12:** Bound Project-team changes to authorized Projects and keep creator identity separate from role text.
- [ ] **06 — P17:** Stop Excel templates/previews from disclosing or accepting unauthorized Project data; define the supported import path.
- [ ] **07 — P0:** Preserve shared Purchase Document links outside the editor's authority during save. [Draft PR #6](https://github.com/KarimHeshamZein/Service-Management/pull/6): documents with any inaccessible linked Item open read-only for scoped editors, and direct edit/delete requests are rejected before changing links or files. Focused Purchase Document regression: 9 passed. Manual English/Arabic UI check and PR review remain open.
- [ ] **08 — P0:** Preserve saved quotation package attachments when their live source is moved, hidden, or deleted.
- [ ] **09 — P8:** Keep saved quotations editable after catalogue changes without rewriting historical line snapshots.
- [ ] **10 — P7:** Make document library scope and own-work visibility consistent with the permission policy.
- [ ] **11 — P15:** Give drafts stable user/workspace/entry identity and clear them only after a confirmed successful save.
- [ ] **12 — P16:** Define device-table row identity and metadata precedence so edits/imports do not silently overwrite asset data.
- [ ] **13 — P21:** Show linked-report impact before source-record changes and a clear outcome after save.

## Priority 2 — broken workflows and everyday UX

- [ ] **14 — P10:** Repair document exports, failed-upload cleanup, and form recovery.
- [ ] **15 — P1/P2:** Repair Category form boundaries, read-only controls, scoped navigation paths, and access wording.
- [ ] **16 — P3:** Make branch-transfer conflicts actionable and keep transfers atomic.
- [ ] **17 — P9:** Align quotation validation and recover entered work after a failed save.
- [ ] **18 — P17:** Finish the Excel import/preview contract after the access issue in item 06 is resolved.
- [ ] **19 — P13:** Improve Project setup navigation and validation recovery.
- [ ] **20 — P20:** Make Record actions and filters accurately reflect what users can do and see.
- [ ] **21 — P22:** Preserve report selections through filtering/errors and show only permitted actions.
- [ ] **22 — P23:** Use result-appropriate colors in report PDFs, with readable text and contrast.

## Priority 3 — larger workflow changes and measured optimization

- [ ] **23 — P11:** Decide and implement document correction and deletion behavior after shared-link protection.
- [ ] **24 — P4:** Simplify same-Department Item/Category organization and recovery.
- [ ] **25 — P5:** Add reviewable cross-Department group transfers after access and preservation safeguards.
- [ ] **26 — P6:** Measure catalogue performance with representative data, then optimize only confirmed bottlenecks.

## Final regression gate

- [ ] After the chosen implementation scope is stable, run the full test suite once before release. Fix any failures and rerun the affected checks; if a fix changes code after the full-suite run, repeat the full suite so the final result covers the final code.

## How each item moves to done

1. Confirm the exact behavior and boundary from the detailed plan; record any policy decision before coding.
2. Create a fresh task branch from the updated `main` after checkpoint integration. Preserve local data and the unrelated root `index.html`.
3. Run focused, proportionate regressions for each source change, including permission/transaction and migration checks when relevant. Do not rerun the full suite for every item. Verify affected screens in a browser, including English/Arabic and relevant mobile/keyboard paths when available. Record any verification that remains blocked.
4. Review the diff and record the PR/commit, test result, and any remaining limitation here. Check the item only when its acceptance criteria are met.

The next concrete change is item **01**. Its proposed scope is the Category grant mutation route and the User Roles grant-saving form; it does not require a database migration or broader Pricing redesign.

## First slice — Pricing Category grants (item 01)

**Policy for this slice:** Only Administrators change Category grants. Pricing managers may still perform authorized catalogue edits; readable ancestor folders are for navigation, not grant mutation. Ordinary Category edits must leave grant rows unchanged. User Roles must show all three Category levels with their paths and preserve grants unless an Administrator explicitly changes them.

- [ ] Update Category create/edit POST authorization so forged grant fields cannot expand a non-Administrator's access.
- [ ] Move grant editing to the Administrator's User Roles page; show complete Category paths and existing selections.
- [ ] Make unchanged Category and User Roles saves preserve existing grants, including nested and legacy grants. Keep explicit revocation possible.
- [ ] Add focused regressions for self-grant attempts, unchanged saves, explicit revocation, and continued authorized Item/Category editing.
- [ ] Verify the affected controls and error/confirmation feedback in English and Arabic; record any browser checks that remain blocked.
- [ ] Record the resulting PR/commit and test evidence beside item 01, then check it when all criteria pass.
