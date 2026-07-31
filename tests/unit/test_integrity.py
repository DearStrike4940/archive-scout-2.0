from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from archive_scout.database.connection import open_database
from archive_scout.database.repositories import get_or_create_target, upsert_capture, upsert_document
from archive_scout.projects.integrity import check_project_integrity
from archive_scout.utils import hash_text, normalize_search


class IntegrityTests(unittest.TestCase):
    def test_missing_and_orphan_files_are_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "captures").mkdir()
            missing = root / "captures" / "missing.txt"
            orphan = root / "captures" / "orphan.txt"
            orphan.write_text("orphan", encoding="utf-8")
            database = open_database(root)
            target_id = get_or_create_target(database, "example.com/*")
            upsert_capture(
                database,
                {"original": "http://example.com", "timestamp": "20060101000000", "mimetype": "text/html", "statuscode": "200", "digest": "", "length": "1"},
                target_id,
                "sig",
            )
            capture_id = database.execute("SELECT id FROM captures").fetchone()[0]
            upsert_document(database, capture_id, missing, "", "", [], hash_text(""), hash_text(""), 1)
            report = check_project_integrity(root, database)
            text = report.read_text(encoding="utf-8")
            self.assertIn("MISSING_FILE", text)
            self.assertIn("ORPHAN_FILE", text)
            database.close()


if __name__ == "__main__":
    unittest.main()
