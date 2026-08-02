# Performance comparison with the attached Wayback Machine Downloader

The attached downloader's visible entry points use several useful performance ideas:

- one reusable HTTP client with connection pooling;
- separate overall, connection, and read timeouts;
- concurrent/asynchronous support libraries;
- extension and keyword filtering before download;
- single-timestamp deduplication;
- optional fast-search dependencies.

Its actual archive engine is imported from `libs.archive_downloader`, which was not included in the supplied files. Archive Scout therefore does not claim exact parity with unseen pagination, scheduling, storage, or retry code.

## What Archive Scout adopts

- `urllib3.PoolManager` keep-alive pools for CDX, page, and media requests.
- Separate connection and read timeouts.
- Fixed request-start spacing shared by workers.
- Bounded in-flight queues instead of submitting a complete archive at once.
- Extension filtering, URL filtering, CDX collapse controls, and snapshot strategies before downloads.
- Batched SQLite writes and resumable index windows.
- Compiled literal prefiltering for large keyword sets.
- Normalized page fields shared by multiple keyword sets in one scan.
- One combined direct-media CDX extension filter instead of one request stream per extension.

## What Archive Scout adds

- A host-wide HTTP 429 circuit breaker.
- Exact `Retry-After` handling.
- Coalescing of simultaneous rate-limit responses.
- One recovery probe before the full queue resumes.
- Unlimited coordinated waiting by default, with user-controlled Stop.
- Persistent SQLite state for interruption, restart, scan history, review work, and errors.
- CDX timeout subdivision down to one-second windows.
- Automatic smallest-window retry with reduced page sizes instead of a fatal timeout.
- Streamed maximum-size enforcement for text and media.
- Redirect/error response draining before keep-alive reuse.
- Forum reconstruction, identifier extraction, legacy embed recovery, duplicate analysis, provenance, snapshot comparison, and project merging.

## Deliberate differences

Archive Scout uses a transparent project user agent rather than browser impersonation. It does not add Torch, Transformers, or a CLIP model to the downloader core because those packages support image similarity rather than faster archive retrieval and would greatly increase installer size and platform risk.

The runtime remains intentionally small: `truststore` and `urllib3`. Optional native parsers or decoders can be evaluated later after cross-platform packaging and the project format are frozen.
