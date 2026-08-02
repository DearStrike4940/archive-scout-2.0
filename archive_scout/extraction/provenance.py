from __future__ import annotations

import sqlite3
from collections import defaultdict
from urllib.parse import urlsplit

from ..utils import utc_now


def trace_provenance(database: sqlite3.Connection) -> int:
    rows = database.execute(
        """
        SELECT dg.id AS group_id,dg.method,dm.document_id,dm.similarity,
               c.original_url,c.timestamp
        FROM duplicate_groups dg
        JOIN duplicate_members dm ON dm.group_id=dg.id
        JOIN documents d ON d.id=dm.document_id
        JOIN captures c ON c.id=d.capture_id
        ORDER BY dg.id,c.timestamp,dm.document_id
        """
    ).fetchall()
    grouped: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        grouped[int(row["group_id"])].append(row)
    created = 0
    with database:
        database.execute("DELETE FROM provenance_edges")
        for items in grouped.values():
            if len(items) < 2:
                continue
            source = items[0]
            source_host = (urlsplit(str(source["original_url"])).hostname or "").casefold()
            for mirror in items[1:]:
                mirror_host = (urlsplit(str(mirror["original_url"])).hostname or "").casefold()
                if source_host == mirror_host and source["original_url"] == mirror["original_url"]:
                    continue
                database.execute(
                    """
                    INSERT OR IGNORE INTO provenance_edges(
                        source_document_id,mirror_document_id,method,similarity,
                        source_timestamp,mirror_timestamp,created_at
                    ) VALUES(?,?,?,?,?,?,?)
                    """,
                    (
                        source["document_id"], mirror["document_id"], source["method"],
                        float(mirror["similarity"]), source["timestamp"], mirror["timestamp"], utc_now(),
                    ),
                )
                created += 1
    return created
