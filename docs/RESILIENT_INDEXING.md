# Resilient CDX indexing

Archive Scout treats temporary Wayback failures as resumable state, not as a reason to abandon the project.

## Window subdivision

Text and direct-media indexing start with monthly windows. A timeout, temporary gateway response, or other splittable transient error subdivides only the failed interval:

```text
month
7 days
1 day
6 hours
1 hour
15 minutes
5 minutes
1 minute
15 seconds
5 seconds
1 second
```

The complete queue, failure count, current page size, and CDX resume key are stored in the project database.

## Smallest-window behavior

A one-second timeout cannot be divided further. Archive Scout then:

1. Lowers the page size for that window, down to a safe minimum.
2. Records a retryable transient delay.
3. Moves the window behind other pending windows when possible.
4. Saves the updated queue.
5. Retries with bounded exponential backoff.
6. Continues until the request succeeds or the user presses Stop.

This directly covers `urllib3.exceptions.ReadTimeoutError` from CDX requests. The exception is converted into a splittable transient request rather than escaping to the interface as a fatal run error.

## What can still stop an operation

Archive Scout does not retry permanent local or configuration failures forever. Examples include:

- malformed CDX parameters
- unsupported database schema
- database corruption
- missing write permission
- missing or damaged packaged runtime files
- invalid regular expressions supplied by the user

Progress is saved before a recoverable operation failure is surfaced.

## Resume

Use **Resume interrupted work** or rerun the original operation. Completed windows are skipped, and the pending split queue continues from the saved state.
