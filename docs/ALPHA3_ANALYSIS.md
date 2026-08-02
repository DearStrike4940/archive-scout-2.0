# Alpha 3 archive analysis

Alpha 3 analysis runs against documents already saved in the project. It does not need to redownload text pages.

## Forum profiles

`auto` detects common forum signatures and otherwise uses the generic parser. Explicit profiles are useful when automatic detection is uncertain:

```text
auto
generic
vbulletin
phpbb
invision
futaba
2channel
```

Thread reconstruction is heuristic. A reconstructed post stores the source URL, capture ID, document ID, order, username/date when available, body text, and body hash.

## Built-in extraction

Built-in patterns cover:

- Google Video `docid`
- Google Video playback URLs
- YouTube video IDs
- Internet Archive identifiers
- `.swf` and Flash media URLs
- Windows Media URLs
- RealMedia URLs
- common legacy uploader IDs

Custom rules use:

```text
name :: regex
name :: field :: regex
```

The selected field can be `title`, `body`, `url`, `source`, or `links`.

## Legacy embed recovery

The parser checks old HTML structures including:

- `object`
- `embed`
- `param`
- `iframe`
- `frame`
- `video`
- `audio`
- `source`
- FlashVars
- script-config URLs

Recovered candidates are classified by likely player/type and stored in `legacy_assets`.

## Controlled external lookup

External lookup is opt-in. A candidate is searched only when:

1. External searching is enabled.
2. Its host matches an explicitly allowed domain or subdomain.
3. The configured lookup limit has not been reached.

A transient failure marks the candidate for a later analysis run instead of ending the complete analysis operation.

## Duplicates and provenance

Exact groups use content hashes. Near-duplicate groups use SimHash candidates and a configurable threshold. Provenance edges order duplicate documents by capture timestamp and store the similarity/method that connected them.

This is a research lead, not proof that the earlier archived page was the original publisher.

## Snapshot research

Adjacent snapshots of each URL are compared and summarized. Extracted values are also scanned across downloaded documents to report first and last capture dates in the current project.

## Reports

```text
reports/analysis/analysis_summary.txt
reports/analysis/forum_threads.tsv
reports/analysis/extractions.tsv
reports/analysis/legacy_assets.tsv
reports/analysis/duplicate_groups.tsv
reports/analysis/provenance.tsv
reports/analysis/snapshot_diffs.tsv
reports/analysis/first_appearances.tsv
```
