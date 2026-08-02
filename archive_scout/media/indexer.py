from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections import defaultdict
from typing import Callable
from urllib.parse import urlsplit

from ..cdx.client import HttpClient, RateLimitDeferred, TransientRequestError
from ..cdx.indexer import decode_plan, encode_plan, month_windows, split_window, window_label
from ..cdx.parameters import parse_cdx
from ..config import ProjectConfig
from ..constants import CDX_URL
from ..database.repositories import get_or_create_media_target, record_error, upsert_media_capture, upsert_media_captures
from ..downloads.rate_limit import FixedRateLimiter, SharedHostGate
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

    for target, extension, year, default_windows in tasks:
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
            completed += len(default_windows)
            continue

        seen = int(state["seen"] or 0) if state else 0
        error_id = int(state["error_id"]) if state and state["error_id"] else None
        plan = decode_plan(state["resume_key"] if state else None, default_windows)
        completed += plan.completed
        total += max(0, plan.planned - len(default_windows))
        pattern = media_target_pattern(target, extension)

        while plan.pending:
            if stop_event.is_set():
                with database:
                    save_media_state(
                        target_id,
                        extension,
                        year,
                        encode_plan(plan),
                        False,
                        seen,
                        error_id,
                    )
                raise Stopped

            current = plan.pending[0]
            label = window_label(current.start, current.end)
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
                    build_media_params(config, pattern, current.start, current.end, current.resume_key),
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
                        if next_resume == current.resume_key:
                            raise RuntimeError("CDX returned the same media resume key twice")
                        current.resume_key = next_resume
                    else:
                        plan.pending.pop(0)
                        plan.completed += 1
                        completed += 1
                    complete = not plan.pending
                    save_media_state(
                        target_id,
                        extension,
                        year,
                        encode_plan(plan),
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
                        encode_plan(plan),
                        False,
                        seen,
                        error_id,
                    )
                raise
            except RateLimitDeferred:
                with database:
                    save_media_state(
                        target_id,
                        extension,
                        year,
                        encode_plan(plan),
                        False,
                        seen,
                        error_id,
                    )
                if callback:
                    callback(
                        ProgressEvent(
                            "rate_limit",
                            "Wayback remained rate limited beyond the configured wait budget. Media index progress was saved for Resume.",
                            completed,
                            total,
                        )
                    )
                raise
            except TransientRequestError as exc:
                parts = split_window(current) if exc.splittable else []
                if parts:
                    plan.pending[0:1] = parts
                    added = len(parts) - 1
                    plan.planned += added
                    total += added
                    with database:
                        save_media_state(
                            target_id,
                            extension,
                            year,
                            encode_plan(plan),
                            False,
                            seen,
                            error_id,
                        )
                    if callback:
                        callback(
                            ProgressEvent(
                                "media_index",
                                (
                                    f"CDX timed out for {pattern} {label}. "
                                    f"Split it into {len(parts)} smaller windows and continuing."
                                ),
                                completed,
                                total,
                            )
                        )
                    continue
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
                        encode_plan(plan),
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
                        encode_plan(plan),
                        False,
                        seen,
                        error_id,
                    )
                raise

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
    limiter = FixedRateLimiter(config.cdx_delay)
    host_gate = SharedHostGate(config.rate_limit_base_pause, config.rate_limit_max_pause)

    def on_retry(attempt: int, total: int, reason: str, wait_seconds: float) -> None:
        if callback:
            if "all Wayback requests paused" in reason:
                limit = f"/{total}" if total else ""
                message = f"{reason}. Shared pause {attempt}{limit} for {wait_seconds:.1f}s; one recovery probe will run next…"
                stage = "rate_limit"
            else:
                message = f"CDX media request failed ({reason}). Retrying attempt {attempt}/{total} in {wait_seconds:.1f}s…"
                stage = "media_index"
            callback(ProgressEvent(stage, message))

    client = HttpClient(
        limiter,
        min(config.retries, 3),
        min(max(config.read_timeout, 15.0), 45.0),
        config.user_agent,
        stop_event,
        retry_callback=on_retry,
        connect_timeout=min(max(config.connect_timeout, 5.0), 30.0),
        read_timeout=min(max(config.read_timeout, 15.0), 45.0),
        pool_size=1,
        host_gate=host_gate,
        rate_limit_attempts=config.rate_limit_attempts,
        rate_limit_max_wait=config.rate_limit_max_wait,
    )
    index_direct_media(config, database, client, stop_event, callback, signature)
    index_embedded_media(config, database, client, stop_event, callback, signature)
    _apply_snapshot_strategy(database, signature, media.snapshot_strategy)
    return signature
