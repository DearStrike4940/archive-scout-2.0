from __future__ import annotations

import concurrent.futures
import hashlib
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlsplit

from ..cdx.client import HttpClient
from ..config import ProjectConfig
from ..database.repositories import record_error, save_media_success
from ..downloads.downloader import replay_url
from ..downloads.rate_limit import FixedRateLimiter
from ..downloads.validation import classify_exception
from ..events import ProgressEvent, Stopped
from ..utils import utc_now
from .indexer import media_query_signature

INVALID_COMPONENT = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_component(value: str, fallback: str = "unnamed") -> str:
    value = INVALID_COMPONENT.sub("_", unquote(value)).strip(" .")
    return value[:180] or fallback


def media_path(root: Path, row: sqlite3.Row, preserve_paths: bool) -> Path:
    parsed = urlsplit(row["original_url"])
    host = safe_component(parsed.hostname or "unknown-host")
    filename = safe_component(Path(parsed.path).name or f"media{row['extension'] or ''}")
    prefix = f"{row['timestamp']}_{row['id']}_"
    if preserve_paths:
        directories = [safe_component(part) for part in Path(parsed.path).parts[:-1] if part not in {"/", ""}]
        return root / "media" / row["media_kind"] / host / Path(*directories) / (prefix + filename)
    return root / "media" / row["media_kind"] / host / (prefix + filename)


def fetch_media(row: sqlite3.Row, config: ProjectConfig, client: HttpClient) -> dict:
    response = client.get(replay_url(row["timestamp"], row["original_url"]), config.media.max_file_bytes)
    data = response["data"]
    content_type = response["headers"].get("Content-Type", "").casefold()
    if not data:
        raise RuntimeError("empty media response")
    if "text/html" in content_type:
        preview = data[:20000].decode("utf-8", "ignore").casefold()
        if "wayback machine" in preview or "not archived" in preview:
            raise RuntimeError("invalid_wayback_replay")
    path = media_path(config.output_dir, row, config.media.preserve_paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".part")
    temp.write_bytes(data)
    os.replace(temp, path)
    return {
        "id": int(row["id"]),
        "path": path,
        "bytes": len(data),
        "hash": hashlib.sha256(data).hexdigest(),
        "status": response["status"],
        "final_url": response["final_url"],
    }


def download_media(
    config: ProjectConfig,
    database: sqlite3.Connection,
    stop_event: threading.Event,
    callback: Callable[[ProgressEvent], None] | None = None,
    states: tuple[str, ...] = ("pending",),
    media_capture_ids: list[int] | None = None,
) -> None:
    clauses: list[str] = []
    params: list[object] = []
    if media_capture_ids:
        clauses.append("id IN (" + ",".join("?" for _ in media_capture_ids) + ")")
        params.extend(media_capture_ids)
    else:
        clauses.extend(["query_signature=?", "download_attempts<?"])
        params.extend([media_query_signature(config), config.max_attempts])
    if states:
        clauses.append("state IN (" + ",".join("?" for _ in states) + ")")
        params.extend(states)
    rows = database.execute(
        "SELECT * FROM media_captures WHERE " + " AND ".join(clauses) + " ORDER BY timestamp,original_url", params
    ).fetchall()
    total = len(rows)
    if not rows:
        if callback:
            callback(ProgressEvent("media_download", "No media captures to download.", 0, 0))
        return
    limiter = FixedRateLimiter(config.download_delay)
    client = HttpClient(limiter, config.retries, max(config.connect_timeout, config.read_timeout), config.user_agent, stop_event)
    complete = errors = 0
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=config.workers, thread_name_prefix="archive-media") as pool:
        futures: dict[concurrent.futures.Future, sqlite3.Row] = {}
        for row in rows:
            if stop_event.is_set():
                raise Stopped
            with database:
                database.execute(
                    "UPDATE media_captures SET state='downloading',download_attempts=download_attempts+1,updated_at=? WHERE id=?",
                    (utc_now(), row["id"]),
                )
            futures[pool.submit(fetch_media, row, config, client)] = row
        for future in concurrent.futures.as_completed(futures):
            row = futures[future]
            if stop_event.is_set():
                raise Stopped
            try:
                result = future.result()
                with database:
                    save_media_success(
                        database, result["id"], result["path"], result["bytes"], result["hash"], result["status"], result["final_url"]
                    )
            except Exception as exc:
                errors += 1
                category, status, retryable = classify_exception(exc)
                if str(exc) == "invalid_wayback_replay":
                    category, retryable = "invalid_wayback_replay", False
                with database:
                    database.execute(
                        "UPDATE media_captures SET state='error',http_status=?,updated_at=? WHERE id=?",
                        (status, utc_now(), row["id"]),
                    )
                    record_error(
                        database, "media_download", category, repr(exc), media_capture_id=int(row["id"]),
                        http_status=status, retryable=retryable
                    )
            complete += 1
            elapsed = max(0.001, time.monotonic() - started)
            if callback:
                callback(ProgressEvent(
                    "media_download",
                    f"Media {complete:,}/{total:,}; errors {errors:,}; {complete/elapsed:.1f}/s",
                    complete, total,
                    {"errors": errors},
                ))


def retry_media_errors(
    config: ProjectConfig,
    database: sqlite3.Connection,
    stop_event: threading.Event,
    callback: Callable[[ProgressEvent], None] | None = None,
    media_capture_ids: list[int] | None = None,
) -> None:
    clauses = ["resolved=0", "ignored=0", "retryable=1", "media_capture_id IS NOT NULL"]
    params: list[object] = []
    selected = media_capture_ids if media_capture_ids is not None else config.retry_media_capture_ids
    if selected:
        clauses.append("media_capture_id IN (" + ",".join("?" for _ in selected) + ")")
        params.extend(int(value) for value in selected)
    rows = database.execute(
        "SELECT DISTINCT media_capture_id FROM errors WHERE " + " AND ".join(clauses) + " ORDER BY media_capture_id",
        params,
    ).fetchall()
    ids = [int(row[0]) for row in rows]
    if callback:
        callback(ProgressEvent("media_retry", f"Retrying {len(ids):,} errored media captures"))
    if ids:
        download_media(config, database, stop_event, callback, states=("error", "pending"), media_capture_ids=ids)
