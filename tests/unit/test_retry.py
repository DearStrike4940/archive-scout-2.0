from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from archive_scout.config import ProjectConfig
from archive_scout.database.connection import open_database
from archive_scout.database.repositories import get_or_create_target, record_error, upsert_capture, upsert_document
from archive_scout.downloads.retry import retry_error_urls
from archive_scout.utils import hash_text, normalize_search


class RetryTests(unittest.TestCase):
    def test_retry_splits_local_scan_errors_from_download_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            database = open_database(root)
            target_id = get_or_create_target(database, "example.com/*")
            for index in (1, 2):
                upsert_capture(
                    database,
                    {
                        "original": f"http://example.com/{index}",
                        "timestamp": f"2006010100000{index}",
                        "mimetype": "text/html",
                        "statuscode": "200",
                        "digest": "",
                        "length": "10",
                    },
                    target_id,
                    "sig",
                )
            rows = database.execute("SELECT id FROM captures ORDER BY id").fetchall()
            local_path = root / "local.txt"
            local_path.write_text("alpha", encoding="utf-8")
            document_id = upsert_document(
                database,
                rows[0]["id"],
                local_path,
                "",
                "alpha",
                [],
                hash_text("alpha"),
                hash_text(normalize_search("alpha")),
                local_path.stat().st_size,
            )
            record_error(database, "scan", "scan_failure", "bad scan", capture_id=rows[0]["id"], document_id=document_id)
            record_error(database, "download", "timeout", "timed out", capture_id=rows[1]["id"])
            config = ProjectConfig(output_dir=root, targets=["example.com/*"], keywords=["alpha"])
            captured = {"documents": [], "captures": []}

            def fake_rescan(database, scan_run_id, keywords, stop_event, callback, document_ids):
                captured["documents"].extend(document_ids)

            def fake_download(config, database, scan_run_id, stop_event, callback, states, capture_ids):
                captured["captures"].extend(capture_ids)

            with patch("archive_scout.downloads.retry.rescan_documents", fake_rescan), patch(
                "archive_scout.downloads.retry.download_archive", fake_download
            ):
                retry_error_urls(config, database, 1, threading.Event(), None)
            self.assertEqual(captured["documents"], [document_id])
            self.assertEqual(captured["captures"], [rows[1]["id"]])
            database.close()


if __name__ == "__main__":
    unittest.main()
