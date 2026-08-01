from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections import defaultdict
from typing import Callable
from urllib.parse import urlsplit

from ..cdx.client import HttpClient
from ..cdx.indexer import decode_resume, encode_resume, month_windows
from ..cdx.parameters import parse_cdx
from ..config import ProjectConfig
from ..constants import CDX_URL
from ..database.repositories import get_or_create_media_target, record_error, upsert_media_capture, upsert_media_captures
from ..downloads.rate_limit import AdaptiveRateLimiter
from ..events import ProgressEvent, Stopped
from ..utils import json_value, parse_cdx_parameter_lines, utc_now
from .extensions import allowed_media_url, media_kind, selected_extensions


def media_query_signature(config: ProjectConfig) -> str:
    media = config.media.normalized()
    payload = {
        "from": config.from_date,
        "to": config.to_date,
        "filters": config.cdx_filters,
        "extra": config.cdx_extra_params,
        "page_size": config.page_size,
        "targets": media.targets or config.targets,
        "extensions": selected_extensions(media),
        "strategy": media.snapshot_strategy,
        "embedded": media.discover_embedded,
        "external": media.allow_external_embeds,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def media_target_pattern(target: str, extension: str) -> str:
    return target.rstrip("*") + "*" + extension


def build_media_params(config: ProjectConfig, pattern: str, start: str, end: str, resume: str | None = None, exact: bool = False):
    params = [
        ("url", pattern),
        ("from", start),
        ("to", end),
        ("output", "json"),
        ("fl", "timestamp,original,mimetype,statuscode,digest,length"),
    ]
    if exact:
        params.append(("matchType", "exact"))
    elif config.cdx_match_type:
        params.append(("matchType", config.cdx_match_type))
    params.extend(("filter", value) for value in config.cdx_filters)
    params.extend(parse_cdx_parameter_lines(config.cdx_extra_params))
    params.extend([("limit", str(config.page_size)), ("showResumeKey", "true")])
    if resume:
        params.append(("resumeKey", resume))
    return params


def _apply_snapshot_strategy(database: sqlite3.Connection, signature: str, strategy: str) -> None:
    if strategy == "all":
        return
    rows = database.execute(
        "SELECT id,original_url,timestamp,state FROM media_captures WHERE query_signature=? ORDER BY original_url,timestamp",
        (signature,),
    ).fetchall()
    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        grouped[row["original_url"]].append(row)
    with database:
        for items in grouped.values():
            keep = items[0] if strategy == "earliest" else items[-1]
            for item in items:
                if item["id"] == keep["id"]:
                    if item["state"] == "skipped_strategy":
                        database.execute("UPDATE media_captures SET state='pending',updated_at=? WHERE id=?", (utc_now(), item["id"]))
                elif item["state"] != "downloaded":
                    database.execute("UPDATE media_captures SET state='skipped_strategy',updated_at=? WHERE id=?", (utc_now(), item["id"]))


def index_direct_media(
    config: ProjectConfig,
    database: sqlite3.Connection,
    client: HttpClient,
    stop_event: threading.Event,
    callback: Callable[[ProgressEvent], None] | None,
    signature: str,
) -> None:
    media = config.media.normalized()
    targets = media.targets or config.targets
    extensions = selected_extensions(media)
    tasks = [
        (target, extension, year, month_windows(config, year))
        for target in targets
        for extension in extensions
        for year in range(config.from_year, config.to_year + 1)
        if month_windows(config, year)
    ]
    total = sum(len(windows) for _, _, _, windows in tasks)
    completed = 0

    def save_media_state(
        target_id: int,
        extension: str,
        year: int,
        resume_key: str | None,
        complete: bool,
        seen: int,
        error_id: int | None,
    ) -> None:
        database.execute(
            """
            INSERT INTO media_index_state(
                target_id,extension,year,query_signature,resume_key,complete,seen,error_id,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(target_id,extension,year,query_signature) DO UPDATE SET
                resume_key=excluded.resume_key,
                complete=excluded.complete,
                seen=excluded.seen,
                error_id=excluded.error_id,
                updated_at=excluded.updated_at
            """,
            (
                target_id,
                extension,
                year,
                signature,
                resume_key,
                int(complete),
                seen,
                error_id,
                utc_now(),
            ),
        )

    for target, extension, year, windows in tasks:
        if stop_event.is_set():
            raise Stopped
        target_id = get_or_create_media_target(database, target)
        state = database.execute(
            """
            SELECT resume_key,complete,seen,error_id FROM media_index_state
            WHERE target_id=? AND extension=? AND year=? AND query_signature=?
            """,
            (target_id, extension, year, signature),
        ).fetchone()
        if state and state["complete"]:
            completed += len(windows)
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
        completed += start_index
        pattern = media_target_pattern(target, extension)

        for window_index in range(start_index, len(windows)):
            start, end = windows[window_index]
            resume = first_resume if window_index == start_index else None
            first_resume = None
            label = f"{year}-{start[4:6]}"

            while True:
                if stop_event.is_set():
                    with database:
                        save_media_state(
                            target_id,
                            extension,
                            year,
                            encode_resume(start, end, resume),
                            False,
                            seen,
                            error_id,
                        )
                    raise Stopped

                if callback:
                    callback(
                        ProgressEvent(
                            "media_index",
                            f"Indexing {pattern} for {label}",
                            completed,
                            total,
                        )
                    )
                try:
                    payload = client.get_json(
                        CDX_URL,
                        build_media_params(config, pattern, start, end, resume),
                    )
                    rows, next_resume = parse_cdx(payload)
                    accepted: list[tuple[dict[str, str], str, str]] = []
                    for row in rows:
                        allowed, kind, actual_extension = allowed_media_url(
                            row["original"],
                            media,
                            row.get("mimetype", ""),
                        )
                        if allowed and kind:
                            accepted.append((row, kind, actual_extension or extension))
                    with database:
                        changed = upsert_media_captures(
                            database,
                            accepted,
                            target_id,
                            signature,
                        )
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
                        save_media_state(
                            target_id,
                            extension,
                            year,
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
                    if callback:
                        callback(
                            ProgressEvent(
                                "media_index",
                                (
                                    f"{pattern} {label}: received {len(rows):,}, "
                                    f"accepted {len(accepted):,}, stored {changed:,}"
                                ),
                                completed,
                                total,
                            )
                        )
                except Stopped:
                    with database:
                        save_media_state(
                            target_id,
                            extension,
                            year,
                            encode_resume(start, end, resume),
                            False,
                            seen,
                            error_id,
                        )
                    raise
                except Exception as exc:
                    with database:
                        error_id = record_error(
                            database,
                            "media_index",
                            "index_failure",
                            f"{pattern} {label}: {type(exc).__name__}: {exc}",
                            retryable=True,
                        )
                        save_media_state(
                            target_id,
                            extension,
                            year,
                            encode_resume(start, end, resume),
                            False,
                            seen,
                            error_id,
                        )
                    raise

                if not next_resume:
                    break
                if next_resume == resume:
                    raise RuntimeError("CDX returned the same media resume key twice")
                resume = next_resume

            completed += 1

def index_embedded_media(
    config: ProjectConfig,
    database: sqlite3.Connection,
    client: HttpClient,
    stop_event: threading.Event,
    callback: Callable[[ProgressEvent], None] | None,
    signature: str,
) -> None:
    media = config.media.normalized()
    if not media.discover_embedded:
        return
    target_hosts = {
        urlsplit("http://" + target.split("/", 1)[0]).hostname or ""
        for target in (media.targets or config.targets)
    }
    candidates: dict[str, int] = {}
    for row in database.execute("SELECT id,links_json FROM documents ORDER BY id"):
        for link in json_value(row["links_json"], []):
            allowed, _, _ = allowed_media_url(link, media)
            if not allowed:
                continue
            host = (urlsplit(link).hostname or "").casefold()
            if not media.allow_external_embeds and host not in target_hosts:
                continue
            candidates.setdefault(link, int(row["id"]))
    total = len(candidates)
    for index, (link, document_id) in enumerate(candidates.items(), 1):
        if stop_event.is_set():
            raise Stopped
        existing = database.execute(
            "SELECT 1 FROM media_captures WHERE original_url=? AND query_signature=? LIMIT 1", (link, signature)
        ).fetchone()
        if existing:
            continue
        if callback:
            callback(ProgressEvent("media_embed", f"Looking up embedded media {index:,}/{total:,}", index, total))
        payload = client.get_json(
            CDX_URL,
            build_media_params(config, link, config.from_date, config.to_date, exact=True),
        )
        rows, _ = parse_cdx(payload)
        if not rows:
            continue
        if media.snapshot_strategy == "earliest":
            chosen = [min(rows, key=lambda row: row["timestamp"])]
        elif media.snapshot_strategy == "latest":
            chosen = [max(rows, key=lambda row: row["timestamp"])]
        else:
            chosen = rows
        for row in chosen:
            allowed, kind, extension = allowed_media_url(row["original"], media, row.get("mimetype", ""))
            if allowed and kind:
                with database:
                    upsert_media_capture(
                        database, row, None, signature, kind, extension, document_id, "embedded"
                    )


def index_media(
    config: ProjectConfig,
    database: sqlite3.Connection,
    stop_event: threading.Event,
    callback: Callable[[ProgressEvent], None] | None = None,
) -> str:
    media = config.media.normalized()
    if not (media.targets or config.targets):
        raise ValueError("add at least one media target or site target")
    if not selected_extensions(media):
        raise ValueError("no image or video extensions remain after include/exclude filtering")
    signature = media_query_signature(config)
    limiter = AdaptiveRateLimiter(config.cdx_delay, 1, config.adaptive_rate_limit)
    def on_retry(attempt: int, total: int, reason: str, wait_seconds: float) -> None:
        if callback:
            callback(
                ProgressEvent(
                    "media_index",
                    f"CDX media request failed ({reason}). Retrying attempt {attempt}/{total} in {wait_seconds:.1f}s…",
                )
            )

    client = HttpClient(
        limiter,
        min(config.retries, 3),
        min(max(config.connect_timeout, 15.0), 60.0),
        config.user_agent,
        stop_event,
        retry_callback=on_retry,
    )
    index_direct_media(config, database, client, stop_event, callback, signature)
    index_embedded_media(config, database, client, stop_event, callback, signature)
    _apply_snapshot_strategy(database, signature, media.snapshot_strategy)
    return signature
