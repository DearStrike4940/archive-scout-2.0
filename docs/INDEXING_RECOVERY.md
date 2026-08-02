# Indexing recovery

This document has been replaced by [RESILIENT_INDEXING.md](RESILIENT_INDEXING.md).

Alpha 3 preserves the complete pending CDX queue and can subdivide failed requests down to one-second windows. At the smallest interval, transient failures are deferred and retried rather than terminating the operation.
