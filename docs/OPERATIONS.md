# Operations

## Text workflows

### Full run

Indexes text captures, downloads pending pages, evaluates every selected keyword set in one pass, and creates reports.

### Index only

Stores CDX capture metadata without downloading pages.

### Download pending

Downloads only pending records already stored in the database and scans them with the selected keyword sets.

### Resume interrupted work

Continues records restored to `pending` after a stopped run. Existing errors remain untouched.

### Offline rescan

Reads every valid local document once and evaluates all selected keyword sets. No network requests occur.

### Retry errors

Retries selected or unresolved errors. Scan and parse failures use a valid local document. Download failures are requested again only when needed. Selected media errors can be retried through the same error viewer.

### Regenerate reports

Recreates the latest text reports from the database without downloading or scanning.

### Integrity check

Reports missing files, empty files, size mismatches, orphaned files, invalid references, and unresolved errors.

## Media workflows

### Index and download selected media

Runs direct CDX extension searches, optionally looks up media linked by saved documents, applies the snapshot strategy, and downloads pending records.

### Index media only

Stores media captures without downloading binary files.

### Download pending media

Downloads media captures whose state is `pending`.

### Retry media errors

Selects unresolved retryable media failures. Successful media files are not downloaded again.

## Media selection order

1. Build the included extension set.
2. Remove explicitly excluded extensions.
3. Remove image types when Images is disabled.
4. Remove video types when Videos is disabled.
5. Index only the remaining extensions.
6. Apply earliest, latest, or all snapshot selection.

## Keyword scoring

The score combines field location, rule weight, exact-phrase bonuses, distinct matched concepts, same-sentence matches, same-paragraph matches, and nearby terms. URL and title matches are weighted above body matches. Repeated matches are capped per field. Required terms and excluded terms act as gates rather than ordinary bonuses.
