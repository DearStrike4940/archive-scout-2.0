from __future__ import annotations

import re


def extract_regex(text: str, pattern: str) -> list[str]:
    compiled = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
    values: list[str] = []
    for match in compiled.finditer(text):
        if match.groups():
            values.append(match.group(1) if len(match.groups()) == 1 else "\t".join(match.groups()))
        else:
            values.append(match.group(0))
    return values
