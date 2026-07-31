from __future__ import annotations

import re
from typing import Iterable

from ..utils import normalize_search


def compile_keywords(keywords: Iterable[str]) -> list[tuple[str, re.Pattern[str]]]:
    compiled: list[tuple[str, re.Pattern[str]]] = []
    for raw in keywords:
        value = raw.strip()
        if not value:
            continue
        if value.lower().startswith("re:"):
            expression = value[3:].strip()
            if expression:
                compiled.append((value, re.compile(expression, re.IGNORECASE)))
        else:
            normalized = normalize_search(value)
            pattern = re.escape(normalized).replace(r"\ ", r"\s+")
            compiled.append((value, re.compile(pattern, re.IGNORECASE)))
    return compiled


def keyword_url_match(url: str, patterns: list[tuple[str, re.Pattern[str]]]) -> bool:
    normalized = normalize_search(url)
    return any(pattern.search(normalized) for _, pattern in patterns)
