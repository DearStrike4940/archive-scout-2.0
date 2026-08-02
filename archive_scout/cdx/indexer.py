from __future__ import annotations

import calendar
import json
import random
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from ..config import ProjectConfig
from ..constants import CDX_URL
from ..database.repositories import get_or_create_target, record_error, upsert_captures
from ..downloads.rate_limit import FixedRateLimiter, SharedHostGate
from ..events import ProgressEvent, Stopped
from ..utils import utc_now
from .client import HttpClient, RateLimitDeferred, TransientRequestError
from .parameters import build_cdx_params, cdx_query_signature, parse_cdx


@dataclass(slots=True)
class PendingWindow:
    start: str
    end: str
    resume_key: str | None = None
    failures: int = 0
    page_size: int = 0


@dataclass(slots=True)
class IndexPlan:
    pending: list[PendingWindow]
    completed: int
    planned: int


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
        if int(payload.get("version", 1)) != 1:
            return None
        start = str(payload["window_start"])
        end = str(payload["window_end"])
        resume = payload.get("resume_key")
        return start, end, str(resume) if resume else None
    except Exception:
        return None


def encode_plan(plan: IndexPlan) -> str | None:
    if not plan.pending:
        return None
    payload = {
        "version": 3,
        "completed": int(plan.completed),
        "planned": int(plan.planned),
        "pending": [
            {
                "start": item.start,
                "end": item.end,
                "resume_key": item.resume_key,
                "failures": int(item.failures),
                "page_size": int(item.page_size),
            }
            for item in plan.pending
        ],
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def decode_plan(value: str | None, default_windows: list[tuple[str, str]]) -> IndexPlan:
    if value and value.lstrip().startswith("{"):
        try:
            payload = json.loads(value)
            version = int(payload.get("version", 1))
            if version in {2, 3}:
                pending: list[PendingWindow] = []
                for raw in payload.get("pending") or []:
                    start = str(raw["start"])
                    end = str(raw["end"])
                    if start <= end:
                        resume = raw.get("resume_key")
                        pending.append(
                            PendingWindow(
                                start,
                                end,
                                str(resume) if resume else None,
                                max(0, int(raw.get("failures", 0))),
                                max(0, int(raw.get("page_size", 0))),
                            )
                        )
                completed = max(0, int(payload.get("completed", 0)))
                planned = max(completed + len(pending), int(payload.get("planned", 0)))
                if pending:
                    return IndexPlan(pending, completed, planned)
        except Exception:
            pass

    legacy = decode_resume(value)
    if legacy:
        saved_start, saved_end, saved_resume = legacy
        later = [(start, end) for start, end in default_windows if start > saved_end]
        completed = sum(1 for _, end in default_windows if end < saved_start)
        pending = [PendingWindow(saved_start, saved_end, saved_resume)]
        pending.extend(PendingWindow(start, end) for start, end in later)
        return IndexPlan(pending, completed, completed + len(pending))

    pending = [PendingWindow(start, end) for start, end in default_windows]
    return IndexPlan(pending, 0, len(pending))


def split_window(window: PendingWindow) -> list[PendingWindow]:
    """Split a failed CDX interval down to one-second windows when necessary."""
    start_dt = datetime.strptime(window.start, "%Y%m%d%H%M%S")
    end_dt = datetime.strptime(window.end, "%Y%m%d%H%M%S")
    duration = end_dt - start_dt

    if duration >= timedelta(days=8):
        chunk = timedelta(days=7)
    elif duration >= timedelta(days=2):
        chunk = timedelta(days=1)
    elif duration >= timedelta(hours=12):
        chunk = timedelta(hours=6)
    elif duration >= timedelta(hours=2):
        chunk = timedelta(hours=1)
    elif duration >= timedelta(minutes=30):
        chunk = timedelta(minutes=15)
    elif duration >= timedelta(minutes=10):
        chunk = timedelta(minutes=5)
    elif duration >= timedelta(minutes=2):
        chunk = timedelta(minutes=1)
    elif duration >= timedelta(seconds=30):
        chunk = timedelta(seconds=15)
    elif duration >= timedelta(seconds=10):
        chunk = timedelta(seconds=5)
    elif duration >= timedelta(seconds=2):
        chunk = timedelta(seconds=1)
    else:
        return []

    parts: list[PendingWindow] = []
    cursor = start_dt
    while cursor <= end_dt:
        part_end = min(end_dt, cursor + chunk - timedelta(seconds=1))
        parts.append(
            PendingWindow(
                cursor.strftime("%Y%m%d%H%M%S"),
                part_end.strftime("%Y%m%d%H%M%S"),
                None,
                0,
                max(25, window.page_size // 2) if window.page_size else 0,
            )
        )
        cursor = part_end + timedelta(seconds=1)
    return parts if len(parts) > 1 else []


def window_label(start: str, end: str) -> str:
    start_date = datetime.strptime(start, "%Y%m%d%H%M%S")
    end_date = datetime.strptime(end, "%Y%m%d%H%M%S")
    if start_date.date() == end_date.date():
        if start_date.hour == 0 and start_date.minute == 0 and end_date.hour == 23 and end_date.minute == 59:
            return start_date.strftime("%Y-%m-%d")
        if start_date.hour == end_date.hour and start_date.minute == end_date.minute:
            return f"{start_date:%Y-%m-%d %H:%M:%S}–{end_date:%H:%M:%S}"
        return f"{start_date:%Y-%m-%d %H:%M}–{end_date:%H:%M}"
    if start_date.day == 1 and end_date.month == start_date.month:
        last_day = calendar.monthrange(start_date.year, start_date.month)[1]
        if end_date.day == last_day:
            return start_date.strftime("%Y-%m")
    return f"{start_date:%Y-%m-%d}–{end_date:%Y-%m-%d}"


def transient_backoff(failures: int) -> float:
    base = min(300.0, 5.0 * (2 ** min(max(0, failures - 1), 6)))
    return base * random.uniform(0.85, 1.15)


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


def _defer_transient_window(
    config: ProjectConfig,
    database: sqlite3.Connection,
    plan: IndexPlan,
    current: PendingWindow,
    target_id: int,
    year: int,
    signature: str,
    seen: int,
    error_id: int | None,
    exc: BaseException,
    callback: Callable[[ProgressEvent], None] | None,
    completed_windows: int,
    total_windows: int,
    stop_event: threading.Event,
) -> int:
    current.failures += 1
    current.page_size = max(25, (current.page_size or config.page_size) // 2)
    message = f"{type(exc).__name__}: {exc}"
    with database:
        error_id = record_error(
            database,
            "index",
            "transient_index_delay",
            f"{window_label(current.start, current.end)}: {message}",
            retryable=True,
        )
        if len(plan.pending) > 1:
            plan.pending.append(plan.pending.pop(0))
        save_state(database, target_id, year, signature, encode_plan(plan), False, seen, error_id)
    if len(plan.pending) > 1:
        emit(
            callback,
            ProgressEvent(
                "index",
                f"Wayback did not answer this smallest window. It was moved behind the remaining windows and will retry automatically (page size {current.page_size}).",
                completed_windows,
                total_windows,
            ),
        )
        return error_id
    wait_seconds = transient_backoff(current.failures)
    emit(
        callback,
        ProgressEvent(
            "index",
            f"Wayback did not answer the smallest remaining window. Archive Scout is staying alive and will retry in {wait_seconds:.1f}s (attempt {current.failures + 1}, page size {current.page_size}).",
            completed_windows,
            total_windows,
        ),
    )
    stop_event.wait(wait_seconds)
    if stop_event.is_set():
        raise Stopped
    return error_id


def index_archive(
    config: ProjectConfig,
    database: sqlite3.Connection,
    stop_event: threading.Event,
    callback: Callable[[ProgressEvent], None] | None = None,
) -> None:
    limiter = FixedRateLimiter(config.cdx_delay)
    host_gate = SharedHostGate(config.rate_limit_base_pause, config.rate_limit_max_pause)

    def on_retry(attempt: int, total: int, reason: str, wait_seconds: float) -> None:
        if "all Wayback requests paused" in reason:
            limit = f"/{total}" if total else ""
            message = f"{reason}. Shared pause {attempt}{limit} for {wait_seconds:.1f}s; one recovery probe will run next…"
        else:
            message = f"CDX request failed ({reason}). Retrying attempt {attempt}/{total} in {wait_seconds:.1f}s…"
        emit(callback, ProgressEvent("rate_limit" if "all Wayback requests paused" in reason else "index", message))

    client = HttpClient(
        limiter,
        min(config.retries, 2),
        min(max(config.read_timeout, 15.0), 45.0),
        config.user_agent,
        stop_event,
        retry_callback=on_retry,
        connect_timeout=min(max(config.connect_timeout, 5.0), 30.0),
        read_timeout=min(max(config.read_timeout, 15.0), 45.0),
        pool_size=1,
        host_gate=host_gate,
        rate_limit_attempts=0,
        rate_limit_max_wait=0,
    )
    signature = cdx_query_signature(config)
    if not config.cdx_collapses:
        emit(callback, ProgressEvent("index", "Warning: no CDX collapse is selected. Every archived snapshot may be returned, which can make broad site queries much slower."))
    for target in config.targets:
        if target.endswith("*") and "/" not in target[:-1]:
            emit(callback, ProgressEvent("index", f"Warning: target {target} is unusually broad. For the whole site, {target[:-1].rstrip('/')}/* is normally clearer."))
    tasks: list[tuple[str, int, list[tuple[str, str]]]] = []
    for target in config.targets:
        for year in range(config.from_year, config.to_year + 1):
            windows = month_windows(config, year)
            if windows:
                tasks.append((target, year, windows))

    total_windows = sum(len(windows) for _, _, windows in tasks)
    completed_windows = 0
    try:
        for target, year, default_windows in tasks:
            if stop_event.is_set():
                raise Stopped
            target_id = get_or_create_target(database, target)
            state = database.execute(
                "SELECT resume_key,complete,seen,error_id FROM index_state WHERE target_id=? AND year=? AND query_signature=?",
                (target_id, year, signature),
            ).fetchone()
            if state and state["complete"]:
                completed_windows += len(default_windows)
                emit(callback, ProgressEvent("index", f"Already indexed {target} for {year}", completed_windows, total_windows))
                continue

            seen = int(state["seen"] or 0) if state else 0
            error_id = int(state["error_id"]) if state and state["error_id"] else None
            plan = decode_plan(state["resume_key"] if state else None, default_windows)
            completed_windows += plan.completed
            total_windows += max(0, plan.planned - len(default_windows))

            while plan.pending:
                if stop_event.is_set():
                    with database:
                        save_state(database, target_id, year, signature, encode_plan(plan), False, seen, error_id)
                    raise Stopped
                current = plan.pending[0]
                label = window_label(current.start, current.end)
                page_size = current.page_size or config.page_size
                params = build_cdx_params(config, target, current.start, current.end, current.resume_key, page_size=page_size)
                emit(callback, ProgressEvent("index", f"Indexing {target} for {label}…", completed_windows, total_windows))
                request_started = time.monotonic()
                try:
                    payload = client.get_json(CDX_URL, params)
                    request_seconds = time.monotonic() - request_started
                    rows, next_resume = parse_cdx(payload)
                    write_started = time.monotonic()
                    with database:
                        changed = upsert_captures(database, rows, target_id, signature)
                        seen += len(rows)
                        current.failures = 0
                        if next_resume:
                            if next_resume == current.resume_key:
                                raise TransientRequestError("CDX returned the same resume key twice", splittable=True)
                            current.resume_key = next_resume
                        else:
                            plan.pending.pop(0)
                            plan.completed += 1
                            completed_windows += 1
                        complete = not plan.pending
                        save_state(database, target_id, year, signature, encode_plan(plan), complete, seen, None if complete else error_id)
                        if error_id:
                            database.execute("UPDATE errors SET resolved=1,last_seen=? WHERE id=?", (utc_now(), error_id))
                            error_id = None
                    write_seconds = time.monotonic() - write_started
                    emit(
                        callback,
                        ProgressEvent(
                            "index",
                            f"{target} {label}: received {len(rows):,}, stored {changed:,}, seen {seen:,} — CDX {request_seconds:.1f}s, database {write_seconds:.2f}s",
                            completed_windows,
                            total_windows,
                        ),
                    )
                except Stopped:
                    with database:
                        save_state(database, target_id, year, signature, encode_plan(plan), False, seen, error_id)
                    raise
                except RateLimitDeferred as exc:
                    # Indexing never aborts for a temporary rate limit. Save and retry.
                    error_id = _defer_transient_window(
                        config, database, plan, current, target_id, year, signature, seen, error_id,
                        exc, callback, completed_windows, total_windows, stop_event,
                    )
                    continue
                except TransientRequestError as exc:
                    parts = split_window(current) if exc.splittable else []
                    if parts:
                        plan.pending[0:1] = parts
                        added = len(parts) - 1
                        plan.planned += added
                        total_windows += added
                        with database:
                            save_state(database, target_id, year, signature, encode_plan(plan), False, seen, error_id)
                        emit(
                            callback,
                            ProgressEvent(
                                "index",
                                f"CDX timed out for {target} {label}. Automatically split it into {len(parts)} smaller windows and continuing.",
                                completed_windows,
                                total_windows,
                            ),
                        )
                        continue
                    error_id = _defer_transient_window(
                        config, database, plan, current, target_id, year, signature, seen, error_id,
                        exc, callback, completed_windows, total_windows, stop_event,
                    )
                    continue
                except Exception as exc:
                    # Configuration/permission errors are not transient; preserving them as
                    # explicit failures avoids an infinite loop around a malformed query.
                    message = f"{target} {label}: {type(exc).__name__}: {exc}"
                    with database:
                        error_id = record_error(database, "index", "index_failure", message, retryable=False)
                        save_state(database, target_id, year, signature, encode_plan(plan), False, seen, error_id)
                    emit(callback, ProgressEvent("index", f"Indexing stopped on a non-transient error for {target} {label}. Progress was saved.", completed_windows, total_windows))
                    raise
            emit(callback, ProgressEvent("index", f"Finished {target} for {year}", completed_windows, total_windows))
    finally:
        client.close()
