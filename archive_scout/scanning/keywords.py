from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Iterable

from ..utils import normalize_search

RULE_PREFIXES = {
    "required": "required",
    "require": "required",
    "optional": "optional",
    "high": "optional",
    "exclude": "excluded",
    "excluded": "excluded",
    "negative": "excluded",
    "exact": "exact",
    "regex": "regex",
    "re": "regex",
}


@dataclass(slots=True)
class KeywordRule:
    label: str
    expression: str
    kind: str = "optional"
    weight: float = 1.0
    case_sensitive: bool = False
    whole_word: bool = False

    def normalized(self) -> "KeywordRule":
        kind = self.kind.strip().casefold()
        if kind not in {"optional", "required", "excluded", "exact", "regex"}:
            raise ValueError(f"unsupported keyword rule type: {self.kind}")
        expression = self.expression.strip()
        if not expression:
            raise ValueError("keyword expression cannot be empty")
        label = self.label.strip() or expression
        return KeywordRule(
            label=label,
            expression=expression,
            kind=kind,
            weight=max(0.0, min(100.0, float(self.weight))),
            case_sensitive=bool(self.case_sensitive),
            whole_word=bool(self.whole_word),
        )

    def to_dict(self) -> dict:
        return asdict(self.normalized())


@dataclass(slots=True)
class CompiledRule:
    rule: KeywordRule
    pattern: re.Pattern[str]


def _split_options(value: str) -> tuple[str, list[str]]:
    parts = [part.strip() for part in re.split(r"\s+\|\s+", value)]
    return parts[0], [part for part in parts[1:] if part]


def parse_keyword_line(raw: str) -> KeywordRule | None:
    line = raw.strip()
    if not line or line.startswith("#"):
        return None
    expression_part, options = _split_options(line)
    kind = "optional"
    expression = expression_part
    prefix_match = re.match(r"^([A-Za-z_ -]+)\s*:\s*(.+)$", expression_part)
    if prefix_match:
        prefix = prefix_match.group(1).strip().casefold().replace(" ", "_")
        mapped = RULE_PREFIXES.get(prefix)
        if mapped:
            kind = mapped
            expression = prefix_match.group(2).strip()
    weight = 3.0 if expression_part.casefold().startswith("high:") else 1.0
    case_sensitive = False
    whole_word = False
    label = expression
    for option in options:
        lowered = option.casefold().strip()
        if lowered in {"case", "case_sensitive", "casesensitive"}:
            case_sensitive = True
        elif lowered in {"whole", "whole_word", "wholeword"}:
            whole_word = True
        elif lowered.startswith("weight="):
            weight = float(option.split("=", 1)[1].strip())
        elif lowered.startswith("label="):
            label = option.split("=", 1)[1].strip() or label
        elif lowered.startswith("type="):
            requested = option.split("=", 1)[1].strip().casefold()
            if requested in {"optional", "required", "excluded", "exact", "regex"}:
                kind = requested
            else:
                raise ValueError(f"unsupported keyword rule type: {requested}")
        else:
            raise ValueError(f"unknown keyword option: {option}")
    if kind == "exact":
        whole_word = False
    return KeywordRule(label, expression, kind, weight, case_sensitive, whole_word).normalized()


def parse_keyword_rules(values: Iterable[str | dict | KeywordRule]) -> list[KeywordRule]:
    rules: list[KeywordRule] = []
    for value in values:
        if isinstance(value, KeywordRule):
            rules.append(value.normalized())
        elif isinstance(value, dict):
            rules.append(KeywordRule(**value).normalized())
        else:
            parsed = parse_keyword_line(str(value))
            if parsed:
                rules.append(parsed)
    unique: dict[tuple, KeywordRule] = {}
    for rule in rules:
        key = (rule.kind, rule.expression, rule.case_sensitive, rule.whole_word, rule.weight, rule.label)
        unique[key] = rule
    return list(unique.values())


def serialize_keyword_rules(rules: Iterable[KeywordRule | dict | str]) -> str:
    return json.dumps([rule.to_dict() for rule in parse_keyword_rules(rules)], ensure_ascii=False, sort_keys=True)


def keyword_rules_to_lines(rules: Iterable[KeywordRule | dict | str]) -> list[str]:
    lines: list[str] = []
    for rule in parse_keyword_rules(rules):
        prefix = "" if rule.kind == "optional" else f"{rule.kind}: "
        options: list[str] = []
        if rule.weight != 1.0:
            options.append(f"weight={rule.weight:g}")
        if rule.case_sensitive:
            options.append("case")
        if rule.whole_word:
            options.append("whole")
        if rule.label != rule.expression:
            options.append(f"label={rule.label}")
        line = prefix + rule.expression
        if options:
            line += " | " + " | ".join(options)
        lines.append(line)
    return lines


def compile_rule(rule: KeywordRule) -> CompiledRule:
    flags = 0 if rule.case_sensitive else re.IGNORECASE
    if rule.kind == "regex":
        pattern_text = rule.expression
    else:
        value = rule.expression if rule.case_sensitive else normalize_search(rule.expression)
        pattern_text = re.escape(value).replace(r"\ ", r"\s+")
        if rule.whole_word:
            pattern_text = rf"(?<!\w){pattern_text}(?!\w)"
    return CompiledRule(rule, re.compile(pattern_text, flags))


def compile_keywords(keywords: Iterable[str | dict | KeywordRule]) -> list[CompiledRule]:
    return [compile_rule(rule) for rule in parse_keyword_rules(keywords)]


def keyword_url_match(url: str, patterns: list[CompiledRule]) -> bool:
    normalized = normalize_search(url)
    return any(item.pattern.search(url if item.rule.case_sensitive else normalized) for item in patterns if item.rule.kind != "excluded")


@dataclass(slots=True)
class KeywordPrefilter:
    literal_pattern: re.Pattern[str] | None
    slow_patterns: list[CompiledRule]
    has_positive_rules: bool

    def matches(self, fields: dict[str, str], normalized_fields: dict[str, str]) -> bool:
        if not self.has_positive_rules:
            return True
        if self.literal_pattern is not None:
            for value in normalized_fields.values():
                if self.literal_pattern.search(value):
                    return True
        for item in self.slow_patterns:
            for field_name, value in fields.items():
                haystack = value if item.rule.case_sensitive else normalized_fields[field_name]
                if item.pattern.search(haystack):
                    return True
        return False


def compile_prefilter(patterns: list[CompiledRule]) -> KeywordPrefilter:
    positive = [item for item in patterns if item.rule.kind != "excluded"]
    literals: list[str] = []
    slow: list[CompiledRule] = []
    for item in positive:
        if item.rule.kind != "regex" and not item.rule.case_sensitive and not item.rule.whole_word:
            normalized = normalize_search(item.rule.expression)
            if normalized:
                literals.append(re.escape(normalized).replace(r"\ ", r"\s+"))
        else:
            slow.append(item)
    literal_pattern = None
    if literals:
        unique = sorted(set(literals), key=lambda value: (-len(value), value))
        literal_pattern = re.compile("(?:" + "|".join(unique) + ")")
    return KeywordPrefilter(literal_pattern, slow, bool(positive))
