# Migration

Archive Scout Alpha 2 uses database schema version 3.

## From Alpha 1

Schema version 2 databases are upgraded in place when opened. New columns and media tables are added while captures, documents, scans, reports, errors, and local files remain intact.

Make an external copy of the project folder before opening an important project in a newer alpha.

## From Archive Scout 1.x

The legacy database is copied to:

```text
archive_scout.v1.backup.sqlite3
```

A new database is built, existing documents are imported, and previous matches are retained as a legacy scan run.

## After migration

Run **Check project integrity** and inspect:

```text
reports/integrity.txt
```

Do not delete the backup until the migrated project has been tested.
