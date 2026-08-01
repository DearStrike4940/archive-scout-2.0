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
from archive_scout.reports.compare import generate_scan_comparison
from archive_scout.utils import hash_text, normalize_search


class Alpha2ComparisonTests(unittest.TestCase):
    def test_scan_comparison_reports_score_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            page = root / "page.txt"
            page.write_text("WTC jumper impact footage", encoding="utf-8")
            database = open_database(root)
            target_id = get_or_create_target(database, "example.com/*")
            upsert_capture(database, {
                "original": "http://example.com/thread", "timestamp": "20060101000000",
                "mimetype": "text/html", "statuscode": "200", "digest": "", "length": "25",
            }, target_id, "sig")
            capture_id = int(database.execute("SELECT id FROM captures").fetchone()[0])
            text = page.read_text(encoding="utf-8")
            document_id = upsert_document(
                database, capture_id, page, "Thread", text, [], hash_text(text),
                hash_text(normalize_search(text)), page.stat().st_size,
            )
            first_set = get_or_create_keyword_set(database, "First", ["WTC"])
            second_set = get_or_create_keyword_set(database, "Second", ["WTC", "jumper"])
            first_run = start_scan_run(database, first_set, "First run", 1, "rescan")
            second_run = start_scan_run(database, second_set, "Second run", 1, "rescan")
            save_match(database, first_run, document_id, {"score": 10, "hits": {"WTC": 1}})
            save_match(database, second_run, document_id, {"score": 25, "hits": {"WTC": 1, "jumper": 1}})
            database.commit()
            output = generate_scan_comparison(database, first_run, second_run, root / "comparison.txt")
            content = output.read_text(encoding="utf-8")
            self.assertIn("delta=+15", content)
            self.assertIn("http://example.com/thread", content)
            database.close()


if __name__ == "__main__":
    unittest.main()
