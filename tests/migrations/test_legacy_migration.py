from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from archive_scout.database.connection import open_database


class LegacyMigrationTests(unittest.TestCase):
    def test_legacy_project_is_backed_up_and_imported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            saved = root / "captures" / "2006" / "01" / "legacy.txt"
            saved.parent.mkdir(parents=True)
            saved.write_text("<html><title>Legacy</title><body>WTC jumper</body></html>", encoding="utf-8")
            database = sqlite3.connect(root / "archive_scout.sqlite3")
            database.executescript(
                """
                CREATE TABLE captures(
                    original TEXT PRIMARY KEY,timestamp TEXT,source_target TEXT,query_signature TEXT,mimetype TEXT,statuscode TEXT,
                    digest TEXT,length INTEGER,state TEXT,attempts INTEGER,path TEXT,title TEXT,score INTEGER,keyword_hits TEXT,
                    hit_fields TEXT,snippets TEXT,interesting_links TEXT,bytes_saved INTEGER,http_status INTEGER,final_url TEXT,error TEXT,updated_at TEXT
                );
                CREATE TABLE index_state(target TEXT,year INTEGER,query_signature TEXT,resume_key TEXT,complete INTEGER,seen INTEGER,error TEXT,updated_at TEXT);
                """
            )
            database.execute(
                "INSERT INTO captures VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "http://example.com/thread", "20060101000000", "example.com/*", "legacy", "text/html", "200", "", 10,
                    "done", 1, str(saved), "Legacy", 8, json.dumps({"WTC": 1}), json.dumps({"WTC": ["body"]}),
                    json.dumps(["wtc jumper"]), json.dumps([]), saved.stat().st_size, 200, "", None, "2026-01-01T00:00:00+00:00",
                ),
            )
            database.commit()
            database.close()
            (root / "project.json").write_text(json.dumps({"keywords": ["WTC", "jumper"]}), encoding="utf-8")
            modern = open_database(root)
            self.assertTrue((root / "archive_scout.v1.backup.sqlite3").exists())
            self.assertEqual(modern.execute("SELECT version FROM schema_info").fetchone()[0], 4)
            self.assertEqual(modern.execute("SELECT COUNT(*) FROM captures").fetchone()[0], 1)
            self.assertEqual(modern.execute("SELECT COUNT(*) FROM documents").fetchone()[0], 1)
            self.assertEqual(modern.execute("SELECT COUNT(*) FROM document_matches").fetchone()[0], 1)
            modern.close()


if __name__ == "__main__":
    unittest.main()
