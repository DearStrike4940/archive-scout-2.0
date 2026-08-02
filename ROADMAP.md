# Archive Scout 2.0 Roadmap

## Alpha 1 — Foundation, rescanning, and retries

Completed:

- Unified cross-platform repository
- Version 2 project database
- Safe migration and backups
- Offline rescanning with preserved scan history
- Retry only errored URLs
- Structured errors and project integrity checking
- Cross-platform tests and builds

## Alpha 2 — Search, scoring, review, and media downloading

Completed:

- Built-in ranked results viewer
- Review labels, notes, tags, filters, and exports
- Advanced keyword rules and proximity scoring
- Multiple named keyword sets in one pass
- Instant offline full-text search
- Scan history and comparison
- Fixed user-controlled pacing and coordinated HTTP 429 recovery
- Keep-alive HTTP pooling and bounded request queues
- Better error controls
- Image/video indexing and downloading
- Extension inclusion and exclusion
- Embedded and optional external media discovery
- Media retry, resume, and reports

## Alpha 3 — Archive recovery and analysis

Completed in this repository:

- Forum post parsing and thread reconstruction
- Forum URL canonicalization
- Automatic and selectable forum profiles
- Custom regular-expression extractors
- Google Video `docid` and legacy identifier extraction
- Legacy Flash, Windows Media, RealPlayer, iframe, playlist, and script-config recovery
- Controlled external-asset searching with an explicit domain allowlist
- Exact and near-duplicate clustering
- Source-to-mirror provenance tracking
- Snapshot comparison
- First-appearance and last-appearance searches
- Project merging
- Shared review, notes, tags, media, scan, and extraction merging
- Schema version 4 migration
- Noninterrupting transient CDX timeout recovery down to one-second windows
- One combined direct-media CDX query for all selected extensions

## Alpha 4 — Integration, reliability, and feature freeze

Planned:

- Large-project performance and memory improvements
- Pause, cancellation, resume, and crash recovery hardening
- Per-target settings and queues
- Import of older script-created archives
- Database backup, restore, repair, and index rebuilding controls
- Final migration support for every alpha
- Stress tests using hundreds of thousands of records
- Project-format and database-schema freeze
- Removal or clear marking of unfinished features

## Beta 1 — Visual redesign and usability

Planned:

- Redesigned interface and navigation
- Light and dark themes
- Improved icons, spacing, typography, progress displays, and empty states
- Simplified and advanced modes
- Better high-DPI, font scaling, keyboard navigation, and accessibility
- Improved tables, highlights, dashboards, charts, and first-run guidance

## Beta 2 — Public testing and optimization

- Broader real-world testing on every operating system
- Parser and relevance improvements
- Performance tuning
- Documentation and installer refinements
- Update notifications

## Beta 3 — Final stabilization

- No major new features
- Final security, migration, packaging, and performance review
- Release-candidate preparation

## Stable release

```text
2.0.0-rc.1
2.0.0
```
