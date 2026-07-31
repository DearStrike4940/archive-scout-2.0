from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from ..constants import ARCHIVE_EXTENSIONS, MEDIA_EXTENSIONS
from ..content import safe_urlsplit
from ..utils import normalize_search
from .keywords import keyword_url_match
from .snippets import make_snippets


def link_is_interesting(link: str, patterns: list[tuple[str, re.Pattern[str]]]) -> bool:
    parsed = safe_urlsplit(link)
    extension = Path(parsed.path).suffix.lower() if parsed else ""
    if extension in MEDIA_EXTENSIONS or extension in ARCHIVE_EXTENSIONS:
        return True
    return keyword_url_match(link, patterns)


def analyze_content(
    original: str,
    title: str,
    visible: str,
    raw: str,
    links: list[str],
    patterns: list[tuple[str, re.Pattern[str]]],
) -> dict:
    fields = {
        "url": original,
        "title": title,
        "body": visible,
        "source": raw[:500000],
        "links": "\n".join(links),
    }
    multipliers = {"url": 5, "title": 4, "body": 1, "source": 1, "links": 2}
    hits: Counter[str] = Counter()
    hit_fields: dict[str, set[str]] = {}
    score = 0
    matched_patterns: list[tuple[str, re.Pattern[str]]] = []
    for field_name, value in fields.items():
        normalized = normalize_search(value)
        for label, pattern in patterns:
            count = sum(1 for _ in pattern.finditer(normalized))
            if not count:
                continue
            hits[label] += count
            hit_fields.setdefault(label, set()).add(field_name)
            score += min(count, 10) * multipliers[field_name]
            matched_patterns.append((label, pattern))
    distinct = len(hits)
    if distinct >= 2:
        score += distinct * 2
    interesting_links = sorted({link for link in links if link_is_interesting(link, patterns)})
    snippets = make_snippets(visible or raw, list(dict.fromkeys(matched_patterns))) if hits else []
    return {
        "score": score,
        "hits": dict(sorted(hits.items())),
        "hit_fields": {key: sorted(value) for key, value in hit_fields.items()},
        "snippets": snippets,
        "interesting_links": interesting_links,
    }
