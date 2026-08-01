from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from ..config import MediaConfig, normalize_extension
from ..constants import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS


def extension_from_url(url: str) -> str:
    try:
        return Path(urlsplit(url).path).suffix.casefold()
    except Exception:
        return ""


def media_kind(extension: str, mimetype: str = "") -> str | None:
    extension = normalize_extension(extension)
    mime = (mimetype or "").split(";", 1)[0].casefold()
    if extension in IMAGE_EXTENSIONS or mime.startswith("image/"):
        return "image"
    if extension in VIDEO_EXTENSIONS or mime.startswith("video/"):
        return "video"
    return None


def selected_extensions(config: MediaConfig) -> list[str]:
    media = config.normalized()
    excluded = set(media.exclude_extensions)
    selected: list[str] = []
    for extension in media.include_extensions:
        kind = media_kind(extension)
        if extension in excluded or kind is None:
            continue
        if kind == "image" and not media.include_images:
            continue
        if kind == "video" and not media.include_videos:
            continue
        selected.append(extension)
    return list(dict.fromkeys(selected))


def allowed_media_url(url: str, config: MediaConfig, mimetype: str = "") -> tuple[bool, str | None, str]:
    extension = extension_from_url(url)
    kind = media_kind(extension, mimetype)
    if not kind:
        return False, None, extension
    selected = set(selected_extensions(config))
    if extension and extension not in selected:
        return False, kind, extension
    if extension in set(config.normalized().exclude_extensions):
        return False, kind, extension
    if kind == "image" and not config.include_images:
        return False, kind, extension
    if kind == "video" and not config.include_videos:
        return False, kind, extension
    return True, kind, extension
