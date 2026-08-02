from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from archive_scout.config import KeywordSetConfig, MediaConfig, ProjectConfig, load_project_config, save_project_config


class Alpha2ConfigTests(unittest.TestCase):
    def test_multiple_keyword_sets_and_media_round_trip(self):
        with tempfile.TemporaryDirectory() as temp:
            config = ProjectConfig(
                output_dir=Path(temp),
                targets=["example.com/*"],
                keywords=[],
                keyword_sets=[
                    KeywordSetConfig("General", ["WTC", "jumper"], True),
                    KeywordSetConfig("Media", ["exact: skylight.mov"], False),
                ],
                retry_media_capture_ids=[7, 9],
                rate_limit_base_pause=45,
                rate_limit_max_pause=240,
                rate_limit_max_wait=900,
                rate_limit_attempts=10,
                media=MediaConfig(
                    enabled=True,
                    targets=["media.example.com/*"],
                    include_extensions=["jpg", ".mp4", ".gif"],
                    exclude_extensions=["gif"],
                    snapshot_strategy="latest",
                ),
            )
            path = save_project_config(config)
            loaded = load_project_config(path)
            self.assertEqual(len(loaded.normalized_keyword_sets()), 2)
            self.assertEqual([item.name for item in loaded.selected_keyword_sets()], ["General"])
            self.assertEqual(loaded.media.targets, ["media.example.com/*"])
            self.assertEqual(loaded.media.snapshot_strategy, "latest")
            self.assertIn(".mp4", loaded.media.include_extensions)
            self.assertIn(".gif", loaded.media.exclude_extensions)
            self.assertEqual(loaded.retry_media_capture_ids, [7, 9])
            self.assertEqual(loaded.rate_limit_base_pause, 45)
            self.assertEqual(loaded.rate_limit_max_pause, 240)
            self.assertEqual(loaded.rate_limit_max_wait, 900)
            self.assertEqual(loaded.rate_limit_attempts, 10)


if __name__ == "__main__":
    unittest.main()
