# Performance comparison with the attached Wayback Machine Downloader

The attached downloader exposes several useful performance ideas at its public entry points:

- one reusable HTTP client with connection pooling;
- separate overall, connect, and read timeouts;
- concurrent/asynchronous support libraries;
- extension and keyword filtering before download;
- single-timestamp deduplication;
- fast-search dependencies such as `ahocorasick_rs`, `orjson`, and `selectolax`.

Its actual archive engine is imported from `libs.archive_downloader`, which was not included in the supplied files. Archive Scout therefore does not claim byte-for-byte or algorithm-for-algorithm parity with the unseen implementation.

## What Archive Scout adopts

- `urllib3.PoolManager` keep-alive pools for CDX, page, and media requests.
- Separate connect and read timeouts.
- Fixed global request-start spacing shared by all workers.
- Bounded concurrency instead of submitting the complete archive at once.
- Extension filtering, URL filtering, CDX collapse controls, and snapshot strategies before downloads begin.
- Batched SQLite writes and resumable index windows.
- A compiled literal prefilter for large keyword sets.
- Normalized page fields shared by multiple keyword sets in the same scan.

## What Archive Scout adds beyond the visible downloader layer

- A host-wide 429 circuit breaker.
- Exact `Retry-After` handling.
- Coalescing of simultaneous 429 responses.
- Stale-permit invalidation so workers already waiting cannot leak through a newly closed circuit.
- One half-open recovery probe before the full queue resumes.
- Unlimited coordinated waiting by default, with user-controlled Stop and an optional finite wait budget.
- Rate-limit pauses that never consume per-URL retry allowances.
- Persistent SQLite state for interruption, restart, scan history, review data, and errors.
- Resumable CDX window subdivision for large or timing-out searches.
- Streamed maximum-size enforcement for text and media.
- Redirect/error response draining before keep-alive reuse.

## Deliberate differences

Archive Scout uses a transparent project user agent rather than browser impersonation. It does not add Torch, Transformers, or a CLIP model to the core downloader because those packages support image similarity search rather than faster archive retrieval and would greatly increase installer size and platform risk.

The current implementation favors a small, testable runtime (`truststore` and `urllib3`) over a large optimization stack. Faster native parsers and JSON decoders can be evaluated later behind optional feature flags after cross-platform packaging is stable.
