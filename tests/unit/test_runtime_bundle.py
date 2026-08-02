from __future__ import annotations

import sys
import tempfile
import unittest
import threading
import urllib.error
from pathlib import Path
from unittest.mock import patch

from archive_scout.cdx.client import HttpClient
from archive_scout.downloads.rate_limit import FixedRateLimiter

from archive_scout.runtime import (
    FrozenBundleError,
    ensure_frozen_bundle_available,
    is_missing_frozen_bundle_error,
)


class RuntimeBundleTests(unittest.TestCase):
    def test_non_frozen_runtime_is_accepted(self):
        with patch.object(sys, "frozen", False, create=True):
            ensure_frozen_bundle_available()

    def test_missing_base_library_is_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app = root / "Archive Scout.app"
            frameworks = app / "Contents" / "Frameworks"
            executable = app / "Contents" / "MacOS" / "Archive Scout"
            frameworks.mkdir(parents=True)
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"launcher")
            with patch.object(sys, "frozen", True, create=True), patch.object(
                sys, "_MEIPASS", str(frameworks), create=True
            ), patch.object(sys, "executable", str(executable)), patch.object(sys, "platform", "darwin"):
                with self.assertRaises(FrozenBundleError) as raised:
                    ensure_frozen_bundle_available()
            self.assertIn("base_library.zip", str(raised.exception))
            self.assertIn("/Applications", str(raised.exception))

    def test_present_base_library_is_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app = root / "Archive Scout.app"
            frameworks = app / "Contents" / "Frameworks"
            executable = app / "Contents" / "MacOS" / "Archive Scout"
            frameworks.mkdir(parents=True)
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"launcher")
            (frameworks / "base_library.zip").write_bytes(b"zip")
            with patch.object(sys, "frozen", True, create=True), patch.object(
                sys, "_MEIPASS", str(frameworks), create=True
            ), patch.object(sys, "executable", str(executable)), patch.object(sys, "platform", "darwin"):
                ensure_frozen_bundle_available()

    def test_nested_url_error_identifies_missing_base_library(self):
        missing = FileNotFoundError(2, "No such file", "/tmp/App.app/Contents/Frameworks/base_library.zip")
        wrapped = urllib.error.URLError(missing)
        self.assertTrue(is_missing_frozen_bundle_error(wrapped))

    def test_unrelated_file_error_is_not_bundle_failure(self):
        missing = FileNotFoundError(2, "No such file", "/tmp/project.json")
        self.assertFalse(is_missing_frozen_bundle_error(missing))

    def test_http_client_does_not_retry_missing_bundle_as_network_failure(self):
        missing = FileNotFoundError(2, "No such file", "/tmp/App.app/Contents/Frameworks/base_library.zip")
        wrapped = urllib.error.URLError(missing)
        client = HttpClient(
            FixedRateLimiter(0),
            retries=3,
            timeout=1,
            user_agent="test",
            stop_event=threading.Event(),
        )
        with patch("archive_scout.cdx.client.ensure_frozen_bundle_available"), patch(
            "archive_scout.cdx.client.urllib.request.urlopen", side_effect=wrapped
        ) as mocked:
            with self.assertRaises(FrozenBundleError):
                client.get("https://example.com", 1024)
        self.assertEqual(mocked.call_count, 1)


if __name__ == "__main__":
    unittest.main()
