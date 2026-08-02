from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Callable

from .cdx.client import RateLimitDeferred
from .cdx.indexer import index_archive
from .config import KeywordSetConfig, ProjectConfig, save_project_config
from .database.connection import open_database
from .database.repositories import finish_scan_run, get_or_create_keyword_set, latest_scan_run, start_scan_run
from .downloads.downloader import download_archive
from .downloads.retry import retry_error_urls
from .events import ProgressEvent, Stopped
from .media.downloader import download_media, retry_media_errors
from .media.indexer import index_media
from .media.reports import generate_media_reports
from .projects.integrity import check_project_integrity
from .reports.text import generate_reports
from .scanning.jobs import ScanJob
from .scanning.rescanner import rescan_keyword_sets

SUPPORTED_MODES = {
    "all", "index", "download", "resume", "rescan", "retry_errors", "report", "integrity",
    "media_all", "media_index", "media_download", "media_retry",
}


def emit(callback: Callable[[ProgressEvent], None] | None, event: ProgressEvent) -> None:
    if callback:
        callback(event)


def prepare_scan_jobs(
    database: sqlite3.Connection,
    config: ProjectConfig,
    mode: str,
) -> list[ScanJob]:
    jobs: list[ScanJob] = []
    selected = config.selected_keyword_sets()
    if not selected:
        raise ValueError("select at least one keyword set containing at least one rule")
    seen_keyword_set_ids: set[int] = set()
    for keyword_set in selected:
        keyword_set_id = get_or_create_keyword_set(database, keyword_set.name, keyword_set.rules)
        if keyword_set_id in seen_keyword_set_ids:
            continue
        seen_keyword_set_ids.add(keyword_set_id)
        run_id = start_scan_run(
            database,
            keyword_set_id,
            f"{keyword_set.name} ({mode})",
            config.minimum_score,
            mode,
            {"keyword_set": keyword_set.name, "rules": keyword_set.rules},
        )
        jobs.append(ScanJob.create(run_id, keyword_set.name, keyword_set.rules))
    database.commit()
    return jobs


def finish_jobs(database: sqlite3.Connection, jobs: list[ScanJob], status: str) -> None:
    for job in jobs:
        finish_scan_run(database, job.scan_run_id, status)


def generate_job_reports(config: ProjectConfig, database: sqlite3.Connection, jobs: list[ScanJob]) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for index, job in enumerate(jobs, 1):
        generated = generate_reports(config, database, job.scan_run_id)
        if index == 1:
            paths.update(generated)
        paths[f"scan_{job.scan_run_id}_folder"] = generated["scan_folder"]
    return paths


def run_project(
    config: ProjectConfig,
    mode: str = "all",
    stop_event: threading.Event | None = None,
    callback: Callable[[ProgressEvent], None] | None = None,
) -> dict[str, Path]:
    config = config.normalized()
    if mode not in SUPPORTED_MODES:
        raise ValueError(f"unsupported mode: {mode}")
    if config.from_date > config.to_date:
        raise ValueError("start date must not be later than end date")
    if mode in {"all", "index"} and not config.targets:
        raise ValueError("at least one target is required")
    if mode.startswith("media_") and not (config.media.targets or config.targets):
        raise ValueError("at least one media target or site target is required")
    if mode in {"all", "download", "resume", "rescan", "retry_errors"} and not config.selected_keyword_sets():
        raise ValueError("select at least one keyword set")
    stop_event = stop_event or threading.Event()
    config.output_dir.mkdir(parents=True, exist_ok=True)
    (config.output_dir / "captures").mkdir(exist_ok=True)
    (config.output_dir / "media").mkdir(exist_ok=True)
    (config.output_dir / "reports").mkdir(exist_ok=True)
    database = open_database(config.output_dir, migrate=True)
    jobs: list[ScanJob] = []
    try:
        save_project_config(config)
        if mode == "integrity":
            path = check_project_integrity(config.output_dir, database, callback)
            emit(callback, ProgressEvent("integrity", f"Integrity report written to {path}"))
            return {"integrity": path}
        if mode == "index":
            index_archive(config, database, stop_event, callback)
            return {"project": config.output_dir / "project.json"}
        if mode == "report":
            existing = latest_scan_run(database)
            if existing is None:
                raise RuntimeError("this project does not contain a completed scan run")
            paths = generate_reports(config, database, existing)
            emit(callback, ProgressEvent("report", f"Reports written to {config.output_dir / 'reports'}"))
            return paths
        if mode == "media_index":
            index_media(config, database, stop_event, callback)
            return generate_media_reports(config, database)
        if mode == "media_download":
            download_media(config, database, stop_event, callback)
            return generate_media_reports(config, database)
        if mode == "media_retry":
            retry_media_errors(config, database, stop_event, callback)
            return generate_media_reports(config, database)
        if mode == "media_all":
            index_media(config, database, stop_event, callback)
            download_media(config, database, stop_event, callback)
            return generate_media_reports(config, database)

        if mode == "all":
            index_archive(config, database, stop_event, callback)

        jobs = prepare_scan_jobs(database, config, mode)
        primary_run_id = jobs[0].scan_run_id
        if mode == "all":
            download_archive(config, database, primary_run_id, stop_event, callback, states=("pending",), scan_jobs=jobs)
        elif mode in {"download", "resume"}:
            download_archive(config, database, primary_run_id, stop_event, callback, states=("pending",), scan_jobs=jobs)
        elif mode == "rescan":
            rescan_keyword_sets(database, jobs, stop_event, callback)
        elif mode == "retry_errors":
            retry_error_urls(config, database, primary_run_id, stop_event, callback, jobs)
            media_error_count = database.execute(
                "SELECT COUNT(*) FROM errors WHERE resolved=0 AND ignored=0 AND retryable=1 AND media_capture_id IS NOT NULL"
            ).fetchone()[0]
            if media_error_count:
                retry_media_errors(
                    config,
                    database,
                    stop_event,
                    callback,
                    config.retry_media_capture_ids or None,
                )
        finish_jobs(database, jobs, "complete")
        database.commit()
        paths = generate_job_reports(config, database, jobs)
        if mode == "retry_errors" and database.execute("SELECT COUNT(*) FROM media_captures").fetchone()[0]:
            paths.update(generate_media_reports(config, database))
        if mode == "all" and config.media.enabled:
            index_media(config, database, stop_event, callback)
            download_media(config, database, stop_event, callback)
            paths.update(generate_media_reports(config, database))
        emit(callback, ProgressEvent("report", f"Reports written to {config.output_dir / 'reports'}"))
        return paths
    except RateLimitDeferred as exc:
        with database:
            database.execute("UPDATE captures SET state='pending' WHERE state='downloading'")
            database.execute("UPDATE media_captures SET state='pending' WHERE state='downloading'")
            finish_jobs(database, jobs, "interrupted")
        emit(
            callback,
            ProgressEvent(
                "rate_limit",
                f"Wayback stayed rate limited beyond the wait budget. Progress was saved; use Resume later. {exc}",
            ),
        )
        raise
    except Stopped:
        with database:
            database.execute("UPDATE captures SET state='pending' WHERE state='downloading'")
            database.execute("UPDATE media_captures SET state='pending' WHERE state='downloading'")
            finish_jobs(database, jobs, "interrupted")
        emit(callback, ProgressEvent("stopped", "Stopped. Progress was saved and can be resumed."))
        raise
    except Exception:
        if jobs:
            with database:
                finish_jobs(database, jobs, "failed")
        raise
    finally:
        database.close()
