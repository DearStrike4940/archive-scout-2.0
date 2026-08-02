# Network performance and HTTP recovery

Archive Scout separates user-selected speed from server-directed protection.

1. **Workers** control concurrent network waits.
2. **Request delay** is the fixed minimum interval between request starts.
3. **The shared Wayback circuit** activates for HTTP 429 or HTTP 503 with `Retry-After`.
4. **CDX window splitting** activates for transient query timeouts.

Worker count and request delays remain exactly as selected.

## Shared 429 circuit

When a request receives HTTP 429:

- `Retry-After` is honored when present;
- every worker pauses together;
- simultaneous 429 responses are combined into one incident;
- stale waiting requests are invalidated;
- one recovery probe runs after the pause;
- the normal queue reopens only after that probe succeeds;
- queued captures remain pending.

The default wait budget is `0`, meaning the operation waits until Wayback recovers or the user presses Stop.

## Connection pooling

Text pages, media, and CDX responses use a shared `urllib3` keep-alive pool with separate connection and read timeouts. Redirect and error responses are drained before connection reuse. Response bodies are streamed and maximum-size limits are applied during the stream.

## Bounded queues

Text and media downloaders keep no more than twice the worker count in flight. This reduces memory use, avoids an initial request burst, and makes Stop more responsive.

## CDX timeouts

CDX requests are serial and resumable. A read timeout subdivides only the failed time interval. A minimum one-second interval is retried with a smaller page size and bounded backoff instead of interrupting the project.

## Combined media indexing

Direct media discovery no longer performs one query per extension. All selected extensions are combined into one server-side regular expression per target and window, reducing request count substantially for mixed image/video jobs.

## Balanced starting settings

```text
Workers: 4
CDX delay: 1.0 seconds
Download delay: 0.5 seconds
429 base pause: 30 seconds
429 maximum pause: 300 seconds
429 wait budget: 0 minutes
```

Lower delays are not always faster. More HTTP 429 responses can create more total idle time.
