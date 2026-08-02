# Architecture

Archive Scout separates archived material from the searches performed against it.

- `captures` stores text capture identity and download state.
- `documents` stores parsed text, local paths, links, and hashes.
- `keyword_sets` stores normalized rule definitions.
- `scan_runs` stores a separate history entry for every search.
- `document_matches` stores one document’s score and evidence for one scan.
- `reviews`, `notes`, and `tags` store human research decisions.
- `errors` stores retryable and resolved failures for text and media.
- `media_captures` stores image/video capture identity, state, file path, and hash.
- `documents_fts` provides offline SQLite full-text search.

This separation allows one downloaded document to be rescanned many times without changing or redownloading it.

## Packages

```text
archive_scout/cdx          CDX requests and resumable indexing
archive_scout/downloads    text downloading, retrying, and fixed request pacing
archive_scout/scanning     keyword parsing, scoring, snippets, rescanning, and FTS
archive_scout/media        media selection, indexing, downloading, and reports
archive_scout/database     schema, migration, and repository functions
archive_scout/reports      text reports, exports, and scan comparison
archive_scout/projects     migration and project integrity
archive_scout/ui           Tkinter desktop interface
```

## Concurrency

Worker threads perform network requests while SQLite writes remain controlled by the main operation flow. Request pacing uses the worker count and delays chosen by the user and does not change them during a run.
