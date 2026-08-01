from __future__ import annotations

from ..utils import clean_space, normalize_search
from .keywords import CompiledRule


def make_snippets(text: str, patterns: list[CompiledRule], limit: int = 5, radius: int = 220) -> list[str]:
    normalized = normalize_search(text)
    snippets: list[str] = []
    starts: list[int] = []
    for item in patterns:
        haystack = text if item.rule.case_sensitive else normalized
        for match in item.pattern.finditer(haystack):
            start = max(0, match.start() - radius)
            end = min(len(haystack), match.end() + radius)
            if any(abs(start - previous) < radius for previous in starts):
                continue
            snippet = clean_space(haystack[start:end])
            if start:
                snippet = "…" + snippet
            if end < len(haystack):
                snippet += "…"
            snippets.append(snippet)
            starts.append(start)
            if len(snippets) >= limit:
                return snippets
    return snippets
