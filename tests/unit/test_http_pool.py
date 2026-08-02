from __future__ import annotations

import concurrent.futures
import gzip
import threading
import time
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from archive_scout.cdx.client import HttpClient
from archive_scout.downloads.rate_limit import FixedRateLimiter, SharedHostGate


class RedirectGzipHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/data")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if self.path == "/data":
            payload = gzip.compress(b'{"ok":true}')
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args) -> None:
        return


class RateLimitThenOkHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    lock = threading.Lock()
    request_times: list[float] = []

    def do_GET(self) -> None:
        with type(self).lock:
            type(self).request_times.append(time.monotonic())
            number = len(type(self).request_times)
        if number == 1:
            self.send_response(429)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        payload = b"ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args) -> None:
        return


class HttpPoolTests(unittest.TestCase):
    def test_redirect_connection_is_drained_before_pool_reuse(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectGzipHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        client = HttpClient(
            FixedRateLimiter(0),
            retries=2,
            timeout=2,
            user_agent="ArchiveScout test",
            stop_event=threading.Event(),
            pool_size=1,
        )
        try:
            url = f"http://127.0.0.1:{server.server_port}/redirect"
            result = client.get(url, 1024, "application/json")
            self.assertEqual(result["data"], b'{"ok":true}')
            self.assertTrue(result["final_url"].endswith("/data"))
        finally:
            client.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_shared_circuit_blocks_stale_workers_until_one_probe_recovers(self) -> None:
        RateLimitThenOkHandler.request_times = []
        server = ThreadingHTTPServer(("127.0.0.1", 0), RateLimitThenOkHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        client = HttpClient(
            FixedRateLimiter(0.05),
            retries=2,
            timeout=3,
            user_agent="ArchiveScout test",
            stop_event=threading.Event(),
            pool_size=3,
            host_gate=SharedHostGate(base_pause=1, max_pause=1),
            rate_limit_attempts=0,
            rate_limit_max_wait=0,
        )
        try:
            url = f"http://127.0.0.1:{server.server_port}/data"
            with patch("archive_scout.downloads.rate_limit.random.uniform", return_value=1.0):
                with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                    results = list(pool.map(lambda _: client.get(url, 100)["data"], range(3)))
            self.assertEqual(results, [b"ok", b"ok", b"ok"])
            self.assertEqual(len(RateLimitThenOkHandler.request_times), 4)
            recovery_gap = RateLimitThenOkHandler.request_times[1] - RateLimitThenOkHandler.request_times[0]
            self.assertGreaterEqual(recovery_gap, 0.85)
        finally:
            client.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
