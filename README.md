# Archive Scout 2.0

Archive Scout is a cross-platform desktop application for indexing public Wayback Machine captures, downloading archived text pages, scanning them for custom keywords, and producing ranked plain-text reports.

This repository replaces the separate Windows, Linux, Intel Mac, and Apple Silicon Mac repositories with one codebase and one release page.

## Downloads

The first public 2.0 alpha release will provide three files:

- [Download for Windows x64](../../releases/latest/download/ArchiveScout-Windows-x64.zip)
- [Download for Linux x64](../../releases/latest/download/ArchiveScout-Linux-x64.tar.gz)
- [Download for macOS Intel and Apple Silicon](../../releases/latest/download/ArchiveScout-macOS-Universal.dmg)

Until a release is published, use **Actions → Build All Platforms → Run workflow** to create test builds.

## What is new in 2.0 alpha 1

Archive Scout 2.0 starts a new project format designed for long-running research rather than a single disposable scan.

- One repository for Windows, Linux, Intel Mac, and Apple Silicon Mac
- Multiple Wayback captures of the same original URL can coexist
- Downloaded documents are stored separately from keyword results
- Every rescan creates a preserved scan run instead of overwriting the previous report
- Existing downloads can be rescanned with new keywords without contacting the Wayback Machine
- Only errored URLs can be retried afterward
- Scan or parsing errors with valid local files are retried locally before any new download is attempted
- Download, scan, parsing, migration, and indexing errors are stored as structured database records
- Version 1 projects are backed up and migrated automatically
- A project-integrity operation checks for missing, empty, mismatched, and orphaned files
- SQLite full-text indexing is prepared for the later search interface
- Plain-text reports remain available and each scan receives its own report folder

## Operation modes

### Index, download, scan, and report

Runs the complete workflow. Archive Scout queries the CDX index, downloads eligible text captures, scans them, and writes reports.

### Index URLs only

Queries CDX and stores capture metadata without downloading anything.

### Download and scan pending URLs

Downloads only captures that have not been completed or attempted as errors.

### Resume interrupted work

Continues captures left pending by a stopped or interrupted run. It does not automatically retry previously failed URLs.

### Rescan existing downloads with current keywords

Reads the files already saved in the project and creates a new scan run. This operation makes no CDX requests and downloads nothing.

### Retry only errored URLs

Selects unresolved retryable errors only. Pages that failed during scanning or parsing are rescanned from disk when their local file is still valid. A capture is downloaded again only when its local copy is missing, invalid, or never completed.

### Regenerate reports only

Recreates the plain-text reports from a completed scan run without scanning or downloading.

### Check project integrity

Checks the database and capture folder for missing files, empty files, size mismatches, broken database links, unresolved errors, and untracked text files.

## Reports

The latest report remains directly inside the `reports` folder:

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

Every completed scan is also preserved in a folder such as:

```text
reports/scan-00003-Current-keywords/
```

Changing the keywords and rescanning therefore does not destroy the report from the earlier keyword set.

## Project files

```text
project.json
archive_scout.sqlite3
archive_scout.v1.backup.sqlite3
captures/
reports/
```

The backup database appears only after a version 1 project is migrated.

## Upgrading a version 1 project

1. Make an external copy of the entire project folder.
2. Open the existing `project.json` in Archive Scout 2.0.
3. Start a local operation such as **Check project integrity** or **Rescan existing downloads**.
4. Archive Scout detects the old database, creates `archive_scout.v1.backup.sqlite3`, builds the version 2 database, imports saved captures, and preserves the old ranking as a legacy scan run.
5. Review `reports/integrity.txt` after migration.

The backup is not deleted automatically.

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

## Building every operating system

GitHub must build each platform on its native runner. Open:

```text
Actions → Build All Platforms → Run workflow
```

A successful manual run creates three downloadable workflow artifacts. Publishing a tag such as `v2.0.0-alpha.1` creates or updates a GitHub Release and attaches the three public packages and their SHA-256 files.

## Current status

`2.0.0-alpha.1` is the foundation release. The database is already prepared for reviews, notes, tags, duplicate groups, forum threads, forum posts, extractions, and snapshot comparisons, but those interfaces and analyzers are being added in later milestones.

See [ROADMAP.md](ROADMAP.md) for the complete implementation plan and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the project structure.

## Responsible use

Archive Scout works with publicly archived material. Users are responsible for following applicable laws, archive policies, site terms, and ethical research practices. Do not use the software to harass people, expose private information, or overwhelm archive infrastructure.
