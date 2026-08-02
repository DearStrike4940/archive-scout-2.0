from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from archive_scout.cdx.client import TransientRequestError
from archive_scout.cdx.indexer import index_archive
from archive_scout.config import ProjectConfig
from archive_scout.database.connection import open_database


class Alpha3TimeoutRecoveryTests(unittest.TestCase):
    def test_one_hour_timeout_is_split_and_does_not_interrupt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = ProjectConfig(
                output_dir=root,
                targets=["flashback.org/*"],
                keywords=["x"],
                from_date="20010912000000",
                to_date="20010912005959",
                cdx_delay=0,
                retries=1,
            ).normalized()
            database = open_database(root)
            timeout = TransientRequestError("read timeout", timed_out=True, splittable=True)
            with patch(
                "archive_scout.cdx.client.HttpClient.get_json",
                side_effect=[timeout, [], [], [], []],
            ) as mocked:
                index_archive(config, database, threading.Event())
            self.assertEqual(mocked.call_count, 5)
            state = database.execute("SELECT complete,resume_key FROM index_state").fetchone()
            self.assertEqual(state["complete"], 1)
            self.assertIsNone(state["resume_key"])
            database.close()

    def test_one_second_timeout_retries_until_success(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = ProjectConfig(
                output_dir=root,
                targets=["example.com/*"],
                keywords=["x"],
                from_date="20010912010101",
                to_date="20010912010101",
                cdx_delay=0,
                retries=1,
            ).normalized()
            database = open_database(root)
            timeout = TransientRequestError("read timeout", timed_out=True, splittable=True)
            with patch("archive_scout.cdx.client.HttpClient.get_json", side_effect=[timeout, []]) as mocked, patch(
                "archive_scout.cdx.indexer.transient_backoff", return_value=0
            ):
                index_archive(config, database, threading.Event())
            self.assertEqual(mocked.call_count, 2)
            state = database.execute("SELECT complete,resume_key FROM index_state").fetchone()
            self.assertEqual(state["complete"], 1)
            self.assertIsNone(state["resume_key"])
            database.close()


if __name__ == "__main__":
    unittest.main()
