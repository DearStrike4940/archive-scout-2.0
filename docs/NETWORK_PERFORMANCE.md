# Network performance and HTTP 429 recovery

Archive Scout 2.0.0-alpha.2.7 separates user-selected speed from server-directed protection:

1. **Workers** control how many requests can wait on network I/O.
2. **Request delay** is the fixed minimum interval between request starts.
3. **The shared Wayback circuit** activates only after HTTP 429, or HTTP 503 with `Retry-After`.

Worker count and request delays remain exactly as selected. Archive Scout does not silently reduce workers, rewrite delays, or gradually change speed.

## Shared circuit breaker

All workers in one text, media, or CDX pool share a host gate. When any request receives HTTP 429:

- `Retry-After` is honored when present;
- every worker pauses together;
- simultaneous 429 responses are coalesced into one incident;
- requests already waiting to start are invalidated rather than leaking through;
- after the pause, exactly one recovery probe is allowed through;
- the normal queue reopens only after that probe receives a non-rate-limited response;
- queued captures stay pending instead of becoming hundreds or thousands of errors.

When `Retry-After` is absent, repeated incidents use bounded exponential pauses beginning at the configured base pause and never exceeding the configured maximum pause.

The default wait budget is `0`, meaning the operation keeps waiting until Wayback recovers or the user presses **Stop**. Setting a nonzero budget makes Archive Scout save the queue and mark the operation interrupted after that amount of coordinated waiting. A server-level pause never consumes a capture's normal per-item download-attempt allowance.

## Connection pooling

Text pages, media, and CDX responses use a shared `urllib3` keep-alive pool with separate connect and read timeouts. This avoids building a new TLS connection for every archived file. Redirect and error responses are drained before a connection returns to the pool, redirects remain bounded, response bodies are streamed in chunks, and maximum-file-size limits are enforced during the stream.

## Bounded queues

Archive Scout keeps no more than twice the worker count in flight. This prevents a large project from submitting every URL at once, reduces memory and database churn, improves stopping behavior, and avoids an initial request burst.

## Recommended settings

Balanced default:

```text
Workers: 4
CDX delay: 1.0 seconds
Download delay: 0.5 seconds
429 base pause: 30 seconds
429 maximum pause: 300 seconds
429 wait budget: 0 minutes (keep waiting)
```

For a heavily throttled period:

```text
Workers: 3
CDX delay: 1.5 seconds
Download delay: 0.8 seconds
```

For small targeted jobs, 4–6 workers may improve throughput. Lowering request delay too far is usually counterproductive because more 429 responses create more idle time. Request-start spacing matters more than raw worker count once downloads are network-bound.

## Keyword scanning performance

Large literal or exact keyword sets use a compiled positive-match prefilter. Pages with no possible positive match skip full per-rule scoring. Normalized URL, title, body, source, and link fields are computed once per page and shared across selected keyword sets. Regex, case-sensitive, and whole-word rules retain the full matching path.

## CDX behavior

CDX requests remain serial and resumable. A timeout splits only the failed date range into smaller windows. HTTP 429 never triggers date splitting because rate limiting is a server-capacity signal rather than evidence that the query window is too large.
