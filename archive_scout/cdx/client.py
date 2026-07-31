from __future__ import annotations

import gzip
import json
import random
import ssl
import threading
import urllib.error
import urllib.parse
import urllib.request
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

from ..constants import RETRYABLE_STATUS
from ..events import RateLimited, Stopped
from ..utils import clean_space
from ..downloads.rate_limit import SharedRateLimiter

try:
    import truststore
except ImportError:
    truststore = None


class HttpClient:
    def __init__(
        self,
        limiter: SharedRateLimiter,
        retries: int,
        timeout: float,
        user_agent: str,
        stop_event: threading.Event,
    ) -> None:
        self.limiter = limiter
        self.retries = retries
        self.timeout = timeout
        self.user_agent = user_agent
        self.stop_event = stop_event
        self.ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT) if truststore else ssl.create_default_context()

    def get(self, url: str, max_bytes: int, accept: str = "*/*") -> dict:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": accept,
            "Connection": "close",
            "Accept-Encoding": "gzip",
        }
        last_error: Exception | None = None
        for attempt in range(self.retries):
            self.limiter.wait(self.stop_event)
            request = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout, context=self.ssl_context) as response:
                    announced = response.headers.get("Content-Length")
                    if announced and announced.isdigit() and int(announced) > max_bytes:
                        raise RuntimeError(f"response exceeds {max_bytes:,} bytes")
                    chunks: list[bytes] = []
                    size = 0
                    while True:
                        if self.stop_event.is_set():
                            raise Stopped
                        chunk = response.read(min(1024 * 1024, max_bytes - size + 1))
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > max_bytes:
                            raise RuntimeError(f"response exceeds {max_bytes:,} bytes")
                        chunks.append(chunk)
                    data = b"".join(chunks)
                    if response.headers.get("Content-Encoding", "").lower() == "gzip":
                        try:
                            data = gzip.decompress(data)
                        except OSError:
                            pass
                    return {
                        "data": data,
                        "status": int(getattr(response, "status", 200)),
                        "headers": dict(response.headers.items()),
                        "final_url": response.geturl(),
                    }
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code not in RETRYABLE_STATUS:
                    raise RuntimeError(f"HTTP {exc.code}: {url}") from exc
                retry_after = parse_retry_after(exc.headers.get("Retry-After"))
                if attempt + 1 == self.retries:
                    if exc.code == 429:
                        raise RateLimited(f"repeated HTTP 429 for {url}") from exc
                    raise RuntimeError(f"HTTP {exc.code} after {self.retries} attempts: {url}") from exc
                self.retry_wait(attempt, retry_after)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                if attempt + 1 == self.retries:
                    raise RuntimeError(f"network failure for {url}: {exc}") from exc
                self.retry_wait(attempt)
        raise RuntimeError(f"request failed for {url}: {last_error}")

    def get_json(self, url: str, params: list[tuple[str, str]], max_bytes: int = 64 * 1024 * 1024) -> object:
        full_url = url + "?" + urllib.parse.urlencode(params, doseq=True)
        response = self.get(full_url, max_bytes, "application/json,text/plain,*/*")
        raw = response["data"].decode("utf-8", "replace").strip()
        if not raw:
            return []
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            preview = clean_space(raw[:500])
            raise RuntimeError(f"CDX returned non-JSON content: {preview}") from exc

    def retry_wait(self, attempt: int, retry_after: float | None = None) -> None:
        base = max(float(retry_after or 0), min(120.0, 2**attempt))
        self.stop_event.wait(base * random.uniform(0.85, 1.2))
        if self.stop_event.is_set():
            raise Stopped


def parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0.0, (parsed - datetime.now(timezone.utc)).total_seconds())
    except Exception:
        return None
