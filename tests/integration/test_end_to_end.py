from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from archive_scout.config import ProjectConfig
from archive_scout.database.connection import open_database
from archive_scout.operations import run_project


class EndToEndTests(unittest.TestCase):
    def test_mocked_index_download_scan_rescan_and_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = ProjectConfig(
                output_dir=root,
                targets=["example.com/*"],
                keywords=["WTC", "jumpers"],
                keyword_set_name="First search",
                from_date="2006",
                to_date="2006",
                workers=2,
                cdx_delay=0,
                download_delay=0,
            )
            cdx_payload = [
                ["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
                ["20060102030405", "http://example.com/thread/1", "text/html", "200", "ABC", "100"],
            ]
            page = b"<html><title>9/11 discussion</title><body>WTC jumpers and canopy footage</body></html>"

            with patch("archive_scout.cdx.client.HttpClient.get_json", return_value=cdx_payload), patch(
                "archive_scout.cdx.client.HttpClient.get",
                return_value={
                    "data": page,
                    "status": 200,
                    "headers": {"Content-Type": "text/html; charset=utf-8"},
                    "final_url": "https://web.archive.org/web/20060102030405id_/http://example.com/thread/1",
                },
            ):
                paths = run_project(config, "all")
            self.assertTrue(paths["matches_ranked"].exists())
            self.assertIn("WTC", paths["matches_ranked"].read_text(encoding="utf-8"))

            database = open_database(root)
            self.assertEqual(database.execute("SELECT COUNT(*) FROM captures").fetchone()[0], 1)
            self.assertEqual(database.execute("SELECT COUNT(*) FROM documents").fetchone()[0], 1)
            self.assertEqual(database.execute("SELECT COUNT(*) FROM scan_runs WHERE status='complete'").fetchone()[0], 1)
            database.close()

            second = ProjectConfig(
                output_dir=root,
                targets=["example.com/*"],
                keywords=["canopy"],
                keyword_set_name="Second search",
                from_date="2006",
                to_date="2006",
            )
            second_paths = run_project(second, "rescan")
            self.assertIn("canopy", second_paths["matches_ranked"].read_text(encoding="utf-8").casefold())
            database = open_database(root)
            self.assertEqual(database.execute("SELECT COUNT(*) FROM scan_runs WHERE status='complete'").fetchone()[0], 2)
            self.assertEqual(database.execute("SELECT COUNT(*) FROM document_matches").fetchone()[0], 2)
            database.close()


if __name__ == "__main__":
    unittest.main()
