from __future__ import annotations

import unittest

from archive_scout.scanning.keywords import compile_keywords, parse_keyword_rules
from archive_scout.scanning.scoring import analyze_content


class Alpha2KeywordTests(unittest.TestCase):
    def test_rule_parser_supports_types_and_options(self):
        rules = parse_keyword_rules([
            "required: World Trade Center | weight=2 | whole",
            "exclude: base jumping",
            "high: jumper",
            "regex: sky(light|line)\\.mov | label=media filename",
        ])
        self.assertEqual(rules[0].kind, "required")
        self.assertEqual(rules[0].weight, 2)
        self.assertTrue(rules[0].whole_word)
        self.assertEqual(rules[1].kind, "excluded")
        self.assertEqual(rules[2].weight, 3)
        self.assertEqual(rules[3].kind, "regex")
        self.assertEqual(rules[3].label, "media filename")

    def test_required_and_excluded_rules_control_results(self):
        patterns = compile_keywords(["required: WTC", "high: jumper", "exclude: stock market"])
        missing = analyze_content("http://example.com", "", "jumper footage", "jumper footage", [], patterns)
        excluded = analyze_content("http://example.com", "", "WTC jumper stock market", "WTC jumper stock market", [], patterns)
        good = analyze_content("http://example.com", "", "WTC jumper impact footage", "WTC jumper impact footage", [], patterns)
        self.assertTrue(missing["required_missing"])
        self.assertEqual(missing["score"], 0)
        self.assertTrue(excluded["excluded"])
        self.assertEqual(excluded["score"], 0)
        self.assertGreater(good["score"], 0)

    def test_proximity_scores_close_terms_higher(self):
        patterns = compile_keywords(["WTC", "jumper"])
        close = analyze_content("http://example.com", "", "WTC jumper impact footage", "WTC jumper impact footage", [], patterns)
        far = analyze_content("http://example.com", "", "WTC " + "word " * 100 + "jumper", "WTC " + "word " * 100 + "jumper", [], patterns)
        self.assertGreater(close["score"], far["score"])


if __name__ == "__main__":
    unittest.main()
