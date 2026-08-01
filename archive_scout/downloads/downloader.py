from __future__ import annotations

import concurrent.futures
import hashlib
import sqlite3
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Callable

from ..cdx.client import HttpClient
from ..cdx.parameters import cdx_query_signature
from ..config import ProjectConfig
from ..constants import REPLAY_URL
from ..content import classify_replay_content, decode_bytes, is_text_candidate, looks_textual_bytes, parse_page
from ..database.repositories import record_error, resolve_errors, save_match, upsert_document
from ..events import ProgressEvent, RateLimited, Stopped
from ..scanning.jobs import ScanJob
from ..scanning.keywords import keyword_url_match
from ..scanning.scoring import analyze_content
from ..utils import atomic_write_text, hash_text, normalize_search, utc_now
from .rate_limit import AdaptiveRateLimiter
from .validation import classify_exception


def replay_url(timestamp: str, original: str) -> str:
    encoded = urllib.parse.quote(original, safe=":/?&=#%+;,[]@!$'()*")
    return f"{REPLAY_URL}/{timestamp}id_/{encoded}"


def capture_path(root: Path, capture_id: int, timestamp: str, original: str) -> Path:
    digest = hashlib.sha1(original.encode("utf-8", "surrogatepass")).hexdigest()
    return root / "captures" / timestamp[:4] / timestamp[4:6] / f"{capture_id}_{digest}.txt"


def select_download_rows(
    database: sqlite3.Connection,
    config: ProjectConfig,
    patterns,
    states: tuple[str, ...] = ("pending",),
    capture_ids: list[int] | None = None,
) -> list[sqlite3.Row]:
    clauses: list[str] = []
    params: list[object] = []
    if not capture_ids:
        clauses.extend(["query_signature=?", "download_attempts<?"])
        params.extend([cdx_query_signature(config), config.max_attempts])
    if states:
        clauses.append("state IN (" + ",".join("?" for _ in states) + ")")
        params.extend(states)
    if capture_ids:
        clauses.append("id IN (" + ",".join("?" for _ in capture_ids) + ")")
        params.extend(capture_ids)
    rows = database.execute(
        "SELECT * FROM captures WHERE " + " AND ".join(clauses) + " ORDER BY timestamp,original_url",
        params,
    ).fetchall()
    selected: list[sqlite3.Row] = []
    for row in rows:
        if not is_text_candidate(row["original_url"], row["mimetype"] or ""):
            with database:
                database.execute("UPDATE captures SET state='skipped',updated_at=? WHERE id=?", (utc_now(), row["id"]))
                record_error(
                    database,
                    "download",
                    "binary_response",
                    "capture is not a text candidate",
                    capture_id=int(row["id"]),
                    retryable=False,
                )
            continue
        if config.download_scope == "keyword_urls" and patterns and not keyword_url_match(row["original_url"], patterns):
            with database:
                database.execute("UPDATE captures SET state='skipped',updated_at=? WHERE id=?", (utc_now(), row["id"]))
            continue
        selected.append(row)
    return selected


def fetch_parse_scan(row: sqlite3.Row, config: ProjectConfig, jobs: list[ScanJob], client: HttpClient) -> dict:
    original = row["original_url"]
    response = client.get(replay_url(row["timestamp"], original), config.max_file_bytes)
    content_type = response["headers"].get("Content-Type", row["mimetype"] or "")
    data = response["data"]
    if not looks_textual_bytes(data, content_type):
        raise RuntimeError("downloaded response was not textual")
    raw = decode_bytes(data, content_type)
    replay_problem = classify_replay_content(raw, response["final_url"])
    if replay_problem:
        raise RuntimeError(replay_problem)
    title, visible, links = parse_page(raw, original)
    analyses = {
        job.scan_run_id: analyze_content(original, title, visible, raw, links, job.patterns)
        for job in jobs
    }
    path = capture_path(config.output_dir, int(row["id"]), row["timestamp"], original)
    atomic_write_text(path, raw)
    return {
        "capture_id": int(row["id"]),
        "path": path,
        "title": title,
        "visible": visible,
        "links": links,
        "analyses": analyses,
        "content_hash": hash_text(raw),
        "normalized_hash": hash_text(normalize_search(visible)),
        "bytes_saved": len(data),
        "http_status": response["status"],
        "final_url": response["final_url"],
    }


def save_success(database: sqlite3.Connection, result: dict) -> None:
    with database:
        document_id = upsert_document(
            database,
            result["capture_id"],
            result["path"],
            result["title"],
            result["visible"],
            result["links"],
            result["content_hash"],
            result["normalized_hash"],
            result["bytes_saved"],
        )
        database.execute(
            "UPDATE captures SET state='downloaded',http_status=?,final_url=?,bytes_saved=?,updated_at=? WHERE id=?",
            (result["http_status"], result["final_url"], result["bytes_saved"], utc_now(), result["capture_id"]),
        )
        for scan_run_id, analysis in result["analyses"].items():
            save_match(database, int(scan_run_id), document_id, analysis)
        resolve_errors(database, capture_id=result["capture_id"], document_id=document_id)


def download_archive(
    config: ProjectConfig,
    database: sqlite3.Connection,
    scan_run_id: int,
    stop_event: threading.Event,
    callback: Callable[[ProgressEvent], None] | None,
    states: tuple[str, ...] = ("pending",),
    capture_ids: list[int] | None = None,
    scan_jobs: list[ScanJob] | None = None,
) -> None:
    if config.download_scope == "index_only":
        if callback:
            callback(ProgressEvent("download", "Index-only mode selected; downloads skipped."))
        return
    jobs = scan_jobs or [ScanJob.create(scan_run_id, config.keyword_set_name, config.keywords)]
    if not jobs or any(not job.patterns for job in jobs):
        raise ValueError("at least one keyword rule is required")
    combined_patterns = [item for job in jobs for item in job.patterns]
    with database:
        database.execute("UPDATE captures SET state='pending' WHERE state='downloading'")
    rows = select_download_rows(database, config, combined_patterns, states=states, capture_ids=capture_ids)
    total = len(rows)
    if not total:
        if callback:
            callback(ProgressEvent("download", "No matching captures to download.", 0, 0))
        return
    limiter = AdaptiveRateLimiter(config.download_delay, config.workers, config.adaptive_rate_limit)
    client = HttpClient(
        limiter,
        config.retries,
        max(config.connect_timeout, config.read_timeout),
        config.user_agent,
        stop_event,
    )
    completed = matched = failures = 0
    started = time.monotonic()
    max_inflight = max(config.workers, config.workers * 3)
    row_iter = iter(rows)
    with concurrent.futures.ThreadPoolExecutor(max_workers=config.workers, thread_name_prefix="archive-scout") as pool:
        futures: dict[concurrent.futures.Future, sqlite3.Row] = {}

        def submit_next() -> bool:
            try:
                row = next(row_iter)
            except StopIteration:
                return False
            if stop_event.is_set():
                raise Stopped
            with database:
                database.execute(
                    "UPDATE captures SET state='downloading',download_attempts=download_attempts+1,updated_at=? WHERE id=?",
                    (utc_now(), row["id"]),
                )
            futures[pool.submit(fetch_parse_scan, row, config, jobs, client)] = row
            return True

        while len(futures) < max_inflight and submit_next():
            pass
        while futures:
            if stop_event.is_set():
                for pending in futures:
                    pending.cancel()
                raise Stopped
            done, _ = concurrent.futures.wait(futures, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                row = futures.pop(future)
                try:
                    result = future.result()
                    save_success(database, result)
                    matched += int(any(
                        int(analysis.get("score") or 0) >= config.minimum_score
                        and not analysis.get("excluded") and not analysis.get("required_missing")
                        for analysis in result["analyses"].values()
                    ))
                except Stopped:
                    with database:
                        database.execute("UPDATE captures SET state='pending',updated_at=? WHERE id=?", (utc_now(), row["id"]))
                    raise
                except Exception as exc:
                    failures += 1
                    category, status, retryable = classify_exception(exc)
                    if str(exc) in {"soft_404", "invalid_wayback_replay"}:
                        category = str(exc)
                        retryable = False
                    with database:
                        database.execute(
                            "UPDATE captures SET state='error',http_status=?,updated_at=? WHERE id=?",
                            (status, utc_now(), row["id"]),
                        )
                        record_error(
                            database,
                            "download",
                            category,
                            repr(exc),
                            capture_id=int(row["id"]),
                            http_status=status,
                            retryable=retryable,
                        )
                    if isinstance(exc, RateLimited):
                        for pending in futures:
                            pending.cancel()
                        raise
                completed += 1
                elapsed = max(0.001, time.monotonic() - started)
                rate = completed / elapsed
                if callback:
                    callback(
                        ProgressEvent(
                            "download",
                            f"Downloaded/scanned {completed:,}/{total:,}; matches {matched:,}; errors {failures:,}; "
                            f"{rate:.1f}/s; active limit {limiter.current_limit}",
                            completed,
                            total,
                            {
                                "matched": matched,
                                "failures": failures,
                                "rate": rate,
                                "active_limit": limiter.current_limit,
                                "effective_delay": limiter.effective_delay,
                            },
                        )
                    )
                while len(futures) < max_inflight and submit_next():
                    pass
