from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from archive_scout.config import MediaConfig, ProjectConfig
from archive_scout.database.connection import open_database
from archive_scout.media.indexer import index_media


class Alpha3MediaIndexTests(unittest.TestCase):
    def test_all_extensions_use_one_cdx_query_per_window(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = ProjectConfig(
                output_dir=root,
                targets=["example.com/*"],
                keywords=["x"],
                from_date="200101",
                to_date="200101",
                cdx_delay=0,
                media=MediaConfig(
                    enabled=True,
                    include_images=True,
                    include_videos=True,
                    include_extensions=["jpg", "png", "mp4", "wmv"],
                    discover_embedded=False,
                ),
            ).normalized()
            database = open_database(root)
            with patch("archive_scout.cdx.client.HttpClient.get_json", return_value=[]) as mocked:
                index_media(config, database, threading.Event())
            self.assertEqual(mocked.call_count, 1)
            params = mocked.call_args.args[1]
            original_filters = [value for key, value in params if key == "filter" and value.startswith("~original:")]
            self.assertEqual(len(original_filters), 1)
            for extension in ("jpg", "png", "mp4", "wmv"):
                self.assertIn(extension, original_filters[0])
            state = database.execute("SELECT extension,complete FROM media_index_state").fetchone()
            self.assertEqual(state["extension"], "__all__")
            self.assertEqual(state["complete"], 1)
            database.close()


if __name__ == "__main__":
    unittest.main()
