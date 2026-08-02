from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from archive_scout.config import AnalysisConfig, ProjectConfig
from archive_scout.database.connection import open_database
from archive_scout.database.repositories import (
    get_or_create_keyword_set,
    get_or_create_target,
    save_match,
    save_note,
    set_match_tags,
    set_review,
    start_scan_run,
    upsert_captures,
    upsert_document,
)
from archive_scout.operations import run_project
from archive_scout.utils import hash_text, normalize_search


class Alpha3MergeIntegrationTests(unittest.TestCase):
    def test_project_merge_preserves_review_work(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source_root = base / "source"
            destination_root = base / "destination"
            source = open_database(source_root)
            target_id = get_or_create_target(source, "example.com/*")
            row = {
                "original": "http://example.com/thread",
                "timestamp": "20050101000000",
                "mimetype": "text/html",
                "statuscode": "200",
                "digest": "A",
                "length": "10",
            }
            upsert_captures(source, [row], target_id, "sig")
            capture_id = source.execute("SELECT id FROM captures").fetchone()[0]
            path = source_root / "page.html"
            path.write_text("alpha", encoding="utf-8")
            document_id = upsert_document(
                source,
                capture_id,
                path,
                "Title",
                "alpha",
                [],
                hash_text("alpha"),
                hash_text(normalize_search("alpha")),
                5,
            )
            keyword_set_id = get_or_create_keyword_set(source, "Set", ["alpha"])
            scan_id = start_scan_run(source, keyword_set_id, "Source scan", 1, "rescan", {})
            match_id = save_match(source, scan_id, document_id, {"score": 5, "hits": {"alpha": 1}})
            set_review(source, match_id, "relevant", "Researcher")
            save_note(source, match_id, "Important source", "Researcher")
            set_match_tags(source, match_id, ["lead"])
            source.commit()
            source.close()

            config = ProjectConfig(
                output_dir=destination_root,
                targets=[],
                keywords=[],
                analysis=AnalysisConfig(merge_source=str(source_root)),
            )
            paths = run_project(config, "merge_project")
            self.assertTrue(paths["merge_summary"].exists())
            destination = open_database(destination_root)
            self.assertEqual(destination.execute("SELECT COUNT(*) FROM documents").fetchone()[0], 1)
            self.assertEqual(destination.execute("SELECT status FROM reviews").fetchone()[0], "relevant")
            self.assertEqual(destination.execute("SELECT text FROM notes").fetchone()[0], "Important source")
            self.assertEqual(destination.execute("SELECT name FROM tags").fetchone()[0], "lead")
            self.assertEqual(destination.execute("SELECT COUNT(*) FROM project_merges").fetchone()[0], 1)
            self.assertEqual(destination.execute("SELECT COUNT(*) FROM documents_fts WHERE documents_fts MATCH 'alpha'").fetchone()[0], 1)
            destination.close()


if __name__ == "__main__":
    unittest.main()
