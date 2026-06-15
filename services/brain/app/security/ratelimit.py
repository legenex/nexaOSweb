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
# Password reset request and confirm share a throttle, kept modest to blunt both reset email
# spamming and token guessing while leaving room for an honest retry. Callers namespace the key
# (for example "pwreset:<host>") so it does not share a bucket with the login limiter.
password_reset_limiter = RateLimiter(max_hits=5, window_seconds=300.0)
