from __future__ import annotations

import threading
import time

from ..events import Stopped


class SharedRateLimiter:
    def __init__(self, delay: float) -> None:
        self.delay = max(0.0, delay)
        self.lock = threading.Lock()
        self.next_request = 0.0

    def wait(self, stop_event: threading.Event) -> None:
        with self.lock:
            if stop_event.is_set():
                raise Stopped
            wait = self.next_request - time.monotonic()
            if wait > 0:
                stop_event.wait(wait)
            if stop_event.is_set():
                raise Stopped
            self.next_request = time.monotonic() + self.delay
