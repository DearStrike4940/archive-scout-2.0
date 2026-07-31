from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable

from ..content import parse_page
from ..database.repositories import get_or_create_target, upsert_document
from ..events import ProgressEvent, Stopped
from ..utils import hash_text, normalize_search, utc_now


def import_text_folder(
    root: Path,
    source_folder: Path,
    database: sqlite3.Connection,
    stop_event,
    callback: Callable[[ProgressEvent], None] | None = None,
) -> int:
    files = sorted(path for path in source_folder.rglob("*") if path.is_file() and path.suffix.lower() in {".txt", ".html", ".htm"})
    target_id = get_or_create_target(database, f"local-import:{source_folder}")
    imported = 0
    for index, path in enumerate(files, 1):
        if stop_event.is_set():
            raise Stopped
        raw = path.read_text(encoding="utf-8", errors="replace")
        original = f"file://{path.resolve()}"
        timestamp = path.stat().st_mtime_ns.__str__()[:14].ljust(14, "0")
        now = utc_now()
        cursor = database.execute(
            """
            INSERT OR IGNORE INTO captures(
                original_url,timestamp,target_id,query_signature,mimetype,state,created_at,updated_at
            ) VALUES(?,?,?,?,?,'downloaded',?,?)
            """,
            (original, timestamp, target_id, "local-import", "text/plain", now, now),
        )
        row = database.execute(
            "SELECT id FROM captures WHERE original_url=? AND timestamp=? AND query_signature='local-import'",
            (original, timestamp),
        ).fetchone()
        capture_id = int(row["id"])
        title, visible, links = parse_page(raw, original)
        upsert_document(
            database,
            capture_id,
            path,
            title,
            visible,
            links,
            hash_text(raw),
            hash_text(normalize_search(visible)),
            path.stat().st_size,
        )
        imported += int(cursor.rowcount > 0)
        if callback:
            callback(ProgressEvent("import", f"Imported {index:,}/{len(files):,}", index, len(files)))
    return imported
