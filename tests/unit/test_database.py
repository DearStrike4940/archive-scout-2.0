from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from archive_scout.database.connection import open_database
from archive_scout.database.repositories import (
    get_or_create_keyword_set,
    get_or_create_target,
    save_match,
    start_scan_run,
    upsert_capture,
    upsert_document,
)
from archive_scout.utils import hash_text, normalize_search


class DatabaseTests(unittest.TestCase):
    def test_v2_schema_and_capture_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            database = open_database(root)
            target_id = get_or_create_target(database, "example.com/*")
            row = {
                "original": "http://example.com/page",
                "timestamp": "20060101000000",
                "mimetype": "text/html",
                "statuscode": "200",
                "digest": "ABC",
                "length": "100",
            }
            self.assertTrue(upsert_capture(database, row, target_id, "sig"))
            self.assertFalse(upsert_capture(database, row, target_id, "sig"))
            row2 = dict(row, timestamp="20070101000000")
            self.assertTrue(upsert_capture(database, row2, target_id, "sig"))
            count = database.execute("SELECT COUNT(*) FROM captures").fetchone()[0]
            self.assertEqual(count, 2)
            database.close()

    def test_scan_runs_do_not_overwrite_each_other(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "capture.txt"
            path.write_text("alpha beta", encoding="utf-8")
            database = open_database(root)
            target_id = get_or_create_target(database, "example.com/*")
            upsert_capture(
                database,
                {
                    "original": "http://example.com/page",
                    "timestamp": "20060101000000",
                    "mimetype": "text/html",
                    "statuscode": "200",
                    "digest": "",
                    "length": "10",
                },
                target_id,
                "sig",
            )
            capture_id = database.execute("SELECT id FROM captures").fetchone()[0]
            document_id = upsert_document(
                database,
                capture_id,
                path,
                "Title",
                "alpha beta",
                [],
                hash_text("alpha beta"),
                hash_text(normalize_search("alpha beta")),
                path.stat().st_size,
            )
            set1 = get_or_create_keyword_set(database, "One", ["alpha"])
            set2 = get_or_create_keyword_set(database, "Two", ["beta"])
            run1 = start_scan_run(database, set1, "run1", 1, "rescan")
            run2 = start_scan_run(database, set2, "run2", 1, "rescan")
            save_match(database, run1, document_id, {"score": 1, "hits": {"alpha": 1}, "hit_fields": {}, "snippets": [], "interesting_links": []})
            save_match(database, run2, document_id, {"score": 2, "hits": {"beta": 1}, "hit_fields": {}, "snippets": [], "interesting_links": []})
            self.assertEqual(database.execute("SELECT COUNT(*) FROM document_matches").fetchone()[0], 2)
            database.close()


if __name__ == "__main__":
    unittest.main()
