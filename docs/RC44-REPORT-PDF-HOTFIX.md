# RC44 saved-report PDF hotfix

Version `1.1.0-rc44` is an application-only update from `1.1.0-rc42`.
It does not change the database schema or production data.

## Fixes

- Long Issue Found and Recommendations content can continue across pages.
- A damaged or unsafe thumbnail falls back to the original evidence image.
- If no evidence file can be decoded, the report remains downloadable and
  shows `Photo unavailable.` in that image position.
- Future uploads with unsafe image dimensions are rejected during validation.
- Any remaining PDF-generation exception is written to the service log with
  the report ID, report number, report type, and traceback.

## Install

Use the local Service Management Console on the production PC:

1. Open **System -> Install update package**.
2. Select `service-management-1.1.0-rc44.zip`.
3. Enter the supplied SHA-256 value.
4. Install the update and wait for the health check to pass.

The deployment workflow creates its normal database and upload safety backup.
No migration is expected because RC44 retains Alembic head `c6a4e8f21d90`.

## Verify

1. Sign in and open the report that previously returned Error 500.
2. Test both **Preview** and **Download PDF**.
3. Confirm all readable evidence images appear.
4. If a placeholder appears, inspect the named report's source evidence and
   replace the unreadable photo when practical.
5. If the report still fails, collect the service log from
   `C:\ServiceManagement\logs`; RC44 records the exact traceback.
