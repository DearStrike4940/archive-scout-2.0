from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from archive_scout.database.connection import open_database
from archive_scout.database.repositories import get_or_create_keyword_set, get_or_create_target, start_scan_run, upsert_capture, upsert_document
from archive_scout.scanning.keywords import compile_keywords
from archive_scout.scanning.rescanner import rescan_documents
from archive_scout.scanning.scoring import analyze_content
from archive_scout.utils import hash_text, normalize_search


class ScanningTests(unittest.TestCase):
    def test_scoring_rewards_multiple_terms(self):
        patterns = compile_keywords(["9/11", "WTC", "jumpers"])
        one = analyze_content("http://example.com", "", "9/11", "9/11", [], patterns)
        three = analyze_content("http://example.com", "", "9/11 WTC jumpers", "9/11 WTC jumpers", [], patterns)
        self.assertGreater(three["score"], one["score"])

    def test_local_rescan_creates_new_match_without_network(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "saved.txt"
            path.write_text("<html><title>Archive</title><body>skylight.mov and canopy</body></html>", encoding="utf-8")
            database = open_database(root)
            target_id = get_or_create_target(database, "example.com/*")
            upsert_capture(
                database,
                {
                    "original": "http://example.com/thread",
                    "timestamp": "20060101000000",
                    "mimetype": "text/html",
                    "statuscode": "200",
                    "digest": "",
                    "length": str(path.stat().st_size),
                },
                target_id,
                "sig",
            )
            capture_id = database.execute("SELECT id FROM captures").fetchone()[0]
            document_id = upsert_document(
                database,
                capture_id,
                path,
                "Archive",
                "skylight.mov and canopy",
                [],
                hash_text(path.read_text()),
                hash_text(normalize_search("skylight.mov and canopy")),
                path.stat().st_size,
            )
            keyword_set_id = get_or_create_keyword_set(database, "Second scan", ["skylight.mov", "canopy"])
            scan_run_id = start_scan_run(database, keyword_set_id, "second scan", 1, "rescan")
            rescan_documents(database, scan_run_id, ["skylight.mov", "canopy"], threading.Event())
            row = database.execute("SELECT score,hits_json FROM document_matches WHERE scan_run_id=?", (scan_run_id,)).fetchone()
            self.assertIsNotNone(row)
            self.assertGreater(row["score"], 0)
            self.assertEqual(database.execute("SELECT COUNT(*) FROM captures").fetchone()[0], 1)
            database.close()


if __name__ == "__main__":
    unittest.main()
