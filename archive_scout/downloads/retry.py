from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Callable

from ..config import ProjectConfig
from ..events import ProgressEvent
from ..scanning.jobs import ScanJob
from ..scanning.rescanner import rescan_documents, rescan_keyword_sets
from .downloader import download_archive


def retry_error_urls(
    config: ProjectConfig,
    database: sqlite3.Connection,
    scan_run_id: int,
    stop_event: threading.Event,
    callback: Callable[[ProgressEvent], None] | None,
    scan_jobs: list[ScanJob] | None = None,
) -> None:
    clauses = ["e.resolved=0", "e.ignored=0", "e.retryable=1", "e.capture_id IS NOT NULL"]
    params: list[object] = []
    if config.retry_error_categories:
        clauses.append("e.category IN (" + ",".join("?" for _ in config.retry_error_categories) + ")")
        params.extend(config.retry_error_categories)
    if config.retry_capture_ids:
        clauses.append("e.capture_id IN (" + ",".join("?" for _ in config.retry_capture_ids) + ")")
        params.extend(config.retry_capture_ids)
    rows = database.execute(
        """
        SELECT e.capture_id,MAX(e.document_id) AS document_id,GROUP_CONCAT(DISTINCT e.operation) AS operations,MAX(d.path) AS path
        FROM errors e LEFT JOIN documents d ON d.id=e.document_id
        WHERE """ + " AND ".join(clauses) + " GROUP BY e.capture_id ORDER BY e.capture_id",
        params,
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
    jobs = scan_jobs or [ScanJob.create(scan_run_id, config.keyword_set_name, config.keywords)]
    if callback:
        callback(ProgressEvent("retry", f"Retrying {len(download_capture_ids):,} downloads and {len(local_document_ids):,} local scans"))
    if local_document_ids:
        if len(jobs) == 1:
            rescan_documents(database, jobs[0].scan_run_id, jobs[0].rules, stop_event, callback, local_document_ids)
        else:
            rescan_keyword_sets(database, jobs, stop_event, callback, local_document_ids)
    if download_capture_ids:
        if len(jobs) == 1:
            download_archive(
                config, database, scan_run_id, stop_event, callback,
                states=("error", "pending", "downloaded"), capture_ids=download_capture_ids,
            )
        else:
            download_archive(
                config, database, scan_run_id, stop_event, callback,
                states=("error", "pending", "downloaded"), capture_ids=download_capture_ids, scan_jobs=jobs,
            )
