from __future__ import annotations

import hashlib
import json
from datetime import datetime

from ..config import ProjectConfig
from ..utils import parse_cdx_parameter_lines


def cdx_query_signature(config: ProjectConfig) -> str:
    payload = {
        "from": config.from_date,
        "to": config.to_date,
        "filters": config.cdx_filters,
        "collapses": config.cdx_collapses,
        "match_type": config.cdx_match_type,
        "extra": config.cdx_extra_params,
        "page_size": config.page_size,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def cdx_year_window(config: ProjectConfig, year: int) -> tuple[str, str] | None:
    start = max(config.from_date, f"{year:04d}0101000000")
    end = min(config.to_date, f"{year:04d}1231235959")
    if start > end:
        return None
    return start, end


def cdx_target_value(target: str, match_type: str) -> str:
    if match_type in {"exact", "prefix", "host", "domain"}:
        target = target.rstrip("*")
    if match_type in {"host", "domain"}:
        target = target.rstrip("/")
    return target


def build_cdx_params(
    config: ProjectConfig,
    target: str,
    start: str,
    end: str,
    resume: str | None = None,
    page_size: int | None = None,
) -> list[tuple[str, str]]:
    params = [
        ("url", cdx_target_value(target, config.cdx_match_type)),
        ("from", start),
        ("to", end),
        ("output", "json"),
        ("fl", "timestamp,original,mimetype,statuscode,digest,length"),
    ]
    if config.cdx_match_type:
        params.append(("matchType", config.cdx_match_type))
    params.extend(("filter", value) for value in config.cdx_filters)
    params.extend(("collapse", value) for value in config.cdx_collapses)
    params.extend(parse_cdx_parameter_lines(config.cdx_extra_params))
    params.extend([("limit", str(page_size or config.page_size)), ("showResumeKey", "true")])
    if resume:
        params.append(("resumeKey", resume))
    return params


def parse_cdx(payload: object) -> tuple[list[dict[str, str]], str | None]:
    if payload in (None, []):
        return [], None
    if isinstance(payload, dict):
        message = str(payload.get("message") or payload.get("error") or payload)
        lowered = message.lower()
        if "no capture" in lowered or "no result" in lowered or "not found" in lowered:
            return [], None
        raise RuntimeError(message)
    if not isinstance(payload, list) or not payload:
        return [], None
    header = payload[0]
    if not isinstance(header, list):
        raise RuntimeError("unexpected CDX response header")
    body = payload[1:]
    resume = None
    if len(body) >= 2 and body[-2] == [] and isinstance(body[-1], list) and len(body[-1]) == 1:
        resume = str(body[-1][0])
        body = body[:-2]
    rows: list[dict[str, str]] = []
    for item in body:
        if not item or not isinstance(item, list) or len(item) != len(header):
            continue
        row = dict(zip(header, item))
        if row.get("timestamp") and row.get("original"):
            rows.append(row)
    return rows, resume
