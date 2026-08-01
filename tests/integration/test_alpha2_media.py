from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from archive_scout.config import MediaConfig, ProjectConfig
from archive_scout.database.connection import open_database
from archive_scout.media.downloader import download_media
from archive_scout.media.extensions import selected_extensions
from archive_scout.media.indexer import index_media


class Alpha2MediaTests(unittest.TestCase):
    def test_extension_include_exclude(self):
        media = MediaConfig(include_extensions=["jpg", "gif", "mp4"], exclude_extensions=["gif"])
        self.assertEqual(selected_extensions(media), [".jpg", ".mp4"])

    def test_mocked_media_index_and_download(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = ProjectConfig(
                output_dir=root,
                targets=["example.com/*"],
                keywords=["example"],
                from_date="2006",
                to_date="2006",
                workers=2,
                cdx_delay=0,
                download_delay=0,
                media=MediaConfig(
                    targets=["example.com/images/*"],
                    include_images=True,
                    include_videos=False,
                    include_extensions=["jpg"],
                    exclude_extensions=[],
                    discover_embedded=False,
                    max_file_mb=10,
                ),
            ).normalized()
            cdx_payload = [
                ["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
                ["20060102030405", "http://example.com/images/photo.jpg", "image/jpeg", "200", "ABC", "4"],
            ]
            with patch("archive_scout.cdx.client.HttpClient.get_json", return_value=cdx_payload):
                database = open_database(root)
                index_media(config, database, threading.Event())
                self.assertEqual(database.execute("SELECT COUNT(*) FROM media_captures").fetchone()[0], 1)
                with patch("archive_scout.cdx.client.HttpClient.get", return_value={
                    "data": b"JPEGDATA", "status": 200, "headers": {"Content-Type": "image/jpeg"},
                    "final_url": "https://web.archive.org/web/20060102030405id_/http://example.com/images/photo.jpg",
                }):
                    download_media(config, database, threading.Event())
                row = database.execute("SELECT state,path FROM media_captures").fetchone()
                self.assertEqual(row["state"], "downloaded")
                self.assertTrue(Path(row["path"]).exists())
                database.close()


if __name__ == "__main__":
    unittest.main()
