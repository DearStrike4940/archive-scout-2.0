from __future__ import annotations

import contextlib
import threading
import time

from ..events import Stopped


class FixedRateLimiter:
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
