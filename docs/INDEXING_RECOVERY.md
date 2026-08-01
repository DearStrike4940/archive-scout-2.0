# Indexing recovery

Archive Scout 2.0.0-alpha.2.2 begins with monthly CDX windows. When the Wayback CDX server times out on a broad request, Archive Scout automatically subdivides only that failed range and continues.

The fallback sizes are:

- month
- seven-day windows
- one-day windows
- six-hour windows
- one-hour windows

The complete pending-window queue and any CDX resume key are stored in the existing `index_state.resume_key` field. No database schema change is required. Stopping the application or reopening the project continues from the saved split window instead of restarting the year.

## Recovering an Alpha 2 or Alpha 2.1 project

1. Replace the existing source with Alpha 2.2 and rebuild the application.
2. Keep the existing project folder, `project.json`, database, captures, and reports.
3. Open the same `project.json`.
4. Use the original operation or `Resume interrupted work`.
5. Archive Scout skips completed years and resumes the incomplete date-window queue.

Do not delete `archive_scout.sqlite3`. Alpha 2.2 uses the existing schema version 3 database.

## Broad target warning

A target covering an entire large site can still be expensive. `collapse=urlkey` is strongly recommended when only one capture per unique URL is needed. Without it, the CDX server may need to enumerate every archived snapshot.

For an entire host, prefer a clear target such as:

```text
2ch.io/*
```

Keep **Collapse URL key** selected unless repeated snapshots of the same URL are required.

## Activity messages

Indexing reports:

- the target and exact date window currently being queried
- retry reason, retry number, and wait time
- automatic split decisions
- rows returned and stored
- total rows seen
- CDX request duration
- SQLite write duration

These values distinguish a slow Wayback query from slow local database work.

## Duplicate keyword sets

Selected keyword sets with identical normalized rules are scanned once. Different rule types still count as different sets; for example, `term` and `exact: term` are not identical.
