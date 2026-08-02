# Archive Scout 2.0

Archive Scout is a cross-platform desktop application for indexing public Wayback Machine captures, downloading archived pages and media, searching saved material, reconstructing archived forums, recovering legacy embeds, comparing snapshots, and reviewing research results.

One repository produces builds for Windows x64, Linux x64, and universal macOS for Intel and Apple Silicon.

## Downloads

- [Download for Windows x64](../../releases/latest/download/ArchiveScout-Windows-x64.zip)
- [Download for Linux x64](../../releases/latest/download/ArchiveScout-Linux-x64.tar.gz)
- [Download for macOS Intel and Apple Silicon](../../releases/latest/download/ArchiveScout-macOS-Universal.zip)

### macOS installation

Extract the ZIP, drag `Archive Scout.app` into `/Applications`, and launch the installed copy. Quit Archive Scout completely before replacing it with a newer release. Do not move, rename, delete, or overwrite the `.app` while it is running.

## What is new in Alpha 3

Alpha 3 keeps the complete Alpha 1 and Alpha 2 workflow and adds archive-recovery and analysis tools.

- Forum URL canonicalization
- Forum profile detection
- Post-level forum parsing
- Thread reconstruction across saved snapshots
- Built-in legacy identifier extraction
- Custom regular-expression extractors
- Google Video `docid` extraction
- Flash, Windows Media, RealPlayer, playlist, iframe, and script-config recovery
- Controlled Wayback searches for externally hosted assets
- Exact duplicate clustering
- Near-duplicate clustering with configurable similarity
- Source-to-mirror provenance tracking
- Adjacent snapshot comparison
- First-appearance and last-appearance searches
- Project merging
- Shared review, note, tag, scan, media, and extraction merging
- Schema version 4 with automatic migration from earlier Alpha projects

Alpha 3 also hardens indexing. A transient CDX timeout no longer ends the project. Archive Scout saves the pending queue, divides only the failed date range, reduces the page size when necessary, and keeps retrying the smallest window until Wayback responds or the user presses Stop.

Direct media indexing now sends one combined CDX query for all selected image and video extensions per target and date window. It no longer sends a separate index query for every extension.

## Main operations

### Index, download, scan, and report

Queries CDX, downloads pending text captures, evaluates every selected keyword set, and creates separate reports for each set. Media can optionally run afterward.

### Rescan existing downloads

Reads saved files locally with new keyword sets. It makes no CDX requests and downloads nothing.

### Retry only errored URLs

Retries selected or unresolved text-page and media errors. Valid local text files are rescanned before a new download is attempted.

### Index and download selected media

Uses one combined extension query for every selected image and video type, records matching captures, and downloads the selected snapshots.

### Run archive recovery and analysis

Processes saved documents without redownloading them. Depending on the Archive analysis settings, it reconstructs forum threads, extracts identifiers, recovers embedded assets, clusters duplicates, compares snapshots, tracks provenance, and writes analysis reports.

### Rebuild forum threads only

Clears and rebuilds the forum-thread and forum-post tables from saved pages without rerunning duplicate, extraction, snapshot, or provenance analysis.

### Merge another Archive Scout project

Copies and merges captures, documents, media, keyword sets, scan runs, matches, reviews, notes, tags, and extraction results from another project. Repeating the same merge does not duplicate the imported project.

Other modes support indexing only, downloading pending records, resuming interrupted work, regenerating reports, checking project integrity, indexing media only, downloading pending media, and retrying media errors only.

## Archive analysis settings

The Archive analysis tab includes:

- Forum reconstruction toggle
- Forum profile: automatic, generic, vBulletin, phpBB, Invision, Futaba, or 2channel-style
- Legacy embed and player recovery
- Snapshot comparison
- Provenance construction
- Near-duplicate similarity threshold
- Controlled external-asset lookup
- Maximum external lookup count
- Explicit external-domain allowlist
- Custom extraction rules
- Source project folder for project merging

External asset searching is disabled unless explicitly enabled. Even then, Archive Scout searches only domains listed in the allowlist.

## Custom extractor syntax

Enter one rule per line in the Archive analysis tab:

```text
name :: regular expression
name :: field :: regular expression
```

Available fields are:

```text
title
body
url
source
links
```

Examples:

```text
Google Video docid :: docid=(-?\d+)
Uploader ID :: url :: /(?:up|upload)(\d+)
Old media filename :: links :: ([A-Za-z0-9_-]+\.(?:wmv|mov|flv|swf))
```

Built-in extractors already cover Google Video identifiers, YouTube identifiers, Internet Archive identifiers, Flash URLs, Windows Media URLs, RealMedia URLs, and common legacy uploader identifiers.

## Forum reconstruction

Archive Scout canonicalizes common forum URL forms before grouping pages into threads. Pagination parameters, post anchors, session values, and common tracking parameters are removed where appropriate. Parsed posts retain their source document, capture timestamp, position, username when detectable, date text when detectable, and a normalized body hash.

Forum reconstruction is heuristic. Unsupported or heavily scripted forum software falls back to the generic parser and may require later parser improvements.

## Duplicate and provenance analysis

Exact groups use stored content hashes. Near-duplicate groups use SimHash candidates and the configured similarity threshold. Duplicate groups are then used to infer possible source-to-mirror relationships by comparing capture times.

Provenance output is evidence for research, not proof of authorship. Earlier capture time means only that the archived copy was captured earlier in the available project data.

## Snapshot comparison and first appearance

Archive Scout compares adjacent downloaded snapshots of each canonical URL and stores a compact change summary. Extracted identifiers can also be searched across saved documents to report the earliest and latest project capture in which each value appears.

## Keyword rule syntax

Enter one rule per line.

```text
World Trade Center
required: WTC
high: jumper
exact: impact footage | weight=4
exclude: base jumping
regex: sky(light|line)\.mov | label=media filename
plaza | whole
Naudet | case
```

Supported prefixes:

```text
required:
optional:
high:
exclude:
exact:
regex:
```

Supported options after a spaced pipe:

```text
| weight=3
| whole
| case
| label=Shared concept
| type=required
```

Required rules must match. Excluded rules remove a page from ranked results. Repeated matches are capped per field so boilerplate cannot dominate a score.

## Full-text search and review

The Results and search tab provides instant offline SQLite full-text search through downloaded documents. Searches can be filtered by scan, review status, score, title, URL, domain, and body text.

Each ranked result can be marked as:

```text
Unreviewed
Relevant
Possibly relevant
False positive
Duplicate
Dead end
Needs follow-up
```

Notes and tags remain attached when projects are merged.

## Media indexing and downloading

The Media tab can download images, videos, or both.

You can configure:

- Separate media targets or reuse normal site targets
- Included extensions
- Excluded extensions
- Images and videos independently
- Direct CDX media discovery
- Media links found inside saved pages
- Optional external embedded media
- Earliest, latest, or every snapshot
- Maximum file size
- Original path preservation

Include rules are applied first, followed by exclusions.

```text
Include: jpg, jpeg, png, gif, mp4, mov
Exclude: gif, mov
```

The direct media indexer creates one server-side extension regular expression and sends one CDX request stream per target and time window. Results are then validated locally before storage.

## Resilient indexing

Indexing starts with monthly windows. A transient timeout or temporary gateway failure causes only the failed window to be divided:

```text
month
7 days
1 day
6 hours
1 hour
15 minutes
5 minutes
1 minute
15 seconds
5 seconds
1 second
```

If a one-second window still fails, Archive Scout lowers that window's CDX page size, saves the state, moves it behind other work when possible, and retries it indefinitely with bounded backoff. Stop remains responsive and the exact queue is restored on resume.

Non-transient failures such as malformed parameters, unsupported project schemas, local permission errors, or a damaged application bundle still stop the affected operation because retrying them forever would not solve the problem.

See [docs/RESILIENT_INDEXING.md](docs/RESILIENT_INDEXING.md).

## HTTP 429 behavior

Worker count and user-selected delays remain fixed. A shared host gate handles explicit HTTP 429 responses:

- Every worker pauses together
- `Retry-After` is honored
- Simultaneous 429 responses are combined into one event
- One recovery probe runs before the full queue reopens
- Pending work remains pending rather than becoming thousands of errors

The default 429 wait budget of `0` means Archive Scout keeps waiting until Wayback recovers or the user presses Stop.

## Project layout

```text
project.json
archive_scout.sqlite3
archive_scout.v1.backup.sqlite3
captures/
media/
reports/
```

Alpha 3 analysis reports are stored in:

```text
reports/analysis/
```

They include:

```text
analysis_summary.txt
forum_threads.tsv
extractions.tsv
legacy_assets.tsv
duplicate_groups.tsv
provenance.tsv
snapshot_diffs.tsv
first_appearances.tsv
```

## Upgrading an older project

Make an external backup of the complete project folder first.

- Schema version 2 projects are upgraded through schema 3 to schema 4.
- Schema version 3 projects are upgraded in place to schema 4.
- Version 1 projects receive `archive_scout.v1.backup.sqlite3` before import.

After migration, run **Check project integrity** and review `reports/integrity.txt`.

## Running from source

Python 3.11 or newer is required.

```bash
python -m pip install -r requirements-runtime.txt
python run_app.py
```

Run the tests with:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

## Building releases

Open:

```text
Actions → Build All Platforms → Run workflow
```

A successful run creates Windows, Linux, and universal macOS artifacts. Pushing a version tag attaches all packages and SHA-256 files to a GitHub Release.

## Current status

`2.0.0-alpha.3` is an alpha release. Back up important projects before migration and verify major research runs with a small date range first.

See [ROADMAP.md](ROADMAP.md), [docs/ALPHA3_ANALYSIS.md](docs/ALPHA3_ANALYSIS.md), [docs/OPERATIONS.md](docs/OPERATIONS.md), [docs/RESILIENT_INDEXING.md](docs/RESILIENT_INDEXING.md), [docs/NETWORK_PERFORMANCE.md](docs/NETWORK_PERFORMANCE.md), [docs/MIGRATION.md](docs/MIGRATION.md), and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Responsible use

Archive Scout works with publicly archived material. Users are responsible for applicable laws, archive policies, site terms, and ethical research practices. Do not use the software to harass people, expose private information, or overwhelm archive infrastructure.
