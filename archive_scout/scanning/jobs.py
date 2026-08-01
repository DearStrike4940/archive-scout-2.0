from __future__ import annotations

from dataclasses import dataclass

from .keywords import CompiledRule, compile_keywords


@dataclass(slots=True)
class ScanJob:
    scan_run_id: int
    keyword_set_name: str
    rules: list[str]
    patterns: list[CompiledRule]

    @classmethod
    def create(cls, scan_run_id: int, keyword_set_name: str, rules: list[str]) -> "ScanJob":
        return cls(scan_run_id, keyword_set_name, list(rules), compile_keywords(rules))
