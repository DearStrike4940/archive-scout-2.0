from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Callable

from ..content import parse_page
from ..database.repositories import record_error, resolve_errors, save_match, upsert_document
from ..events import ProgressEvent, Stopped
from ..utils import hash_text, normalize_search
from .keywords import compile_keywords
from .scoring import analyze_content


def rescan_documents(
    database: sqlite3.Connection,
    scan_run_id: int,
    keywords: list[str],
    stop_event: threading.Event,
    callback: Callable[[ProgressEvent], None] | None = None,
    document_ids: list[int] | None = None,
) -> None:
    patterns = compile_keywords(keywords)
    if not patterns:
        raise ValueError("at least one keyword is required")
    if document_ids:
        placeholders = ",".join("?" for _ in document_ids)
        rows = database.execute(
            f"""
            SELECT d.*,c.original_url,c.id AS capture_id FROM documents d
            JOIN captures c ON c.id=d.capture_id
            WHERE d.id IN ({placeholders}) ORDER BY d.id
            """,
            document_ids,
        ).fetchall()
    else:
        rows = database.execute(
            """
            SELECT d.*,c.original_url,c.id AS capture_id FROM documents d
            JOIN captures c ON c.id=d.capture_id ORDER BY d.id
            """
        ).fetchall()
    total = len(rows)
    for index, row in enumerate(rows, 1):
        if stop_event.is_set():
            raise Stopped
        path = Path(row["path"])
        if not path.exists():
            with database:
                record_error(
                    database,
                    "scan",
                    "missing_local_file",
                    f"saved file is missing: {path}",
                    capture_id=int(row["capture_id"]),
                    document_id=int(row["id"]),
                    retryable=True,
                )
                database.execute("UPDATE captures SET state='error' WHERE id=?", (row["capture_id"],))
            if callback:
                callback(ProgressEvent("rescan", f"Missing local file {index:,}/{total:,}", index, total))
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
            title, visible, links = parse_page(raw, row["original_url"])
            analysis = analyze_content(row["original_url"], title, visible, raw, links, patterns)
            with database:
                upsert_document(
                    database,
                    int(row["capture_id"]),
                    path,
                    title,
                    visible,
                    links,
                    hash_text(raw),
                    hash_text(normalize_search(visible)),
                    path.stat().st_size,
                )
                save_match(database, scan_run_id, int(row["id"]), analysis)
                resolve_errors(
                    database,
                    capture_id=int(row["capture_id"]),
                    document_id=int(row["id"]),
                    operations=("scan", "parse"),
                )
        except Exception as exc:
            with database:
                record_error(
                    database,
                    "scan",
                    "scan_failure",
                    repr(exc),
                    capture_id=int(row["capture_id"]),
                    document_id=int(row["id"]),
                    retryable=True,
                )
        if callback:
            callback(ProgressEvent("rescan", f"Rescanned {index:,}/{total:,}", index, total))
