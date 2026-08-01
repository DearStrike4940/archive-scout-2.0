from __future__ import annotations

import sqlite3
from pathlib import Path

from ..config import ProjectConfig
from ..downloads.downloader import replay_url
from ..utils import atomic_write_text, utc_now


def generate_media_reports(config: ProjectConfig, database: sqlite3.Connection) -> dict[str, Path]:
    rows = database.execute("SELECT * FROM media_captures ORDER BY media_kind,original_url,timestamp").fetchall()
    errors = database.execute(
        """
        SELECT e.*,mc.original_url,mc.timestamp FROM errors e
        JOIN media_captures mc ON mc.id=e.media_capture_id
        WHERE e.resolved=0 AND e.ignored=0 ORDER BY e.last_seen,e.id
        """
    ).fetchall()
    reports = config.output_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    indexed = "\n".join(
        f"{row['timestamp']}\t{row['media_kind']}\t{row['extension'] or ''}\t{row['state']}\t{row['original_url']}"
        for row in rows
    )
    downloaded = "\n".join(
        f"{row['timestamp']}\t{row['media_kind']}\t{row['bytes_saved']}\t{row['path']}\t{row['original_url']}"
        for row in rows if row["state"] == "downloaded"
    )
    wayback = "\n".join(replay_url(row["timestamp"], row["original_url"]) for row in rows)
    error_text = "\n".join(
        f"{row['last_seen']}\t{row['category']}\t{row['attempt_count']}\t{row['timestamp']}\t{row['original_url']}\t{row['message']}"
        for row in errors
    )
    counts = dict(database.execute("SELECT state,COUNT(*) FROM media_captures GROUP BY state").fetchall())
    summary = "\n".join([
        "Archive Scout media report",
        f"Generated: {utc_now()}",
        f"Indexed media captures: {len(rows):,}",
        f"Downloaded: {counts.get('downloaded', 0):,}",
        f"Pending: {counts.get('pending', 0):,}",
        f"Errors: {counts.get('error', 0):,}",
        f"Unresolved media errors: {len(errors):,}",
        f"Snapshot strategy: {config.media.snapshot_strategy}",
        f"Included extensions: {', '.join(config.media.include_extensions)}",
        f"Excluded extensions: {', '.join(config.media.exclude_extensions) or '(none)'}",
    ]) + "\n"
    contents = {
        "media_indexed.txt": indexed + ("\n" if indexed else ""),
        "media_downloaded.txt": downloaded + ("\n" if downloaded else ""),
        "media_wayback_urls.txt": wayback + ("\n" if wayback else ""),
        "media_errors.txt": error_text + ("\n" if error_text else ""),
        "media_summary.txt": summary,
    }
    paths: dict[str, Path] = {}
    for name, text in contents.items():
        path = reports / name
        atomic_write_text(path, text)
        paths[name.removesuffix(".txt")] = path
    return paths
