from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from archive_scout.config import KeywordSetConfig, ProjectConfig
from archive_scout.database.connection import open_database
from archive_scout.database.repositories import get_or_create_target, upsert_capture, upsert_document
from archive_scout.operations import run_project
from archive_scout.utils import hash_text, normalize_search


class Alpha2MultiScanTests(unittest.TestCase):
    def test_one_rescan_creates_results_for_multiple_keyword_sets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "saved.txt"
            path.write_text("<html><body>WTC jumper skylight.mov canopy</body></html>", encoding="utf-8")
            database = open_database(root)
            target_id = get_or_create_target(database, "example.com/*")
            upsert_capture(database, {
                "original": "http://example.com/thread", "timestamp": "20060101000000", "mimetype": "text/html",
                "statuscode": "200", "digest": "", "length": str(path.stat().st_size),
            }, target_id, "legacy")
            capture_id = database.execute("SELECT id FROM captures").fetchone()[0]
            upsert_document(database, capture_id, path, "", "WTC jumper skylight.mov canopy", [], hash_text(path.read_text()), hash_text(normalize_search(path.read_text())), path.stat().st_size)
            database.commit()
            database.close()
            config = ProjectConfig(
                output_dir=root,
                targets=[],
                keywords=[],
                keyword_sets=[
                    KeywordSetConfig("General", ["WTC", "jumper"], True),
                    KeywordSetConfig("Media", ["skylight.mov", "canopy"], True),
                ],
                from_date="2000",
                to_date="2010",
            )
            run_project(config, "rescan")
            database = open_database(root)
            self.assertEqual(database.execute("SELECT COUNT(*) FROM scan_runs WHERE status='complete'").fetchone()[0], 2)
            self.assertEqual(database.execute("SELECT COUNT(*) FROM document_matches").fetchone()[0], 2)
            database.close()


if __name__ == "__main__":
    unittest.main()
