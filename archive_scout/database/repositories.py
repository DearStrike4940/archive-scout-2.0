from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from ..utils import normalize_search, utc_now


def get_or_create_target(database: sqlite3.Connection, pattern: str) -> int:
    row = database.execute("SELECT id FROM targets WHERE pattern=?", (pattern,)).fetchone()
    if row:
        return int(row["id"])
    cursor = database.execute(
        "INSERT INTO targets(pattern,created_at) VALUES(?,?)",
        (pattern, utc_now()),
    )
    return int(cursor.lastrowid)


def upsert_capture(database: sqlite3.Connection, row: dict[str, str], target_id: int, query_signature: str) -> bool:
    existing = database.execute(
        "SELECT id FROM captures WHERE original_url=? AND timestamp=? AND query_signature=?",
        (row["original"], row["timestamp"], query_signature),
    ).fetchone()
    now = utc_now()
    if existing:
        database.execute(
            """
            UPDATE captures SET target_id=?,mimetype=?,statuscode=?,digest=?,length=?,updated_at=?
            WHERE id=?
            """,
            (
                target_id,
                row.get("mimetype", ""),
                row.get("statuscode", ""),
                row.get("digest", ""),
                int(row.get("length") or 0),
                now,
                existing["id"],
            ),
        )
        return False
    database.execute(
        """
        INSERT INTO captures(
            original_url,timestamp,target_id,query_signature,mimetype,statuscode,digest,length,state,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            row["original"], row["timestamp"], target_id, query_signature,
            row.get("mimetype", ""), row.get("statuscode", ""), row.get("digest", ""),
            int(row.get("length") or 0), "pending", now, now,
        ),
    )
    return True


def keyword_fingerprint(keywords: list[str]) -> str:
    normalized = [normalize_search(value) for value in keywords if value.strip()]
    raw = json.dumps(normalized, ensure_ascii=False, sort_keys=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_or_create_keyword_set(database: sqlite3.Connection, name: str, keywords: list[str]) -> int:
    fingerprint = keyword_fingerprint(keywords)
    row = database.execute("SELECT id FROM keyword_sets WHERE fingerprint=?", (fingerprint,)).fetchone()
    now = utc_now()
    if row:
        database.execute(
            "UPDATE keyword_sets SET name=?,updated_at=? WHERE id=?",
            (name, now, row["id"]),
        )
        return int(row["id"])
    cursor = database.execute(
        "INSERT INTO keyword_sets(name,fingerprint,keywords_json,created_at,updated_at) VALUES(?,?,?,?,?)",
        (name, fingerprint, json.dumps(keywords, ensure_ascii=False), now, now),
    )
    return int(cursor.lastrowid)


def start_scan_run(database: sqlite3.Connection, keyword_set_id: int, name: str, minimum_score: int, source_operation: str) -> int:
    cursor = database.execute(
        """
        INSERT INTO scan_runs(keyword_set_id,name,status,minimum_score,started_at,source_operation)
        VALUES(?,?,'running',?,?,?)
        """,
        (keyword_set_id, name, minimum_score, utc_now(), source_operation),
    )
    return int(cursor.lastrowid)


def finish_scan_run(database: sqlite3.Connection, scan_run_id: int, status: str = "complete") -> None:
    database.execute(
        "UPDATE scan_runs SET status=?,completed_at=? WHERE id=?",
        (status, utc_now(), scan_run_id),
    )


def latest_scan_run(database: sqlite3.Connection, keyword_set_id: int | None = None) -> int | None:
    if keyword_set_id is None:
        row = database.execute(
            "SELECT id FROM scan_runs WHERE status='complete' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    else:
        row = database.execute(
            "SELECT id FROM scan_runs WHERE status='complete' AND keyword_set_id=? ORDER BY id DESC LIMIT 1",
            (keyword_set_id,),
        ).fetchone()
    return int(row["id"]) if row else None


def upsert_document(
    database: sqlite3.Connection,
    capture_id: int,
    path: Path,
    title: str,
    body_text: str,
    links: list[str],
    content_hash: str,
    normalized_hash: str,
    size_bytes: int,
) -> int:
    now = utc_now()
    row = database.execute("SELECT id FROM documents WHERE capture_id=?", (capture_id,)).fetchone()
    links_json = json.dumps(links, ensure_ascii=False)
    if row:
        document_id = int(row["id"])
        database.execute(
            """
            UPDATE documents SET path=?,title=?,body_text=?,links_json=?,content_hash=?,normalized_hash=?,size_bytes=?,updated_at=?
            WHERE id=?
            """,
            (str(path), title, body_text, links_json, content_hash, normalized_hash, size_bytes, now, document_id),
        )
    else:
        cursor = database.execute(
            """
            INSERT INTO documents(capture_id,path,title,body_text,links_json,content_hash,normalized_hash,size_bytes,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (capture_id, str(path), title, body_text, links_json, content_hash, normalized_hash, size_bytes, now, now),
        )
        document_id = int(cursor.lastrowid)
    database.execute(
        "UPDATE captures SET document_id=?,state='downloaded',bytes_saved=?,updated_at=? WHERE id=?",
        (document_id, size_bytes, now, capture_id),
    )
    fts_enabled = database.execute("SELECT value FROM project_meta WHERE key='fts5'").fetchone()
    if fts_enabled and fts_enabled["value"] == "1":
        original = database.execute("SELECT original_url FROM captures WHERE id=?", (capture_id,)).fetchone()["original_url"]
        database.execute("DELETE FROM documents_fts WHERE rowid=?", (document_id,))
        database.execute(
            "INSERT INTO documents_fts(rowid,title,body_text,original_url) VALUES(?,?,?,?)",
            (document_id, title, body_text, original),
        )
    return document_id


def save_match(database: sqlite3.Connection, scan_run_id: int, document_id: int, analysis: dict) -> int:
    now = utc_now()
    database.execute(
        """
        INSERT INTO document_matches(
            scan_run_id,document_id,score,hits_json,fields_json,snippets_json,interesting_links_json,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?)
        ON CONFLICT(scan_run_id,document_id) DO UPDATE SET
            score=excluded.score,hits_json=excluded.hits_json,fields_json=excluded.fields_json,
            snippets_json=excluded.snippets_json,interesting_links_json=excluded.interesting_links_json,
            updated_at=excluded.updated_at
        """,
        (
            scan_run_id,
            document_id,
            int(analysis.get("score") or 0),
            json.dumps(analysis.get("hits") or {}, ensure_ascii=False, sort_keys=True),
            json.dumps(analysis.get("hit_fields") or {}, ensure_ascii=False, sort_keys=True),
            json.dumps(analysis.get("snippets") or [], ensure_ascii=False),
            json.dumps(analysis.get("interesting_links") or [], ensure_ascii=False),
            now,
            now,
        ),
    )
    row = database.execute(
        "SELECT id FROM document_matches WHERE scan_run_id=? AND document_id=?",
        (scan_run_id, document_id),
    ).fetchone()
    match_id = int(row["id"])
    database.execute("DELETE FROM keyword_hits WHERE match_id=?", (match_id,))
    fields = analysis.get("hit_fields") or {}
    for label, count in (analysis.get("hits") or {}).items():
        database.execute(
            "INSERT INTO keyword_hits(match_id,label,count,fields_json) VALUES(?,?,?,?)",
            (match_id, label, int(count), json.dumps(fields.get(label, []), ensure_ascii=False)),
        )
    return match_id


def record_error(
    database: sqlite3.Connection,
    operation: str,
    category: str,
    message: str,
    capture_id: int | None = None,
    document_id: int | None = None,
    http_status: int | None = None,
    retryable: bool = True,
) -> int:
    now = utc_now()
    row = database.execute(
        """
        SELECT id,attempt_count FROM errors
        WHERE resolved=0 AND operation=? AND category=? AND COALESCE(capture_id,0)=COALESCE(?,0)
          AND COALESCE(document_id,0)=COALESCE(?,0)
        ORDER BY id DESC LIMIT 1
        """,
        (operation, category, capture_id, document_id),
    ).fetchone()
    if row:
        database.execute(
            "UPDATE errors SET message=?,http_status=?,attempt_count=?,retryable=?,last_seen=? WHERE id=?",
            (message, http_status, int(row["attempt_count"]) + 1, int(retryable), now, row["id"]),
        )
        return int(row["id"])
    cursor = database.execute(
        """
        INSERT INTO errors(
            capture_id,document_id,operation,category,message,http_status,attempt_count,retryable,resolved,first_seen,last_seen
        ) VALUES(?,?,?,?,?,?,1,?,0,?,?)
        """,
        (capture_id, document_id, operation, category, message, http_status, int(retryable), now, now),
    )
    return int(cursor.lastrowid)


def resolve_errors(database: sqlite3.Connection, capture_id: int | None = None, document_id: int | None = None, operations: tuple[str, ...] | None = None) -> None:
    clauses = ["resolved=0"]
    params: list[object] = []
    if capture_id is not None:
        clauses.append("capture_id=?")
        params.append(capture_id)
    if document_id is not None:
        clauses.append("document_id=?")
        params.append(document_id)
    if operations:
        clauses.append("operation IN (" + ",".join("?" for _ in operations) + ")")
        params.extend(operations)
    database.execute("UPDATE errors SET resolved=1,last_seen=? WHERE " + " AND ".join(clauses), (utc_now(), *params))
