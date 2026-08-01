from __future__ import annotations

import csv
import json
import sqlite3
import zipfile
from pathlib import Path

from ..database.repositories import result_rows
from ..downloads.downloader import replay_url
from ..utils import atomic_write_text, json_value


def export_scan(
    database: sqlite3.Connection,
    scan_run_id: int,
    destination: Path,
    format_name: str,
    review_status: str = "",
    minimum_score: int = 0,
    search: str = "",
) -> Path:
    rows = result_rows(database, scan_run_id, minimum_score, review_status, search, limit=1_000_000)
    destination.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for row in rows:
        records.append({
            "match_id": row["id"],
            "score": row["score"],
            "review_status": row["review_status"],
            "title": row["title"] or "",
            "timestamp": row["timestamp"],
            "original_url": row["original_url"],
            "wayback_url": replay_url(row["timestamp"], row["original_url"]),
            "local_file": row["path"],
            "hits": json_value(row["hits_json"], {}),
            "snippets": json_value(row["snippets_json"], []),
            "note": row["note"],
            "tags": row["tags"],
        })
    format_name = format_name.casefold()
    if format_name == "json":
        atomic_write_text(destination, json.dumps(records, indent=2, ensure_ascii=False) + "\n")
    elif format_name == "csv":
        with destination.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=[
                "match_id", "score", "review_status", "title", "timestamp", "original_url", "wayback_url",
                "local_file", "hits", "snippets", "note", "tags"
            ])
            writer.writeheader()
            for record in records:
                record = dict(record)
                record["hits"] = json.dumps(record["hits"], ensure_ascii=False)
                record["snippets"] = json.dumps(record["snippets"], ensure_ascii=False)
                writer.writerow(record)
    elif format_name in {"md", "markdown"}:
        blocks = []
        for index, record in enumerate(records, 1):
            blocks.append("\n".join([
                f"## {index}. {record['title'] or '(untitled)'}",
                f"- Score: {record['score']}",
                f"- Review: {record['review_status']}",
                f"- Timestamp: {record['timestamp']}",
                f"- Original: {record['original_url']}",
                f"- Wayback: {record['wayback_url']}",
                f"- Tags: {record['tags'] or '(none)'}",
                f"- Note: {record['note'] or '(none)'}",
                "",
                "Snippets:",
                *[f"- {snippet}" for snippet in record["snippets"]],
            ]))
        atomic_write_text(destination, "# Archive Scout review export\n\n" + "\n\n".join(blocks) + "\n")
    else:
        raise ValueError(f"unsupported export format: {format_name}")
    return destination


def export_review_package(
    database: sqlite3.Connection,
    scan_run_id: int,
    destination: Path,
    review_status: str = "",
    minimum_score: int = 0,
    search: str = "",
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    base = destination.with_suffix("")
    json_path = base.with_suffix(".json")
    csv_path = base.with_suffix(".csv")
    md_path = base.with_suffix(".md")
    export_scan(database, scan_run_id, json_path, "json", review_status, minimum_score, search)
    export_scan(database, scan_run_id, csv_path, "csv", review_status, minimum_score, search)
    export_scan(database, scan_run_id, md_path, "markdown", review_status, minimum_score, search)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in (json_path, csv_path, md_path):
            archive.write(path, path.name)
    for path in (json_path, csv_path, md_path):
        path.unlink(missing_ok=True)
    return destination
