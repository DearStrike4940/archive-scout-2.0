from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from archive_scout.config import ProjectConfig
from archive_scout.database.connection import open_database
from archive_scout.database.repositories import get_or_create_target, upsert_capture, upsert_document
from archive_scout.operations import run_project
from archive_scout.utils import hash_text, normalize_search


class OperationTests(unittest.TestCase):
    def test_rescan_operation_generates_reports_without_targets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "existing.txt"
            path.write_text("<html><body>LOL Superman canopy</body></html>", encoding="utf-8")
            database = open_database(root)
            target_id = get_or_create_target(database, "legacy/*")
            upsert_capture(
                database,
                {"original": "http://example.com/old", "timestamp": "20060101000000", "mimetype": "text/html", "statuscode": "200", "digest": "", "length": str(path.stat().st_size)},
                target_id,
                "legacy",
            )
            capture_id = database.execute("SELECT id FROM captures").fetchone()[0]
            upsert_document(database, capture_id, path, "", "LOL Superman canopy", [], hash_text(path.read_text()), hash_text(normalize_search("LOL Superman canopy")), path.stat().st_size)
            database.commit()
            database.close()
            config = ProjectConfig(output_dir=root, targets=[], keywords=["LOL Superman", "canopy"], from_date="2000", to_date="2010")
            paths = run_project(config, "rescan")
            self.assertTrue(paths["matches_ranked"].exists())
            text = paths["matches_ranked"].read_text(encoding="utf-8")
            self.assertIn("LOL Superman", text)


if __name__ == "__main__":
    unittest.main()
