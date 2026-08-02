# Changelog

## 2.0.0-alpha.3

- Added schema version 4 and automatic migration from schema versions 2 and 3
- Added forum URL canonicalization, forum-profile detection, post parsing, and cross-snapshot thread reconstruction
- Added built-in Google Video `docid`, YouTube, Internet Archive, Flash, Windows Media, RealMedia, and legacy uploader extraction
- Added custom field-aware regular-expression extractors with context and source offsets
- Added legacy `object`, `embed`, `param`, iframe, frame, audio/video, FlashVars, and script-config asset recovery
- Added controlled external-asset Wayback lookup with explicit domain allowlists and lookup limits
- Added exact duplicate grouping and SimHash-based near-duplicate clustering
- Added source-to-mirror provenance edges and provenance reports
- Added adjacent snapshot comparison and first/last-appearance reports
- Added full project merging for captures, documents, media, scans, matches, reviews, notes, tags, and extractions
- Rebuilt SQLite full-text search automatically after project merges
- Added archive-analysis, forum-only rebuild, and project-merge operations to the interface
- Extended CDX timeout subdivision from one-hour windows down through 15-minute, five-minute, one-minute, 15-second, five-second, and one-second windows
- Changed smallest-window transient failures from fatal errors into saved, automatically retried work with reduced page sizes and bounded backoff
- Converted `urllib3` read timeouts and transient non-JSON gateway responses into resumable CDX failures
- Reworked direct media indexing to use one combined server-side extension filter per target and date window instead of one CDX query per extension
- Preserved local validation of returned media extensions and MIME types
- Added Alpha 3 analysis, merge, schema-migration, combined-media-index, and minimum-window timeout regression tests
- Expanded the automated suite to 61 tests

## 2.0.0-alpha.2.7

- Replaced independent per-worker HTTP 429 retries with one shared host-wide circuit breaker
- Obeyed Wayback `Retry-After` responses and coalesced simultaneous 429 responses into one incident
- Added half-open recovery: after a pause, one probe request tests Wayback before the full queue reopens
- Invalidated stale worker permits so requests already waiting when a 429 arrives cannot leak through after the circuit closes
- Added bounded exponential server backoff when `Retry-After` is absent
- Kept worker count and user-selected request delays fixed; server pauses do not rewrite project settings
- Prevented persistent rate limiting from turning thousands of queued captures into individual errors
- Made the 429 wait budget optional; the default of zero keeps the run paused until Wayback recovers or the user presses Stop
- Saved the pending queue and marked the run interrupted only when a nonzero 429 wait budget is exhausted
- Prevented server-level deferrals from consuming a capture's per-item download-attempt allowance
- Replaced `urllib` connection-per-request behavior with a shared `urllib3` keep-alive connection pool
- Added separate connect and read timeouts to pooled requests
- Bounded text and media in-flight queues to twice the worker count instead of submitting every media item at once
- Added visible 429 pause, retry, and graceful-deferral messages to the Activity tab
- Added 429 base pause, maximum pause, and wait-budget controls
- Changed new-project defaults to 4 workers, 1.0-second CDX spacing, and 0.5-second replay spacing
- Precomputed normalized page fields once per scan instead of once per keyword and field
- Added a compiled literal-keyword prefilter that skips full scoring on clearly nonmatching pages
- Drained redirect and error responses before connection reuse to prevent poisoned keep-alive sockets
- Added pooled-HTTP, redirect-reuse, shared-backpressure, half-open-probe, deferral, and large-keyword-set regression tests
- Expanded the automated suite to 49 tests

## 2.0.0-alpha.2.6

- Removed adaptive rate limiting, dynamic worker reduction, automatic cooldowns, penalty multipliers, and gradual worker recovery
- Replaced adaptive request control with fixed user-selected worker counts and fixed CDX/download delays
- Changed repeated HTTP 429 responses into per-request retryable errors instead of aborting the entire download queue
- Removed the adaptive-rate-limit setting from the interface and new project files
- Kept compatibility with older project files that still contain the unused `adaptive_rate_limit` field
- Simplified progress messages so they no longer report a changing active-worker limit or effective delay
- Retained adaptive CDX date-window splitting because it handles oversized index queries rather than changing request speed
- Added regression tests confirming that the limiter has no adaptive state or failure feedback loop

## 2.0.0-alpha.2.5

- Removed `hdiutil` from the macOS release pipeline after both direct and writable-image DMG workflows repeatedly failed with `Resource busy` on the hosted runner
- Replaced the macOS DMG with `ArchiveScout-macOS-Universal.zip`
- Packaged the signed universal application with `ditto -c -k --sequesterRsrc --keepParent` so bundle metadata, resource forks, and symbolic links are preserved
- Extracted the completed ZIP into a clean temporary directory during the build
- Re-ran bundle integrity and strict code-signature verification against the extracted release copy
- Updated the workflow, README download link, release documentation, and checksums to use the macOS ZIP
- Added a regression test preventing `hdiutil` and DMG packaging from returning to the alpha release workflow

## 2.0.0-alpha.2.4

- Fixed the macOS build failing at `hdiutil create` with `Resource busy` after the application bundle had already built and verified successfully
- Replaced direct `hdiutil create -srcfolder` packaging with a writable-image, mount, copy, detach, and convert workflow
- Moved temporary disk-image work into the GitHub runner temporary directory instead of the repository build tree
- Added bounded retries for transient disk-image creation failures
- Added retry and forced fallback handling when a disk image remains busy during detach
- Preserved bundle verification before signing, inside the writable image, and inside the final compressed DMG
- Added a packaging regression test that prevents the fragile `-srcfolder` workflow from returning

## 2.0.0-alpha.2.3

- Fixed missing `base_library.zip` failures being mislabeled as Wayback network errors
- Added a frozen-runtime integrity check before every operation and HTTP request
- Added a clear recovery message when the running macOS app was moved, renamed, deleted, replaced, or incompletely copied
- Prevented a missing application runtime from entering CDX retry and date-window splitting logic
- Switched macOS application staging from `cp -R` to `ditto` to preserve bundle metadata and symbolic links
- Added macOS bundle verification before signing, after staging, and after mounting the finished DMG
- Added broken-symbolic-link validation for the complete `.app` bundle
- Added strict code-signature verification during the macOS build
- Pinned PyInstaller 6.21.0 for reproducible package layout
- Added runtime-bundle regression tests

## 2.0.0-alpha.2.2

- Fixed monthly CDX requests still aborting a run when a broad site query timed out
- Added adaptive date-window splitting from months to seven-day, daily, six-hour, and hourly requests
- Preserved dynamically split CDX queues in the existing index-state resume field
- Resumed split indexing plans after Stop, application exit, or network failure
- Reduced CDX timeout retries to two before automatically subdividing the date range
- Limited individual CDX waits to 45 seconds while retaining visible retry messages
- Applied adaptive splitting to direct image and video indexing as well as text-page indexing
- Kept transient timeout splits out of the Errors table unless the smallest supported window also fails
- Expanded the automated suite to 31 tests

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
