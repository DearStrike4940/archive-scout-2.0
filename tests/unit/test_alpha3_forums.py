from __future__ import annotations

import unittest

from archive_scout.parsing.forums import canonicalize_forum_url, parse_forum_posts


class Alpha3ForumTests(unittest.TestCase):
    def test_canonicalization_removes_pagination_and_post_anchor(self):
        key, url = canonicalize_forum_url("https://web.archive.org/web/20060101000000/http://example.com/showthread.php?t=55&page=3#post99")
        self.assertEqual(key, "example.com|thread:55")
        self.assertEqual(url, "http://example.com/showthread.php?t=55")

    def test_generic_forum_posts_are_reconstructed(self):
        raw = """
        <html><title>Thread title</title>
        <div id="post_10" class="post"><span class="username">Alice</span><time>2005-01-01</time><div class="postbody">Hello world</div></div>
        <div id="post_11" class="post"><span class="username">Bob</span><div class="postbody">Second post</div></div>
        </html>
        """
        thread = parse_forum_posts(raw, "http://example.com/showthread.php?t=55&page=2")
        self.assertEqual(thread.canonical_key, "example.com|thread:55")
        self.assertEqual(thread.title, "Thread title")
        self.assertEqual(len(thread.posts), 2)
        self.assertEqual(thread.posts[0].post_key, "10")
        self.assertIn("Hello world", thread.posts[0].body_text)


if __name__ == "__main__":
    unittest.main()
