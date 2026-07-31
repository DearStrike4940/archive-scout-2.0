# Migrating Archive Scout 1.x Projects

Archive Scout 2.0 automatically recognizes the older `captures` table where `original` was the primary key.

Before migration, copy the full project folder to another drive or location.

When migration begins, Archive Scout creates:

```text
archive_scout.v1.backup.sqlite3
```

The active `archive_scout.sqlite3` then becomes the version 2 database. Existing capture files are not copied or renamed. Their current paths are imported.

After migration, run **Check project integrity**. Missing legacy files are recorded as retryable migration errors and appear in `errors.txt` and `integrity.txt`.

Do not delete the backup until the migrated project has been tested and the reports have been reviewed.
