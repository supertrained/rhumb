"""Per-agent, per-service rate limiter for the proxy service.

Uses a Redis sorted-set sliding window (one key per agent+service pair).
Falls open (allows requests) when Redis is unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable


@runtime_checkable
class RedisLike(Protocol):
    """Minimal async Redis interface used by the rate limiter."""

    async def zcount(self, name: str, *, min: float, max: float) -> int: ...  # noqa: A002
    async def zadd(self, name: str, mapping: dict[str, float]) -> Any: ...
    async def expire(self, name: str, time: int) -> Any: ...


@dataclass
class RateLimitStatus:
    """Snapshot of the current rate-limit state for a single key."""

    remaining: int
    limit: int
    reset_at: datetime
    is_limited: bool


class RateLimiter:
    """Sliding-window rate limiter backed by Redis sorted sets.

    Each ``(agent_id, service)`` pair is tracked under a Redis key
    ``ratelimit:{agent_id}:{service}`` where members are timestamps
    scored by their epoch value.

    If Redis is unavailable the limiter **fails open** (allows the request).
    """

    def __init__(self, redis_client: Optional[RedisLike] = None) -> None:
        self.redis = redis_client
        # In-memory fallback when no Redis client is provided.
        self._mem_store: Dict[str, List[float]] = {}

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

    async def check_rate_limit(
        self,
        agent_id: str,
        service: str,
        limit_qpm: int,
    ) -> Tuple[bool, RateLimitStatus]:
        """Check (and record) a request against the sliding window.

        Args:
            agent_id: Agent making the request.
            service: Target provider service.
            limit_qpm: Allowed requests per minute.

        Returns:
            ``(allowed, status)`` — *allowed* is ``True`` when under limit.
        """
        key = f"ratelimit:{agent_id}:{service}"
        now = datetime.utcnow()
        now_ts = now.timestamp()
        window_start_ts = (now - timedelta(seconds=60)).timestamp()

        count = await self._count_in_window(key, window_start_ts, now_ts)

        remaining = max(0, limit_qpm - count)
        is_limited = remaining <= 0

        reset_at = datetime.utcfromtimestamp(window_start_ts) + timedelta(seconds=60)

        status = RateLimitStatus(
            remaining=remaining,
            limit=limit_qpm,
            reset_at=reset_at,
            is_limited=is_limited,
        )

        if not is_limited:
            await self._record_request(key, now_ts)

        return (not is_limited), status

    # ------------------------------------------------------------------
    # Redis / in-memory helpers
    # ------------------------------------------------------------------

    async def _count_in_window(
        self, key: str, window_start: float, window_end: float
    ) -> int:
        """Count requests in the sliding window."""
        if self.redis is not None:
            try:
                count: int = await self.redis.zcount(key, min=window_start, max=window_end)
                return count
            except Exception:
                pass  # fail-open

        # In-memory fallback
        entries = self._mem_store.get(key, [])
        return sum(1 for ts in entries if window_start <= ts <= window_end)

    async def _record_request(self, key: str, ts: float) -> None:
        """Record a request timestamp."""
        if self.redis is not None:
            try:
                await self.redis.zadd(key, {str(ts): ts})
                await self.redis.expire(key, 120)
                return
            except Exception:
                pass  # fall through to memory

        # In-memory fallback
        if key not in self._mem_store:
            self._mem_store[key] = []
        self._mem_store[key].append(ts)
        # Prune entries older than 2 min
        cutoff = ts - 120
        self._mem_store[key] = [t for t in self._mem_store[key] if t > cutoff]

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def reset(self, agent_id: str, service: str) -> None:
        """Clear in-memory entries for a key (used in tests)."""
        key = f"ratelimit:{agent_id}:{service}"
        self._mem_store.pop(key, None)


# ------------------------------------------------------------------
# Singleton accessor
# ------------------------------------------------------------------

_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter(redis_client: Optional[RedisLike] = None) -> RateLimiter:
    """Return (or create) the global :class:`RateLimiter` singleton."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(redis_client)
    return _rate_limiter
