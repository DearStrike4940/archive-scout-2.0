# Indexing recovery

Archive Scout 2.0.0-alpha.2.1 divides each selected year into monthly CDX windows.

Each completed month is saved in `index_state`. If a request fails or the run is stopped, the current month and CDX resume key are stored in the existing `resume_key` column. Starting the same project again continues from that month.

## Recovering an Alpha 2 project

1. Replace the Alpha 2 source with Alpha 2.1 and rebuild the application.
2. Keep the existing project folder, `project.json`, database, captures, and reports.
3. Open the same `project.json`.
4. Use the original operation or `Resume interrupted work`.
5. Archive Scout skips years already marked complete and retries the incomplete year in monthly windows.

Do not delete `archive_scout.sqlite3`. The patch uses the existing schema version 3 database.

## Activity messages

Indexing now reports:

- the target and month currently being queried
- retry reason, retry number, and wait time
- rows returned and stored
- total rows seen
- CDX request duration
- SQLite write duration

These values make it possible to distinguish a slow Wayback query from slow local database work.

## Duplicate keyword sets

Selected keyword sets with identical normalized rules are scanned once. Different rule types still count as different sets; for example, `term` and `exact: term` are not identical.
