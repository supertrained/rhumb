"""Read-only AN Score cache — structural separation layer (WU-41.4).

All routing, explanation, and provider-listing code MUST read scores through
this module.  The cache is populated by the scoring service (the only writer)
and refreshed on a configurable TTL.

Architectural invariants (from Resolve spec §2.4):
  - Routing engine reads scores from a read-only cache; cannot write to Score DB.
  - Cache is a read-only snapshot refreshed periodically.
  - No consumer of this module may mutate score data.
"""

from __future__ import annotations

import hashlib
import logging
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from config import settings

logger = logging.getLogger(__name__)

# ── Data types ────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CachedScore:
    """Immutable snapshot of a service's AN Score.  Consumers get this."""

    service_slug: str
    an_score: float
    execution_score: float
    access_readiness_score: float | None
    autonomy_score: float | None
    confidence: float
    tier: str
    refreshed_at: float  # monotonic clock when this entry was fetched


@dataclass(frozen=True, slots=True)
class ScoreAuditEntry:
    """Chain-hashed immutable audit record for a score change event."""

    entry_id: str
    service_slug: str
    old_score: float | None
    new_score: float
    change_reason: str  # "initial" | "recalculation" | "evidence_update"
    timestamp: datetime
    chain_hash: str  # SHA-256(prev_hash + entry_id + service_slug + new_score + timestamp)
    prev_hash: str


# ── Read-only cache ──────────────────────────────────────────────────


class ScoreReadCache:
    """Thread-safe, TTL-based read-only score cache.

    Populated by ``refresh()`` which pulls from the score DB (Supabase).
    All public methods are read-only.
    """

    def __init__(
        self,
        *,
        ttl_seconds: float = 300.0,
        max_entries: int = 5000,
    ) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._store: dict[str, CachedScore] = {}
        self._lock = threading.RLock()
        self._last_full_refresh: float = 0.0
        self._clock = time.monotonic

    # ── Public read-only API ──────────────────────────────────────

    def get(self, service_slug: str) -> CachedScore | None:
        """Return cached score for a service, or None if absent/expired."""
        with self._lock:
            entry = self._store.get(service_slug)
            if entry is None:
                return None
            if self._clock() - entry.refreshed_at > self._ttl:
                # Expired — remove and return None
                self._store.pop(service_slug, None)
                return None
            return entry

    def get_many(self, slugs: list[str]) -> dict[str, CachedScore]:
        """Batch lookup.  Returns only found/valid entries."""
        now = self._clock()
        result: dict[str, CachedScore] = {}
        expired: list[str] = []
        with self._lock:
            for slug in slugs:
                entry = self._store.get(slug)
                if entry is None:
                    continue
                if now - entry.refreshed_at > self._ttl:
                    expired.append(slug)
                    continue
                result[slug] = entry
            for slug in expired:
                self._store.pop(slug, None)
        return result

    def scores_by_slug(self, slugs: list[str]) -> dict[str, float]:
        """Convenience: return {slug: an_score} for routing consumers."""
        entries = self.get_many(slugs)
        return {slug: entry.an_score for slug, entry in entries.items()}

    def all_scores(self) -> dict[str, CachedScore]:
        """Return a snapshot of all valid cached scores."""
        now = self._clock()
        with self._lock:
            return {
                slug: entry
                for slug, entry in self._store.items()
                if now - entry.refreshed_at <= self._ttl
            }

    @property
    def last_refresh_age_seconds(self) -> float:
        """Seconds since last full refresh, or infinity if never refreshed."""
        if self._last_full_refresh == 0.0:
            return float("inf")
        return self._clock() - self._last_full_refresh

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._store)

    # ── Refresh (called by scoring service / background task) ─────

    def _populate(self, entries: list[CachedScore]) -> int:
        """Internal: replace cache contents with fresh entries.

        Called by the scoring service's refresh routine — the only writer.
        """
        now = self._clock()
        new_store: dict[str, CachedScore] = {}
        for entry in entries:
            new_store[entry.service_slug] = CachedScore(
                service_slug=entry.service_slug,
                an_score=entry.an_score,
                execution_score=entry.execution_score,
                access_readiness_score=entry.access_readiness_score,
                autonomy_score=entry.autonomy_score,
                confidence=entry.confidence,
                tier=entry.tier,
                refreshed_at=now,
            )
        with self._lock:
            self._store = new_store
            self._last_full_refresh = now
        return len(new_store)

    def _upsert(self, entry: CachedScore) -> None:
        """Internal: update a single entry (after a score recomputation)."""
        now = self._clock()
        refreshed = CachedScore(
            service_slug=entry.service_slug,
            an_score=entry.an_score,
            execution_score=entry.execution_score,
            access_readiness_score=entry.access_readiness_score,
            autonomy_score=entry.autonomy_score,
            confidence=entry.confidence,
            tier=entry.tier,
            refreshed_at=now,
        )
        with self._lock:
            self._store[entry.service_slug] = refreshed
            # Evict oldest if over capacity
            if len(self._store) > self._max_entries:
                oldest_key = min(
                    self._store,
                    key=lambda k: self._store[k].refreshed_at,
                )
                self._store.pop(oldest_key, None)


# ── Score audit chain ─────────────────────────────────────────────


class ScoreAuditChain:
    """Append-only, chain-hashed audit log for score changes.

    Each entry is linked to the previous via SHA-256 chain hash.
    This is the structural guarantee that score mutations are auditable.
    """

    GENESIS_HASH = "0" * 64

    def __init__(self) -> None:
        self._entries: list[ScoreAuditEntry] = []
        self._lock = threading.Lock()
        self._prev_hash: str = self.GENESIS_HASH
        self._entry_counter: int = 0

    @staticmethod
    def _compute_hash(
        prev_hash: str,
        entry_id: str,
        service_slug: str,
        new_score: float,
        timestamp: str,
    ) -> str:
        payload = f"{prev_hash}|{entry_id}|{service_slug}|{new_score:.4f}|{timestamp}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def append(
        self,
        service_slug: str,
        old_score: float | None,
        new_score: float,
        change_reason: str = "recalculation",
    ) -> ScoreAuditEntry:
        """Record a score change.  Returns the new audit entry."""
        with self._lock:
            self._entry_counter += 1
            entry_id = f"saud_{self._entry_counter:08d}"
            now = datetime.now(timezone.utc)
            chain_hash = self._compute_hash(
                self._prev_hash,
                entry_id,
                service_slug,
                new_score,
                now.isoformat(),
            )
            entry = ScoreAuditEntry(
                entry_id=entry_id,
                service_slug=service_slug,
                old_score=old_score,
                new_score=new_score,
                change_reason=change_reason,
                timestamp=now,
                chain_hash=chain_hash,
                prev_hash=self._prev_hash,
            )
            self._entries.append(entry)
            self._prev_hash = chain_hash
            return entry

    def history(
        self,
        service_slug: str | None = None,
        limit: int = 50,
    ) -> list[ScoreAuditEntry]:
        """Return audit entries, optionally filtered by service slug."""
        with self._lock:
            if service_slug:
                filtered = [e for e in self._entries if e.service_slug == service_slug]
            else:
                filtered = list(self._entries)
        return filtered[-limit:]

    def verify_chain(self) -> bool:
        """Verify the integrity of the entire audit chain."""
        with self._lock:
            prev_hash = self.GENESIS_HASH
            for entry in self._entries:
                expected = self._compute_hash(
                    prev_hash,
                    entry.entry_id,
                    entry.service_slug,
                    entry.new_score,
                    entry.timestamp.isoformat(),
                )
                if entry.chain_hash != expected or entry.prev_hash != prev_hash:
                    return False
                prev_hash = entry.chain_hash
            return True

    @property
    def length(self) -> int:
        with self._lock:
            return len(self._entries)

    @property
    def latest_hash(self) -> str:
        with self._lock:
            return self._prev_hash


# ── Supabase refresh helper ──────────────────────────────────────


async def fetch_scores_from_db() -> list[CachedScore]:
    """Pull latest scores from the score DB (Supabase).

    This is the ONLY function that touches the score DB for reads.
    It returns immutable CachedScore entries for the cache to ingest.
    """
    url = (
        f"{settings.supabase_url}/rest/v1/scores"
        f"?select=service_slug,aggregate_recommendation_score,execution_score,access_readiness_score,autonomy_score,confidence,tier,dimension_snapshot,calculated_at"
        f"&order=calculated_at.desc"
    )
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            rows = resp.json()
    except Exception:
        logger.exception("score_cache_refresh_failed")
        return []

    # Deduplicate: keep only the latest per slug (query ordered desc)
    seen: set[str] = set()
    entries: list[CachedScore] = []
    for row in rows:
        slug = row.get("service_slug")
        if not slug or slug in seen:
            continue
        seen.add(slug)

        snapshot = row.get("dimension_snapshot") or {}
        breakdown = snapshot.get("score_breakdown", {})
        aggregate_score = row.get("aggregate_recommendation_score")
        base_score = row.get("score")

        resolved_an_score = aggregate_score if aggregate_score is not None else base_score
        if resolved_an_score is None:
            continue

        resolved_execution_score = row.get("execution_score")
        if resolved_execution_score is None:
            resolved_execution_score = breakdown.get("execution", resolved_an_score)

        resolved_access_readiness = row.get("access_readiness_score")
        if resolved_access_readiness is None:
            resolved_access_readiness = breakdown.get("access_readiness")

        resolved_autonomy = row.get("autonomy_score")
        if resolved_autonomy is None:
            resolved_autonomy = breakdown.get("autonomy")

        entries.append(CachedScore(
            service_slug=slug,
            an_score=float(resolved_an_score),
            execution_score=float(resolved_execution_score),
            access_readiness_score=(
                float(resolved_access_readiness)
                if resolved_access_readiness is not None
                else None
            ),
            autonomy_score=(
                float(resolved_autonomy)
                if resolved_autonomy is not None
                else None
            ),
            confidence=float(row.get("confidence", 0.5)) if "confidence" in row else 0.5,
            tier=str(row.get("tier", "L1")) if "tier" in row else "L1",
            refreshed_at=0.0,  # Will be set by _populate
        ))

    return entries


# ── Module-level singletons ──────────────────────────────────────

_score_cache: ScoreReadCache | None = None
_audit_chain: ScoreAuditChain | None = None


def get_score_cache() -> ScoreReadCache:
    """Return the module-level score cache singleton."""
    global _score_cache
    if _score_cache is None:
        _score_cache = ScoreReadCache(ttl_seconds=300.0, max_entries=5000)
    return _score_cache


def get_audit_chain() -> ScoreAuditChain:
    """Return the module-level audit chain singleton."""
    global _audit_chain
    if _audit_chain is None:
        _audit_chain = ScoreAuditChain()
    return _audit_chain


# ── Background auto-refresh task ─────────────────────────────────

import asyncio

_refresh_task: asyncio.Task | None = None
_refresh_stop_event: asyncio.Event | None = None

REFRESH_INTERVAL_SECONDS = 300.0  # 5 minutes


async def _refresh_loop(
    cache: ScoreReadCache,
    interval: float = REFRESH_INTERVAL_SECONDS,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Background loop that refreshes the score cache periodically.

    Runs until cancelled or stop_event is set.
    """
    logger.info(
        "score_cache_refresh_loop_started interval=%.0fs",
        interval,
    )
    while True:
        try:
            entries = await fetch_scores_from_db()
            if entries:
                count = cache._populate(entries)
                logger.info(
                    "score_cache_refreshed count=%d age=%.1fs",
                    count,
                    cache.last_refresh_age_seconds,
                )
            else:
                logger.warning("score_cache_refresh_empty — DB returned no scores")
        except Exception:
            logger.exception("score_cache_refresh_error")

        # Wait for the interval or until stopped
        if stop_event:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
                break  # stop_event was set
            except asyncio.TimeoutError:
                continue  # Normal timeout — loop again
        else:
            await asyncio.sleep(interval)


async def start_score_cache_refresh() -> None:
    """Start the background score cache refresh task.

    Call once during application startup (lifespan).
    """
    global _refresh_task, _refresh_stop_event

    cache = get_score_cache()

    # Initial synchronous warm-up
    try:
        entries = await fetch_scores_from_db()
        if entries:
            count = cache._populate(entries)
            logger.info("score_cache_initial_warmup count=%d", count)
        else:
            logger.warning("score_cache_initial_warmup_empty")
    except Exception:
        logger.exception("score_cache_initial_warmup_failed")

    # Start background loop
    _refresh_stop_event = asyncio.Event()
    _refresh_task = asyncio.create_task(
        _refresh_loop(cache, REFRESH_INTERVAL_SECONDS, _refresh_stop_event),
        name="score_cache_refresh",
    )


async def stop_score_cache_refresh() -> None:
    """Stop the background score cache refresh task.

    Call during application shutdown (lifespan).
    """
    global _refresh_task, _refresh_stop_event

    if _refresh_stop_event:
        _refresh_stop_event.set()

    if _refresh_task and not _refresh_task.done():
        try:
            await asyncio.wait_for(_refresh_task, timeout=5.0)
        except asyncio.TimeoutError:
            _refresh_task.cancel()
            try:
                await _refresh_task
            except asyncio.CancelledError:
                pass
        logger.info("score_cache_refresh_loop_stopped")

    _refresh_task = None
    _refresh_stop_event = None
