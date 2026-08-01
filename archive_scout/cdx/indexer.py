from __future__ import annotations

import calendar
import json
import sqlite3
import threading
import time
from typing import Callable

from ..config import ProjectConfig
from ..constants import CDX_URL
from ..database.repositories import get_or_create_target, record_error, upsert_captures
from ..downloads.rate_limit import SharedRateLimiter
from ..events import ProgressEvent, RateLimited, Stopped
from ..utils import utc_now
from .client import HttpClient
from .parameters import build_cdx_params, cdx_query_signature, parse_cdx


def emit(callback: Callable[[ProgressEvent], None] | None, event: ProgressEvent) -> None:
    if callback:
        callback(event)


def month_windows(config: ProjectConfig, year: int) -> list[tuple[str, str]]:
    windows: list[tuple[str, str]] = []
    for month in range(1, 13):
        last_day = calendar.monthrange(year, month)[1]
        start = max(config.from_date, f"{year:04d}{month:02d}01000000")
        end = min(config.to_date, f"{year:04d}{month:02d}{last_day:02d}235959")
        if start <= end:
            windows.append((start, end))
    return windows


def encode_resume(start: str, end: str, resume: str | None) -> str:
    return json.dumps(
        {"version": 1, "window_start": start, "window_end": end, "resume_key": resume},
        separators=(",", ":"),
        sort_keys=True,
    )


def decode_resume(value: str | None) -> tuple[str, str, str | None] | None:
    if not value or not value.lstrip().startswith("{"):
        return None
    try:
        payload = json.loads(value)
        start = str(payload["window_start"])
        end = str(payload["window_end"])
        resume = payload.get("resume_key")
        return start, end, str(resume) if resume else None
    except Exception:
        return None


def save_state(
    database: sqlite3.Connection,
    target_id: int,
    year: int,
    signature: str,
    resume_key: str | None,
    complete: bool,
    seen: int,
    error_id: int | None,
) -> None:
    database.execute(
        """
        INSERT INTO index_state(target_id,year,query_signature,resume_key,complete,seen,error_id,updated_at)
        VALUES(?,?,?,?,?,?,?,?)
        ON CONFLICT(target_id,year,query_signature) DO UPDATE SET
            resume_key=excluded.resume_key,
            complete=excluded.complete,
            seen=excluded.seen,
            error_id=excluded.error_id,
            updated_at=excluded.updated_at
        """,
        (target_id, year, signature, resume_key, int(complete), seen, error_id, utc_now()),
    )


def index_archive(
    config: ProjectConfig,
    database: sqlite3.Connection,
    stop_event: threading.Event,
    callback: Callable[[ProgressEvent], None] | None = None,
) -> None:
    limiter = SharedRateLimiter(config.cdx_delay, 1, config.adaptive_rate_limit)

    def on_retry(attempt: int, total: int, reason: str, wait_seconds: float) -> None:
        emit(
            callback,
            ProgressEvent(
                "index",
                f"CDX request failed ({reason}). Retrying attempt {attempt}/{total} in {wait_seconds:.1f}s…",
            ),
        )

    client = HttpClient(
        limiter,
        min(config.retries, 3),
        min(max(config.connect_timeout, 15.0), 60.0),
        config.user_agent,
        stop_event,
        retry_callback=on_retry,
    )
    signature = cdx_query_signature(config)
    plan: list[tuple[str, int, list[tuple[str, str]]]] = []
    for target in config.targets:
        for year in range(config.from_year, config.to_year + 1):
            windows = month_windows(config, year)
            if windows:
                plan.append((target, year, windows))

    total_windows = sum(len(windows) for _, _, windows in plan)
    completed_windows = 0

    for target, year, windows in plan:
        if stop_event.is_set():
            raise Stopped
        target_id = get_or_create_target(database, target)
        state = database.execute(
            """
            SELECT resume_key,complete,seen,error_id
            FROM index_state
            WHERE target_id=? AND year=? AND query_signature=?
            """,
            (target_id, year, signature),
        ).fetchone()

        if state and state["complete"]:
            completed_windows += len(windows)
            emit(
                callback,
                ProgressEvent(
                    "index",
                    f"Already indexed {target} for {year}",
                    completed_windows,
                    total_windows,
                ),
            )
            continue

        seen = int(state["seen"] or 0) if state else 0
        error_id = int(state["error_id"]) if state and state["error_id"] else None
        saved = decode_resume(state["resume_key"] if state else None)
        start_index = 0
        first_resume: str | None = None
        if saved:
            saved_start, saved_end, first_resume = saved
            for index, window in enumerate(windows):
                if window == (saved_start, saved_end):
                    start_index = index
                    break

        completed_windows += start_index

        for window_index in range(start_index, len(windows)):
            start, end = windows[window_index]
            resume = first_resume if window_index == start_index else None
            first_resume = None
            label = f"{year}-{start[4:6]}"

            while True:
                if stop_event.is_set():
                    with database:
                        save_state(
                            database,
                            target_id,
                            year,
                            signature,
                            encode_resume(start, end, resume),
                            False,
                            seen,
                            error_id,
                        )
                    raise Stopped

                params = build_cdx_params(config, target, start, end, resume)
                emit(
                    callback,
                    ProgressEvent(
                        "index",
                        f"Indexing {target} for {label}…",
                        completed_windows,
                        total_windows,
                    ),
                )
                request_started = time.monotonic()
                try:
                    payload = client.get_json(CDX_URL, params)
                    request_seconds = time.monotonic() - request_started
                    rows, next_resume = parse_cdx(payload)
                    write_started = time.monotonic()
                    with database:
                        changed = upsert_captures(database, rows, target_id, signature)
                        seen += len(rows)
                        if next_resume:
                            next_state = encode_resume(start, end, next_resume)
                            complete = False
                        elif window_index + 1 < len(windows):
                            next_start, next_end = windows[window_index + 1]
                            next_state = encode_resume(next_start, next_end, None)
                            complete = False
                        else:
                            next_state = None
                            complete = True
                        save_state(
                            database,
                            target_id,
                            year,
                            signature,
                            next_state,
                            complete,
                            seen,
                            None if complete else error_id,
                        )
                        if complete and error_id:
                            database.execute(
                                "UPDATE errors SET resolved=1,last_seen=? WHERE id=?",
                                (utc_now(), error_id),
                            )
                    write_seconds = time.monotonic() - write_started
                    emit(
                        callback,
                        ProgressEvent(
                            "index",
                            (
                                f"{target} {label}: received {len(rows):,}, stored {changed:,}, "
                                f"seen {seen:,} — CDX {request_seconds:.1f}s, database {write_seconds:.2f}s"
                            ),
                            completed_windows,
                            total_windows,
                        ),
                    )
                except Stopped:
                    with database:
                        save_state(
                            database,
                            target_id,
                            year,
                            signature,
                            encode_resume(start, end, resume),
                            False,
                            seen,
                            error_id,
                        )
                    raise
                except Exception as exc:
                    category = "rate_limit" if isinstance(exc, RateLimited) else "index_failure"
                    message = f"{target} {label}: {type(exc).__name__}: {exc}"
                    with database:
                        error_id = record_error(database, "index", category, message, retryable=True)
                        save_state(
                            database,
                            target_id,
                            year,
                            signature,
                            encode_resume(start, end, resume),
                            False,
                            seen,
                            error_id,
                        )
                    emit(
                        callback,
                        ProgressEvent(
                            "index",
                            f"Indexing failed for {target} {label}. Progress was saved.",
                            completed_windows,
                            total_windows,
                        ),
                    )
                    raise

                if not next_resume:
                    break
                if next_resume == resume:
                    raise RuntimeError("CDX returned the same resume key twice")
                resume = next_resume

            completed_windows += 1
            emit(
                callback,
                ProgressEvent(
                    "index",
                    f"Finished {target} for {label}",
                    completed_windows,
                    total_windows,
                ),
            )
