from __future__ import annotations

from ..content import parse_page


def extract_links(raw: str, original_url: str) -> list[str]:
    return parse_page(raw, original_url)[2]
