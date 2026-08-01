# Archive Scout 2.0

Archive Scout is a cross-platform desktop application for indexing public Wayback Machine captures, downloading archived pages and media, searching saved material, and reviewing ranked results.

One repository now produces builds for Windows x64, Linux x64, and universal macOS for Intel and Apple Silicon.

## Downloads

- [Download for Windows x64](../../releases/latest/download/ArchiveScout-Windows-x64.zip)
- [Download for Linux x64](../../releases/latest/download/ArchiveScout-Linux-x64.tar.gz)
- [Download for macOS Intel and Apple Silicon](../../releases/latest/download/ArchiveScout-macOS-Universal.dmg)

### macOS installation

Open the DMG, drag `Archive Scout.app` into `/Applications`, eject the DMG, and launch the installed copy. Quit Archive Scout completely before replacing it with a newer release. Do not move, rename, delete, or overwrite the `.app` while it is running; frozen Python applications continue loading bundled runtime files from the application bundle during use.

## What is new in Alpha 2

Alpha 2 keeps every Alpha 1 feature and adds a full search-and-review workspace.

- Built-in ranked results viewer
- Sortable results with matching snippets
- Review labels, notes, tags, and next-unreviewed navigation
- Filtered CSV, JSON, Markdown, and review-package exports
- Named keyword sets that can be imported, exported, duplicated, and selected independently
- Multiple keyword sets evaluated in one pass over each downloaded page
- Required, excluded, exact-phrase, regex, weighted, case-sensitive, and whole-word rules
- Same-sentence, same-paragraph, and nearby-term scoring bonuses
- Instant offline SQLite full-text search within the selected scan
- Scan history, report regeneration, deletion, renaming, and two-scan comparison
- Error viewer with selected text-page and media retries
- Adaptive rate limiting that lowers active concurrency after archive throttling
- Adaptive CDX date splitting when broad monthly requests time out
- Direct image and video indexing and downloading
- Image/video discovery from links inside saved pages
- Separate media targets and include/exclude extension lists
- Earliest, latest, or every archived media snapshot
- Resumable media downloads, error-only retries, checksums, and media reports

Alpha 1 features remain available, including offline rescanning, structured errors, version 1 migration, project integrity checks, and preserved scan history.

## Main operations

### Index, download, scan, and report

Queries CDX, downloads pending text captures, evaluates every selected keyword set, and creates separate reports for each set. Media can optionally run afterward.

### Rescan existing downloads

Reads saved files locally with new keyword sets. It makes no CDX requests and downloads nothing.

### Retry only errored URLs

Retries selected or unresolved text-page and media errors. Valid local text files are rescanned before a new download is attempted.

### Index and download selected media

Searches selected sites and paths for image and video extensions, records matching Wayback captures, and downloads the chosen snapshots into the project’s `media` folder.

Other modes support indexing only, downloading pending records, resuming interrupted work, regenerating reports, checking project integrity, indexing media only, downloading pending media, and retrying media errors only.

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

Several spellings or translations can be grouped under one concept by assigning them the same label.

```text
World Trade Center | label=WTC concept
W.T.C. | label=WTC concept
Torres Gemelas | label=WTC concept
```

Required rules must match. Excluded rules remove a page from ranked results. Each rule is capped per field so repeated boilerplate cannot dominate the score.

## Full-text search

The Results and search tab provides instant offline searching through downloaded documents. SQLite FTS syntax supports words, quoted phrases, and Boolean expressions such as:

```text
"impact footage"
WTC AND jumper
lobby OR plaza
jumper NOT base
```

Searches can be limited to title, body, URL, domain, and the currently selected scan.

## Reviewing results

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

Notes and comma-separated tags are stored in the project database. The viewer can filter by status, score, text, and scan, and exports use the active filters.

## Media downloading

The Media tab can download images, videos, or both.

You can configure:

- Separate media sites and paths, or reuse the normal targets
- Included extensions
- Excluded extensions
- Images and videos independently
- Direct CDX media discovery
- Media links found in saved pages
- Whether externally hosted embedded media is allowed
- Earliest, latest, or every snapshot
- Maximum file size
- Original path preservation

Include rules are applied first, followed by exclusions. For example:

```text
Include: jpg, jpeg, png, gif, mp4, mov
Exclude: gif, mov
```

results in only JPG, JPEG, PNG, and MP4 downloads.

Media files are stored separately from text captures:

```text
media/
├── image/
└── video/
```

Media reports include indexed URLs, successful downloads, Wayback URLs, errors, and summary counts.

## Project layout

```text
project.json
archive_scout.sqlite3
archive_scout.v1.backup.sqlite3
captures/
media/
reports/
```

The backup database appears only after an old project is migrated.

Each keyword scan is preserved in a separate folder:

```text
reports/scan-00001-General/
reports/scan-00002-Media-filenames/
```

The latest report is also copied directly into `reports` for convenience.

## Reports

Text scan reports:

```text
matches_ranked.txt
matched_urls.txt
wayback_urls.txt
interesting_links.txt
keyword_counts.txt
all_indexed_urls.txt
errors.txt
summary.txt
integrity.txt
```

Media reports:

```text
media_indexed.txt
media_downloaded.txt
media_wayback_urls.txt
media_errors.txt
media_summary.txt
```

## Upgrading an older project

Make an external backup of the project folder first. Archive Scout automatically upgrades Alpha 1 schema version 2 projects to schema version 3. Version 1 projects receive a separate `archive_scout.v1.backup.sqlite3` before their data is imported.

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

`2.0.0-alpha.2.2` is an alpha release. Keep backups of important projects and verify large media jobs with a narrow date range first.

See [ROADMAP.md](ROADMAP.md), [docs/OPERATIONS.md](docs/OPERATIONS.md), [docs/INDEXING_RECOVERY.md](docs/INDEXING_RECOVERY.md), and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Responsible use

Archive Scout works with publicly archived material. Users are responsible for following applicable laws, archive policies, site terms, and ethical research practices. Do not use the software to harass people, expose private information, or overwhelm archive infrastructure.
