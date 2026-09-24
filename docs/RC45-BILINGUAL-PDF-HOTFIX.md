# RC45 bilingual saved-report PDF hotfix

Version `1.1.0-rc45` is an offline Install/Repair update from `1.1.0-rc44` or
earlier `1.1.0` release candidates. It does not change the database schema or
production data.

## Fixes

- English letters remain visible when Issue Found or another narrative contains
  both English and Arabic.
- English paragraphs are left-aligned and Arabic paragraphs are right-aligned.
- English product names and numbers remain visible inside Arabic paragraphs.
- Attention and record-detail pages use the same corrected narrative renderer.

## Install

1. Extract `service-management-offline-1.1.0-rc45.zip` completely.
2. Run `Setup-ServiceManagement.cmd`.
3. Select **Repair existing installation**.
4. Complete Repair and reopen the Service Management Console.

Repair preserves the existing database, uploads, users, configuration, and
application port. No migration is expected because RC45 retains Alembic head
`c6a4e8f21d90`.

## Verify

1. Open saved report `MR-2026-00009`.
2. Preview page 2 and the Issue Found record-detail page.
3. Confirm English and Arabic paragraphs are visible and separately aligned.
4. Download the PDF and confirm it matches the preview.
