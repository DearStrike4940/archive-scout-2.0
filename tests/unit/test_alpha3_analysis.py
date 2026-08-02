from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from archive_scout.analysis.diffs import build_first_appearances, compare_snapshots
from archive_scout.analysis.duplicates import cluster_duplicates
from archive_scout.database.connection import open_database
from archive_scout.database.repositories import get_or_create_target, upsert_captures, upsert_document
from archive_scout.extraction.provenance import trace_provenance
from archive_scout.utils import hash_text, normalize_search


class Alpha3AnalysisTests(unittest.TestCase):
    def _document(self, database, root, target_id, url, timestamp, text, suffix):
        row = {
            "original": url,
            "timestamp": timestamp,
            "mimetype": "text/html",
            "statuscode": "200",
            "digest": suffix,
            "length": str(len(text)),
        }
        upsert_captures(database, [row], target_id, "sig")
        capture_id = database.execute(
            "SELECT id FROM captures WHERE original_url=? AND timestamp=?", (url, timestamp)
        ).fetchone()[0]
        path = root / f"{suffix}.html"
        path.write_text(text, encoding="utf-8")
        return upsert_document(
            database,
            capture_id,
            path,
            "Title",
            text,
            [],
            hash_text(text),
            hash_text(normalize_search(text)),
            len(text),
        )

    def test_duplicates_provenance_diffs_and_first_appearance(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            database = open_database(root)
            target = get_or_create_target(database, "example.com/*")
            self._document(database, root, target, "http://example.com/a", "20010101000000", "alpha beta gamma delta", "a1")
            self._document(database, root, target, "http://mirror.net/a", "20020101000000", "alpha beta gamma delta", "a2")
            self._document(database, root, target, "http://example.com/page", "20010101000000", "old text", "p1")
            self._document(database, root, target, "http://example.com/page", "20020101000000", "old text NEW-ID", "p2")
            database.commit()

            duplicates = cluster_duplicates(database, 0.90)
            self.assertGreaterEqual(duplicates.exact_groups, 1)
            self.assertGreaterEqual(trace_provenance(database), 1)
            diffs = compare_snapshots(database)
            self.assertGreaterEqual(diffs.compared_pairs, 1)
            self.assertEqual(build_first_appearances(database, ["NEW-ID"]), 1)
            first = database.execute("SELECT first_timestamp FROM first_appearances WHERE query='NEW-ID'").fetchone()
            self.assertEqual(first["first_timestamp"], "20020101000000")
            database.close()


if __name__ == "__main__":
    unittest.main()
