from __future__ import annotations

from pathlib import Path

from ..constants import ARCHIVE_EXTENSIONS, MEDIA_EXTENSIONS
from ..content import safe_urlsplit


def media_links(links: list[str]) -> list[str]:
    result: list[str] = []
    for link in links:
        parsed = safe_urlsplit(link)
        extension = Path(parsed.path).suffix.lower() if parsed else ""
        if extension in MEDIA_EXTENSIONS or extension in ARCHIVE_EXTENSIONS:
            result.append(link)
    return sorted(set(result))
