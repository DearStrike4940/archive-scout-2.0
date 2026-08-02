from __future__ import annotations

import threading
import time
import unittest

from archive_scout.downloads.rate_limit import FixedRateLimiter


class FixedRateLimiterTests(unittest.TestCase):
    def test_delay_remains_fixed(self) -> None:
        limiter = FixedRateLimiter(0.03)
        stop = threading.Event()
        started = time.monotonic()
        with limiter.slot(stop):
            pass
        with limiter.slot(stop):
            pass
        self.assertGreaterEqual(time.monotonic() - started, 0.02)

    def test_limiter_has_no_adaptive_state(self) -> None:
        limiter = FixedRateLimiter(0)
        self.assertFalse(hasattr(limiter, "active_limit"))
        self.assertFalse(hasattr(limiter, "cooldown_until"))
        self.assertFalse(hasattr(limiter, "record_failure"))


if __name__ == "__main__":
    unittest.main()
