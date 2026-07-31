from __future__ import annotations

VERSION = "2.0.0-alpha.1"
SCHEMA_VERSION = 2
APP_NAME = "Archive Scout"
CDX_URL = "https://web.archive.org/cdx/search/cdx"
REPLAY_URL = "https://web.archive.org/web"
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
TEXT_EXTENSIONS = {
    ".asp", ".aspx", ".cfm", ".cgi", ".css", ".htm", ".html", ".inc",
    ".js", ".json", ".jsp", ".php", ".shtml", ".text", ".txt", ".xhtml", ".xml"
}
BINARY_EXTENSIONS = {
    ".3gp", ".7z", ".ace", ".aiff", ".asf", ".avi", ".bin", ".bmp", ".bz2",
    ".cab", ".class", ".dmg", ".doc", ".docx", ".exe", ".f4v", ".flac", ".flv",
    ".gif", ".gz", ".ico", ".iso", ".jar", ".jpeg", ".jpg", ".m4a", ".m4v",
    ".mid", ".mkv", ".mov", ".mp3", ".mp4", ".mpeg", ".mpg", ".ogg", ".ogm",
    ".ogv", ".pdf", ".png", ".ppt", ".pptx", ".qt", ".rar", ".rm", ".rmvb",
    ".swf", ".tar", ".tif", ".tiff", ".torrent", ".ts", ".vob", ".wav", ".webm",
    ".webp", ".wmv", ".xls", ".xlsx", ".zip"
}
MEDIA_EXTENSIONS = {
    ".3gp", ".asf", ".avi", ".f4v", ".flv", ".m4v", ".mkv", ".mov", ".mp4",
    ".mpeg", ".mpg", ".ogm", ".ogv", ".qt", ".rm", ".rmvb", ".swf", ".ts",
    ".vob", ".webm", ".wmv"
}
ARCHIVE_EXTENSIONS = {".7z", ".ace", ".cab", ".gz", ".rar", ".tar", ".tgz", ".zip"}
OPERATION_MODES = {
    "Index, download, scan, and report": "all",
    "Index URLs only": "index",
    "Download and scan pending URLs": "download",
    "Resume interrupted work": "resume",
    "Rescan existing downloads with current keywords": "rescan",
    "Retry only errored URLs": "retry_errors",
    "Regenerate reports only": "report",
    "Check project integrity": "integrity",
}
SCOPE_LABELS = {
    "All archived text pages (thorough)": "all_text",
    "Only URLs containing a keyword (fast)": "keyword_urls",
    "Index only; download nothing": "index_only",
}
