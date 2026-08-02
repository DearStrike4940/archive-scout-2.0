from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExtractionRule:
    name: str
    pattern: str
    field: str = "all"
    case_sensitive: bool = False


@dataclass(frozen=True, slots=True)
class ExtractionHit:
    name: str
    extractor_type: str
    field: str
    value: str
    context: str
    start: int
    end: int


BUILTIN_RULES: tuple[ExtractionRule, ...] = (
    ExtractionRule("google_video_docid", r"(?i)(?:[?&]|\b)docid=(-?\d{5,})", "all"),
    ExtractionRule("google_video_videoplay", r"(?i)video\.google\.[^/\s]+/videoplay\?[^\s\"'<>]*?docid=(-?\d{5,})", "all"),
    ExtractionRule("youtube_video_id", r"(?i)(?:youtube\.com/(?:watch\?[^\s\"'<>]*?v=|embed/)|youtu\.be/)([A-Za-z0-9_-]{6,15})", "all"),
    ExtractionRule("internet_archive_identifier", r"(?i)archive\.org/(?:details|download)/([A-Za-z0-9._-]+)", "all"),
    ExtractionRule("flash_movie", r"(?i)(https?://[^\s\"'<>]+?\.swf(?:[?#][^\s\"'<>]*)?)", "all"),
    ExtractionRule("windows_media", r"(?i)(https?://[^\s\"'<>]+?\.(?:wmv|asf|asx|wma)(?:[?#][^\s\"'<>]*)?)", "all"),
    ExtractionRule("real_media", r"(?i)(https?://[^\s\"'<>]+?\.(?:rm|ram|rpm|smil)(?:[?#][^\s\"'<>]*)?)", "all"),
    ExtractionRule("legacy_uploader_id", r"(?i)\b((?:uporg|viploader|vlphp|iup|upupmoo|upload|up)[_-]?\d{4,})\b", "all"),
)


def parse_extractor_rules(lines: list[str]) -> list[ExtractionRule]:
    """Parse ``name :: regex`` or ``name :: field :: regex`` lines."""
    result: list[ExtractionRule] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split("::", 2)]
        if len(parts) == 2:
            name, pattern = parts
            field = "all"
        elif len(parts) == 3:
            name, field, pattern = parts
        else:
            raise ValueError(f"invalid extractor rule: {line}")
        field = field.casefold()
        if field not in {"all", "title", "body", "url", "source", "links"}:
            raise ValueError(f"invalid extractor field in rule: {line}")
        re.compile(pattern)
        result.append(ExtractionRule(name or "custom", pattern, field))
    return result


def _value_from_match(match: re.Match[str]) -> str:
    if match.groups():
        values = [value for value in match.groups() if value is not None]
        if len(values) == 1:
            return values[0]
        if values:
            return "\t".join(values)
    return match.group(0)


def extract_rule(text: str, rule: ExtractionRule, context_chars: int = 120) -> list[ExtractionHit]:
    flags = re.MULTILINE | (0 if rule.case_sensitive else re.IGNORECASE)
    compiled = re.compile(rule.pattern, flags)
    values: list[ExtractionHit] = []
    seen: set[tuple[str, int, int]] = set()
    for match in compiled.finditer(text):
        value = _value_from_match(match).strip()
        if not value:
            continue
        key = (value, match.start(), match.end())
        if key in seen:
            continue
        seen.add(key)
        start = max(0, match.start() - context_chars)
        end = min(len(text), match.end() + context_chars)
        context = re.sub(r"\s+", " ", text[start:end]).strip()
        values.append(ExtractionHit(rule.name, "regex", rule.field, value, context, match.start(), match.end()))
    return values


def extract_regex(text: str, pattern: str) -> list[str]:
    return [hit.value for hit in extract_rule(text, ExtractionRule("custom", pattern))]


def run_extractors(fields: dict[str, str], custom_rules: list[ExtractionRule] | None = None) -> list[ExtractionHit]:
    rules = list(BUILTIN_RULES)
    rules.extend(custom_rules or [])
    hits: list[ExtractionHit] = []
    seen: set[tuple[str, str, str]] = set()
    for rule in rules:
        selected_fields = fields.items() if rule.field == "all" else [(rule.field, fields.get(rule.field, ""))]
        for field_name, text in selected_fields:
            if not text:
                continue
            applied = ExtractionRule(rule.name, rule.pattern, field_name, rule.case_sensitive)
            for hit in extract_rule(text, applied):
                key = (hit.name, hit.value, field_name)
                if key in seen:
                    continue
                seen.add(key)
                hits.append(hit)
    return hits
