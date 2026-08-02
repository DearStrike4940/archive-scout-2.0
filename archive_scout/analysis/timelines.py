from __future__ import annotations

import sqlite3


def build_timeline(database: sqlite3.Connection) -> list[dict]:
    rows = database.execute(
        """
        SELECT pe.id,pe.method,pe.similarity,pe.source_timestamp,pe.mirror_timestamp,
               cs.original_url AS source_url,cm.original_url AS mirror_url
        FROM provenance_edges pe
        JOIN documents ds ON ds.id=pe.source_document_id
        JOIN captures cs ON cs.id=ds.capture_id
        JOIN documents dm ON dm.id=pe.mirror_document_id
        JOIN captures cm ON cm.id=dm.capture_id
        ORDER BY pe.source_timestamp,pe.mirror_timestamp,pe.id
        """
    ).fetchall()
    return [dict(row) for row in rows]
