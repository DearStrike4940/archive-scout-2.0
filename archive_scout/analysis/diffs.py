from __future__ import annotations

import difflib
import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass

from ..utils import clean_space, utc_now


@dataclass(slots=True)
class DiffSummary:
    compared_pairs: int = 0
    changed_pairs: int = 0
    first_appearances: int = 0


def _summary(earlier: str, later: str) -> dict:
    earlier_lines = [clean_space(line) for line in earlier.splitlines() if clean_space(line)]
    later_lines = [clean_space(line) for line in later.splitlines() if clean_space(line)]
    matcher = difflib.SequenceMatcher(None, earlier, later, autojunk=False)
    earlier_set = set(earlier_lines)
    later_set = set(later_lines)
    added = sorted(later_set - earlier_set)
    removed = sorted(earlier_set - later_set)
    return {
        "similarity": round(matcher.ratio(), 6),
        "earlier_chars": len(earlier),
        "later_chars": len(later),
        "added_lines": added[:200],
        "removed_lines": removed[:200],
        "added_count": len(added),
        "removed_count": len(removed),
    }


def compare_snapshots(database: sqlite3.Connection) -> DiffSummary:
    rows = database.execute(
        """
        SELECT c.id AS capture_id,c.original_url,c.timestamp,d.body_text
        FROM captures c JOIN documents d ON d.id=c.document_id
        WHERE c.state='downloaded'
        ORDER BY c.original_url,c.timestamp,c.id
        """
    ).fetchall()
    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        grouped[str(row["original_url"])].append(row)
    summary = DiffSummary()
    with database:
        database.execute("DELETE FROM snapshot_diffs")
        for items in grouped.values():
            for earlier, later in zip(items, items[1:]):
                result = _summary(str(earlier["body_text"] or ""), str(later["body_text"] or ""))
                database.execute(
                    """
                    INSERT INTO snapshot_diffs(earlier_capture_id,later_capture_id,summary_json,created_at)
                    VALUES(?,?,?,?)
                    ON CONFLICT(earlier_capture_id,later_capture_id) DO UPDATE SET
                        summary_json=excluded.summary_json,created_at=excluded.created_at
                    """,
                    (earlier["capture_id"], later["capture_id"], json.dumps(result, ensure_ascii=False), utc_now()),
                )
                summary.compared_pairs += 1
                if result["similarity"] < 0.999999:
                    summary.changed_pairs += 1
    return summary


def build_first_appearances(database: sqlite3.Connection, queries: list[str]) -> int:
    queries = list(dict.fromkeys(value.strip() for value in queries if value.strip()))
    if not queries:
        return 0
    rows = database.execute(
        """
        SELECT c.id AS capture_id,c.original_url,c.timestamp,d.title,d.body_text,d.links_json
        FROM captures c JOIN documents d ON d.id=c.document_id
        ORDER BY c.original_url,c.timestamp,c.id
        """
    ).fetchall()
    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        grouped[str(row["original_url"])].append(row)
    count = 0
    with database:
        database.execute("DELETE FROM first_appearances")
        for original_url, items in grouped.items():
            for query in queries:
                needle = query.casefold()
                matching = [
                    row for row in items
                    if needle in (" ".join((str(row["title"] or ""), str(row["body_text"] or ""), str(row["links_json"] or "")))).casefold()
                ]
                if not matching:
                    continue
                first, last = matching[0], matching[-1]
                database.execute(
                    """
                    INSERT INTO first_appearances(query,original_url,first_capture_id,first_timestamp,last_capture_id,last_timestamp,created_at)
                    VALUES(?,?,?,?,?,?,?)
                    """,
                    (query, original_url, first["capture_id"], first["timestamp"], last["capture_id"], last["timestamp"], utc_now()),
                )
                count += 1
    return count
