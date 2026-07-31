from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable

from ..events import ProgressEvent
from ..utils import atomic_write_text, utc_now


def check_project_integrity(
    root: Path,
    database: sqlite3.Connection,
    callback: Callable[[ProgressEvent], None] | None = None,
) -> Path:
    issues: list[str] = []
    referenced: set[Path] = set()
    documents = database.execute(
        """
        SELECT d.id,d.path,d.size_bytes,c.id AS capture_id,c.original_url,c.state
        FROM documents d JOIN captures c ON c.id=d.capture_id ORDER BY d.id
        """
    ).fetchall()
    total = len(documents)
    for index, row in enumerate(documents, 1):
        path = Path(row["path"])
        referenced.add(path.resolve())
        if not path.exists():
            issues.append(f"MISSING_FILE\tdocument={row['id']}\tcapture={row['capture_id']}\t{row['original_url']}\t{path}")
        elif not path.is_file():
            issues.append(f"NOT_A_FILE\tdocument={row['id']}\t{path}")
        elif path.stat().st_size == 0:
            issues.append(f"EMPTY_FILE\tdocument={row['id']}\t{row['original_url']}\t{path}")
        elif int(row["size_bytes"] or 0) and path.stat().st_size != int(row["size_bytes"]):
            issues.append(
                f"SIZE_MISMATCH\tdocument={row['id']}\tdatabase={row['size_bytes']}\tdisk={path.stat().st_size}\t{path}"
            )
        if callback and (index % 100 == 0 or index == total):
            callback(ProgressEvent("integrity", f"Checked {index:,}/{total:,} saved documents", index, total))
    bad_captures = database.execute(
        """
        SELECT id,original_url,state,document_id FROM captures
        WHERE (state='downloaded' AND document_id IS NULL)
           OR (document_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM documents d WHERE d.id=captures.document_id))
        ORDER BY id
        """
    ).fetchall()
    for row in bad_captures:
        issues.append(
            f"BROKEN_DATABASE_LINK\tcapture={row['id']}\tstate={row['state']}\tdocument={row['document_id']}\t{row['original_url']}"
        )
    capture_root = root / "captures"
    if capture_root.exists():
        for path in capture_root.rglob("*.txt"):
            if path.resolve() not in referenced:
                issues.append(f"ORPHAN_FILE\t{path}")
    unresolved = database.execute(
        "SELECT operation,category,COUNT(*) AS count FROM errors WHERE resolved=0 GROUP BY operation,category ORDER BY operation,category"
    ).fetchall()
    lines = [
        "Archive Scout project integrity report",
        f"Generated: {utc_now()}",
        f"Project: {root}",
        f"Documents checked: {total:,}",
        f"Issues found: {len(issues):,}",
        "",
        "UNRESOLVED ERROR COUNTS",
    ]
    lines.extend(f"{row['operation']}\t{row['category']}\t{row['count']}" for row in unresolved)
    lines.extend(["", "INTEGRITY ISSUES"])
    lines.extend(issues or ["None"])
    path = root / "reports" / "integrity.txt"
    atomic_write_text(path, "\n".join(lines) + "\n")
    return path
