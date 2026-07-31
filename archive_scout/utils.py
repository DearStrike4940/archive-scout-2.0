from __future__ import annotations

import calendar
import hashlib
import html
import json
import os
import re
import tempfile
import unicodedata
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

SPACE_PATTERN = re.compile(r"\s+")
CDX_RESERVED_PARAMETERS = {
    "url", "from", "to", "output", "fl", "showresumekey", "resumekey", "limit", "matchtype"
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_space(value: str) -> str:
    return SPACE_PATTERN.sub(" ", value or "").strip()


def normalize_search(value: str) -> str:
    value = html.unescape(urllib.parse.unquote(value or ""))
    value = unicodedata.normalize("NFKC", value).casefold().replace("_", " ")
    return clean_space(value)


def normalize_target(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("target cannot be empty")
    value = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", value).lstrip("/")
    if not value:
        raise ValueError("target cannot be empty")
    if "*" in value:
        return value
    if "/" not in value:
        return value.rstrip("/") + "/*"
    if value.endswith("/"):
        return value + "*"
    return value + "*"


def normalize_cdx_date(value: str, end: bool = False) -> str:
    digits = re.sub(r"[^0-9]", "", str(value or ""))
    if len(digits) == 4:
        return digits + ("1231235959" if end else "0101000000")
    if len(digits) == 6:
        year = int(digits[:4])
        month = int(digits[4:6])
        if not 1 <= month <= 12:
            raise ValueError(f"invalid CDX month: {value}")
        day = calendar.monthrange(year, month)[1] if end else 1
        return f"{year:04d}{month:02d}{day:02d}" + ("235959" if end else "000000")
    if len(digits) == 8:
        year = int(digits[:4])
        month = int(digits[4:6])
        day = int(digits[6:8])
        datetime(year, month, day)
        return digits + ("235959" if end else "000000")
    if len(digits) == 14:
        datetime.strptime(digits, "%Y%m%d%H%M%S")
        return digits
    raise ValueError("CDX dates must be YYYY, YYYYMM, YYYYMMDD, or YYYYMMDDhhmmss")


def parse_cdx_parameter_lines(lines: Iterable[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if "=" not in line:
            raise ValueError(f"CDX parameter must use key=value: {line}")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", key):
            raise ValueError(f"invalid CDX parameter name: {key}")
        if key.casefold() in CDX_RESERVED_PARAMETERS:
            raise ValueError(f"{key} is controlled by the app and cannot be added as an advanced parameter")
        pairs.append((key, value))
    return pairs


def hash_text(value: str, algorithm: str = "sha256") -> str:
    return hashlib.new(algorithm, value.encode("utf-8", "replace")).hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", errors="replace", newline="\n") as handle:
            handle.write(text)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def json_value(value: str | None, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default
