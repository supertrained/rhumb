"""AUD-4: Durable idempotency store backed by Supabase.

Replaces the in-memory IdempotencyStore with a database-backed version
that survives restarts and works across multiple workers.

Design:
- Atomic claim-then-execute: INSERT with ON CONFLICT prevents TOCTOU races
- TTL-based expiration: entries expire after configurable window (default 1h)
- Periodic cleanup: expired entries are pruned on check() calls
- Fallback: if DB is unavailable, logs warning and allows execution
  (fail-open is intentional — better to risk a duplicate than block all executions)
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    """Stored result for a previous execution with this key."""

    key: str
    execution_id: str
    recipe_id: str
    status: str
    result_hash: str
    created_at: datetime
    expires_at: datetime


class DurableIdempotencyStore:
    """Database-backed idempotency store for recipe executions.

    Ensures retry-safe execution across restarts and multiple workers:
    - Same key → same result (within TTL window)
    - Atomic claim via INSERT ... ON CONFLICT
    - Periodic cleanup of expired entries

    Falls back to allowing execution if DB is unavailable (fail-open).
    """

    def __init__(
        self,
        supabase_client: Any,
        *,
        window_seconds: int = 3600,
        cleanup_interval_seconds: int = 300,
    ) -> None:
        self._db = supabase_client
        self._window_seconds = window_seconds
        self._cleanup_interval = cleanup_interval_seconds
        self._last_cleanup = 0.0

    async def check(self, key: str) -> IdempotencyRecord | None:
        """Check if an idempotency key has a stored result.

        Returns the stored record if found and not expired, else None.
        Also triggers periodic cleanup of expired entries.
        """
        try:
            # Periodic cleanup
            now = time.monotonic()
            if now - self._last_cleanup > self._cleanup_interval:
                await self._cleanup_expired()
                self._last_cleanup = now

            result = await self._db.table("idempotency_keys").select(
                "key, execution_id, recipe_id, status, result_hash, created_at, expires_at"
            ).eq("key", key).maybe_single().execute()

            if result.data is None:
                return None

            row = result.data
            expires_at = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > expires_at:
                # Expired — delete and return None
                await self._db.table("idempotency_keys").delete().eq("key", key).execute()
                return None

            return IdempotencyRecord(
                key=row["key"],
                execution_id=row["execution_id"],
                recipe_id=row["recipe_id"],
                status=row["status"],
                result_hash=row["result_hash"],
                created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
                expires_at=expires_at,
            )
        except Exception:
            logger.warning("durable_idempotency_check_failed key=%s", key, exc_info=True)
            return None  # Fail-open: allow execution if DB unavailable

    async def claim(
        self,
        key: str,
        execution_id: str,
        recipe_id: str,
        org_id: str = "",
        agent_id: str = "",
    ) -> IdempotencyRecord | None:
        """Atomically claim an idempotency key for a new execution.

        Returns None if the claim succeeded (key was not previously claimed).
        Returns the existing IdempotencyRecord if the key was already claimed
        (another worker got there first).

        This is the atomic guard against TOCTOU races: the INSERT uses
        ON CONFLICT to detect concurrent claims.
        """
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=self._window_seconds)

        try:
            # Try to insert — if key already exists, the ON CONFLICT returns the existing row
            result = await self._db.rpc("idempotency_claim", {
                "p_key": key,
                "p_execution_id": execution_id,
                "p_recipe_id": recipe_id,
                "p_status": "pending",
                "p_result_hash": "",
                "p_expires_at": expires.isoformat(),
                "p_org_id": org_id or None,
                "p_agent_id": agent_id or None,
            }).execute()

            if result.data and isinstance(result.data, list) and len(result.data) > 0:
                row = result.data[0]
                if row.get("already_exists"):
                    return IdempotencyRecord(
                        key=row["key"],
                        execution_id=row["execution_id"],
                        recipe_id=row["recipe_id"],
                        status=row["status"],
                        result_hash=row["result_hash"],
                        created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
                        expires_at=datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00")),
                    )
            return None  # Claim succeeded

        except Exception:
            logger.warning("durable_idempotency_claim_failed key=%s", key, exc_info=True)
            return None  # Fail-open

    async def store(
        self,
        key: str,
        execution_id: str,
        recipe_id: str,
        status: str,
        result_hash: str,
    ) -> IdempotencyRecord:
        """Store/update an execution result for an idempotency key."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=self._window_seconds)

        record = IdempotencyRecord(
            key=key,
            execution_id=execution_id,
            recipe_id=recipe_id,
            status=status,
            result_hash=result_hash,
            created_at=now,
            expires_at=expires,
        )

        try:
            await self._db.table("idempotency_keys").upsert({
                "key": key,
                "execution_id": execution_id,
                "recipe_id": recipe_id,
                "status": status,
                "result_hash": result_hash,
                "created_at": now.isoformat(),
                "expires_at": expires.isoformat(),
            }).execute()
        except Exception:
            logger.warning("durable_idempotency_store_failed key=%s", key, exc_info=True)

        return record

    async def _cleanup_expired(self) -> None:
        """Delete expired idempotency entries."""
        try:
            cutoff = datetime.now(timezone.utc).isoformat()
            await self._db.table("idempotency_keys").delete().lt(
                "expires_at", cutoff
            ).execute()
        except Exception:
            logger.warning("durable_idempotency_cleanup_failed", exc_info=True)

    @staticmethod
    def generate_key(
        recipe_id: str,
        inputs: dict[str, Any],
        agent_id: str = "",
    ) -> str:
        """Generate a deterministic idempotency key from recipe + inputs + agent."""
        payload = json.dumps(
            {"recipe_id": recipe_id, "inputs": inputs, "agent_id": agent_id},
            sort_keys=True,
            separators=(",", ":"),
        )
        return f"idem_{hashlib.sha256(payload.encode()).hexdigest()[:32]}"
