from __future__ import annotations

import contextlib
import threading
import time

from ..events import Stopped


class AdaptiveRateLimiter:
    def __init__(self, delay: float, max_workers: int = 1, adaptive: bool = True) -> None:
        self.base_delay = max(0.0, float(delay))
        self.max_workers = max(1, int(max_workers))
        self.adaptive = bool(adaptive)
        self.condition = threading.Condition()
        self.next_request = 0.0
        self.active = 0
        self.active_limit = self.max_workers
        self.cooldown_until = 0.0
        self.penalty = 1.0
        self.success_streak = 0

    @property
    def current_limit(self) -> int:
        with self.condition:
            return self.active_limit

    @property
    def effective_delay(self) -> float:
        with self.condition:
            return self.base_delay * self.penalty

    def _wait_interruptibly(self, stop_event: threading.Event, seconds: float) -> None:
        if seconds <= 0:
            return
        stop_event.wait(seconds)
        if stop_event.is_set():
            raise Stopped

    @contextlib.contextmanager
    def slot(self, stop_event: threading.Event):
        while True:
            with self.condition:
                if stop_event.is_set():
                    raise Stopped
                now = time.monotonic()
                wait = max(0.0, self.cooldown_until - now, self.next_request - now)
                if self.active < self.active_limit and wait <= 0:
                    self.active += 1
                    self.next_request = now + self.base_delay * self.penalty
                    break
                self.condition.wait(timeout=min(max(wait, 0.05), 0.5))
        try:
            yield
        finally:
            with self.condition:
                self.active = max(0, self.active - 1)
                self.condition.notify_all()

    def wait(self, stop_event: threading.Event) -> None:
        with self.slot(stop_event):
            return

    def record_success(self) -> None:
        with self.condition:
            self.success_streak += 1
            if self.adaptive and self.success_streak >= 25:
                if self.active_limit < self.max_workers:
                    self.active_limit += 1
                self.penalty = max(1.0, self.penalty * 0.8)
                self.success_streak = 0
                self.condition.notify_all()

    def record_failure(self, status: int | None = None, retry_after: float | None = None) -> None:
        if not self.adaptive:
            return
        with self.condition:
            self.success_streak = 0
            if status in {429, 502, 503, 504}:
                self.active_limit = max(1, self.active_limit // 2)
                self.penalty = min(16.0, max(2.0, self.penalty * 2.0))
                cooldown = max(float(retry_after or 0), min(120.0, max(2.0, self.base_delay * self.penalty * 4)))
                self.cooldown_until = max(self.cooldown_until, time.monotonic() + cooldown)
            else:
                self.penalty = min(8.0, max(1.0, self.penalty * 1.2))
            self.condition.notify_all()


SharedRateLimiter = AdaptiveRateLimiter
