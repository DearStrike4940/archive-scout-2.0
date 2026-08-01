from __future__ import annotations

import sqlite3
from pathlib import Path

from ..constants import SCHEMA_VERSION
from .schema import initialize_schema

DATABASE_NAME = "archive_scout.sqlite3"


def database_version(path: Path) -> int | None:
    if not path.exists():
        return None
    database: sqlite3.Connection | None = None
    try:
        database = sqlite3.connect(path)
        row = database.execute("SELECT version FROM schema_info LIMIT 1").fetchone()
        return int(row[0]) if row else None
    except Exception:
        return None
    finally:
        if database is not None:
            database.close()


def is_modern_database(path: Path) -> bool:
    return database_version(path) in {2, SCHEMA_VERSION}


def open_database(root: Path, migrate: bool = True) -> sqlite3.Connection:
    root.mkdir(parents=True, exist_ok=True)
    path = root / DATABASE_NAME
    if migrate and path.exists() and not is_modern_database(path):
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
