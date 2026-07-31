from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Callable

from ..config import ProjectConfig
from ..events import ProgressEvent
from ..scanning.rescanner import rescan_documents
from .downloader import download_archive


def retry_error_urls(
    config: ProjectConfig,
    database: sqlite3.Connection,
    scan_run_id: int,
    stop_event: threading.Event,
    callback: Callable[[ProgressEvent], None] | None,
) -> None:
    rows = database.execute(
        """
        SELECT
            e.capture_id,
            MAX(e.document_id) AS document_id,
            GROUP_CONCAT(DISTINCT e.operation) AS operations,
            MAX(d.path) AS path
        FROM errors e
        LEFT JOIN documents d ON d.id=e.document_id
        WHERE e.resolved=0 AND e.retryable=1 AND e.capture_id IS NOT NULL
        GROUP BY e.capture_id
        ORDER BY e.capture_id
        """
    ).fetchall()
    local_document_ids: list[int] = []
    download_capture_ids: list[int] = []
    for row in rows:
        capture_id = int(row["capture_id"])
        document_id = int(row["document_id"]) if row["document_id"] is not None else None
        path = Path(row["path"]) if row["path"] else None
        operations = {value for value in str(row["operations"] or "").split(",") if value}
        if document_id and path and path.exists() and operations and operations.issubset({"scan", "parse"}):
            local_document_ids.append(document_id)
        else:
            download_capture_ids.append(capture_id)
    if callback:
        callback(
            ProgressEvent(
                "retry",
                f"Retrying {len(download_capture_ids):,} downloads and {len(local_document_ids):,} local scans",
            )
        )
    if local_document_ids:
        rescan_documents(database, scan_run_id, config.keywords, stop_event, callback, local_document_ids)
    if download_capture_ids:
        download_archive(
            config,
            database,
            scan_run_id,
            stop_event,
            callback,
            states=("error", "pending", "downloaded"),
            capture_ids=download_capture_ids,
        )

