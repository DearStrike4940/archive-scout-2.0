# Architecture

Archive Scout separates downloaded material, searches, analysis, and human review so each can be rerun independently.

## Core storage

- `captures` stores archived text-capture identity and download state.
- `documents` stores parsed text, local paths, links, and hashes.
- `media_captures` stores image/video capture identity, state, local path, and hash.
- `keyword_sets` stores normalized rule definitions.
- `scan_runs` stores a separate history entry for each search.
- `document_matches` stores one document's score and evidence for one scan.
- `reviews`, `notes`, and `tags` store human research decisions.
- `errors` stores retryable, deferred, resolved, and permanent failures.
- `documents_fts` provides offline SQLite full-text search.

## Alpha 3 analysis storage

- `analysis_runs` records each analysis execution and its summary.
- `forum_threads` stores canonical thread identity and aggregate dates/counts.
- `forum_posts` stores reconstructed posts tied to source documents and captures.
- `extractions` stores built-in and custom identifier matches with field and offsets.
- `legacy_assets` stores recovered player/embed assets and lookup state.
- `duplicate_groups` and `duplicate_members` store exact and near-duplicate clusters.
- `provenance_edges` stores inferred source-to-mirror relationships.
- `snapshot_diffs` stores adjacent-snapshot change summaries.
- `first_appearances` stores earliest and latest captures for extracted values.
- `project_merges` prevents the same source project from being merged repeatedly.

## Packages

```text
archive_scout/cdx          pooled CDX requests, deep window splitting, and resumable indexing
archive_scout/downloads    shared HTTP backpressure, text downloading, retries, and fixed pacing
archive_scout/scanning     keyword parsing, scoring, snippets, rescanning, and FTS
archive_scout/media        combined media indexing, downloading, discovery, and reports
archive_scout/parsing      forum and legacy-embed parsing
archive_scout/extraction   regex extraction and provenance construction
archive_scout/analysis     duplicates, snapshot diffs, first appearances, and analysis orchestration
archive_scout/database     schema, migrations, and repository functions
archive_scout/reports      text reports, exports, and scan comparison
archive_scout/projects     migration, integrity, and project merging
archive_scout/ui           Tkinter desktop interface
```

## Concurrency and network behavior

Worker threads use one keep-alive `urllib3` pool. SQLite writes remain controlled by the operation flow. User-selected worker counts and request delays do not change during a run.

HTTP 429 responses close one shared host circuit. Every worker waits, one recovery probe runs after the pause, and the complete queue reopens only after recovery.

CDX timeout recovery is different from rate limiting. A timeout subdivides only the failed date interval. At the smallest interval, the request is saved and retried until success or user cancellation.

## Media indexing

Direct media indexing builds one case-insensitive extension regular expression from all selected image/video extensions. One CDX stream is sent per target and time window. Returned URLs are validated locally before insertion. This avoids multiplying the number of CDX requests by the number of extensions.
