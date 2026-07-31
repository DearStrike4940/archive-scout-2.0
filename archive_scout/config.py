from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .constants import VERSION
from .utils import atomic_write_text, normalize_cdx_date, normalize_target, parse_cdx_parameter_lines


@dataclass(slots=True)
class ProjectConfig:
    output_dir: Path
    targets: list[str]
    keywords: list[str]
    keyword_set_name: str = "Current keywords"
    from_year: int = 2000
    to_year: int = datetime.now().year
    from_date: str = ""
    to_date: str = ""
    cdx_filters: list[str] = field(default_factory=lambda: ["statuscode:200"])
    cdx_collapses: list[str] = field(default_factory=lambda: ["urlkey"])
    cdx_match_type: str = ""
    cdx_extra_params: list[str] = field(default_factory=list)
    workers: int = 6
    download_scope: str = "all_text"
    minimum_score: int = 1
    max_file_mb: float = 25.0
    page_size: int = 5000
    cdx_delay: float = 0.8
    download_delay: float = 0.25
    retries: int = 6
    connect_timeout: float = 30.0
    read_timeout: float = 180.0
    max_attempts: int = 4
    user_agent: str = "ArchiveScout/2.0 public web archive research client"

    def normalized(self) -> "ProjectConfig":
        targets = list(dict.fromkeys(normalize_target(value) for value in self.targets if value.strip()))
        keywords = list(dict.fromkeys(value.strip() for value in self.keywords if value.strip()))
        output_dir = Path(self.output_dir).expanduser().resolve()
        from_date = normalize_cdx_date(self.from_date or str(self.from_year), end=False)
        to_date = normalize_cdx_date(self.to_date or str(self.to_year), end=True)
        filters = list(dict.fromkeys(value.strip() for value in self.cdx_filters if value.strip()))
        collapses = list(dict.fromkeys(value.strip() for value in self.cdx_collapses if value.strip()))
        match_type = self.cdx_match_type.strip()
        if match_type not in {"", "exact", "prefix", "host", "domain"}:
            raise ValueError("matchType must be exact, prefix, host, domain, or blank")
        extra_params = [f"{key}={value}" for key, value in parse_cdx_parameter_lines(self.cdx_extra_params)]
        return ProjectConfig(
            output_dir=output_dir,
            targets=targets,
            keywords=keywords,
            keyword_set_name=self.keyword_set_name.strip() or "Current keywords",
            from_year=int(from_date[:4]),
            to_year=int(to_date[:4]),
            from_date=from_date,
            to_date=to_date,
            cdx_filters=filters,
            cdx_collapses=collapses,
            cdx_match_type=match_type,
            cdx_extra_params=extra_params,
            workers=min(32, max(1, int(self.workers))),
            download_scope=self.download_scope if self.download_scope in {"all_text", "keyword_urls", "index_only"} else "all_text",
            minimum_score=max(1, int(self.minimum_score)),
            max_file_mb=max(0.1, float(self.max_file_mb)),
            page_size=min(10000, max(100, int(self.page_size))),
            cdx_delay=max(0.0, float(self.cdx_delay)),
            download_delay=max(0.0, float(self.download_delay)),
            retries=min(12, max(1, int(self.retries))),
            connect_timeout=max(1.0, float(self.connect_timeout)),
            read_timeout=max(1.0, float(self.read_timeout)),
            max_attempts=min(20, max(1, int(self.max_attempts))),
            user_agent=self.user_agent.strip() or "ArchiveScout/2.0 public web archive research client",
        )

    @property
    def max_file_bytes(self) -> int:
        return int(self.max_file_mb * 1024 * 1024)

    def to_payload(self) -> dict:
        payload = asdict(self)
        payload["output_dir"] = str(self.output_dir)
        payload["version"] = VERSION
        return payload


def save_project_config(config: ProjectConfig) -> Path:
    config = config.normalized()
    path = config.output_dir / "project.json"
    atomic_write_text(path, json.dumps(config.to_payload(), indent=2, ensure_ascii=False) + "\n")
    return path


def load_project_config(path: Path) -> ProjectConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ProjectConfig(
        output_dir=Path(payload.get("output_dir") or path.parent),
        targets=list(payload.get("targets") or []),
        keywords=list(payload.get("keywords") or []),
        keyword_set_name=str(payload.get("keyword_set_name") or "Current keywords"),
        from_year=int(payload.get("from_year", 2000)),
        to_year=int(payload.get("to_year", datetime.now().year)),
        from_date=str(payload.get("from_date") or payload.get("from_year", 2000)),
        to_date=str(payload.get("to_date") or payload.get("to_year", datetime.now().year)),
        cdx_filters=list(payload["cdx_filters"]) if "cdx_filters" in payload else ["statuscode:200"],
        cdx_collapses=list(payload["cdx_collapses"]) if "cdx_collapses" in payload else ["urlkey"],
        cdx_match_type=str(payload.get("cdx_match_type", "")),
        cdx_extra_params=list(payload.get("cdx_extra_params") or []),
        workers=int(payload.get("workers", 6)),
        download_scope=str(payload.get("download_scope", "all_text")),
        minimum_score=int(payload.get("minimum_score", 1)),
        max_file_mb=float(payload.get("max_file_mb", 25.0)),
        page_size=int(payload.get("page_size", 5000)),
        cdx_delay=float(payload.get("cdx_delay", 0.8)),
        download_delay=float(payload.get("download_delay", 0.25)),
        retries=int(payload.get("retries", 6)),
        connect_timeout=float(payload.get("connect_timeout", 30.0)),
        read_timeout=float(payload.get("read_timeout", 180.0)),
        max_attempts=int(payload.get("max_attempts", 4)),
        user_agent=str(payload.get("user_agent", "ArchiveScout/2.0 public web archive research client")),
    ).normalized()
