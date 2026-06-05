"""PP-16 durable state for Resolve route-plan enforcement.

This module keeps route-plan nonce state out of the signed token helper so the
cryptographic verifier remains pure while Runtime can still make one-time-use,
revocation, and kill-switch decisions against shared state.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from services.route_plan_enforcement import canonical_json_sha256

logger = logging.getLogger(__name__)


class RoutePlanStateUnavailable(RuntimeError):
    """Raised when route-plan durable state is required but unavailable."""


@dataclass(frozen=True, slots=True)
class RoutePlanClaim:
    """Outcome of checking and claiming a route-plan nonce."""

    allowed: bool
    stop_condition: str | None
    state_backend: str
    nonce_hash: str | None = None
    detail: str = ""


class RoutePlanStateStore:
    """Database-backed route-plan nonce/revocation state.

    Nonces are persisted as deterministic hashes so raw opaque-token internals
    do not need to be stored or surfaced. INSERT uniqueness provides the replay
    guard; explicit ``revoked`` rows provide operator invalidation.
    """

    def __init__(
        self,
        supabase_client: Any,
        *,
        cleanup_interval_seconds: int = 3600,
    ) -> None:
        self._db = supabase_client
        self._cleanup_interval = cleanup_interval_seconds
        self._last_cleanup = 0.0
        self._fallback: dict[str, float] = {}
        self._fallback_revoked: set[str] = set()

    async def check_and_claim(
        self,
        *,
        nonce: str | None,
        route_plan_id_hash: str | None,
        expires_at: int | float | datetime | None,
        allow_fallback: bool = True,
    ) -> RoutePlanClaim:
        """Atomically claim a nonce or return a fail-closed replay/revocation stop."""

        nonce_hash = _nonce_hash(nonce)
        if nonce_hash is None:
            return RoutePlanClaim(
                allowed=False,
                stop_condition="route_plan_missing",
                state_backend="none",
                detail="Route plan validation did not expose a nonce.",
            )

        try:
            return await self._db_check_and_claim(
                nonce_hash=nonce_hash,
                route_plan_id_hash=route_plan_id_hash,
                expires_at=_as_datetime(expires_at),
            )
        except Exception as exc:
            if not allow_fallback:
                logger.error(
                    "route_plan_state_unavailable nonce=%s fail_closed=true",
                    nonce_hash[:24],
                    exc_info=True,
                )
                raise RoutePlanStateUnavailable("Durable route-plan state unavailable") from exc
            logger.warning(
                "route_plan_state_db_failed nonce=%s; using memory fallback",
                nonce_hash[:24],
                exc_info=True,
            )
            return self._fallback_check_and_claim(nonce_hash, expires_at=_as_datetime(expires_at))

    async def revoke_nonce(
        self,
        nonce: str,
        *,
        reason: str = "revoked",
        route_plan_id_hash: str | None = None,
    ) -> RoutePlanClaim:
        """Persistently mark a route-plan nonce as revoked."""

        nonce_hash = _nonce_hash(nonce)
        if nonce_hash is None:
            return RoutePlanClaim(False, "route_plan_missing", "none")
        now = datetime.now(timezone.utc)
        row = {
            "nonce_hash": nonce_hash,
            "route_plan_id_hash": route_plan_id_hash,
            "state": "revoked",
            "claimed_at": now.isoformat(),
            "expires_at": (now + timedelta(days=7)).isoformat(),
            "revoked_at": now.isoformat(),
            "revocation_reason": reason,
        }
        try:
            await self._db.table("route_plan_state").upsert(row).execute()
            return RoutePlanClaim(True, None, "database", nonce_hash=nonce_hash)
        except Exception:
            self._fallback_revoked.add(nonce_hash)
            logger.warning("route_plan_revoke_db_failed nonce=%s", nonce_hash[:24], exc_info=True)
            return RoutePlanClaim(True, None, "memory_fallback", nonce_hash=nonce_hash)

    async def _db_check_and_claim(
        self,
        *,
        nonce_hash: str,
        route_plan_id_hash: str | None,
        expires_at: datetime,
    ) -> RoutePlanClaim:
        mono_now = time.monotonic()
        if mono_now - self._last_cleanup > self._cleanup_interval:
            await self._cleanup_expired()
            self._last_cleanup = mono_now

        existing = (
            await self._db.table("route_plan_state")
            .select("nonce_hash,state,revoked_at,revocation_reason")
            .eq("nonce_hash", nonce_hash)
            .maybe_single()
            .execute()
        )
        if existing.data:
            state = str(existing.data.get("state") or "claimed")
            if state == "revoked" or existing.data.get("revoked_at") is not None:
                return RoutePlanClaim(
                    allowed=False,
                    stop_condition="route_plan_revoked",
                    state_backend="database",
                    nonce_hash=nonce_hash,
                    detail=str(existing.data.get("revocation_reason") or "Route plan revoked."),
                )
            return RoutePlanClaim(
                allowed=False,
                stop_condition="route_plan_replay",
                state_backend="database",
                nonce_hash=nonce_hash,
                detail="Route plan nonce was already claimed.",
            )

        row = {
            "nonce_hash": nonce_hash,
            "route_plan_id_hash": route_plan_id_hash,
            "state": "claimed",
            "claimed_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        try:
            await self._db.table("route_plan_state").insert(row).execute()
        except Exception as exc:
            err = str(exc).lower()
            if "duplicate" in err or "unique" in err or "23505" in err:
                return RoutePlanClaim(
                    allowed=False,
                    stop_condition="route_plan_replay",
                    state_backend="database",
                    nonce_hash=nonce_hash,
                    detail="Route plan nonce was concurrently claimed.",
                )
            raise

        return RoutePlanClaim(True, None, "database", nonce_hash=nonce_hash)

    def _fallback_check_and_claim(self, nonce_hash: str, *, expires_at: datetime) -> RoutePlanClaim:
        now = time.time()
        stale = [key for key, expiry in self._fallback.items() if expiry <= now]
        for key in stale:
            self._fallback.pop(key, None)

        if nonce_hash in self._fallback_revoked:
            return RoutePlanClaim(
                False, "route_plan_revoked", "memory_fallback", nonce_hash=nonce_hash
            )
        if nonce_hash in self._fallback:
            return RoutePlanClaim(
                False, "route_plan_replay", "memory_fallback", nonce_hash=nonce_hash
            )

        self._fallback[nonce_hash] = expires_at.timestamp()
        return RoutePlanClaim(True, None, "memory_fallback", nonce_hash=nonce_hash)

    async def _cleanup_expired(self) -> None:
        try:
            cutoff = datetime.now(timezone.utc).isoformat()
            await self._db.table("route_plan_state").delete().lt("expires_at", cutoff).execute()
        except Exception:
            logger.warning("route_plan_state_cleanup_failed", exc_info=True)


_route_plan_state_store: RoutePlanStateStore | None = None


async def init_route_plan_state_store(
    supabase_client: Any | None = None,
) -> RoutePlanStateStore:
    """Return the module-level route-plan state store."""

    global _route_plan_state_store
    if _route_plan_state_store is not None:
        return _route_plan_state_store

    if supabase_client is None:
        try:
            from db.client import get_supabase_client

            supabase_client = await get_supabase_client()
        except Exception:
            logger.warning(
                "route_plan_state_init_failed; using in-memory fallback",
                exc_info=True,
            )
            supabase_client = _UnavailableSupabase()
    _route_plan_state_store = RoutePlanStateStore(supabase_client)
    return _route_plan_state_store


def reset_route_plan_state_store_for_tests() -> None:
    """Clear the module singleton for focused tests."""

    global _route_plan_state_store
    _route_plan_state_store = None


def _nonce_hash(nonce: str | None) -> str | None:
    if not nonce:
        return None
    return canonical_json_sha256({"route_plan_nonce": str(nonce)})


def _as_datetime(value: int | float | datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromtimestamp(float(value), tz=timezone.utc)


class _UnavailableSupabase:
    def table(self, name: str) -> Any:
        raise RoutePlanStateUnavailable("Supabase route-plan state store unavailable")
