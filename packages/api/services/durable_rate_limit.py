"""AUD-21: Durable rate limiting that survives restarts and works across workers.

Problem: rate_limit.py and upstream_budget.py use in-memory dictionaries that
reset on every deploy/restart. An attacker can bypass rate limits by timing
attacks around deploys, and legitimate rate state is lost on restarts.

Solution: A durable sliding-window rate limiter backed by Supabase.
- State persists across restarts
- Works across multiple workers (shared DB state)
- Falls back to in-memory if DB is unavailable (fail-open with warning)
- Periodic cleanup of expired windows

Architecture: This module provides the durable backend. The existing
RateLimitMiddleware can be wired to use this instead of _buckets.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


class DurableRateLimiter:
    """Database-backed sliding-window rate limiter.

    Each rate limit check atomically increments a counter in the DB
    and returns whether the request is allowed.

    Uses a simple counter-per-window approach (fixed windows with
    interpolation) rather than storing individual timestamps, which
    is more efficient for DB storage.
    """

    def __init__(
        self,
        supabase_client: Any,
        *,
        cleanup_interval_seconds: int = 300,
    ) -> None:
        self._db = supabase_client
        self._cleanup_interval = cleanup_interval_seconds
        self._last_cleanup = 0.0
        # In-memory fallback for when DB is unavailable
        self._fallback: dict[str, _FallbackWindow] = {}

    async def check_and_increment(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> tuple[bool, int]:
        """Check if a request is allowed and increment the counter.

        Args:
            key: Rate limit key (e.g., "ip:1.2.3.4:execute")
            limit: Maximum requests per window
            window_seconds: Window duration in seconds

        Returns:
            (allowed, remaining): Whether the request is allowed and
            how many requests remain in the current window
        """
        try:
            result = await self._db_check_increment(key, limit, window_seconds)
            return result
        except Exception:
            logger.warning(
                "durable_rate_limit_db_failed key=%s, falling back to in-memory",
                key, exc_info=True,
            )
            return self._fallback_check(key, limit, window_seconds)

    async def _db_check_increment(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> tuple[bool, int]:
        """Atomic check-and-increment via database RPC."""
        now = datetime.now(timezone.utc)

        # Periodic cleanup
        mono_now = time.monotonic()
        if mono_now - self._last_cleanup > self._cleanup_interval:
            await self._cleanup_expired()
            self._last_cleanup = mono_now

        result = await self._db.rpc("rate_limit_check", {
            "p_key": key,
            "p_limit": limit,
            "p_window_seconds": window_seconds,
            "p_now": now.isoformat(),
        }).execute()

        if result.data and isinstance(result.data, list) and len(result.data) > 0:
            row = result.data[0]
            allowed = row.get("allowed", False)
            remaining = row.get("remaining", 0)
            return allowed, remaining

        # If RPC returned unexpected shape, allow (fail-open)
        return True, limit - 1

    def _fallback_check(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> tuple[bool, int]:
        """In-memory fallback when DB is unavailable."""
        now = time.monotonic()
        window = self._fallback.get(key)

        if window is None or now - window.window_start > window_seconds:
            self._fallback[key] = _FallbackWindow(
                count=1, window_start=now
            )
            return True, limit - 1

        if window.count >= limit:
            return False, 0

        window.count += 1
        remaining = limit - window.count
        return True, remaining

    async def get_state(self, key: str) -> dict[str, Any] | None:
        """Get current rate limit state for a key (for diagnostics)."""
        try:
            result = await self._db.table("rate_limit_windows").select(
                "key, request_count, window_start, window_end"
            ).eq("key", key).maybe_single().execute()

            if result.data:
                return result.data
        except Exception:
            logger.warning("durable_rate_limit_get_state_failed key=%s", key, exc_info=True)
        return None

    async def reset(self, key: str) -> bool:
        """Reset rate limit state for a key (admin operation)."""
        try:
            await self._db.table("rate_limit_windows").delete().eq("key", key).execute()
            self._fallback.pop(key, None)
            return True
        except Exception:
            logger.warning("durable_rate_limit_reset_failed key=%s", key, exc_info=True)
            return False

    async def _cleanup_expired(self) -> None:
        """Delete expired rate limit windows."""
        try:
            cutoff = datetime.now(timezone.utc).isoformat()
            await self._db.table("rate_limit_windows").delete().lt(
                "window_end", cutoff
            ).execute()
        except Exception:
            logger.warning("durable_rate_limit_cleanup_failed", exc_info=True)

        # Also clean up in-memory fallback
        now = time.monotonic()
        stale = [k for k, v in self._fallback.items() if now - v.window_start > 300]
        for k in stale:
            del self._fallback[k]


class _FallbackWindow:
    """Simple in-memory rate limit window for fallback."""
    __slots__ = ("count", "window_start")

    def __init__(self, count: int, window_start: float):
        self.count = count
        self.window_start = window_start
