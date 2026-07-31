from __future__ import annotations

import sqlite3


def search_documents(database: sqlite3.Connection, query: str, limit: int = 500) -> list[sqlite3.Row]:
    enabled = database.execute("SELECT value FROM project_meta WHERE key='fts5'").fetchone()
    if not enabled or enabled["value"] != "1":
        raise RuntimeError("SQLite FTS5 is not available in this Python build")
    return database.execute(
        """
        SELECT d.*,c.original_url,c.timestamp,bm25(documents_fts) AS rank
        FROM documents_fts
        JOIN documents d ON d.id=documents_fts.rowid
        JOIN captures c ON c.id=d.capture_id
        WHERE documents_fts MATCH ?
        ORDER BY rank LIMIT ?
        """,
        (query, limit),
    ).fetchall()
