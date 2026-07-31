from __future__ import annotations

import html
import re
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path

from .constants import BINARY_EXTENSIONS, TEXT_EXTENSIONS
from .utils import clean_space

URL_PATTERN = re.compile(r'''(?ix)\b(?:https?://|ftp://|www\.)[^\s<>"'()\[\]{}]+''')
TITLE_PATTERN = re.compile(r"(?is)<title[^>]*>(.*?)</title>")
TAG_PATTERN = re.compile(r"(?is)<[^>]+>")
SOFT_ERROR_MARKERS = (
    "wayback machine doesn't have that page archived",
    "this url has been excluded from the wayback machine",
    "page cannot be displayed due to robots.txt",
    "the machine that serves this file is down",
    "not in archive",
)


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.text: list[str] = []
        self.ignore_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript", "svg"}:
            self.ignore_depth += 1
        for key, value in attrs:
            if value and key.lower() in {"href", "src", "data", "poster", "action", "movie"}:
                self.links.append(value.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self.ignore_depth:
            self.ignore_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.ignore_depth and data:
            self.text.append(data)


def safe_urlsplit(url: str):
    try:
        return urllib.parse.urlsplit(url)
    except (TypeError, ValueError, UnicodeError):
        return None


def normalize_link(raw: str, base: str) -> str:
    raw = html.unescape(raw or "").strip().strip("'\"").rstrip(".,;:!?)]]}")
    if not raw:
        return ""
    if raw.lower().startswith("www."):
        raw = "http://" + raw
    try:
        return urllib.parse.urljoin(base, raw)
    except ValueError:
        return raw


def title_from_html(raw: str) -> str:
    match = TITLE_PATTERN.search(raw)
    if not match:
        return ""
    return clean_space(html.unescape(TAG_PATTERN.sub(" ", match.group(1))))[:500]


def decode_bytes(data: bytes, content_type: str = "") -> str:
    candidates: list[str] = []
    charset_match = re.search(r"charset\s*=\s*['\"]?([A-Za-z0-9._-]+)", content_type, re.IGNORECASE)
    if charset_match:
        candidates.append(charset_match.group(1))
    head = data[:4096].decode("ascii", "ignore")
    meta_match = re.search(r"charset\s*=\s*['\"]?([A-Za-z0-9._-]+)", head, re.IGNORECASE)
    if meta_match:
        candidates.append(meta_match.group(1))
    candidates.extend(["utf-8", "windows-1252", "latin-1"])
    for encoding in dict.fromkeys(candidates):
        try:
            return data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", "replace")


def looks_textual_bytes(data: bytes, content_type: str = "") -> bool:
    mime = (content_type or "").split(";", 1)[0].lower()
    if mime.startswith("text/") or any(token in mime for token in ("html", "xml", "json", "javascript")):
        return True
    if mime.startswith(("image/", "audio/", "video/", "font/")):
        return False
    if b"\x00" in data[:4096]:
        return False
    if not data:
        return True
    sample = data[:4096]
    control = sum(byte < 9 or 13 < byte < 32 for byte in sample)
    return control / len(sample) < 0.05


def is_text_candidate(url: str, mimetype: str = "") -> bool:
    parsed = safe_urlsplit(url)
    extension = Path(parsed.path).suffix.lower() if parsed else ""
    mime = (mimetype or "").split(";", 1)[0].lower()
    if extension in TEXT_EXTENSIONS:
        return True
    if extension in BINARY_EXTENSIONS:
        return False
    if mime.startswith("text/") or any(token in mime for token in ("html", "xml", "json", "javascript")):
        return True
    if mime.startswith(("image/", "audio/", "video/", "font/")):
        return False
    if any(token in mime for token in ("zip", "rar", "gzip", "pdf", "octet-stream", "shockwave", "msword")):
        return False
    return True


def parse_page(raw: str, original: str) -> tuple[str, str, list[str]]:
    parser = PageParser()
    try:
        parser.feed(raw)
    except Exception:
        pass
    visible = clean_space(" ".join(parser.text))
    links: set[str] = set()
    for value in parser.links:
        normalized = normalize_link(value, original)
        if normalized:
            links.add(normalized)
    for value in URL_PATTERN.findall(raw):
        normalized = normalize_link(value, original)
        if normalized:
            links.add(normalized)
    return title_from_html(raw), visible, sorted(links)


def classify_replay_content(raw: str, final_url: str) -> str | None:
    lowered = raw[:20000].casefold()
    if any(marker in lowered for marker in SOFT_ERROR_MARKERS):
        return "soft_404"
    if "/web/" not in final_url and "web.archive.org" in final_url:
        return "invalid_wayback_replay"
    return None
