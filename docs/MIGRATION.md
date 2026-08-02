# Migration

Archive Scout Alpha 3 uses database schema version 4.

## From Alpha 2

Schema version 3 databases are upgraded in place when opened. Alpha 3 adds analysis, forum, extraction, provenance, first-appearance, and project-merge storage while preserving captures, documents, media, scans, reviews, notes, tags, errors, and local files.

## From Alpha 1

Schema version 2 databases are upgraded through schema version 3 to version 4 in one open operation.

## From Archive Scout 1.x

The legacy database is copied to:

```text
archive_scout.v1.backup.sqlite3
```

A new database is built, existing documents are imported, and previous matches are retained as a legacy scan run.

## Before and after migration

Make an external copy of the complete project folder before opening an important project in a newer alpha. After migration, run **Check project integrity** and inspect:

```text
reports/integrity.txt
```

Do not delete the version 1 backup until the migrated project has been tested.
