from __future__ import annotations

import re
from collections import Counter
from itertools import combinations
from pathlib import Path

from ..constants import ARCHIVE_EXTENSIONS, MEDIA_EXTENSIONS
from ..content import safe_urlsplit
from ..utils import normalize_search
from .keywords import CompiledRule, KeywordPrefilter, keyword_url_match
from .snippets import make_snippets

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|[\r\n]+")
PARAGRAPH_SPLIT = re.compile(r"(?:\r?\n){2,}|</p\s*>|<br\s*/?>\s*<br\s*/?>", re.IGNORECASE)
WORD_PATTERN = re.compile(r"\S+")


def link_is_interesting(link: str, patterns: list[CompiledRule]) -> bool:
    parsed = safe_urlsplit(link)
    extension = Path(parsed.path).suffix.lower() if parsed else ""
    if extension in MEDIA_EXTENSIONS or extension in ARCHIVE_EXTENSIONS:
        return True
    return keyword_url_match(link, patterns)


def _matches(item: CompiledRule, value: str, normalized_value: str) -> list[re.Match[str]]:
    haystack = value if item.rule.case_sensitive else normalized_value
    return list(item.pattern.finditer(haystack))


def _matched_labels_in_segments(text: str, patterns: list[CompiledRule], splitter: re.Pattern[str]) -> int:
    bonus = 0
    for segment in splitter.split(text):
        if not segment.strip():
            continue
        normalized_segment = normalize_search(segment)
        labels = {
            item.rule.label
            for item in patterns
            if item.rule.kind != "excluded" and item.pattern.search(segment if item.rule.case_sensitive else normalized_segment)
        }
        if len(labels) >= 2:
            bonus += len(labels) * (len(labels) - 1)
    return bonus


def _proximity_bonus(text: str, patterns: list[CompiledRule], window_words: int = 25) -> tuple[int, dict]:
    normalized = normalize_search(text)
    word_spans = list(WORD_PATTERN.finditer(normalized))
    if not word_spans:
        return 0, {"window_words": window_words, "pairs": 0}
    positions: dict[str, list[int]] = {}
    for item in patterns:
        if item.rule.kind == "excluded":
            continue
        for match in item.pattern.finditer(normalized):
            word_index = 0
            lo, hi = 0, len(word_spans)
            while lo < hi:
                mid = (lo + hi) // 2
                if word_spans[mid].start() < match.start():
                    lo = mid + 1
                else:
                    hi = mid
            word_index = max(0, lo - 1)
            positions.setdefault(item.rule.label, []).append(word_index)
    close_pairs = 0
    minimum_distance: int | None = None
    for left, right in combinations(positions, 2):
        distance = min(abs(a - b) for a in positions[left] for b in positions[right])
        minimum_distance = distance if minimum_distance is None else min(minimum_distance, distance)
        if distance <= window_words:
            close_pairs += 1
    return close_pairs * 6, {
        "window_words": window_words,
        "pairs": close_pairs,
        "minimum_distance": minimum_distance,
    }


def prepare_analysis_fields(
    original: str,
    title: str,
    visible: str,
    raw: str,
    links: list[str],
) -> tuple[dict[str, str], dict[str, str]]:
    fields = {
        "url": original,
        "title": title,
        "body": visible,
        "source": raw[:500000],
        "links": "\n".join(links),
    }
    return fields, {name: normalize_search(value) for name, value in fields.items()}


def analyze_content(
    original: str,
    title: str,
    visible: str,
    raw: str,
    links: list[str],
    patterns: list[CompiledRule],
    prefilter: KeywordPrefilter | None = None,
    prepared_fields: dict[str, str] | None = None,
    prepared_normalized_fields: dict[str, str] | None = None,
) -> dict:
    if prepared_fields is None or prepared_normalized_fields is None:
        fields, normalized_fields = prepare_analysis_fields(original, title, visible, raw, links)
    else:
        fields = prepared_fields
        normalized_fields = prepared_normalized_fields
    if prefilter is not None and not prefilter.matches(fields, normalized_fields):
        return {
            "score": 0,
            "hits": {},
            "hit_fields": {},
            "snippets": [],
            "interesting_links": [],
            "excluded": False,
            "excluded_labels": [],
            "required_missing": any(item.rule.kind == "required" for item in patterns),
            "missing_required_labels": sorted({item.rule.label for item in patterns if item.rule.kind == "required"}),
            "proximity": {
                "window_words": 25,
                "pairs": 0,
                "minimum_distance": None,
                "sentence_bonus": 0,
                "paragraph_bonus": 0,
                "score_bonus": 0,
            },
        }
    multipliers = {"url": 6.0, "title": 5.0, "body": 1.0, "source": 0.75, "links": 2.5}
    hits: Counter[str] = Counter()
    hit_fields: dict[str, set[str]] = {}
    score = 0.0
    matched_rules: dict[str, CompiledRule] = {}
    excluded_labels: set[str] = set()
    required_labels = {item.rule.label for item in patterns if item.rule.kind == "required"}

    for field_name, value in fields.items():
        normalized_value = normalized_fields[field_name]
        for item in patterns:
            matches = _matches(item, value, normalized_value)
            count = len(matches)
            if not count:
                continue
            label = item.rule.label
            hits[label] += count
            hit_fields.setdefault(label, set()).add(field_name)
            matched_rules[label] = item
            if item.rule.kind == "excluded":
                excluded_labels.add(label)
                continue
            exact_bonus = 2.0 if item.rule.kind == "exact" else 1.0
            contribution = min(count, 10) * multipliers[field_name] * item.rule.weight * exact_bonus
            score += contribution

    missing_required = sorted(required_labels - set(hits))
    excluded = bool(excluded_labels)
    distinct = len([label for label in hits if label not in excluded_labels])
    if distinct >= 2:
        score += distinct * 3

    sentence_bonus = _matched_labels_in_segments(visible, list(matched_rules.values()), SENTENCE_SPLIT) * 4
    paragraph_bonus = _matched_labels_in_segments(raw, list(matched_rules.values()), PARAGRAPH_SPLIT) * 2
    proximity_bonus, proximity = _proximity_bonus(visible, list(matched_rules.values()))
    score += sentence_bonus + paragraph_bonus + proximity_bonus
    proximity.update({"sentence_bonus": sentence_bonus, "paragraph_bonus": paragraph_bonus, "score_bonus": proximity_bonus})

    if excluded or missing_required:
        score = 0
    interesting_links = sorted({link for link in links if link_is_interesting(link, patterns)})
    positive_patterns = [item for item in matched_rules.values() if item.rule.kind != "excluded"]
    snippets = make_snippets(visible or raw, positive_patterns) if positive_patterns else []
    return {
        "score": int(round(score)),
        "hits": dict(sorted(hits.items())),
        "hit_fields": {key: sorted(value) for key, value in hit_fields.items()},
        "snippets": snippets,
        "interesting_links": interesting_links,
        "excluded": excluded,
        "excluded_labels": sorted(excluded_labels),
        "required_missing": bool(missing_required),
        "missing_required_labels": missing_required,
        "proximity": proximity,
    }
