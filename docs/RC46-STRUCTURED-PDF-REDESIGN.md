# RC46 Structured PDF Redesign

Version `1.1.0-rc46` is an offline Install/Repair update from RC42, RC44, or
RC45. It does not add a database migration and does not replace production
records, uploads, settings, or credentials.

## Changes

- Correct logical word and line order for long Arabic report narratives.
- Replace the narrow Attention table with full-width action cards.
- Use a consistent branded cover, navigation, record, evidence, and approval
  design with a light AFAQY watermark.
- Remove layout rules that moved an entire long record to a later page and left
  large blank areas.
- Keep three equal photo frames per row for both portrait and landscape files.
- Keep the complete recommendation in the linked detailed record while the
  Attention register focuses on the issue requiring review.

## Offline production update

1. Back up the production database and upload directory.
2. Extract `service-management-offline-1.1.0-rc46.zip` completely.
3. Run `Setup-ServiceManagement.cmd` as Administrator.
4. Select **Repair existing installation**.
5. Confirm the existing installation directory and complete the repair.
6. Open the dashboard and preview the affected saved report again. Saved report
   PDFs are rendered at preview/download time, so no report regeneration or
   migration is required.

## Verification

- Confirm the existing records and photos remain available.
- Preview a report containing long English and Arabic Issue Found text.
- Confirm Arabic reads from right to left in the correct sentence order.
- Confirm the Attention card, detailed record, photo grid, and approval page
  render without clipping or overlapping.
