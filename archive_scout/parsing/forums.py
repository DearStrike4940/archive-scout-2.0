from __future__ import annotations

import hashlib
import html
import re
import urllib.parse
from dataclasses import dataclass, field
from html.parser import HTMLParser

from ..content import title_from_html
from ..utils import clean_space

WAYBACK_REPLAY = re.compile(r"^https?://web\.archive\.org/web/\d{1,14}(?:[a-z_]+)?/(https?://.+)$", re.I)
THREAD_PATH_PATTERNS = (
    re.compile(r"/(?:threads?|topics?|showthread|viewtopic|discussion|discussions)/[^?#]*?(\d{2,})", re.I),
    re.compile(r"/(?:threads?|topics?)/(\d{2,})(?:[/?#]|$)", re.I),
    re.compile(r"/(?:res|thread|topic)/(\d{2,})(?:[/?#]|$)", re.I),
    re.compile(r"/test/read\.cgi/[^/]+/(\d{6,})(?:[/?#]|$)", re.I),
    re.compile(r"/(?:showthread|viewtopic)\.php(?:[?#]|$)", re.I),
)
THREAD_QUERY_KEYS = ("threadid", "showtopic", "topicid", "topic", "tid", "t")
PAGE_QUERY_KEYS = {
    "page", "p", "start", "st", "offset", "view", "mode", "sort", "order", "sid",
    "session", "sessionid", "highlight", "goto", "postcount", "pp", "perpage",
}
POST_MARKERS = re.compile(
    r"(?:^|[\s_-])(?:post(?:body|content|message|text)?|message|comment|reply|entry|res|response)(?:[\s_-]|$|\d)",
    re.I,
)
USERNAME_MARKERS = re.compile(r"(?:user(?:name)?|author|poster|name|handle|nickname)", re.I)
DATE_MARKERS = re.compile(r"(?:date|time|posted|timestamp)", re.I)
POST_ID_PATTERN = re.compile(r"(?:post|message|comment|reply|res)[_-]?(\d+)", re.I)


@dataclass(slots=True)
class ForumPost:
    post_key: str
    username: str = ""
    posted_at: str = ""
    position: int = 0
    body_text: str = ""


@dataclass(slots=True)
class ForumThread:
    canonical_key: str
    canonical_url: str
    title: str
    profile: str
    posts: list[ForumPost] = field(default_factory=list)


def unwrap_wayback_url(url: str) -> str:
    match = WAYBACK_REPLAY.match(url.strip())
    return urllib.parse.unquote(match.group(1)) if match else url.strip()


def _host_and_path(url: str) -> tuple[str, str, list[tuple[str, str]]]:
    clean = unwrap_wayback_url(url)
    if not urllib.parse.urlsplit(clean).scheme:
        clean = "http://" + clean.lstrip("/")
    parsed = urllib.parse.urlsplit(clean)
    host = (parsed.hostname or "").casefold()
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    return host, path, urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)


def canonicalize_forum_url(url: str) -> tuple[str, str]:
    """Return a stable thread key and a clean canonical URL.

    Pagination, session, fragment, and post-anchor information are discarded. Common
    vBulletin, phpBB, Invision, Futaba/2channel, and path-based thread identifiers are
    retained. The function is deliberately conservative with a bare ``id=`` parameter.
    """
    host, path, pairs = _host_and_path(url)
    lowered_path = path.casefold()
    query = {key.casefold(): value for key, value in pairs}
    thread_id = ""
    source = ""
    for key in THREAD_QUERY_KEYS:
        value = query.get(key, "")
        if value and re.fullmatch(r"[A-Za-z0-9._-]+", value):
            thread_id, source = value, key
            break
    if not thread_id and ("thread" in lowered_path or "topic" in lowered_path or "showthread" in lowered_path or "viewtopic" in lowered_path):
        value = query.get("id", "")
        if value and re.fullmatch(r"[A-Za-z0-9._-]+", value):
            thread_id, source = value, "id"
    if not thread_id:
        for pattern in THREAD_PATH_PATTERNS:
            match = pattern.search(path)
            if match and match.groups():
                thread_id, source = match.group(1), "path"
                break
    kept: list[tuple[str, str]] = []
    for key, value in pairs:
        lowered = key.casefold()
        if lowered in PAGE_QUERY_KEYS or lowered.startswith("utm_"):
            continue
        if thread_id and lowered not in {source, "id" if source == "id" else source}:
            continue
        if lowered in THREAD_QUERY_KEYS or lowered == "id":
            kept.append((lowered, value))
    if thread_id:
        canonical_key = f"{host}|thread:{thread_id}"
        if source == "path":
            canonical_path = path
            canonical_query = ""
        else:
            canonical_path = path
            canonical_query = urllib.parse.urlencode([(source, thread_id)])
    else:
        canonical_path = path.rstrip("/") or "/"
        canonical_query = urllib.parse.urlencode(sorted(kept))
        canonical_key = f"{host}|path:{canonical_path.casefold()}"
        if canonical_query:
            canonical_key += "?" + canonical_query.casefold()
    canonical_url = urllib.parse.urlunsplit(("http", host, canonical_path, canonical_query, ""))
    return canonical_key, canonical_url


def detect_forum_profile(raw: str, url: str = "") -> str:
    sample = (raw[:250000] + " " + url).casefold()
    if "showthread.php" in sample or "vbulletin" in sample or "postbit" in sample:
        return "vbulletin"
    if "viewtopic.php" in sample or "phpbb" in sample or "postbody" in sample:
        return "phpbb"
    if "showtopic=" in sample or "invision" in sample or "ipbwrapper" in sample:
        return "invision"
    if "futaba.php" in sample or "<blockquote" in sample and "no." in sample:
        return "futaba"
    if "/test/read.cgi/" in sample or "2ch" in sample or "5ch" in sample:
        return "2channel"
    return "generic"


class _ForumParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.posts: list[ForumPost] = []
        self._depth = 0
        self._capture_depth: int | None = None
        self._capture_attrs: dict[str, str] = {}
        self._capture_text: list[str] = []
        self._username_text: list[str] = []
        self._date_text: list[str] = []
        self._special_stack: list[str] = []

    @staticmethod
    def _attrs(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key.casefold(): (value or "") for key, value in attrs}

    @staticmethod
    def _is_post(tag: str, attrs: dict[str, str]) -> bool:
        if tag.casefold() not in {"div", "li", "article", "tr", "td", "section", "blockquote", "dl"}:
            return False
        signature = " ".join((attrs.get("id", ""), attrs.get("class", ""), attrs.get("data-post-id", "")))
        if attrs.get("data-post-id"):
            return True
        return bool(POST_MARKERS.search(signature))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._depth += 1
        mapped = self._attrs(attrs)
        if self._capture_depth is None and self._is_post(tag, mapped):
            self._capture_depth = self._depth
            self._capture_attrs = mapped
            self._capture_text = []
            self._username_text = []
            self._date_text = []
            self._special_stack = []
        elif self._capture_depth is not None:
            signature = " ".join((mapped.get("id", ""), mapped.get("class", ""), mapped.get("rel", "")))
            if USERNAME_MARKERS.search(signature):
                self._special_stack.append("username")
            elif DATE_MARKERS.search(signature) or tag.casefold() == "time":
                self._special_stack.append("date")
            else:
                self._special_stack.append("")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self._capture_depth is None or not data.strip():
            return
        self._capture_text.append(data)
        if self._special_stack:
            if self._special_stack[-1] == "username":
                self._username_text.append(data)
            elif self._special_stack[-1] == "date":
                self._date_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._capture_depth is not None:
            if self._depth == self._capture_depth:
                self._finish_post()
            elif self._special_stack:
                self._special_stack.pop()
        self._depth = max(0, self._depth - 1)

    def _finish_post(self) -> None:
        body = clean_space(html.unescape(" ".join(self._capture_text)))
        username = clean_space(html.unescape(" ".join(self._username_text)))[:300]
        posted_at = clean_space(html.unescape(" ".join(self._date_text)))[:300]
        signature = " ".join((self._capture_attrs.get("id", ""), self._capture_attrs.get("class", ""), self._capture_attrs.get("data-post-id", "")))
        match = POST_ID_PATTERN.search(signature)
        key = self._capture_attrs.get("data-post-id", "") or (match.group(1) if match else "")
        if body and len(body) >= 3:
            if not key:
                key = "hash:" + hashlib.sha256(body.casefold().encode("utf-8", "replace")).hexdigest()[:20]
            self.posts.append(ForumPost(key, username, posted_at, len(self.posts) + 1, body))
        self._capture_depth = None
        self._capture_attrs = {}
        self._capture_text = []
        self._username_text = []
        self._date_text = []
        self._special_stack = []


def _deduplicate_posts(posts: list[ForumPost]) -> list[ForumPost]:
    result: list[ForumPost] = []
    seen_keys: set[str] = set()
    seen_bodies: set[str] = set()
    for post in posts:
        body_hash = hashlib.sha256(post.body_text.casefold().encode("utf-8", "replace")).hexdigest()
        if post.post_key in seen_keys or body_hash in seen_bodies:
            continue
        seen_keys.add(post.post_key)
        seen_bodies.add(body_hash)
        post.position = len(result) + 1
        result.append(post)
    return result


def parse_forum_posts(raw: str, original_url: str, profile: str = "auto") -> ForumThread:
    selected_profile = detect_forum_profile(raw, original_url) if profile == "auto" else profile
    parser = _ForumParser()
    try:
        parser.feed(raw)
        parser.close()
    except Exception:
        pass
    posts = _deduplicate_posts(parser.posts)
    canonical_key, canonical_url = canonicalize_forum_url(original_url)
    return ForumThread(
        canonical_key=canonical_key,
        canonical_url=canonical_url,
        title=title_from_html(raw),
        profile=selected_profile,
        posts=posts,
    )
