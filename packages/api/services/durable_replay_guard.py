"""AUD-25: Durable x402 transaction replay prevention.

Problem: The tx_hash replay guard in capability_execute.py uses an in-memory
dict that resets on every restart. An attacker can replay a tx_hash after a
deploy to get a second execution for free.

Solution: Check the `usdc_receipts` table (already persists tx_hashes) and
a dedicated `tx_replay_guard` table for atomic claim-then-execute.

Design:
- Atomic INSERT with ON CONFLICT prevents TOCTOU races
- Falls back to in-memory if DB unavailable (fail-open with warning)
- 24-hour TTL with periodic cleanup
- Works across workers via shared DB state
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


class ReplayGuardUnavailable(RuntimeError):
    """Raised when durable replay protection is unavailable and fallback is disallowed."""


class DurableReplayGuard:
    """Database-backed transaction replay prevention.

    Ensures each tx_hash can only be used once for execution,
    persisting across restarts and multiple workers.
    """

    def __init__(
        self,
        supabase_client: Any,
        *,
        ttl_seconds: int = 86400,  # 24 hours
        cleanup_interval_seconds: int = 3600,
    ) -> None:
        self._db = supabase_client
        self._ttl_seconds = ttl_seconds
        self._cleanup_interval = cleanup_interval_seconds
        self._last_cleanup = 0.0
        # In-memory fallback
        self._fallback: dict[str, float] = {}

    async def check_and_claim(self, tx_hash: str, *, allow_fallback: bool = True) -> bool:
        """Check if a tx_hash has been used. Returns True if it's a REPLAY (reject).

        Atomically claims the hash if it hasn't been used.

        If ``allow_fallback`` is False, database failures raise
        ``ReplayGuardUnavailable`` instead of silently degrading to
        per-process memory.
        """
        key = tx_hash.lower().strip()
        if not key:
            return True  # Empty hash is always a replay

        try:
            return await self._db_check_and_claim(key)
        except Exception as exc:
            if not allow_fallback:
                logger.error(
                    "durable_replay_guard_unavailable tx=%s fail_closed=true",
                    key[:16],
                    exc_info=True,
                )
                raise ReplayGuardUnavailable("Durable replay protection unavailable") from exc
            logger.warning(
                "durable_replay_guard_db_failed tx=%s, falling back to in-memory",
                key[:16], exc_info=True,
            )
            return self._fallback_check(key)

    async def _db_check_and_claim(self, key: str) -> bool:
        """Atomic check-and-claim via database.

        INSERT with ON CONFLICT: if the row exists, it's a replay.
        """
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=self._ttl_seconds)

        # Periodic cleanup
        mono_now = time.monotonic()
        if mono_now - self._last_cleanup > self._cleanup_interval:
            await self._cleanup_expired()
            self._last_cleanup = mono_now

        try:
            # Also check usdc_receipts for historical tx hashes
            existing = await self._db.table("usdc_receipts").select(
                "tx_hash"
            ).eq("tx_hash", key).maybe_single().execute()

            if existing.data is not None:
                logger.warning("replay_detected_in_usdc_receipts tx=%s", key[:16])
                return True  # Replay from historical record

            # Atomic claim in replay guard table
            result = await self._db.table("tx_replay_guard").insert({
                "tx_hash": key,
                "claimed_at": now.isoformat(),
                "expires_at": expires.isoformat(),
            }).execute()

            return False  # First use, allowed

        except Exception as e:
            err_str = str(e)
            if "duplicate" in err_str.lower() or "unique" in err_str.lower() or "23505" in err_str:
                # Unique constraint violation = replay
                return True
            raise  # Re-raise for other errors

    def _fallback_check(self, key: str) -> bool:
        """In-memory fallback when DB is unavailable."""
        now = time.time()

        # Cleanup stale entries
        stale = [k for k, ts in self._fallback.items() if now - ts > self._ttl_seconds]
        for k in stale:
            del self._fallback[k]

        if key in self._fallback:
            return True  # Replay

        self._fallback[key] = now
        return False  # First use

    async def _cleanup_expired(self) -> None:
        """Delete expired replay guard entries."""
        try:
            cutoff = datetime.now(timezone.utc).isoformat()
            await self._db.table("tx_replay_guard").delete().lt(
                "expires_at", cutoff
            ).execute()
        except Exception:
            logger.warning("durable_replay_guard_cleanup_failed", exc_info=True)

    async def is_known(self, tx_hash: str) -> bool:
        """Check if a tx_hash is known without claiming it (read-only)."""
        key = tx_hash.lower().strip()
        try:
            # Check both tables
            guard = await self._db.table("tx_replay_guard").select(
                "tx_hash"
            ).eq("tx_hash", key).maybe_single().execute()
            if guard.data:
                return True

            receipt = await self._db.table("usdc_receipts").select(
                "tx_hash"
            ).eq("tx_hash", key).maybe_single().execute()
            if receipt.data:
                return True

            return False
        except Exception:
            return key in self._fallback
