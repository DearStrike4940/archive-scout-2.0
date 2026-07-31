from __future__ import annotations

import re

EMBED_URL_PATTERN = re.compile(r'''(?is)(?:src|href|data|movie|file)\s*=\s*["']([^"']+)["']''')


def extract_embed_candidates(raw: str) -> list[str]:
    return sorted(set(match.group(1).strip() for match in EMBED_URL_PATTERN.finditer(raw) if match.group(1).strip()))
