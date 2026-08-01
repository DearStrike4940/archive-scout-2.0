from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from ..content import parse_page
from ..database.repositories import (
    get_or_create_keyword_set,
    get_or_create_target,
    record_error,
    save_match,
    start_scan_run,
    finish_scan_run,
    upsert_document,
)
from ..database.schema import initialize_schema
from ..utils import hash_text, json_value, normalize_search, utc_now


def legacy_columns(database: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in database.execute(f"PRAGMA table_info({table})")}


def is_legacy_archive_scout(path: Path) -> bool:
    if not path.exists():
        return False
    database = None
    try:
        database = sqlite3.connect(path)
        tables = {row[0] for row in database.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "captures" not in tables or "schema_info" in tables:
            return False
        columns = legacy_columns(database, "captures")
        return "original" in columns and "timestamp" in columns
    except Exception:
        return False
    finally:
        if database is not None:
            database.close()


def migrate_legacy_project(root: Path) -> Path:
    root = root.expanduser().resolve()
    database_path = root / "archive_scout.sqlite3"
    if not is_legacy_archive_scout(database_path):
        return database_path
    backup_path = root / "archive_scout.v1.backup.sqlite3"
    temp_path = root / "archive_scout.v3.migrating.sqlite3"
    if temp_path.exists():
        temp_path.unlink()
    legacy = sqlite3.connect(database_path)
    legacy.row_factory = sqlite3.Row
    if not backup_path.exists():
        backup = sqlite3.connect(backup_path)
        legacy.backup(backup)
        backup.close()
    modern = sqlite3.connect(temp_path)
    modern.row_factory = sqlite3.Row
    modern.execute("PRAGMA foreign_keys=ON")
    initialize_schema(modern)
    project_payload: dict = {}
    project_path = root / "project.json"
    if project_path.exists():
        try:
            project_payload = json.loads(project_path.read_text(encoding="utf-8"))
        except Exception:
            project_payload = {}
    keywords = list(project_payload.get("keywords") or ["Imported legacy results"])
    keyword_set_id = get_or_create_keyword_set(modern, "Imported legacy keywords", keywords)
    scan_run_id = start_scan_run(modern, keyword_set_id, "Imported Archive Scout 1.x results", 1, "migration")
    capture_columns = legacy_columns(legacy, "captures")
    rows = legacy.execute("SELECT * FROM captures ORDER BY timestamp,original").fetchall()
    now = utc_now()
    for row in rows:
        target_id = get_or_create_target(modern, str(row["source_target"] or "legacy-import/*"))
        signature = str(row["query_signature"] or "legacy") if "query_signature" in capture_columns else "legacy"
        state = str(row["state"] or "pending")
        mapped_state = {
            "done": "downloaded",
            "downloading": "pending",
            "error": "error",
            "skipped": "skipped",
            "pending": "pending",
        }.get(state, state)
        cursor = modern.execute(
            """
            INSERT INTO captures(
                original_url,timestamp,target_id,query_signature,mimetype,statuscode,digest,length,state,
                download_attempts,http_status,final_url,bytes_saved,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row["original"],
                row["timestamp"],
                target_id,
                signature,
                row["mimetype"] if "mimetype" in capture_columns else "",
                row["statuscode"] if "statuscode" in capture_columns else "",
                row["digest"] if "digest" in capture_columns else "",
                int(row["length"] or 0) if "length" in capture_columns else 0,
                mapped_state,
                int(row["attempts"] or 0) if "attempts" in capture_columns else 0,
                row["http_status"] if "http_status" in capture_columns else None,
                row["final_url"] if "final_url" in capture_columns else None,
                int(row["bytes_saved"] or 0) if "bytes_saved" in capture_columns else 0,
                now,
                now,
            ),
        )
        capture_id = int(cursor.lastrowid)
        path_value = row["path"] if "path" in capture_columns else None
        document_id = None
        if path_value:
            path = Path(path_value)
            if not path.is_absolute():
                path = root / path
            if path.exists():
                try:
                    raw = path.read_text(encoding="utf-8", errors="replace")
                    title, visible, links = parse_page(raw, row["original"])
                    document_id = upsert_document(
                        modern,
                        capture_id,
                        path,
                        str(row["title"] or title) if "title" in capture_columns else title,
                        visible,
                        links,
                        hash_text(raw),
                        hash_text(normalize_search(visible)),
                        path.stat().st_size,
                    )
                except Exception as exc:
                    record_error(
                        modern,
                        "migration",
                        "import_failure",
                        repr(exc),
                        capture_id=capture_id,
                        retryable=True,
                    )
            else:
                record_error(
                    modern,
                    "migration",
                    "missing_local_file",
                    f"legacy file is missing: {path}",
                    capture_id=capture_id,
                    retryable=True,
                )
        if document_id is not None:
            analysis = {
                "score": int(row["score"] or 0) if "score" in capture_columns else 0,
                "hits": json_value(row["keyword_hits"], {}) if "keyword_hits" in capture_columns else {},
                "hit_fields": json_value(row["hit_fields"], {}) if "hit_fields" in capture_columns else {},
                "snippets": json_value(row["snippets"], []) if "snippets" in capture_columns else [],
                "interesting_links": json_value(row["interesting_links"], []) if "interesting_links" in capture_columns else [],
            }
            save_match(modern, scan_run_id, document_id, analysis)
        legacy_error = row["error"] if "error" in capture_columns else None
        if legacy_error:
            record_error(
                modern,
                "download" if mapped_state == "error" else "legacy",
                "legacy_error",
                str(legacy_error),
                capture_id=capture_id,
                document_id=document_id,
                retryable=mapped_state == "error",
            )
    if "index_state" in {row[0] for row in legacy.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
        columns = legacy_columns(legacy, "index_state")
        for row in legacy.execute("SELECT * FROM index_state"):
            target_id = get_or_create_target(modern, str(row["target"]))
            modern.execute(
                """
                INSERT OR REPLACE INTO index_state(target_id,year,query_signature,resume_key,complete,seen,error_id,updated_at)
                VALUES(?,?,?,?,?,?,NULL,?)
                """,
                (
                    target_id,
                    int(row["year"]),
                    str(row["query_signature"] if "query_signature" in columns else "legacy"),
                    row["resume_key"],
                    int(row["complete"] or 0),
                    int(row["seen"] or 0),
                    row["updated_at"] or now,
                ),
            )
    finish_scan_run(modern, scan_run_id)
    modern.execute("INSERT OR REPLACE INTO project_meta(key,value) VALUES('migrated_from','1.x')")
    modern.execute("INSERT OR REPLACE INTO project_meta(key,value) VALUES('migration_backup',?)", (str(backup_path),))
    modern.commit()
    modern.close()
    legacy.close()
    os.replace(temp_path, database_path)
    return database_path
