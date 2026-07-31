from __future__ import annotations

from pathlib import Path

from ..projects.migration import migrate_legacy_project


def migrate_project(root: Path) -> Path:
    return migrate_legacy_project(root)


__all__ = ["migrate_project"]
