from __future__ import annotations

from ..constants import SCHEMA_VERSION

SCHEMA_SQL = f"""
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS schema_info(
    version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS project_meta(
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS targets(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL UNIQUE,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS captures(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_url TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    target_id INTEGER,
    query_signature TEXT NOT NULL,
    mimetype TEXT,
    statuscode TEXT,
    digest TEXT,
    length INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT 'pending',
    download_attempts INTEGER NOT NULL DEFAULT 0,
    document_id INTEGER,
    http_status INTEGER,
    final_url TEXT,
    bytes_saved INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(original_url,timestamp,query_signature),
    FOREIGN KEY(target_id) REFERENCES targets(id)
);
CREATE INDEX IF NOT EXISTS captures_state_idx ON captures(state,download_attempts,timestamp);
CREATE INDEX IF NOT EXISTS captures_original_idx ON captures(original_url,timestamp);
CREATE INDEX IF NOT EXISTS captures_signature_idx ON captures(query_signature,timestamp);
CREATE TABLE IF NOT EXISTS documents(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capture_id INTEGER NOT NULL UNIQUE,
    path TEXT NOT NULL,
    title TEXT,
    body_text TEXT,
    links_json TEXT,
    content_hash TEXT,
    normalized_hash TEXT,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(capture_id) REFERENCES captures(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS documents_hash_idx ON documents(content_hash);
CREATE INDEX IF NOT EXISTS documents_normalized_hash_idx ON documents(normalized_hash);
CREATE TABLE IF NOT EXISTS keyword_sets(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    fingerprint TEXT NOT NULL UNIQUE,
    keywords_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scan_runs(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword_set_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    minimum_score INTEGER NOT NULL DEFAULT 1,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    source_operation TEXT NOT NULL,
    FOREIGN KEY(keyword_set_id) REFERENCES keyword_sets(id)
);
CREATE INDEX IF NOT EXISTS scan_runs_status_idx ON scan_runs(status,started_at);
CREATE TABLE IF NOT EXISTS document_matches(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_run_id INTEGER NOT NULL,
    document_id INTEGER NOT NULL,
    score INTEGER NOT NULL DEFAULT 0,
    hits_json TEXT,
    fields_json TEXT,
    snippets_json TEXT,
    interesting_links_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(scan_run_id,document_id),
    FOREIGN KEY(scan_run_id) REFERENCES scan_runs(id) ON DELETE CASCADE,
    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS document_matches_score_idx ON document_matches(scan_run_id,score DESC);
CREATE TABLE IF NOT EXISTS keyword_hits(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    label TEXT NOT NULL,
    count INTEGER NOT NULL,
    fields_json TEXT,
    UNIQUE(match_id,label),
    FOREIGN KEY(match_id) REFERENCES document_matches(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS errors(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capture_id INTEGER,
    document_id INTEGER,
    operation TEXT NOT NULL,
    category TEXT NOT NULL,
    message TEXT NOT NULL,
    http_status INTEGER,
    attempt_count INTEGER NOT NULL DEFAULT 1,
    retryable INTEGER NOT NULL DEFAULT 1,
    resolved INTEGER NOT NULL DEFAULT 0,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    FOREIGN KEY(capture_id) REFERENCES captures(id) ON DELETE CASCADE,
    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS errors_unresolved_idx ON errors(resolved,retryable,operation,category);
CREATE TABLE IF NOT EXISTS index_state(
    target_id INTEGER NOT NULL,
    year INTEGER NOT NULL,
    query_signature TEXT NOT NULL,
    resume_key TEXT,
    complete INTEGER NOT NULL DEFAULT 0,
    seen INTEGER NOT NULL DEFAULT 0,
    error_id INTEGER,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(target_id,year,query_signature),
    FOREIGN KEY(target_id) REFERENCES targets(id) ON DELETE CASCADE,
    FOREIGN KEY(error_id) REFERENCES errors(id)
);
CREATE TABLE IF NOT EXISTS reviews(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'unreviewed',
    reviewer TEXT,
    reviewed_at TEXT,
    UNIQUE(match_id),
    FOREIGN KEY(match_id) REFERENCES document_matches(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS notes(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER,
    capture_id INTEGER,
    text TEXT NOT NULL,
    author TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(match_id) REFERENCES document_matches(id) ON DELETE CASCADE,
    FOREIGN KEY(capture_id) REFERENCES captures(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS tags(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS match_tags(
    match_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY(match_id,tag_id),
    FOREIGN KEY(match_id) REFERENCES document_matches(id) ON DELETE CASCADE,
    FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS duplicate_groups(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    method TEXT NOT NULL,
    representative_document_id INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY(representative_document_id) REFERENCES documents(id)
);
CREATE TABLE IF NOT EXISTS duplicate_members(
    group_id INTEGER NOT NULL,
    document_id INTEGER NOT NULL,
    similarity REAL NOT NULL DEFAULT 1.0,
    PRIMARY KEY(group_id,document_id),
    FOREIGN KEY(group_id) REFERENCES duplicate_groups(id) ON DELETE CASCADE,
    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS forum_threads(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_key TEXT NOT NULL UNIQUE,
    title TEXT,
    profile TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS forum_posts(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id INTEGER NOT NULL,
    document_id INTEGER NOT NULL,
    post_key TEXT,
    username TEXT,
    posted_at TEXT,
    position INTEGER,
    body_text TEXT,
    UNIQUE(thread_id,document_id,post_key),
    FOREIGN KEY(thread_id) REFERENCES forum_threads(id) ON DELETE CASCADE,
    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS extractions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    extractor_name TEXT NOT NULL,
    value TEXT NOT NULL,
    context TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS snapshot_diffs(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    earlier_capture_id INTEGER NOT NULL,
    later_capture_id INTEGER NOT NULL,
    summary_json TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(earlier_capture_id,later_capture_id),
    FOREIGN KEY(earlier_capture_id) REFERENCES captures(id) ON DELETE CASCADE,
    FOREIGN KEY(later_capture_id) REFERENCES captures(id) ON DELETE CASCADE
);
"""


def initialize_schema(database) -> None:
    database.executescript(SCHEMA_SQL)
    row = database.execute("SELECT version FROM schema_info LIMIT 1").fetchone()
    if row is None:
        database.execute("INSERT INTO schema_info(version) VALUES(?)", (SCHEMA_VERSION,))
    elif int(row[0]) != SCHEMA_VERSION:
        raise RuntimeError(f"unsupported Archive Scout schema version: {row[0]}")
    try:
        database.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(title,body_text,original_url)"
        )
        database.execute("INSERT OR REPLACE INTO project_meta(key,value) VALUES('fts5','1')")
    except Exception:
        database.execute("INSERT OR REPLACE INTO project_meta(key,value) VALUES('fts5','0')")
