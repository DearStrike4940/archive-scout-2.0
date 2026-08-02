from __future__ import annotations

import contextlib
import random
import threading
import time
from dataclasses import dataclass

from ..events import Stopped


class FixedRateLimiter:
    """A fixed, user-controlled minimum delay between request starts."""

    def __init__(self, delay: float) -> None:
        self.delay = max(0.0, float(delay))
        self.condition = threading.Condition()
        self.next_request = 0.0

    @contextlib.contextmanager
    def slot(self, stop_event: threading.Event):
        while True:
            with self.condition:
                if stop_event.is_set():
                    raise Stopped
                now = time.monotonic()
                wait = max(0.0, self.next_request - now)
                if wait <= 0:
                    self.next_request = now + self.delay
                    break
                self.condition.wait(timeout=min(max(wait, 0.05), 0.5))
        yield

    def wait(self, stop_event: threading.Event) -> None:
        with self.slot(stop_event):
            return


@dataclass(frozen=True, slots=True)
class HostPermit:
    generation: int
    probe: bool = False


class SharedHostGate:
    """Coordinates HTTP 429 pauses without rewriting the user's speed settings.

    A 429 response closes a host-wide circuit. Every worker waits for the same
    Retry-After/backoff period. When that period ends, exactly one request is
    allowed through as a recovery probe; the normal queue reopens only after
    that probe receives a non-rate-limited response. This prevents both a
    thundering herd and a cascade of per-URL 429 errors.
    """

    def __init__(
        self,
        base_pause: float = 30.0,
        max_pause: float = 300.0,
        coalesce_seconds: float = 2.0,
        decay_seconds: float = 300.0,
    ) -> None:
        self.base_pause = max(1.0, float(base_pause))
        self.max_pause = max(self.base_pause, float(max_pause))
        self.coalesce_seconds = max(0.1, float(coalesce_seconds))
        self.decay_seconds = max(self.coalesce_seconds, float(decay_seconds))
        self.condition = threading.Condition()
        self.blocked_until = 0.0
        self.last_signal = 0.0
        self.incidents = 0
        self.reason = ""
        self.generation = 0
        self.probe_required = False
        self.probe_inflight = False

    def acquire_request(self, stop_event: threading.Event) -> HostPermit:
        while True:
            with self.condition:
                if stop_event.is_set():
                    raise Stopped
                now = time.monotonic()
                remaining = self.blocked_until - now
                if remaining > 0:
                    self.condition.wait(timeout=min(max(remaining, 0.05), 0.5))
                    continue
                if self.probe_required:
                    if not self.probe_inflight:
                        self.probe_inflight = True
                        return HostPermit(self.generation, True)
                    self.condition.wait(timeout=0.5)
                    continue
                return HostPermit(self.generation, False)

    def permit_is_current(self, permit: HostPermit) -> bool:
        with self.condition:
            if permit.generation != self.generation:
                return False
            if self.blocked_until > time.monotonic():
                return False
            if permit.probe:
                return self.probe_required and self.probe_inflight
            return not self.probe_required

    def finish_request(self, permit: HostPermit, recovered: bool) -> None:
        if not permit.probe:
            return
        with self.condition:
            if permit.generation != self.generation:
                return
            self.probe_inflight = False
            if recovered:
                self.probe_required = False
                self.blocked_until = 0.0
                self.incidents = 0
                self.reason = ""
                self.generation += 1
            self.condition.notify_all()

    def wait(self, stop_event: threading.Event) -> None:
        """Compatibility wait that observes only the active closed period."""
        while True:
            with self.condition:
                if stop_event.is_set():
                    raise Stopped
                remaining = self.blocked_until - time.monotonic()
                if remaining <= 0:
                    return
                self.condition.wait(timeout=min(max(remaining, 0.05), 0.5))

    def pause_for_rate_limit(
        self,
        retry_after: float | None = None,
        reason: str = "HTTP 429",
    ) -> float:
        now = time.monotonic()
        with self.condition:
            new_incident = now - self.last_signal > self.coalesce_seconds
            if now - self.last_signal > self.decay_seconds:
                self.incidents = 0
            if new_incident:
                self.incidents += 1
            self.last_signal = now

            if retry_after is not None and retry_after > 0:
                pause = max(1.0, float(retry_after))
            else:
                exponent = max(0, min(self.incidents - 1, 4))
                pause = min(self.max_pause, self.base_pause * (2**exponent))
                pause *= random.uniform(0.9, 1.1)

            self.blocked_until = max(self.blocked_until, now + pause)
            self.reason = reason
            self.probe_required = True
            self.probe_inflight = False
            self.generation += 1
            self.condition.notify_all()
            return max(0.0, self.blocked_until - now)

    def remaining(self) -> float:
        with self.condition:
            return max(0.0, self.blocked_until - time.monotonic())
