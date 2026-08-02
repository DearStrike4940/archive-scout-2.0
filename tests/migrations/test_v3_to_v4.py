from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from archive_scout.database.connection import open_database
from archive_scout.database.schema import BASE_SCHEMA_SQL


class V3ToV4MigrationTests(unittest.TestCase):
    def test_v3_database_is_upgraded_in_place(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            database = sqlite3.connect(root / "archive_scout.sqlite3")
            database.executescript(BASE_SCHEMA_SQL)
            database.execute("DELETE FROM schema_info")
            database.execute("INSERT INTO schema_info(version) VALUES(3)")
            for table in ("analysis_runs", "legacy_assets", "provenance_edges", "first_appearances", "project_merges"):
                database.execute(f"DROP TABLE IF EXISTS {table}")
            database.commit()
            database.close()

            modern = open_database(root)
            self.assertEqual(modern.execute("SELECT version FROM schema_info").fetchone()[0], 4)
            for table in ("analysis_runs", "legacy_assets", "provenance_edges", "first_appearances", "project_merges"):
                self.assertIsNotNone(modern.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())
            forum_columns = {row[1] for row in modern.execute("PRAGMA table_info(forum_threads)")}
            self.assertIn("canonical_url", forum_columns)
            extraction_columns = {row[1] for row in modern.execute("PRAGMA table_info(extractions)")}
            self.assertIn("extractor_type", extraction_columns)
            modern.close()


if __name__ == "__main__":
    unittest.main()
