"""A tiny in process sliding window rate limiter.

Sufficient for login throttling on a single worker. Behind multiple workers a shared
store would be needed, noted for the production hardening pass.
"""

import time
from collections import defaultdict, deque

_hits: dict[str, deque[float]] = defaultdict(deque)


class RateLimiter:
    def __init__(self, max_hits: int, window_seconds: float) -> None:
        self.max_hits = max_hits
        self.window = window_seconds

    def allow(self, key: str) -> bool:
        now = time.time()
        bucket = _hits[key]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.max_hits:
            return False
        bucket.append(now)
        return True


login_limiter = RateLimiter(max_hits=5, window_seconds=60.0)
