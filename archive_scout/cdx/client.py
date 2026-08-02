from __future__ import annotations

import json
import random
import ssl
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable

import urllib3

from ..constants import RETRYABLE_STATUS
from ..downloads.rate_limit import FixedRateLimiter, SharedHostGate
from ..events import Stopped
from ..runtime import ensure_frozen_bundle_available, frozen_bundle_error_from_exception, is_missing_frozen_bundle_error
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


class RateLimitDeferred(TransientRequestError):
    """Raised only after the server-directed wait budget has been exhausted."""

    def __init__(self, message: str, *, status: int = 429, waited: float = 0.0) -> None:
        super().__init__(message, status=status, splittable=False)
        self.waited = float(waited)


def is_timeout_error(exc: BaseException) -> bool:
    current: BaseException | None = exc
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if isinstance(current, (TimeoutError, urllib3.exceptions.TimeoutError)):
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
        limiter: FixedRateLimiter,
        retries: int,
        timeout: float,
        user_agent: str,
        stop_event: threading.Event,
        retry_callback: Callable[[int, int, str, float], None] | None = None,
        *,
        connect_timeout: float | None = None,
        read_timeout: float | None = None,
        pool_size: int = 4,
        host_gate: SharedHostGate | None = None,
        rate_limit_attempts: int = 0,
        rate_limit_max_wait: float = 0.0,
    ) -> None:
        self.limiter = limiter
        self.retries = max(1, int(retries))
        self.timeout = max(1.0, float(timeout))
        self.connect_timeout = max(1.0, float(connect_timeout if connect_timeout is not None else timeout))
        self.read_timeout = max(1.0, float(read_timeout if read_timeout is not None else timeout))
        self.user_agent = user_agent
        self.stop_event = stop_event
        self.retry_callback = retry_callback
        self.host_gate = host_gate or SharedHostGate()
        self.rate_limit_attempts = max(0, int(rate_limit_attempts))
        self.rate_limit_max_wait = max(0.0, float(rate_limit_max_wait))
        self.ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT) if truststore else ssl.create_default_context()
        self.pool = urllib3.PoolManager(
            num_pools=2,
            maxsize=max(1, int(pool_size)),
            block=True,
            ssl_context=self.ssl_context,
        )
        self.request_timeout = urllib3.Timeout(connect=self.connect_timeout, read=self.read_timeout)

    def close(self) -> None:
        self.pool.clear()

    @staticmethod
    def _discard_response(response) -> None:
        """Consume or close an unused response before returning its connection.

        urllib3 connections cannot be safely reused after redirects or error
        responses unless the response body has been drained. If draining fails,
        close the response so the pool opens a clean connection instead.
        """
        if response is None:
            return
        try:
            drain = getattr(response, "drain_conn", None)
            if callable(drain):
                drain()
            response.release_conn()
        except Exception:
            try:
                response.close()
            except Exception:
                pass

    def _request_once(self, url: str, headers: dict[str, str]):
        current_url = url
        for _ in range(11):
            ensure_frozen_bundle_available()
            response = self.pool.request(
                "GET",
                current_url,
                headers=headers,
                preload_content=False,
                redirect=False,
                retries=False,
                timeout=self.request_timeout,
            )
            if response.status in {301, 302, 303, 307, 308}:
                location = response.headers.get("Location")
                if not location:
                    return response, current_url
                self._discard_response(response)
                current_url = urllib.parse.urljoin(current_url, location)
                continue
            return response, current_url
        raise RuntimeError(f"too many redirects: {url}")

    def _read_response(self, response, max_bytes: int) -> bytes:
        announced = response.headers.get("Content-Length")
        if announced and str(announced).isdigit() and int(announced) > max_bytes:
            raise RuntimeError(f"response exceeds {max_bytes:,} bytes")
        chunks: list[bytes] = []
        size = 0
        for chunk in response.stream(amt=1024 * 1024, decode_content=True):
            if self.stop_event.is_set():
                raise Stopped
            if not chunk:
                continue
            size += len(chunk)
            if size > max_bytes:
                raise RuntimeError(f"response exceeds {max_bytes:,} bytes")
            chunks.append(chunk)
        return b"".join(chunks)

    def get(self, url: str, max_bytes: int, accept: str = "*/*") -> dict:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": accept,
            "Accept-Encoding": "gzip, deflate",
        }
        ensure_frozen_bundle_available()
        generic_attempt = 0
        rate_attempt = 0
        total_rate_wait = 0.0
        last_error: Exception | None = None

        while True:
            ensure_frozen_bundle_available()
            response = None
            permit = self.host_gate.acquire_request(self.stop_event)
            try:
                with self.limiter.slot(self.stop_event):
                    if not self.host_gate.permit_is_current(permit):
                        self.host_gate.finish_request(permit, recovered=False)
                        continue
                    response, final_url = self._request_once(url, headers)
                status = int(response.status)

                if status == 429 or (status == 503 and response.headers.get("Retry-After")):
                    retry_after = parse_retry_after(response.headers.get("Retry-After"))
                    self._discard_response(response)
                    response = None
                    rate_attempt += 1
                    wait_seconds = self.host_gate.pause_for_rate_limit(
                        retry_after,
                        f"HTTP {status}",
                    )
                    total_rate_wait += wait_seconds
                    if self.retry_callback:
                        self.retry_callback(
                            rate_attempt,
                            self.rate_limit_attempts,
                            f"HTTP {status}; all Wayback requests paused",
                            wait_seconds,
                        )
                    attempts_exhausted = self.rate_limit_attempts > 0 and rate_attempt >= self.rate_limit_attempts
                    wait_exhausted = self.rate_limit_max_wait > 0 and total_rate_wait > self.rate_limit_max_wait
                    if attempts_exhausted or wait_exhausted:
                        raise RateLimitDeferred(
                            (
                                f"Wayback continued returning HTTP {status} after "
                                f"{rate_attempt} coordinated pauses. Progress was saved for resume."
                            ),
                            status=status,
                            waited=total_rate_wait,
                        )
                    continue

                self.host_gate.finish_request(permit, recovered=True)

                if status >= 400:
                    self._discard_response(response)
                    response = None
                    if status not in RETRYABLE_STATUS:
                        raise RuntimeError(f"HTTP {status}: {url}")
                    generic_attempt += 1
                    if generic_attempt >= self.retries:
                        raise TransientRequestError(
                            f"HTTP {status} after {self.retries} attempts: {url}",
                            status=status,
                            splittable=status in {408, 500, 502, 503, 504},
                        )
                    self.retry_wait(generic_attempt - 1, f"HTTP {status}")
                    continue

                data = self._read_response(response, max_bytes)
                result = {
                    "data": data,
                    "status": status,
                    "headers": dict(response.headers.items()),
                    "final_url": final_url,
                }
                self._discard_response(response)
                return result
            except (RateLimitDeferred, Stopped):
                self.host_gate.finish_request(permit, recovered=False)
                if response is not None:
                    self._discard_response(response)
                raise
            except RuntimeError:
                self.host_gate.finish_request(permit, recovered=False)
                if response is not None:
                    self._discard_response(response)
                raise
            except (urllib3.exceptions.HTTPError, TimeoutError, OSError) as exc:
                self.host_gate.finish_request(permit, recovered=False)
                if response is not None:
                    self._discard_response(response)
                if is_missing_frozen_bundle_error(exc):
                    raise frozen_bundle_error_from_exception(exc) from exc
                last_error = exc
                timed_out = is_timeout_error(exc)
                generic_attempt += 1
                if generic_attempt >= self.retries:
                    raise TransientRequestError(
                        f"network failure for {url}: {exc}",
                        timed_out=timed_out,
                        splittable=timed_out,
                    ) from exc
                self.retry_wait(generic_attempt - 1, "read timeout" if timed_out else str(exc))

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
            lowered = preview.casefold()
            transient_markers = ("gateway", "temporarily unavailable", "timeout", "server error", "rate limit", "too many requests", "<html")
            if any(marker in lowered for marker in transient_markers):
                raise TransientRequestError(
                    f"CDX returned transient non-JSON content: {preview}",
                    splittable=True,
                ) from exc
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
