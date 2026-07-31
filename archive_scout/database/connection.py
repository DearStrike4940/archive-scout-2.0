from __future__ import annotations

import sqlite3
from pathlib import Path

from .schema import initialize_schema

DATABASE_NAME = "archive_scout.sqlite3"


def is_v2_database(path: Path) -> bool:
    if not path.exists():
        return False

    database = None

    try:
        database = sqlite3.connect(path)
        row = database.execute(
            "SELECT version FROM schema_info LIMIT 1"
        ).fetchone()
        return bool(row and int(row[0]) == 2)
    except Exception:
        return False
    finally:
        if database is not None:
            database.close()


def open_database(root: Path, migrate: bool = True) -> sqlite3.Connection:
    root.mkdir(parents=True, exist_ok=True)
    path = root / DATABASE_NAME
    if migrate and path.exists() and not is_v2_database(path):
        from ..projects.migration import migrate_legacy_project
        migrate_legacy_project(root)
    database = sqlite3.connect(path, timeout=60)
    database.row_factory = sqlite3.Row
    database.execute("PRAGMA journal_mode=WAL")
    database.execute("PRAGMA synchronous=NORMAL")
    database.execute("PRAGMA foreign_keys=ON")
    initialize_schema(database)
    database.commit()
    return database
