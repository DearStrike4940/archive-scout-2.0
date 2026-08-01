from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from ..constants import REVIEW_STATUSES
from ..scanning.keywords import keyword_rules_to_lines, parse_keyword_rules, serialize_keyword_rules
from ..utils import normalize_search, utc_now


def get_or_create_target(database: sqlite3.Connection, pattern: str, settings: dict | None = None) -> int:
    row = database.execute("SELECT id FROM targets WHERE pattern=?", (pattern,)).fetchone()
    settings_json = json.dumps(settings or {}, ensure_ascii=False, sort_keys=True)
    if row:
        if settings is not None:
            database.execute("UPDATE targets SET settings_json=? WHERE id=?", (settings_json, row["id"]))
        return int(row["id"])
    cursor = database.execute(
        "INSERT INTO targets(pattern,settings_json,created_at) VALUES(?,?,?)",
        (pattern, settings_json, utc_now()),
    )
    return int(cursor.lastrowid)


def _capture_values(
    row: dict[str, str],
    target_id: int,
    query_signature: str,
    now: str,
) -> tuple:
    return (
        row["original"],
        row["timestamp"],
        target_id,
        query_signature,
        row.get("mimetype", ""),
        row.get("statuscode", ""),
        row.get("digest", ""),
        int(row.get("length") or 0),
        "pending",
        now,
        now,
    )


def upsert_captures(
    database: sqlite3.Connection,
    rows: list[dict[str, str]],
    target_id: int,
    query_signature: str,
) -> int:
    if not rows:
        return 0
    now = utc_now()
    values = [_capture_values(row, target_id, query_signature, now) for row in rows]
    before = database.total_changes
    database.executemany(
        """
        INSERT INTO captures(
            original_url,timestamp,target_id,query_signature,mimetype,statuscode,digest,length,state,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(original_url,timestamp,query_signature) DO UPDATE SET
            target_id=excluded.target_id,
            mimetype=excluded.mimetype,
            statuscode=excluded.statuscode,
            digest=excluded.digest,
            length=excluded.length,
            updated_at=excluded.updated_at
        """,
        values,
    )
    return database.total_changes - before


def upsert_capture(database: sqlite3.Connection, row: dict[str, str], target_id: int, query_signature: str) -> bool:
    existing = database.execute(
        "SELECT 1 FROM captures WHERE original_url=? AND timestamp=? AND query_signature=?",
        (row["original"], row["timestamp"], query_signature),
    ).fetchone()
    upsert_captures(database, [row], target_id, query_signature)
    return existing is None


def keyword_fingerprint(keywords: list[str | dict]) -> str:
    rules = parse_keyword_rules(keywords)
    raw = serialize_keyword_rules(rules)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_or_create_keyword_set(database: sqlite3.Connection, name: str, keywords: list[str | dict]) -> int:
    rules = parse_keyword_rules(keywords)
    lines = keyword_rules_to_lines(rules)
    fingerprint = keyword_fingerprint(lines)
    row = database.execute("SELECT id FROM keyword_sets WHERE fingerprint=?", (fingerprint,)).fetchone()
    now = utc_now()
    rules_json = serialize_keyword_rules(rules)
    keywords_json = json.dumps(lines, ensure_ascii=False)
    if row:
        database.execute(
            "UPDATE keyword_sets SET name=?,keywords_json=?,rules_json=?,updated_at=? WHERE id=?",
            (name, keywords_json, rules_json, now, row["id"]),
        )
        return int(row["id"])
    cursor = database.execute(
        "INSERT INTO keyword_sets(name,fingerprint,keywords_json,rules_json,created_at,updated_at) VALUES(?,?,?,?,?,?)",
        (name, fingerprint, keywords_json, rules_json, now, now),
    )
    return int(cursor.lastrowid)


def list_keyword_sets(database: sqlite3.Connection) -> list[sqlite3.Row]:
    return database.execute("SELECT * FROM keyword_sets ORDER BY name COLLATE NOCASE,id").fetchall()


def start_scan_run(
    database: sqlite3.Connection,
    keyword_set_id: int,
    name: str,
    minimum_score: int,
    source_operation: str,
    metadata: dict | None = None,
) -> int:
    cursor = database.execute(
        """
        INSERT INTO scan_runs(keyword_set_id,name,status,minimum_score,started_at,source_operation,metadata_json)
        VALUES(?,?,'running',?,?,?,?)
        """,
        (keyword_set_id, name, minimum_score, utc_now(), source_operation, json.dumps(metadata or {}, ensure_ascii=False)),
    )
    return int(cursor.lastrowid)


def finish_scan_run(database: sqlite3.Connection, scan_run_id: int, status: str = "complete") -> None:
    started = database.execute("SELECT started_at FROM scan_runs WHERE id=?", (scan_run_id,)).fetchone()
    completed = utc_now()
    document_count = database.execute(
        "SELECT COUNT(*) FROM document_matches WHERE scan_run_id=?", (scan_run_id,)
    ).fetchone()[0]
    minimum = database.execute("SELECT minimum_score FROM scan_runs WHERE id=?", (scan_run_id,)).fetchone()
    minimum_score = int(minimum[0]) if minimum else 1
    match_count = database.execute(
        "SELECT COUNT(*) FROM document_matches WHERE scan_run_id=? AND score>=? AND excluded=0 AND required_missing=0",
        (scan_run_id, minimum_score),
    ).fetchone()[0]
    duration = 0.0
    if started:
        try:
            from datetime import datetime
            duration = max(0.0, (datetime.fromisoformat(completed) - datetime.fromisoformat(started[0])).total_seconds())
        except Exception:
            duration = 0.0
    database.execute(
        """
        UPDATE scan_runs SET status=?,completed_at=?,document_count=?,match_count=?,duration_seconds=? WHERE id=?
        """,
        (status, completed, int(document_count), int(match_count), float(duration), scan_run_id),
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


def list_scan_runs(database: sqlite3.Connection) -> list[sqlite3.Row]:
    return database.execute(
        """
        SELECT sr.*,ks.name AS keyword_set_name
        FROM scan_runs sr JOIN keyword_sets ks ON ks.id=sr.keyword_set_id
        ORDER BY sr.id DESC
        """
    ).fetchall()


def rename_scan_run(database: sqlite3.Connection, scan_run_id: int, name: str) -> None:
    database.execute("UPDATE scan_runs SET name=? WHERE id=?", (name.strip() or f"Scan {scan_run_id}", scan_run_id))


def delete_scan_run(database: sqlite3.Connection, scan_run_id: int) -> None:
    database.execute("DELETE FROM scan_runs WHERE id=?", (scan_run_id,))


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
            scan_run_id,document_id,score,hits_json,fields_json,snippets_json,interesting_links_json,
            excluded,required_missing,proximity_json,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(scan_run_id,document_id) DO UPDATE SET
            score=excluded.score,hits_json=excluded.hits_json,fields_json=excluded.fields_json,
            snippets_json=excluded.snippets_json,interesting_links_json=excluded.interesting_links_json,
            excluded=excluded.excluded,required_missing=excluded.required_missing,
            proximity_json=excluded.proximity_json,updated_at=excluded.updated_at
        """,
        (
            scan_run_id,
            document_id,
            int(round(float(analysis.get("score") or 0))),
            json.dumps(analysis.get("hits") or {}, ensure_ascii=False, sort_keys=True),
            json.dumps(analysis.get("hit_fields") or {}, ensure_ascii=False, sort_keys=True),
            json.dumps(analysis.get("snippets") or [], ensure_ascii=False),
            json.dumps(analysis.get("interesting_links") or [], ensure_ascii=False),
            int(bool(analysis.get("excluded"))),
            int(bool(analysis.get("required_missing"))),
            json.dumps(analysis.get("proximity") or {}, ensure_ascii=False, sort_keys=True),
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
    database.execute("INSERT OR IGNORE INTO reviews(match_id,status) VALUES(?,'unreviewed')", (match_id,))
    return match_id


def record_error(
    database: sqlite3.Connection,
    operation: str,
    category: str,
    message: str,
    capture_id: int | None = None,
    document_id: int | None = None,
    media_capture_id: int | None = None,
    http_status: int | None = None,
    retryable: bool = True,
) -> int:
    now = utc_now()
    row = database.execute(
        """
        SELECT id,attempt_count FROM errors
        WHERE resolved=0 AND ignored=0 AND operation=? AND category=?
          AND COALESCE(capture_id,0)=COALESCE(?,0)
          AND COALESCE(document_id,0)=COALESCE(?,0)
          AND COALESCE(media_capture_id,0)=COALESCE(?,0)
        ORDER BY id DESC LIMIT 1
        """,
        (operation, category, capture_id, document_id, media_capture_id),
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
            capture_id,document_id,media_capture_id,operation,category,message,http_status,
            attempt_count,retryable,resolved,ignored,first_seen,last_seen
        ) VALUES(?,?,?,?,?,?,?,1,?,0,0,?,?)
        """,
        (capture_id, document_id, media_capture_id, operation, category, message, http_status, int(retryable), now, now),
    )
    return int(cursor.lastrowid)


def resolve_errors(
    database: sqlite3.Connection,
    capture_id: int | None = None,
    document_id: int | None = None,
    media_capture_id: int | None = None,
    operations: tuple[str, ...] | None = None,
) -> None:
    clauses = ["resolved=0"]
    params: list[object] = []
    if capture_id is not None:
        clauses.append("capture_id=?")
        params.append(capture_id)
    if document_id is not None:
        clauses.append("document_id=?")
        params.append(document_id)
    if media_capture_id is not None:
        clauses.append("media_capture_id=?")
        params.append(media_capture_id)
    if operations:
        clauses.append("operation IN (" + ",".join("?" for _ in operations) + ")")
        params.extend(operations)
    database.execute("UPDATE errors SET resolved=1,last_seen=? WHERE " + " AND ".join(clauses), (utc_now(), *params))


def ignore_errors(database: sqlite3.Connection, error_ids: list[int], ignored: bool = True) -> None:
    if not error_ids:
        return
    database.execute(
        "UPDATE errors SET ignored=?,last_seen=? WHERE id IN (" + ",".join("?" for _ in error_ids) + ")",
        (int(ignored), utc_now(), *error_ids),
    )


def list_errors(database: sqlite3.Connection, unresolved_only: bool = True) -> list[sqlite3.Row]:
    where = "WHERE e.resolved=0 AND e.ignored=0" if unresolved_only else ""
    return database.execute(
        f"""
        SELECT e.*,c.original_url,c.timestamp,d.path,mc.original_url AS media_url,mc.path AS media_path
        FROM errors e
        LEFT JOIN captures c ON c.id=e.capture_id
        LEFT JOIN documents d ON d.id=e.document_id
        LEFT JOIN media_captures mc ON mc.id=e.media_capture_id
        {where}
        ORDER BY e.last_seen DESC,e.id DESC
        """
    ).fetchall()


def set_review(database: sqlite3.Connection, match_id: int, status: str, reviewer: str = "") -> None:
    if status not in REVIEW_STATUSES:
        raise ValueError(f"unsupported review status: {status}")
    database.execute(
        """
        INSERT INTO reviews(match_id,status,reviewer,reviewed_at) VALUES(?,?,?,?)
        ON CONFLICT(match_id) DO UPDATE SET status=excluded.status,reviewer=excluded.reviewer,reviewed_at=excluded.reviewed_at
        """,
        (match_id, status, reviewer.strip() or None, utc_now() if status != "unreviewed" else None),
    )


def save_note(database: sqlite3.Connection, match_id: int, text: str, author: str = "") -> None:
    now = utc_now()
    row = database.execute("SELECT id FROM notes WHERE match_id=? ORDER BY id LIMIT 1", (match_id,)).fetchone()
    if row:
        database.execute(
            "UPDATE notes SET text=?,author=?,updated_at=? WHERE id=?",
            (text, author.strip() or None, now, row["id"]),
        )
    elif text.strip():
        database.execute(
            "INSERT INTO notes(match_id,text,author,created_at,updated_at) VALUES(?,?,?,?,?)",
            (match_id, text, author.strip() or None, now, now),
        )


def set_match_tags(database: sqlite3.Connection, match_id: int, tags: list[str]) -> None:
    database.execute("DELETE FROM match_tags WHERE match_id=?", (match_id,))
    for raw in tags:
        name = raw.strip()
        if not name:
            continue
        database.execute("INSERT OR IGNORE INTO tags(name) VALUES(?)", (name,))
        tag_id = database.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()["id"]
        database.execute("INSERT OR IGNORE INTO match_tags(match_id,tag_id) VALUES(?,?)", (match_id, tag_id))


def result_rows(
    database: sqlite3.Connection,
    scan_run_id: int,
    minimum_score: int = 0,
    review_status: str = "",
    search: str = "",
    limit: int = 10000,
) -> list[sqlite3.Row]:
    clauses = ["m.scan_run_id=?", "m.score>=?"]
    params: list[object] = [scan_run_id, minimum_score]
    if review_status:
        clauses.append("COALESCE(r.status,'unreviewed')=?")
        params.append(review_status)
    if search.strip():
        clauses.append("(LOWER(c.original_url) LIKE ? OR LOWER(d.title) LIKE ? OR LOWER(d.body_text) LIKE ?)")
        value = "%" + search.casefold() + "%"
        params.extend([value, value, value])
    params.append(limit)
    return database.execute(
        """
        SELECT m.*,d.path,d.title,d.body_text,d.size_bytes,c.original_url,c.timestamp,c.mimetype,
               COALESCE(r.status,'unreviewed') AS review_status,r.reviewer,r.reviewed_at,
               COALESCE((SELECT text FROM notes n WHERE n.match_id=m.id ORDER BY n.id LIMIT 1),'') AS note,
               COALESCE((SELECT GROUP_CONCAT(t.name, ', ') FROM match_tags mt JOIN tags t ON t.id=mt.tag_id WHERE mt.match_id=m.id),'') AS tags
        FROM document_matches m
        JOIN documents d ON d.id=m.document_id
        JOIN captures c ON c.id=d.capture_id
        LEFT JOIN reviews r ON r.match_id=m.id
        WHERE """ + " AND ".join(clauses) + " ORDER BY m.score DESC,c.timestamp,c.original_url LIMIT ?",
        params,
    ).fetchall()


def get_or_create_media_target(database: sqlite3.Connection, pattern: str) -> int:
    row = database.execute("SELECT id FROM media_targets WHERE pattern=?", (pattern,)).fetchone()
    if row:
        return int(row["id"])
    cursor = database.execute(
        "INSERT INTO media_targets(pattern,created_at) VALUES(?,?)", (pattern, utc_now())
    )
    return int(cursor.lastrowid)


def upsert_media_captures(
    database: sqlite3.Connection,
    items: list[tuple[dict[str, str], str, str]],
    target_id: int | None,
    query_signature: str,
    source_document_id: int | None = None,
    source_type: str = "cdx",
) -> int:
    if not items:
        return 0
    now = utc_now()
    values = [
        (
            row["original"],
            row["timestamp"],
            target_id,
            source_document_id,
            source_type,
            query_signature,
            media_kind,
            extension,
            row.get("mimetype", ""),
            row.get("statuscode", ""),
            row.get("digest", ""),
            int(row.get("length") or 0),
            "pending",
            now,
            now,
        )
        for row, media_kind, extension in items
    ]
    before = database.total_changes
    database.executemany(
        """
        INSERT INTO media_captures(
            original_url,timestamp,target_id,source_document_id,source_type,query_signature,media_kind,extension,
            mimetype,statuscode,digest,length,state,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(original_url,timestamp,query_signature) DO UPDATE SET
            target_id=excluded.target_id,
            source_document_id=COALESCE(excluded.source_document_id,media_captures.source_document_id),
            source_type=excluded.source_type,
            media_kind=excluded.media_kind,
            extension=excluded.extension,
            mimetype=excluded.mimetype,
            statuscode=excluded.statuscode,
            digest=excluded.digest,
            length=excluded.length,
            updated_at=excluded.updated_at
        """,
        values,
    )
    return database.total_changes - before


def upsert_media_capture(
    database: sqlite3.Connection,
    row: dict[str, str],
    target_id: int | None,
    query_signature: str,
    media_kind: str,
    extension: str,
    source_document_id: int | None = None,
    source_type: str = "cdx",
) -> bool:
    existing = database.execute(
        "SELECT 1 FROM media_captures WHERE original_url=? AND timestamp=? AND query_signature=?",
        (row["original"], row["timestamp"], query_signature),
    ).fetchone()
    upsert_media_captures(
        database,
        [(row, media_kind, extension)],
        target_id,
        query_signature,
        source_document_id,
        source_type,
    )
    return existing is None


def save_media_success(
    database: sqlite3.Connection,
    media_capture_id: int,
    path: Path,
    bytes_saved: int,
    content_hash: str,
    http_status: int,
    final_url: str,
) -> None:
    database.execute(
        """
        UPDATE media_captures SET state='downloaded',path=?,bytes_saved=?,content_hash=?,http_status=?,final_url=?,updated_at=?
        WHERE id=?
        """,
        (str(path), int(bytes_saved), content_hash, int(http_status), final_url, utc_now(), media_capture_id),
    )
    resolve_errors(database, media_capture_id=media_capture_id)
