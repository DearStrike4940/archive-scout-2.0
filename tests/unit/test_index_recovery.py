from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from archive_scout.cdx.client import TransientRequestError
from archive_scout.cdx.indexer import index_archive
from archive_scout.config import KeywordSetConfig, ProjectConfig
from archive_scout.database.connection import open_database
from archive_scout.database.repositories import get_or_create_target, upsert_captures
from archive_scout.events import Stopped
from archive_scout.operations import run_project


class IndexRecoveryTests(unittest.TestCase):
    def test_full_year_is_partitioned_into_months(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = ProjectConfig(
                output_dir=root,
                targets=["example.com/*"],
                keywords=["example"],
                from_date="2003",
                to_date="2003",
                cdx_delay=0,
            ).normalized()
            database = open_database(root)
            with patch("archive_scout.cdx.client.HttpClient.get_json", return_value=[]) as mocked:
                index_archive(config, database, threading.Event())
            self.assertEqual(mocked.call_count, 12)
            state = database.execute("SELECT complete,seen,resume_key FROM index_state").fetchone()
            self.assertEqual(state["complete"], 1)
            self.assertEqual(state["seen"], 0)
            self.assertIsNone(state["resume_key"])
            database.close()

    def test_timeout_is_split_into_smaller_windows_and_continues(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = ProjectConfig(
                output_dir=root,
                targets=["example.com/*"],
                keywords=["example"],
                from_date="200301",
                to_date="200301",
                cdx_delay=0,
                retries=1,
            ).normalized()
            database = open_database(root)
            timeout = TransientRequestError(
                "read operation timed out",
                timed_out=True,
                splittable=True,
            )
            with patch(
                "archive_scout.cdx.client.HttpClient.get_json",
                side_effect=[timeout, [], [], [], [], []],
            ) as mocked:
                index_archive(config, database, threading.Event())
            self.assertEqual(mocked.call_count, 6)
            state = database.execute("SELECT complete,resume_key FROM index_state").fetchone()
            self.assertEqual(state["complete"], 1)
            self.assertIsNone(state["resume_key"])
            self.assertEqual(database.execute("SELECT COUNT(*) FROM errors").fetchone()[0], 0)
            database.close()

    def test_split_window_plan_survives_stop_and_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = ProjectConfig(
                output_dir=root,
                targets=["example.com/*"],
                keywords=["example"],
                from_date="200301",
                to_date="200301",
                cdx_delay=0,
                retries=1,
            ).normalized()
            database = open_database(root)
            timeout = TransientRequestError(
                "read operation timed out",
                timed_out=True,
                splittable=True,
            )
            with patch(
                "archive_scout.cdx.client.HttpClient.get_json",
                side_effect=[timeout, Stopped()],
            ):
                with self.assertRaises(Stopped):
                    index_archive(config, database, threading.Event())
            state = database.execute("SELECT complete,resume_key FROM index_state").fetchone()
            self.assertEqual(state["complete"], 0)
            self.assertIn('"version":2', state["resume_key"])
            with patch("archive_scout.cdx.client.HttpClient.get_json", return_value=[]) as mocked:
                index_archive(config, database, threading.Event())
            self.assertEqual(mocked.call_count, 5)
            state = database.execute("SELECT complete,resume_key FROM index_state").fetchone()
            self.assertEqual(state["complete"], 1)
            self.assertIsNone(state["resume_key"])
            database.close()

    def test_failed_index_does_not_create_empty_scan_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = ProjectConfig(
                output_dir=root,
                targets=["example.com/*"],
                keywords=["example"],
                from_date="2003",
                to_date="2003",
                cdx_delay=0,
            )
            with patch(
                "archive_scout.cdx.client.HttpClient.get_json",
                side_effect=RuntimeError("simulated CDX failure"),
            ):
                with self.assertRaises(RuntimeError):
                    run_project(config, "all")
            database = open_database(root)
            self.assertEqual(database.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0], 0)
            self.assertEqual(database.execute("SELECT COUNT(*) FROM errors").fetchone()[0], 1)
            database.close()

    def test_stop_is_not_recorded_as_an_index_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = ProjectConfig(
                output_dir=root,
                targets=["example.com/*"],
                keywords=["example"],
                from_date="2003",
                to_date="2003",
            ).normalized()
            database = open_database(root)
            stop_event = threading.Event()
            stop_event.set()
            with self.assertRaises(Stopped):
                index_archive(config, database, stop_event)
            self.assertEqual(database.execute("SELECT COUNT(*) FROM errors").fetchone()[0], 0)
            database.close()

    def test_capture_rows_are_written_in_one_batch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            database = open_database(root)
            target_id = get_or_create_target(database, "example.com/*")
            rows = [
                {
                    "original": f"http://example.com/{index}",
                    "timestamp": f"20030101{index:06d}",
                    "mimetype": "text/html",
                    "statuscode": "200",
                    "digest": str(index),
                    "length": "100",
                }
                for index in range(1000)
            ]
            changed = upsert_captures(database, rows, target_id, "sig")
            self.assertEqual(changed, 1000)
            self.assertEqual(database.execute("SELECT COUNT(*) FROM captures").fetchone()[0], 1000)
            database.close()

    def test_identical_selected_keyword_sets_are_scanned_once(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            database = open_database(root)
            target_id = get_or_create_target(database, "example.com/*")
            row = {
                "original": "http://example.com/page",
                "timestamp": "20030101000000",
                "mimetype": "text/html",
                "statuscode": "200",
                "digest": "ABC",
                "length": "10",
            }
            upsert_captures(database, [row], target_id, "sig")
            capture_id = database.execute("SELECT id FROM captures").fetchone()[0]
            path = root / "page.txt"
            path.write_text("alpha", encoding="utf-8")
            from archive_scout.database.repositories import upsert_document
            from archive_scout.utils import hash_text, normalize_search
            upsert_document(
                database,
                capture_id,
                path,
                "",
                "alpha",
                [],
                hash_text("alpha"),
                hash_text(normalize_search("alpha")),
                5,
            )
            database.commit()
            database.close()
            config = ProjectConfig(
                output_dir=root,
                targets=[],
                keywords=[],
                keyword_sets=[
                    KeywordSetConfig("One", ["alpha"], True),
                    KeywordSetConfig("Duplicate", ["alpha"], True),
                ],
                from_date="2003",
                to_date="2003",
            )
            run_project(config, "rescan")
            database = open_database(root)
            self.assertEqual(database.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0], 1)
            database.close()


if __name__ == "__main__":
    unittest.main()
