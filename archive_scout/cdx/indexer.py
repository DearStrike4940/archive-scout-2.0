from __future__ import annotations

import sqlite3
import threading
from typing import Callable

from ..config import ProjectConfig
from ..constants import CDX_URL
from ..database.repositories import get_or_create_target, record_error, resolve_errors, upsert_capture
from ..downloads.rate_limit import SharedRateLimiter
from ..events import ProgressEvent, RateLimited, Stopped
from ..utils import utc_now
from .client import HttpClient
from .parameters import build_cdx_params, cdx_query_signature, cdx_year_window, parse_cdx


def emit(callback: Callable[[ProgressEvent], None] | None, event: ProgressEvent) -> None:
    if callback:
        callback(event)


def index_archive(
    config: ProjectConfig,
    database: sqlite3.Connection,
    stop_event: threading.Event,
    callback: Callable[[ProgressEvent], None] | None,
) -> None:
    limiter = SharedRateLimiter(config.cdx_delay)
    client = HttpClient(
        limiter,
        config.retries,
        max(config.connect_timeout, config.read_timeout),
        config.user_agent,
        stop_event,
    )
    signature = cdx_query_signature(config)
    windows: list[tuple[str, int, tuple[str, str]]] = []
    for target in config.targets:
        for year in range(config.from_year, config.to_year + 1):
            window = cdx_year_window(config, year)
            if window:
                windows.append((target, year, window))
    total_windows = len(windows)
    completed_windows = 0
    for target, year, window in windows:
        if stop_event.is_set():
            raise Stopped
        target_id = get_or_create_target(database, target)
        start, end = window
        state = database.execute(
            "SELECT resume_key,complete,seen FROM index_state WHERE target_id=? AND year=? AND query_signature=?",
            (target_id, year, signature),
        ).fetchone()
        if state and state["complete"]:
            completed_windows += 1
            emit(callback, ProgressEvent("index", f"Already indexed {target} for {year}", completed_windows, total_windows))
            continue
        resume = state["resume_key"] if state else None
        seen = int(state["seen"] or 0) if state else 0
        while True:
            params = build_cdx_params(config, target, start, end, resume)
            emit(callback, ProgressEvent("index", f"Indexing {target} for {year}…", completed_windows, total_windows))
            try:
                payload = client.get_json(CDX_URL, params)
                rows, next_resume = parse_cdx(payload)
                inserted = 0
                with database:
                    for row in rows:
                        inserted += int(upsert_capture(database, row, target_id, signature))
                    seen += len(rows)
                    database.execute(
                        """
                        INSERT INTO index_state(target_id,year,query_signature,resume_key,complete,seen,error_id,updated_at)
                        VALUES(?,?,?,?,?,?,NULL,?)
                        ON CONFLICT(target_id,year,query_signature) DO UPDATE SET
                            resume_key=excluded.resume_key,complete=excluded.complete,seen=excluded.seen,error_id=NULL,updated_at=excluded.updated_at
                        """,
                        (target_id, year, signature, next_resume, 0 if next_resume else 1, seen, utc_now()),
                    )
                    resolve_errors(database, operations=("index",))
                emit(
                    callback,
                    ProgressEvent(
                        "index",
                        f"{target} {year}: received {len(rows):,}, added {inserted:,}, seen {seen:,}",
                        completed_windows,
                        total_windows,
                    ),
                )
            except Exception as exc:
                category = "rate_limit" if isinstance(exc, RateLimited) else "index_failure"
                with database:
                    error_id = record_error(database, "index", category, repr(exc), retryable=True)
                    database.execute(
                        """
                        INSERT INTO index_state(target_id,year,query_signature,resume_key,complete,seen,error_id,updated_at)
                        VALUES(?,?,?,?,0,?,?,?)
                        ON CONFLICT(target_id,year,query_signature) DO UPDATE SET
                            resume_key=excluded.resume_key,complete=0,seen=excluded.seen,error_id=excluded.error_id,updated_at=excluded.updated_at
                        """,
                        (target_id, year, signature, resume, seen, error_id, utc_now()),
                    )
                raise
            if not next_resume:
                break
            if next_resume == resume:
                raise RuntimeError("CDX returned the same resume key twice")
            resume = next_resume
        completed_windows += 1
        emit(callback, ProgressEvent("index", f"Finished {target} for {year}", completed_windows, total_windows))
