from __future__ import annotations

import html
import re
import urllib.parse
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from ..constants import AUDIO_EXTENSIONS, MEDIA_EXTENSIONS
from ..content import normalize_link, safe_urlsplit
from ..utils import clean_space

EMBED_URL_PATTERN = re.compile(
    r'''(?is)(?:src|href|data|movie|file|filename|url|media|clip|video|audio)\s*[:=]\s*["']([^"']+)["']'''
)
SCRIPT_MEDIA_PATTERN = re.compile(
    r'''(?ix)(?:file|url|src|movie|media|playlist|clip)\s*[:=]\s*["']([^"']+\.(?:swf|flv|wmv|asf|asx|mov|mp4|mpe?g|avi|rm|ram|rpm|smil|m3u8?|pls|mp3|wav)(?:[?#][^"']*)?)["']'''
)
FLASHVARS_URL_PATTERN = re.compile(r"(?i)(?:^|[&;])(?:file|url|movie|video|stream)=([^&;]+)")
LEGACY_EXTENSIONS = MEDIA_EXTENSIONS | AUDIO_EXTENSIONS | {
    ".asx", ".m3u", ".m3u8", ".pls", ".ram", ".rpm", ".smil", ".swf",
}


@dataclass(frozen=True, slots=True)
class EmbedCandidate:
    url: str
    asset_type: str
    player: str
    context: str = ""


def classify_embed(url: str, tag: str = "", mime: str = "", classid: str = "") -> tuple[str, str]:
    parsed = safe_urlsplit(url)
    extension = Path(parsed.path).suffix.casefold() if parsed else ""
    signature = " ".join((tag, mime, classid, extension)).casefold()
    if ".swf" in signature or "shockwave" in signature or "flash" in signature:
        return "flash", "Adobe Flash"
    if extension in {".wmv", ".wma", ".asf", ".asx"} or "windows-media" in signature or "6bf52a52" in signature:
        return "media", "Windows Media Player"
    if extension in {".rm", ".ram", ".rpm", ".smil"} or "realplayer" in signature or "cfcdaa03" in signature:
        return "media", "RealPlayer"
    if extension in {".m3u", ".m3u8", ".pls", ".asx", ".ram", ".smil"}:
        return "playlist", "Legacy playlist"
    if extension in MEDIA_EXTENSIONS or extension in AUDIO_EXTENSIONS:
        return "media", "Embedded media"
    if tag in {"iframe", "frame"}:
        return "frame", "Embedded frame"
    return "asset", "Legacy embed"


class _EmbedParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.candidates: list[EmbedCandidate] = []
        self.object_stack: list[dict[str, str]] = []

    @staticmethod
    def _attrs(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key.casefold(): html.unescape(value or "") for key, value in attrs}

    def _add(self, raw: str, tag: str, attrs: dict[str, str], context: str = "") -> None:
        raw = raw.strip()
        if not raw or raw.casefold().startswith(("javascript:", "data:", "mailto:")):
            return
        resolved = normalize_link(raw, self.base_url)
        if not resolved:
            return
        asset_type, player = classify_embed(
            resolved,
            tag,
            attrs.get("type", ""),
            attrs.get("classid", ""),
        )
        self.candidates.append(EmbedCandidate(resolved, asset_type, player, clean_space(context)[:500]))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        mapped = self._attrs(attrs)
        if tag == "object":
            self.object_stack.append(mapped)
        for key in ("src", "data", "href", "poster"):
            if mapped.get(key) and tag in {"object", "embed", "param", "iframe", "frame", "video", "audio", "source", "a"}:
                self._add(mapped[key], tag, mapped, f"<{tag} {key}>")
        if tag == "param":
            name = mapped.get("name", "").casefold()
            value = mapped.get("value", "")
            if name in {"movie", "file", "filename", "url", "src", "media", "clip", "flashvars"}:
                if name == "flashvars":
                    for match in FLASHVARS_URL_PATTERN.finditer(value):
                        self._add(urllib.parse.unquote_plus(match.group(1)), tag, mapped, "flashvars")
                else:
                    self._add(value, tag, mapped, f"param:{name}")

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "object" and self.object_stack:
            self.object_stack.pop()


def extract_embed_candidates(raw: str, base_url: str = "") -> list[EmbedCandidate]:
    parser = _EmbedParser(base_url)
    try:
        parser.feed(raw)
        parser.close()
    except Exception:
        pass
    for pattern, label in ((EMBED_URL_PATTERN, "attribute/config"), (SCRIPT_MEDIA_PATTERN, "script config")):
        for match in pattern.finditer(raw):
            value = html.unescape(match.group(1)).strip()
            resolved = normalize_link(value, base_url)
            if not resolved:
                continue
            asset_type, player = classify_embed(resolved)
            parser.candidates.append(EmbedCandidate(resolved, asset_type, player, label))
    unique: dict[tuple[str, str], EmbedCandidate] = {}
    for candidate in parser.candidates:
        unique.setdefault((candidate.url, candidate.asset_type), candidate)
    return sorted(unique.values(), key=lambda item: (item.url, item.asset_type))
