from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from archive_scout.config import MediaConfig, ProjectConfig
from archive_scout.database.connection import open_database
from archive_scout.database.repositories import record_error, upsert_media_capture
from archive_scout.media.downloader import retry_media_errors


class Alpha2MediaRetryTests(unittest.TestCase):
    def test_retry_can_be_limited_to_selected_media_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = ProjectConfig(
                output_dir=root,
                targets=["example.com/*"],
                keywords=["example"],
                media=MediaConfig(targets=["example.com/*"], include_extensions=["jpg"]),
            ).normalized()
            database = open_database(root)
            for timestamp, name in (("20060101000000", "one.jpg"), ("20060102000000", "two.jpg")):
                upsert_media_capture(database, {
                    "original": f"http://example.com/{name}", "timestamp": timestamp,
                    "mimetype": "image/jpeg", "statuscode": "200", "digest": "", "length": "10",
                }, None, "sig", "image", ".jpg")
            ids = [int(row[0]) for row in database.execute("SELECT id FROM media_captures ORDER BY id")]
            for media_id in ids:
                record_error(database, "media_download", "timeout", "timeout", media_capture_id=media_id)
                database.execute("UPDATE media_captures SET state='error' WHERE id=?", (media_id,))
            database.commit()
            with patch("archive_scout.media.downloader.download_media") as mocked:
                retry_media_errors(config, database, threading.Event(), media_capture_ids=[ids[1]])
                self.assertEqual(mocked.call_args.kwargs["media_capture_ids"], [ids[1]])
            database.close()


if __name__ == "__main__":
    unittest.main()
