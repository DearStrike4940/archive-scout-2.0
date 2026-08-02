from __future__ import annotations

import re
import urllib.error



def classify_exception(exc: Exception) -> tuple[str, int | None, bool]:
    message = str(exc).casefold()
    status = None
    if "429" in message or "rate limit" in message:
        return "rate_limit", 429, True
    match = re.search(r"http\s+(\d{3})", message)
    if match:
        status = int(match.group(1))
        if status == 404:
            return "missing_capture", status, False
        if 400 <= status < 500:
            return "http_client_error", status, status in {408, 425, 429}
        return "http_server_error", status, True
    if "timeout" in message or "timed out" in message:
        return "timeout", status, True
    if "ssl" in message or "certificate" in message:
        return "ssl", status, True
    if "exceeds" in message and "bytes" in message:
        return "oversized_response", status, False
    if "network failure" in message or "urlopen" in message or "connection" in message:
        return "connection", status, True
    return "unknown", status, True
