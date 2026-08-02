# Operations

## Text workflows

### Full run

Indexes text captures, downloads pending pages, evaluates every selected keyword set in one pass, and creates reports.

### Index only

Stores CDX capture metadata without downloading pages.

### Download pending

Downloads pending records already stored in the database and scans them with the selected keyword sets.

### Resume interrupted work

Continues the saved CDX window queue and restores interrupted downloads to pending. Existing errors remain available for review.

### Offline rescan

Reads every valid local document once and evaluates all selected keyword sets. No network requests occur.

### Retry errors

Retries selected or unresolved errors. Scan and parse failures use valid local documents. Download failures are requested again only when necessary.

### Regenerate reports

Recreates the latest text reports from the database without downloading or scanning.

### Integrity check

Reports missing files, empty files, size mismatches, orphaned files, invalid references, and unresolved errors.

## Media workflows

### Index and download selected media

Builds one combined CDX extension filter for all selected image/video types, indexes matching captures, applies the selected snapshot strategy, and downloads pending records.

### Index media only

Stores media captures without downloading binary files.

### Download pending media

Downloads media captures whose state is `pending`.

### Retry media errors

Retries selected or unresolved media failures. Existing successful files are not downloaded again.

## Alpha 3 analysis workflows

### Run archive recovery and analysis

Uses saved documents to:

1. Canonicalize forum URLs.
2. Parse posts and reconstruct threads.
3. Run built-in and custom extractors.
4. Recover legacy player and embed URLs.
5. Optionally search allowed external hosts in Wayback.
6. Build exact and near-duplicate groups.
7. Compare adjacent snapshots.
8. Search for first and last appearances of extracted values.
9. Infer source-to-mirror provenance edges.
10. Write analysis reports.

### Rebuild forum threads only

Recreates only `forum_threads` and `forum_posts`. It does not rerun extractors, external lookups, duplicate clustering, snapshot comparison, or provenance.

### Merge another Archive Scout project

Merges another project's stored research into the open project. Captures and media retain their identities; copied local files are placed under `captures/merged/` and `media/merged/`. Scan history, review status, notes, tags, and extraction results are preserved. The full-text index is rebuilt after the merge.

## Media selection order

1. Build the included extension set.
2. Remove explicitly excluded extensions.
3. Remove image types when Images is disabled.
4. Remove video types when Videos is disabled.
5. Build one combined CDX extension filter.
6. Validate returned URL extensions and MIME types locally.
7. Apply earliest, latest, or all snapshot selection.

## Keyword scoring

The score combines field location, rule weight, exact-phrase bonuses, distinct matched concepts, same-sentence matches, same-paragraph matches, and nearby terms. URL and title matches are weighted above body matches. Repeated matches are capped per field. Required and excluded terms act as gates.
