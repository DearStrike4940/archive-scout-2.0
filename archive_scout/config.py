from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .constants import DEFAULT_IMAGE_EXTENSIONS, DEFAULT_VIDEO_EXTENSIONS, VERSION
from .scanning.keywords import keyword_rules_to_lines, parse_keyword_rules
from .utils import atomic_write_text, normalize_cdx_date, normalize_target, parse_cdx_parameter_lines


def normalize_extension(value: str) -> str:
    value = value.strip().casefold()
    if not value:
        return ""
    return value if value.startswith(".") else "." + value


@dataclass(slots=True)
class KeywordSetConfig:
    name: str
    rules: list[str] = field(default_factory=list)
    selected: bool = True

    def normalized(self) -> "KeywordSetConfig":
        name = self.name.strip() or "Keyword set"
        normalized_rules = keyword_rules_to_lines(parse_keyword_rules(self.rules))
        return KeywordSetConfig(name=name, rules=normalized_rules, selected=bool(self.selected))

    def to_payload(self) -> dict:
        return asdict(self.normalized())


@dataclass(slots=True)
class MediaConfig:
    enabled: bool = False
    targets: list[str] = field(default_factory=list)
    include_images: bool = True
    include_videos: bool = True
    include_extensions: list[str] = field(
        default_factory=lambda: list(DEFAULT_IMAGE_EXTENSIONS) + list(DEFAULT_VIDEO_EXTENSIONS)
    )
    exclude_extensions: list[str] = field(default_factory=list)
    discover_embedded: bool = True
    allow_external_embeds: bool = False
    snapshot_strategy: str = "earliest"
    max_file_mb: float = 500.0
    preserve_paths: bool = True

    def normalized(self) -> "MediaConfig":
        targets = list(dict.fromkeys(normalize_target(value) for value in self.targets if value.strip()))
        include = [normalize_extension(value) for value in self.include_extensions]
        exclude = [normalize_extension(value) for value in self.exclude_extensions]
        include = list(dict.fromkeys(value for value in include if value))
        exclude = list(dict.fromkeys(value for value in exclude if value))
        strategy = self.snapshot_strategy.strip().casefold()
        if strategy not in {"earliest", "latest", "all"}:
            raise ValueError("media snapshot strategy must be earliest, latest, or all")
        return MediaConfig(
            enabled=bool(self.enabled),
            targets=targets,
            include_images=bool(self.include_images),
            include_videos=bool(self.include_videos),
            include_extensions=include,
            exclude_extensions=exclude,
            discover_embedded=bool(self.discover_embedded),
            allow_external_embeds=bool(self.allow_external_embeds),
            snapshot_strategy=strategy,
            max_file_mb=max(0.1, float(self.max_file_mb)),
            preserve_paths=bool(self.preserve_paths),
        )

    @property
    def max_file_bytes(self) -> int:
        return int(self.max_file_mb * 1024 * 1024)

    def to_payload(self) -> dict:
        return asdict(self.normalized())


@dataclass(slots=True)
class ProjectConfig:
    output_dir: Path
    targets: list[str]
    keywords: list[str]
    keyword_set_name: str = "Current keywords"
    keyword_sets: list[KeywordSetConfig | dict] = field(default_factory=list)
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
    adaptive_rate_limit: bool = True
    retry_error_categories: list[str] = field(default_factory=list)
    retry_capture_ids: list[int] = field(default_factory=list)
    retry_media_capture_ids: list[int] = field(default_factory=list)
    media: MediaConfig | dict = field(default_factory=MediaConfig)

    def normalized_keyword_sets(self) -> list[KeywordSetConfig]:
        sets: list[KeywordSetConfig] = []
        for value in self.keyword_sets:
            if isinstance(value, KeywordSetConfig):
                item = value
            elif isinstance(value, dict):
                item = KeywordSetConfig(
                    name=str(value.get("name") or "Keyword set"),
                    rules=list(value.get("rules") or value.get("keywords") or []),
                    selected=bool(value.get("selected", True)),
                )
            else:
                continue
            item = item.normalized()
            if item.rules:
                sets.append(item)
        if not sets and self.keywords:
            sets.append(KeywordSetConfig(self.keyword_set_name, list(self.keywords), True).normalized())
        unique: dict[str, KeywordSetConfig] = {}
        for item in sets:
            base = item.name
            name = base
            suffix = 2
            while name.casefold() in unique:
                name = f"{base} {suffix}"
                suffix += 1
            if name != item.name:
                item = KeywordSetConfig(name, item.rules, item.selected)
            unique[name.casefold()] = item
        return list(unique.values())

    def selected_keyword_sets(self) -> list[KeywordSetConfig]:
        return [item for item in self.normalized_keyword_sets() if item.selected]

    def normalized(self) -> "ProjectConfig":
        targets = list(dict.fromkeys(normalize_target(value) for value in self.targets if value.strip()))
        keyword_sets = self.normalized_keyword_sets()
        first = keyword_sets[0] if keyword_sets else KeywordSetConfig(self.keyword_set_name, [], True)
        output_dir = Path(self.output_dir).expanduser().resolve()
        from_date = normalize_cdx_date(self.from_date or str(self.from_year), end=False)
        to_date = normalize_cdx_date(self.to_date or str(self.to_year), end=True)
        filters = list(dict.fromkeys(value.strip() for value in self.cdx_filters if value.strip()))
        collapses = list(dict.fromkeys(value.strip() for value in self.cdx_collapses if value.strip()))
        match_type = self.cdx_match_type.strip()
        if match_type not in {"", "exact", "prefix", "host", "domain"}:
            raise ValueError("matchType must be exact, prefix, host, domain, or blank")
        extra_params = [f"{key}={value}" for key, value in parse_cdx_parameter_lines(self.cdx_extra_params)]
        media = self.media if isinstance(self.media, MediaConfig) else MediaConfig(**self.media)
        media = media.normalized()
        return ProjectConfig(
            output_dir=output_dir,
            targets=targets,
            keywords=list(first.rules),
            keyword_set_name=first.name,
            keyword_sets=keyword_sets,
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
            adaptive_rate_limit=bool(self.adaptive_rate_limit),
            retry_error_categories=list(dict.fromkeys(value.strip() for value in self.retry_error_categories if value.strip())),
            retry_capture_ids=sorted({int(value) for value in self.retry_capture_ids if int(value) > 0}),
            retry_media_capture_ids=sorted({int(value) for value in self.retry_media_capture_ids if int(value) > 0}),
            media=media,
        )

    @property
    def max_file_bytes(self) -> int:
        return int(self.max_file_mb * 1024 * 1024)

    def to_payload(self) -> dict:
        config = self.normalized()
        payload = asdict(config)
        payload["output_dir"] = str(config.output_dir)
        payload["keyword_sets"] = [item.to_payload() for item in config.normalized_keyword_sets()]
        payload["media"] = config.media.to_payload() if isinstance(config.media, MediaConfig) else dict(config.media)
        payload["version"] = VERSION
        return payload


def save_project_config(config: ProjectConfig) -> Path:
    config = config.normalized()
    path = config.output_dir / "project.json"
    atomic_write_text(path, json.dumps(config.to_payload(), indent=2, ensure_ascii=False) + "\n")
    return path


def load_project_config(path: Path) -> ProjectConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    keyword_sets = list(payload.get("keyword_sets") or [])
    media_payload = payload.get("media") or {}
    return ProjectConfig(
        output_dir=Path(payload.get("output_dir") or path.parent),
        targets=list(payload.get("targets") or []),
        keywords=list(payload.get("keywords") or []),
        keyword_set_name=str(payload.get("keyword_set_name") or "Current keywords"),
        keyword_sets=keyword_sets,
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
        adaptive_rate_limit=bool(payload.get("adaptive_rate_limit", True)),
        retry_error_categories=list(payload.get("retry_error_categories") or []),
        retry_capture_ids=[int(value) for value in payload.get("retry_capture_ids") or []],
        retry_media_capture_ids=[int(value) for value in payload.get("retry_media_capture_ids") or []],
        media=MediaConfig(
            enabled=bool(media_payload.get("enabled", False)),
            targets=list(media_payload.get("targets") or []),
            include_images=bool(media_payload.get("include_images", True)),
            include_videos=bool(media_payload.get("include_videos", True)),
            include_extensions=list(media_payload.get("include_extensions") or list(DEFAULT_IMAGE_EXTENSIONS) + list(DEFAULT_VIDEO_EXTENSIONS)),
            exclude_extensions=list(media_payload.get("exclude_extensions") or []),
            discover_embedded=bool(media_payload.get("discover_embedded", True)),
            allow_external_embeds=bool(media_payload.get("allow_external_embeds", False)),
            snapshot_strategy=str(media_payload.get("snapshot_strategy", "earliest")),
            max_file_mb=float(media_payload.get("max_file_mb", 500.0)),
            preserve_paths=bool(media_payload.get("preserve_paths", True)),
        ),
    ).normalized()
