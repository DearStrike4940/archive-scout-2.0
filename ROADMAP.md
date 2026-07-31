# Archive Scout 2.0 Roadmap

## Alpha 1: project foundation

Implemented in this repository:

- Unified cross-platform repository
- Version 2 SQLite project format
- Safe version 1 migration and backup
- Capture identity based on original URL, timestamp, and CDX query signature
- Separate documents, keyword sets, scan runs, matches, hits, and structured errors
- Offline rescanning with preserved scan history
- Retry only errored URLs
- Local retry for scan and parsing errors
- Project integrity report
- Full-text index storage
- Cross-platform tests and release workflow

## Alpha 2: advanced searching and scoring

- Named and editable keyword sets
- Multiple keyword sets in one pass
- Required, optional, excluded, and weighted terms
- Whole-word and case-sensitive matching
- Exact phrase controls
- Synonym, spelling, punctuation, and language groups
- Same-sentence, same-paragraph, and configurable proximity bonuses
- Maximum contribution per term
- Search within previous results
- Full-text search interface

## Alpha 3: result review interface

- Built-in report viewer
- Sort and filter by score, date, domain, title, term, and state
- Match highlighting and snippets
- Local-file and Wayback buttons
- Unreviewed, relevant, possible, false positive, duplicate, dead end, and follow-up labels
- Notes, tags, reviewer names, and timestamps
- Next-unreviewed navigation
- Selected-result exports

## Alpha 4: forum research

- Post-level parsing
- Thread and topic ID extraction
- Forum URL canonicalization
- Thread-page grouping
- Print, archive, and normal-page deduplication
- Username, date, post number, and body extraction
- Thread reconstruction
- Missing-page detection
- Parser profiles for vBulletin, phpBB, Invision, XenForo, MyAnimeList, Something Awful, Ogrish, and generic forums

## Alpha 5: extraction and media recovery

- User-defined regular-expression extractors
- Google Video `docid` extraction
- Thread, topic, filename, and media-ID extraction
- Links from matching lines, paragraphs, and forum posts
- Legacy `<embed>`, `<object>`, `<param>`, Flash, Windows Media, RealPlayer, iframe, and JavaScript-player detection
- External media host grouping
- Archived external-asset discovery
- Controlled cross-domain crawling and approval queue

## Alpha 6: duplicates and provenance

- Exact and normalized content hashes
- Near-duplicate similarity
- Duplicate clusters and hidden duplicate counts
- Canonical representative selection
- Mirror and renamed-copy tracking
- Source-to-mirror chronology
- First known mention and first archived copy

## Alpha 7: snapshot research

- Earliest, latest, first successful, closest-date, monthly, yearly, first-and-last, limited, and every-capture policies
- Text, link, title, and embed comparisons
- First-appearance and disappearance searches
- Snapshot timelines

## Alpha 8: projects and collaboration

- Import arbitrary HTML and text collections
- Project merging
- Shared review packages
- Review-result merging
- Collections and review queues
- Saved searches and search history
- Keyword, CDX, extractor, media-extension, and language templates

## Beta: reliability and distribution

- Adaptive rate limiting
- Dynamic worker reduction and recovery
- Per-target settings and queues
- Improved ETA and throughput reporting
- Retry by selected error category
- Automatic update checks
- Stable Windows x64, Linux x64, and universal macOS releases
