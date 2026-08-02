from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from archive_scout.database.connection import open_database
from archive_scout.database.schema import BASE_SCHEMA_SQL


class V2ToV3MigrationTests(unittest.TestCase):
    def test_v2_database_is_upgraded_in_place(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            database = sqlite3.connect(root / "archive_scout.sqlite3")
            database.executescript(BASE_SCHEMA_SQL)
            database.execute("DELETE FROM schema_info")
            database.execute("INSERT INTO schema_info(version) VALUES(2)")
            database.commit()
            database.close()
            modern = open_database(root)
            self.assertEqual(modern.execute("SELECT version FROM schema_info").fetchone()[0], 4)
            self.assertIn("rules_json", {row[1] for row in modern.execute("PRAGMA table_info(keyword_sets)")})
            self.assertIsNotNone(modern.execute("SELECT name FROM sqlite_master WHERE name='media_captures'").fetchone())
            modern.close()


if __name__ == "__main__":
    unittest.main()
