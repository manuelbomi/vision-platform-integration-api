"""In-memory token-bucket rate limiting, keyed by API key.

This is intentionally the simplest thing that works for a single-instance
deployment: one bucket per API key, refilled continuously at a fixed rate,
capped at a maximum burst size. No external service required.

For a multi-instance deployment behind a load balancer, this in-process
dict stops being authoritative (each instance would enforce its own
limit independently, effectively multiplying the real limit by the number
of instances). The production fix is to move the bucket state to Redis
(e.g. via a small Lua script for atomic check-and-decrement) so every
instance shares the same counters - see the README's hardening notes.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status

from .auth import require_api_key
from .config import settings


@dataclass
class _Bucket:
    tokens: float
    last_refill: float


class TokenBucketRateLimiter:
    def __init__(self, capacity: int = 20, refill_rate_per_sec: float = 5.0) -> None:
        self.capacity = capacity
        self.refill_rate_per_sec = refill_rate_per_sec
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Return True and consume one token if the caller is under limit."""
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                # First request for this key: start full, minus the token
                # this call consumes.
                self._buckets[key] = _Bucket(tokens=self.capacity - 1, last_refill=now)
                return True

            elapsed = max(0.0, now - bucket.last_refill)
            bucket.tokens = min(self.capacity, bucket.tokens + elapsed * self.refill_rate_per_sec)
            bucket.last_refill = now

            if bucket.tokens >= 1:
                bucket.tokens -= 1
                return True
            return False


# Lazily-constructed process-wide limiter, so it always reflects the current
# `settings` values at first use (tests mutate `settings` before resetting).
_limiter: TokenBucketRateLimiter | None = None


def get_rate_limiter() -> TokenBucketRateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = TokenBucketRateLimiter(
            capacity=settings.rate_limit_capacity,
            refill_rate_per_sec=settings.rate_limit_refill_per_sec,
        )
    return _limiter


def reset_rate_limiter() -> None:
    """Drop the process-wide limiter so it gets rebuilt from current settings.

    Used by tests and by anything that changes rate limit settings at
    runtime; production code normally never needs this.
    """
    global _limiter
    _limiter = None


async def enforce_rate_limit(api_key: str = Depends(require_api_key)) -> str:
    """FastAPI dependency: authenticate, then enforce the token bucket.

    Chaining on ``require_api_key`` means auth failures (401/403) are
    reported before rate limiting is even considered.
    """
    limiter = get_rate_limiter()
    if not limiter.allow(api_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded, slow down",
        )
    return api_key
