from __future__ import annotations

import unittest

from archive_scout.extraction.regex import parse_extractor_rules, run_extractors
from archive_scout.parsing.embeds import extract_embed_candidates


class Alpha3ExtractionTests(unittest.TestCase):
    def test_builtin_and_custom_identifier_extraction(self):
        fields = {
            "url": "http://video.google.com/videoplay?docid=-123456789",
            "body": "Mirror code ABC-999 and viploader12345",
            "title": "",
            "source": "",
            "links": "",
        }
        custom = parse_extractor_rules([r"mirror_code :: body :: (ABC-\d+)"])
        hits = run_extractors(fields, custom)
        pairs = {(hit.name, hit.value) for hit in hits}
        self.assertIn(("google_video_docid", "-123456789"), pairs)
        self.assertIn(("legacy_uploader_id", "viploader12345"), pairs)
        self.assertIn(("mirror_code", "ABC-999"), pairs)

    def test_legacy_embed_recovery_detects_players_and_script_urls(self):
        raw = """
        <object classid="clsid:6BF52A52"><param name="URL" value="movie.wmv"></object>
        <embed src="player.swf" type="application/x-shockwave-flash">
        <script>var file = 'https://cdn.example.net/video.flv';</script>
        """
        items = extract_embed_candidates(raw, "http://example.com/thread/")
        urls = {item.url for item in items}
        self.assertIn("http://example.com/thread/movie.wmv", urls)
        self.assertIn("http://example.com/thread/player.swf", urls)
        self.assertIn("https://cdn.example.net/video.flv", urls)
        self.assertTrue(any(item.player == "Windows Media Player" for item in items))
        self.assertTrue(any(item.player == "Adobe Flash" for item in items))


if __name__ == "__main__":
    unittest.main()
