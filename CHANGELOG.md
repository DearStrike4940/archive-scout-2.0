# Changelog

## 2.0.0-alpha.2.1

- Fixed Start silently doing nothing while a previous worker was still shutting down
- Cleared completed worker references so runs can be restarted reliably
- Split large annual CDX searches into resumable monthly windows
- Reduced CDX retries from six long attempts to three bounded attempts
- Added visible retry reasons, attempt numbers, and wait times to the Activity log
- Added per-request CDX and database timing to indexing progress
- Replaced per-capture SELECT/INSERT/UPDATE loops with batched SQLite upserts
- Applied the same monthly windowing, shorter retry cycle, and batching to direct media indexing
- Prevented Stop actions from being recorded as indexing failures
- Prevented failed indexing attempts from creating empty scan runs
- Prevented identical selected keyword sets from creating duplicate scan jobs
- Preserved monthly resume progress inside the existing project database format
- Expanded the automated suite to 29 tests

## 2.0.0-alpha.2

- Added built-in ranked result viewing, sorting, filtering, snippets, notes, tags, and review labels
- Added next-unreviewed navigation and filtered CSV, JSON, Markdown, and review-package exports
- Added named keyword-set creation, duplication, import, export, and multi-set scanning in one pass
- Added required, excluded, exact, regex, weighted, case-sensitive, whole-word, and shared-label keyword rules
- Added same-sentence, same-paragraph, distinct-term, and proximity scoring bonuses
- Added instant offline full-text search restricted to the selected scan when desired
- Added scan history controls and two-scan comparison reports
- Added adaptive request limiting with concurrency reduction, cooldowns, and gradual recovery
- Added an error viewer with selected text-page and media retries
- Added direct image/video CDX indexing and embedded-media discovery
- Added separate media targets, image/video toggles, include/exclude extension lists, and snapshot strategies
- Added resumable media downloading, media error retries, safe paths, hashes, size limits, and media reports
- Added schema version 3 and automatic in-place migration from Alpha 1 schema version 2
- Expanded the automated suite to 24 unit, migration, and integration tests
- Updated GitHub artifact actions to Node.js 24-compatible versions

## 2.0.0-alpha.1

- Unified the Windows, Linux, Intel Mac, and Apple Silicon projects
- Added version 2 project database and safe version 1 migration
- Added preserved keyword sets and scan runs
- Added offline rescanning without CDX or download requests
- Added retry-only-errored-URLs operation
- Added local retries for scan and parsing errors
- Added structured error categories and resolution state
- Added project-integrity reports
- Added full-text document index storage
- Added cross-platform build and release workflow
