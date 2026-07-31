from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Callable

from .cdx.indexer import index_archive
from .config import ProjectConfig, save_project_config
from .database.connection import open_database
from .database.repositories import (
    finish_scan_run,
    get_or_create_keyword_set,
    latest_scan_run,
    start_scan_run,
)
from .downloads.downloader import download_archive
from .downloads.retry import retry_error_urls
from .events import ProgressEvent, Stopped
from .projects.integrity import check_project_integrity
from .reports.text import generate_reports
from .scanning.rescanner import rescan_documents

SUPPORTED_MODES = {"all", "index", "download", "resume", "rescan", "retry_errors", "report", "integrity"}


def emit(callback: Callable[[ProgressEvent], None] | None, event: ProgressEvent) -> None:
    if callback:
        callback(event)


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
    if mode in {"all", "download", "resume", "rescan", "retry_errors"} and not config.keywords:
        raise ValueError("at least one keyword is required")
    stop_event = stop_event or threading.Event()
    config.output_dir.mkdir(parents=True, exist_ok=True)
    (config.output_dir / "captures").mkdir(exist_ok=True)
    (config.output_dir / "reports").mkdir(exist_ok=True)
    database = open_database(config.output_dir, migrate=True)
    scan_run_id: int | None = None
    try:
        save_project_config(config)
        if mode == "integrity":
            path = check_project_integrity(config.output_dir, database, callback)
            emit(callback, ProgressEvent("integrity", f"Integrity report written to {path}"))
            return {"integrity": path}
        if mode == "index":
            index_archive(config, database, stop_event, callback)
            return {"project": config.output_dir / "project.json"}
        keyword_set_id = get_or_create_keyword_set(database, config.keyword_set_name, config.keywords)
        if mode == "report":
            existing = latest_scan_run(database, keyword_set_id) or latest_scan_run(database)
            if existing is None:
                raise RuntimeError("this project does not contain a completed scan run")
            paths = generate_reports(config, database, existing)
            emit(callback, ProgressEvent("report", f"Reports written to {config.output_dir / 'reports'}"))
            return paths
        scan_run_id = start_scan_run(
            database,
            keyword_set_id,
            f"{config.keyword_set_name} ({mode})",
            config.minimum_score,
            mode,
        )
        database.commit()
        if mode == "all":
            index_archive(config, database, stop_event, callback)
            download_archive(config, database, scan_run_id, stop_event, callback, states=("pending",))
        elif mode in {"download", "resume"}:
            download_archive(config, database, scan_run_id, stop_event, callback, states=("pending",))
        elif mode == "rescan":
            rescan_documents(database, scan_run_id, config.keywords, stop_event, callback)
        elif mode == "retry_errors":
            retry_error_urls(config, database, scan_run_id, stop_event, callback)
        finish_scan_run(database, scan_run_id, "complete")
        database.commit()
        paths = generate_reports(config, database, scan_run_id)
        emit(callback, ProgressEvent("report", f"Reports written to {config.output_dir / 'reports'}"))
        return paths
    except Stopped:
        with database:
            database.execute("UPDATE captures SET state='pending' WHERE state='downloading'")
            if scan_run_id is not None:
                finish_scan_run(database, scan_run_id, "interrupted")
        emit(callback, ProgressEvent("stopped", "Stopped. Progress was saved and can be resumed."))
        raise
    except Exception:
        if scan_run_id is not None:
            with database:
                finish_scan_run(database, scan_run_id, "failed")
        raise
    finally:
        database.close()
