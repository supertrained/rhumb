"""In-memory sliding-window rate limiter middleware.

Implements per-IP rate limiting with tiered limits for different endpoint
categories. Returns standard rate-limit headers and 429 Too Many Requests
when exceeded.

Architecture note: this is an in-memory implementation suitable for a
single-instance Railway deployment. For multi-instance, replace the
_buckets dict with a shared Redis store (the interface is the same).
"""

import time
from collections import defaultdict
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from db.client import get_supabase_client
from services.durable_rate_limit import DurableRateLimiter

# ── Rate Limit Tiers ────────────────────────────────────────────────
# (max_requests, window_seconds)
TIER_AUTH = (10, 60)        # Auth endpoints: 10/min (brute-force protection)
TIER_EXECUTE = (30, 60)     # Capability execution: 30/min
TIER_WRITE = (20, 60)       # Write operations: 20/min
TIER_READ = (120, 60)       # Public read endpoints: 120/min
TIER_HEALTH = (300, 60)     # Health/status: generous

# ── Route Classification ────────────────────────────────────────────
# Prefix-based tier assignment. More specific prefixes match first.
_ROUTE_TIERS: list[tuple[str, str, tuple[int, int]]] = [
    # (method, path_prefix, tier)
    ("POST", "/v1/auth/", TIER_AUTH),
    ("GET", "/v1/auth/", TIER_AUTH),
    ("POST", "/v1/capabilities/", TIER_EXECUTE),
    ("POST", "/v1/proxy/", TIER_EXECUTE),
    ("POST", "/v1/", TIER_WRITE),
    ("PUT", "/v1/", TIER_WRITE),
    ("GET", "/healthz", TIER_HEALTH),
    ("GET", "/v1/status", TIER_HEALTH),
    ("GET", "/v1/", TIER_READ),
]


def _classify(method: str, path: str) -> tuple[int, int]:
    """Return (max_requests, window_seconds) for the given request."""
    for route_method, prefix, tier in _ROUTE_TIERS:
        if method == route_method and path.startswith(prefix):
            return tier
    # Default: read tier
    return TIER_READ


def _client_ip(request: Request) -> str:
    """Extract the real client IP, respecting X-Forwarded-For from Railway."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # First IP in the chain is the real client
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ── Sliding Window Bucket ───────────────────────────────────────────
class _SlidingWindow:
    """Per-key sliding window counter with automatic cleanup."""

    __slots__ = ("timestamps",)

    def __init__(self):
        self.timestamps: list[float] = []

    def hit(self, now: float, window: float, limit: int) -> tuple[bool, int]:
        """Record a hit. Returns (allowed, remaining)."""
        # Evict expired timestamps
        cutoff = now - window
        self.timestamps = [t for t in self.timestamps if t > cutoff]

        remaining = max(0, limit - len(self.timestamps))
        if len(self.timestamps) >= limit:
            return False, 0

        self.timestamps.append(now)
        return True, remaining - 1  # -1 because we just consumed one


# Global bucket store. Keys are (ip, tier_key).
_buckets: dict[str, _SlidingWindow] = defaultdict(_SlidingWindow)
_last_cleanup = time.monotonic()
_CLEANUP_INTERVAL = 300  # Evict stale buckets every 5 minutes


def _maybe_cleanup(now: float):
    """Periodically remove empty/stale buckets to prevent memory growth."""
    global _last_cleanup
    if now - _last_cleanup < _CLEANUP_INTERVAL:
        return
    _last_cleanup = now
    stale_keys = [
        k for k, v in _buckets.items()
        if not v.timestamps or v.timestamps[-1] < now - 120
    ]
    for k in stale_keys:
        del _buckets[k]


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter with per-IP, per-tier enforcement."""

    def __init__(self, app):
        super().__init__(app)
        self._durable: DurableRateLimiter | None = None
        self._durable_init_attempted = False

    async def _get_durable(self) -> DurableRateLimiter | None:
        if self._durable is not None:
            return self._durable
        if self._durable_init_attempted:
            return None

        self._durable_init_attempted = True
        try:
            supabase = await get_supabase_client()
            self._durable = DurableRateLimiter(supabase)
        except Exception:
            self._durable = None
        return self._durable

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip rate limiting for OPTIONS (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Skip rate limiting for admin endpoints (they have their own auth)
        path = request.url.path
        if "/admin" in path:
            return await call_next(request)

        ip = _client_ip(request)
        limit, window = _classify(request.method, path)
        now = time.monotonic()

        durable = await self._get_durable()
        if durable is not None:
            bucket_key = f"ip:{ip}:{request.method}:{path}:{limit}:{window}"
            allowed, remaining = await durable.check_and_increment(bucket_key, limit, window)
            retry_after = window
        else:
            _maybe_cleanup(now)
            bucket_key = f"{ip}:{limit}:{window}"
            bucket = _buckets[bucket_key]
            allowed, remaining = bucket.hit(now, window, limit)
            retry_after = int(window - (now - bucket.timestamps[0])) + 1 if not allowed else window

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": f"Too many requests. Limit: {limit} per {window}s. Retry after {retry_after}s.",
                    "resolution": "Wait for the Retry-After period, or authenticate with an API key for higher limits.",
                    "request_id": getattr(request.state, "request_id", None),
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                    "X-Request-ID": getattr(request.state, "request_id", ""),
                },
            )

        response: Response = await call_next(request)

        # Add rate limit headers to all responses
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + window)

        return response
