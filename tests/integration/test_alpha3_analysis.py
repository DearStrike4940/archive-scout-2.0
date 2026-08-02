from __future__ import annotations

import tempfile
import threading
import unittest
from unittest.mock import patch
from pathlib import Path

from archive_scout.config import AnalysisConfig, ProjectConfig
from archive_scout.database.connection import open_database
from archive_scout.database.repositories import get_or_create_target, upsert_captures, upsert_document
from archive_scout.operations import run_project
from archive_scout.utils import hash_text, normalize_search


class Alpha3AnalysisIntegrationTests(unittest.TestCase):
    def test_analysis_workflow_builds_all_core_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            database = open_database(root)
            target_id = get_or_create_target(database, "example.com/*")
            raw = """
            <html><title>Recovered thread</title>
            <div id="post_1" class="post"><span class="username">Alice</span><div class="postbody">Google video docid=-123456 and mirror ABC-42</div></div>
            <object><param name="movie" value="http://cdn.example.net/player.swf"></object>
            </html>
            """
            row = {
                "original": "http://example.com/showthread.php?t=7&page=2",
                "timestamp": "20050101000000",
                "mimetype": "text/html",
                "statuscode": "200",
                "digest": "A",
                "length": str(len(raw)),
            }
            upsert_captures(database, [row], target_id, "sig")
            capture_id = database.execute("SELECT id FROM captures").fetchone()[0]
            path = root / "thread.html"
            path.write_text(raw, encoding="utf-8")
            upsert_document(
                database,
                capture_id,
                path,
                "Recovered thread",
                "Google video docid=-123456 and mirror ABC-42",
                ["http://cdn.example.net/player.swf"],
                hash_text(raw),
                hash_text(normalize_search(raw)),
                len(raw),
            )
            database.commit()
            database.close()

            config = ProjectConfig(
                output_dir=root,
                targets=[],
                keywords=[],
                from_date="2000",
                to_date="2010",
                analysis=AnalysisConfig(
                    extractor_rules=[r"mirror_code :: body :: (ABC-\d+)"],
                    search_external_assets=False,
                ),
            )
            paths = run_project(config, "analysis", threading.Event())
            self.assertTrue(paths["analysis_summary"].exists())
            database = open_database(root)
            self.assertEqual(database.execute("SELECT COUNT(*) FROM forum_threads").fetchone()[0], 1)
            self.assertEqual(database.execute("SELECT COUNT(*) FROM forum_posts").fetchone()[0], 1)
            self.assertGreaterEqual(database.execute("SELECT COUNT(*) FROM extractions").fetchone()[0], 2)
            self.assertGreaterEqual(database.execute("SELECT COUNT(*) FROM legacy_assets").fetchone()[0], 1)
            self.assertEqual(database.execute("SELECT status FROM analysis_runs ORDER BY id DESC").fetchone()[0], "complete")
            database.close()

    def test_controlled_external_asset_lookup_queues_media_capture(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            database = open_database(root)
            target_id = get_or_create_target(database, "example.com/*")
            raw = '<object><param name="movie" value="http://cdn.example.net/player.swf"></object>'
            row = {
                "original": "http://example.com/thread",
                "timestamp": "20050101000000",
                "mimetype": "text/html",
                "statuscode": "200",
                "digest": "A",
                "length": str(len(raw)),
            }
            upsert_captures(database, [row], target_id, "sig")
            capture_id = database.execute("SELECT id FROM captures").fetchone()[0]
            path = root / "external.html"
            path.write_text(raw, encoding="utf-8")
            upsert_document(
                database, capture_id, path, "External", "External player",
                ["http://cdn.example.net/player.swf"], hash_text(raw),
                hash_text(normalize_search(raw)), len(raw),
            )
            database.commit()
            database.close()

            payload = [["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
                       ["20050102000000", "http://cdn.example.net/player.swf", "application/x-shockwave-flash", "200", "B", "20"]]
            config = ProjectConfig(
                output_dir=root,
                targets=["example.com/*"],
                keywords=[],
                from_date="2000",
                to_date="2010",
                cdx_delay=0,
                analysis=AnalysisConfig(
                    search_external_assets=True,
                    external_domains=["example.net"],
                    external_asset_limit=10,
                ),
            )
            with patch("archive_scout.cdx.client.HttpClient.get_json", return_value=payload):
                run_project(config, "analysis", threading.Event())
            database = open_database(root)
            media = database.execute("SELECT original_url,media_kind,extension,source_type FROM media_captures").fetchone()
            self.assertIsNotNone(media)
            self.assertEqual(media["original_url"], "http://cdn.example.net/player.swf")
            self.assertEqual(media["media_kind"], "video")
            self.assertEqual(media["extension"], ".swf")
            self.assertEqual(media["source_type"], "external_asset")
            database.close()


if __name__ == "__main__":
    unittest.main()
