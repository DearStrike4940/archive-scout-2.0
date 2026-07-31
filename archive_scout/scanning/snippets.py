from __future__ import annotations

import re

from ..utils import clean_space, normalize_search


def make_snippets(
    text: str,
    patterns: list[tuple[str, re.Pattern[str]]],
    limit: int = 5,
    radius: int = 220,
) -> list[str]:
    normalized = normalize_search(text)
    snippets: list[str] = []
    starts: list[int] = []
    for _, pattern in patterns:
        for match in pattern.finditer(normalized):
            start = max(0, match.start() - radius)
            end = min(len(normalized), match.end() + radius)
            if any(abs(start - previous) < radius for previous in starts):
                continue
            snippet = clean_space(normalized[start:end])
            if start:
                snippet = "…" + snippet
            if end < len(normalized):
                snippet += "…"
            snippets.append(snippet)
            starts.append(start)
            if len(snippets) >= limit:
                return snippets
    return snippets
