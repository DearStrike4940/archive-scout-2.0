# Architecture

Archive Scout 2.0 separates archive acquisition from research interpretation.

## Data flow

```text
CDX indexing
    ↓
captures
    ↓
download and validation
    ↓
documents and full-text index
    ↓
keyword set + scan run
    ↓
document matches and keyword hits
    ↓
reports and later review states
```

A document is downloaded once. Any number of scan runs can reference it afterward.

## Important tables

- `targets`: CDX target patterns
- `captures`: individual Wayback captures identified by URL, timestamp, and query signature
- `documents`: successfully saved and parsed local files
- `keyword_sets`: immutable keyword-list fingerprints with editable display names
- `scan_runs`: preserved executions of a keyword set
- `document_matches`: scores and snippets for a document during one scan run
- `keyword_hits`: per-keyword counts and matching fields
- `errors`: structured, retryable, and resolvable failures
- `index_state`: resumable CDX windows

Tables for reviews, tags, forum posts, duplicate groups, extractions, and snapshot diffs are included so later milestones can be added without another destructive project migration.

## Migration

When `archive_scout.sqlite3` contains the version 1 schema:

1. The database is copied to `archive_scout.v1.backup.sqlite3`.
2. A temporary version 2 database is created.
3. Legacy captures and index state are imported.
4. Existing files are parsed and added as documents.
5. Legacy scores become an imported scan run.
6. The temporary database replaces the active database only after migration finishes.

The original copy remains untouched as the backup.

## Retry behavior

Normal download and resume operations select pending captures. They do not mix previous errors into the normal queue.

The error-only operation selects unresolved errors marked retryable:

- A scan or parsing error with an existing local file is retried locally.
- A download error, missing file, or invalid local copy is queued for another Wayback request.
- Successful captures outside the error selection are not touched.

## Reports

Each scan run receives a permanent report directory. The latest report is also written into the root `reports` folder for compatibility with Archive Scout 1.x habits and external scripts.
