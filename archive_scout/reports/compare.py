from __future__ import annotations

import sqlite3
from pathlib import Path

from ..utils import atomic_write_text, utc_now


def _run_label(database: sqlite3.Connection, scan_run_id: int) -> str:
    row = database.execute(
        """
        SELECT sr.name,ks.name AS keyword_set_name
        FROM scan_runs sr JOIN keyword_sets ks ON ks.id=sr.keyword_set_id
        WHERE sr.id=?
        """,
        (scan_run_id,),
    ).fetchone()
    if not row:
        raise ValueError(f"scan run {scan_run_id} does not exist")
    return f"{scan_run_id} — {row['name']} — {row['keyword_set_name']}"


def _rows(database: sqlite3.Connection, scan_run_id: int) -> dict[int, sqlite3.Row]:
    rows = database.execute(
        """
        SELECT m.document_id,m.score,m.hits_json,m.excluded,m.required_missing,
               d.title,c.original_url,c.timestamp,
               COALESCE(r.status,'unreviewed') AS review_status
        FROM document_matches m
        JOIN documents d ON d.id=m.document_id
        JOIN captures c ON c.id=d.capture_id
        LEFT JOIN reviews r ON r.match_id=m.id
        WHERE m.scan_run_id=?
        """,
        (scan_run_id,),
    ).fetchall()
    return {int(row["document_id"]): row for row in rows}


def generate_scan_comparison(
    database: sqlite3.Connection,
    first_scan_id: int,
    second_scan_id: int,
    destination: Path,
) -> Path:
    if first_scan_id == second_scan_id:
        raise ValueError("select two different scan runs")
    first = _rows(database, first_scan_id)
    second = _rows(database, second_scan_id)
    shared = sorted(set(first) & set(second))
    only_first = sorted(set(first) - set(second))
    only_second = sorted(set(second) - set(first))
    changed = sorted(
        shared,
        key=lambda document_id: abs(int(second[document_id]["score"]) - int(first[document_id]["score"])),
        reverse=True,
    )
    lines = [
        "Archive Scout scan comparison",
        f"Generated: {utc_now()}",
        f"First: {_run_label(database, first_scan_id)}",
        f"Second: {_run_label(database, second_scan_id)}",
        f"Documents in both: {len(shared):,}",
        f"Only in first: {len(only_first):,}",
        f"Only in second: {len(only_second):,}",
        "",
        "SCORE CHANGES",
    ]
    for document_id in changed:
        left = first[document_id]
        right = second[document_id]
        delta = int(right["score"]) - int(left["score"])
        lines.append(
            "\t".join(
                [
                    f"delta={delta:+d}",
                    f"first={left['score']}",
                    f"second={right['score']}",
                    left["timestamp"],
                    left["original_url"],
                    left["title"] or "(untitled)",
                ]
            )
        )
    lines.extend(["", "ONLY IN FIRST"])
    for document_id in only_first:
        row = first[document_id]
        lines.append(f"{row['score']}\t{row['timestamp']}\t{row['original_url']}\t{row['title'] or '(untitled)'}")
    lines.extend(["", "ONLY IN SECOND"])
    for document_id in only_second:
        row = second[document_id]
        lines.append(f"{row['score']}\t{row['timestamp']}\t{row['original_url']}\t{row['title'] or '(untitled)'}")
    atomic_write_text(destination, "\n".join(lines) + "\n")
    return destination
