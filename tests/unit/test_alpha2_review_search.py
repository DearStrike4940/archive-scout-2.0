from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from archive_scout.database.connection import open_database
from archive_scout.database.repositories import (
    get_or_create_keyword_set, get_or_create_target, result_rows, save_match, save_note, set_match_tags, set_review,
    start_scan_run, upsert_capture, upsert_document,
)
from archive_scout.reports.export import export_scan
from archive_scout.scanning.full_text import search_documents
from archive_scout.utils import hash_text, normalize_search


class Alpha2ReviewSearchTests(unittest.TestCase):
    def test_review_notes_tags_exports_and_full_text(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "page.txt"
            path.write_text("World Trade Center jumper impact footage", encoding="utf-8")
            database = open_database(root)
            target_id = get_or_create_target(database, "example.com/*")
            upsert_capture(database, {
                "original": "http://example.com/thread", "timestamp": "20060101000000", "mimetype": "text/html",
                "statuscode": "200", "digest": "", "length": str(path.stat().st_size),
            }, target_id, "sig")
            capture_id = database.execute("SELECT id FROM captures").fetchone()[0]
            document_id = upsert_document(database, capture_id, path, "WTC Thread", path.read_text(), [], hash_text(path.read_text()), hash_text(normalize_search(path.read_text())), path.stat().st_size)
            set_id = get_or_create_keyword_set(database, "Set", ["WTC"])
            run_id = start_scan_run(database, set_id, "Run", 1, "rescan")
            match_id = save_match(database, run_id, document_id, {"score": 10, "hits": {"WTC": 1}, "hit_fields": {"WTC": ["body"]}, "snippets": ["jumper impact"], "interesting_links": []})
            set_review(database, match_id, "relevant", "tester")
            save_note(database, match_id, "Strong lead", "tester")
            set_match_tags(database, match_id, ["9/11", "video"])
            database.commit()
            rows = result_rows(database, run_id, review_status="relevant")
            self.assertEqual(rows[0]["note"], "Strong lead")
            self.assertIn("video", rows[0]["tags"])
            fts = search_documents(database, '"jumper impact"', scan_run_id=run_id)
            self.assertEqual(len(fts), 1)
            self.assertEqual(search_documents(database, '"jumper impact"', scan_run_id=run_id + 999), [])
            export = export_scan(database, run_id, root / "review.json", "json")
            self.assertIn("Strong lead", export.read_text(encoding="utf-8"))
            database.close()


if __name__ == "__main__":
    unittest.main()
