from __future__ import annotations

import gzip
import json
import random
import ssl
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable

from ..constants import RETRYABLE_STATUS
from ..downloads.rate_limit import AdaptiveRateLimiter
from ..events import RateLimited, Stopped
from ..utils import clean_space

try:
    import truststore
except ImportError:
    truststore = None


class TransientRequestError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        timed_out: bool = False,
        splittable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.timed_out = timed_out
        self.splittable = splittable


def is_timeout_error(exc: BaseException) -> bool:
    current: BaseException | None = exc
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if isinstance(current, TimeoutError):
            return True
        reason = getattr(current, "reason", None)
        if isinstance(reason, BaseException) and reason is not current:
            current = reason
            continue
        current = current.__cause__ or current.__context__
    return False


class HttpClient:
    def __init__(
        self,
        limiter: AdaptiveRateLimiter,
        retries: int,
        timeout: float,
        user_agent: str,
        stop_event: threading.Event,
        retry_callback: Callable[[int, int, str, float], None] | None = None,
    ) -> None:
        self.limiter = limiter
        self.retries = max(1, int(retries))
        self.timeout = max(1.0, float(timeout))
        self.user_agent = user_agent
        self.stop_event = stop_event
        self.retry_callback = retry_callback
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
            request = urllib.request.Request(url, headers=headers)
            try:
                with self.limiter.slot(self.stop_event):
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
                        result = {
                            "data": data,
                            "status": int(getattr(response, "status", 200)),
                            "headers": dict(response.headers.items()),
                            "final_url": response.geturl(),
                        }
                self.limiter.record_success()
                return result
            except urllib.error.HTTPError as exc:
                last_error = exc
                retry_after = parse_retry_after(exc.headers.get("Retry-After"))
                self.limiter.record_failure(exc.code, retry_after)
                if exc.code not in RETRYABLE_STATUS:
                    raise RuntimeError(f"HTTP {exc.code}: {url}") from exc
                if attempt + 1 == self.retries:
                    if exc.code == 429:
                        raise RateLimited(f"repeated HTTP 429 for {url}") from exc
                    raise TransientRequestError(
                        f"HTTP {exc.code} after {self.retries} attempts: {url}",
                        status=exc.code,
                        splittable=exc.code in {408, 500, 502, 503, 504},
                    ) from exc
                self.retry_wait(attempt, f"HTTP {exc.code}", retry_after)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                timed_out = is_timeout_error(exc)
                self.limiter.record_failure(None, None)
                if attempt + 1 == self.retries:
                    raise TransientRequestError(
                        f"network failure for {url}: {exc}",
                        timed_out=timed_out,
                        splittable=timed_out,
                    ) from exc
                self.retry_wait(attempt, "read timeout" if timed_out else str(exc))
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

    def retry_wait(self, attempt: int, reason: str, retry_after: float | None = None) -> None:
        base = max(float(retry_after or 0), min(120.0, 2**attempt))
        wait_seconds = base * random.uniform(0.85, 1.2)
        if self.retry_callback:
            self.retry_callback(attempt + 2, self.retries, reason, wait_seconds)
        self.stop_event.wait(wait_seconds)
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
