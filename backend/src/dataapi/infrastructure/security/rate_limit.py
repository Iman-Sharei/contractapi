"""In-memory sliding-window rate limiter (per client key)."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock

from dataapi.core.errors import AppError


@dataclass
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_seconds: int


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, *, limit: int, window_seconds: int = 60) -> RateLimitResult:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            q = self._hits[key]
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= limit:
                retry = int(window_seconds - (now - q[0])) + 1
                raise AppError(
                    type_="https://dataapi.dev/problems/rate-limited",
                    title="Too Many Requests",
                    status=429,
                    detail=f"Rate limit of {limit} requests per {window_seconds}s exceeded.",
                    extensions={
                        "retry_after": max(retry, 1),
                        "limit": limit,
                        "remaining": 0,
                        "reset": max(retry, 1),
                    },
                )
            q.append(now)
            remaining = max(limit - len(q), 0)
            reset = int(window_seconds - (now - q[0])) + 1 if q else window_seconds
            return RateLimitResult(
                allowed=True,
                limit=limit,
                remaining=remaining,
                reset_seconds=max(reset, 1),
            )


limiter = SlidingWindowRateLimiter()
