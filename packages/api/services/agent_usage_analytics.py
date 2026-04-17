"""Usage tracking and aggregation per agent per service.

Tracks every proxy call with result status and provides aggregation
queries for usage summaries — per-agent, per-service, and per-org.

GAP-3: ``UsageMeterEngine`` is the canonical durable writer for
``agent_usage_events``.  This module retains ``record_event()`` for
backward compatibility (direct callers, identity-integration tests)
but the metering engine no longer delegates event persistence here.

Reads are now durable-aware: when a Supabase client is present,
``_query_events`` and ``get_recent_events`` query the durable table
so both analytics and billing share a single source of truth.

Round 11 (WU 2.2): Usage analytics layer.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional

from schemas.agent_identity import AgentIdentityStore, get_agent_identity_store
from services.service_slugs import public_service_slug

logger = logging.getLogger(__name__)


def _public_usage_service_slug(service: Any) -> str:
    """Normalize a metered service id for public/reporting surfaces."""
    cleaned = str(service or "").strip().lower()
    if not cleaned:
        return ""
    return public_service_slug(cleaned) or cleaned


def _publicize_usage_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of a usage event with its public service id normalized."""
    normalized = dict(event)
    normalized["service"] = _public_usage_service_slug(event.get("service"))
    return normalized


class UsageEvent:
    """Single usage event (one proxy call)."""

    __slots__ = ("event_id", "agent_id", "service", "result", "latency_ms", "created_at")

    def __init__(
        self,
        agent_id: str,
        service: str,
        result: str,
        latency_ms: float = 0.0,
        created_at: Optional[datetime] = None,
    ) -> None:
        self.event_id = str(uuid.uuid4())
        self.agent_id = agent_id
        self.service = service
        self.result = result  # "success", "error", "rate_limited", "auth_failed"
        self.latency_ms = latency_ms
        self.created_at = created_at or datetime.now(tz=UTC)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "agent_id": self.agent_id,
            "service": self.service,
            "result": self.result,
            "latency_ms": self.latency_ms,
            "created_at": self.created_at.isoformat(),
        }


class AgentUsageAnalytics:
    """Track and aggregate usage per agent per service.

    When a Supabase client is present, reads query the durable
    ``agent_usage_events`` table.  Otherwise falls back to in-memory
    storage for dev/test.
    """

    def __init__(
        self,
        identity_store: Optional[AgentIdentityStore] = None,
        supabase_client: Any = None,
    ) -> None:
        self._identity_store = identity_store
        self.supabase = supabase_client
        # True once ensure_supabase() has been attempted (prevents repeated DB probes)
        self._supabase_attempted: bool = supabase_client is not None
        # In-memory event store (dev/test fallback)
        self._events: List[UsageEvent] = []

    @property
    def identity_store(self) -> AgentIdentityStore:
        if self._identity_store is None:
            self._identity_store = get_agent_identity_store()
        return self._identity_store

    # ── Lazy Supabase (mirrors UsageMeterEngine pattern) ─────────────

    async def ensure_supabase(self) -> bool:
        """Attempt to resolve a Supabase client if none was injected.

        Called lazily on first read so that the production singleton — created
        without a client — will still query durable storage once the DB is
        reachable.  Only probes once (guarded by ``_supabase_attempted``) to
        avoid repeated connection attempts.  Returns ``True`` if a client is
        now available.

        Tests that deliberately use in-memory mode should pass
        ``supabase_client=<mock>`` at construction time; the guard ensures
        those instances are never overridden by a stray real connection.
        """
        if self._supabase_attempted:
            return self.supabase is not None
        self._supabase_attempted = True
        try:
            from db.client import get_supabase_client

            self.supabase = await get_supabase_client()
            return True
        except Exception:
            logger.debug("Supabase not available — agent usage analytics using in-memory fallback")
            return False

    # ── Recording ────────────────────────────────────────────────────

    async def record_event(
        self,
        agent_id: str,
        service: str,
        result: str,
        latency_ms: float = 0.0,
    ) -> str:
        """Record a usage event.

        .. note::

            In production, prefer ``UsageMeterEngine.record_metered_call``
            which writes the canonical durable row with full schema
            (including ``response_size_bytes``).  This method is retained
            for backward compat and direct callers.

        Returns:
            ``event_id`` (UUID).
        """
        event = UsageEvent(
            agent_id=agent_id,
            service=service,
            result=result,
            latency_ms=latency_ms,
        )

        if self.supabase is not None:
            await self.supabase.table("agent_usage_events").insert(event.to_dict()).execute()
        else:
            self._events.append(event)

        # Update last_used on service access record
        await self.identity_store.record_usage(agent_id, service, result)

        return event.event_id

    # ── Aggregation ──────────────────────────────────────────────────

    async def get_usage_summary(
        self,
        agent_id: str,
        service: Optional[str] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Aggregate usage for an agent over a time window.

        Returns:
            {
                "agent_id": str,
                "period_days": int,
                "total_calls": int,
                "successful_calls": int,
                "failed_calls": int,
                "rate_limited_calls": int,
                "services": { "<name>": { "calls": int, "success_rate": float } },
                "avg_latency_ms": float,
            }
        """
        cutoff = datetime.now(tz=UTC) - timedelta(days=days)
        events = [_publicize_usage_event(event) for event in await self._query_events(agent_id, cutoff)]

        requested_service = _public_usage_service_slug(service)
        if requested_service:
            events = [event for event in events if event.get("service") == requested_service]

        total = len(events)
        success = sum(1 for e in events if e["result"] == "success")
        failed = sum(1 for e in events if e["result"] in ("error", "auth_failed"))
        rate_limited = sum(1 for e in events if e["result"] == "rate_limited")
        avg_latency = (
            sum(float(e["latency_ms"]) for e in events) / total if total > 0 else 0.0
        )

        # Per-service breakdown
        by_service: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"calls": 0, "successes": 0}
        )
        for e in events:
            by_service[e["service"]]["calls"] += 1
            if e["result"] == "success":
                by_service[e["service"]]["successes"] += 1

        services_summary: Dict[str, Dict[str, Any]] = {}
        for svc, counts in by_service.items():
            rate = counts["successes"] / counts["calls"] if counts["calls"] > 0 else 0.0
            services_summary[svc] = {
                "calls": counts["calls"],
                "success_rate": round(rate, 4),
            }

        return {
            "agent_id": agent_id,
            "period_days": days,
            "total_calls": total,
            "successful_calls": success,
            "failed_calls": failed,
            "rate_limited_calls": rate_limited,
            "services": services_summary,
            "avg_latency_ms": round(avg_latency, 2),
        }

    async def get_organization_usage(
        self,
        organization_id: str,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Aggregate usage across all agents in an organization."""
        agents = await self.identity_store.list_agents(
            organization_id=organization_id
        )

        total_calls = 0
        agents_usage: Dict[str, Any] = {}

        for agent in agents:
            summary = await self.get_usage_summary(agent.agent_id, days=days)
            agents_usage[agent.agent_id] = summary
            total_calls += summary["total_calls"]

        return {
            "organization_id": organization_id,
            "period_days": days,
            "total_calls": total_calls,
            "agents": agents_usage,
        }

    # ── Query Helpers ────────────────────────────────────────────────

    async def _query_events(
        self,
        agent_id: str,
        cutoff: datetime,
    ) -> List[Dict[str, Any]]:
        """Query events from durable storage or in-memory fallback.

        Returns a list of dicts with at least ``result``, ``latency_ms``,
        and ``service`` keys — uniform across both paths.
        """
        if self.supabase is not None:
            query = (
                self.supabase.table("agent_usage_events")
                .select("event_id,agent_id,service,result,latency_ms,created_at")
                .eq("agent_id", agent_id)
                .gte("created_at", cutoff.isoformat())
            )
            resp = await query.execute()
            rows = resp.data or []
            return rows

        results: List[Dict[str, Any]] = []
        for e in self._events:
            if e.agent_id != agent_id:
                continue
            if e.created_at < cutoff:
                continue
            results.append(e.to_dict())
        return results

    async def get_recent_events(
        self,
        agent_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get recent events for an agent (most recent first)."""
        if self.supabase is not None:
            resp = await (
                self.supabase.table("agent_usage_events")
                .select("event_id,agent_id,service,result,latency_ms,created_at")
                .eq("agent_id", agent_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return [_publicize_usage_event(event) for event in (resp.data or [])]

        agent_events = [e for e in self._events if e.agent_id == agent_id]
        agent_events.sort(key=lambda e: e.created_at, reverse=True)
        return [_publicize_usage_event(e.to_dict()) for e in agent_events[:limit]]

    @property
    def total_events(self) -> int:
        """Total number of tracked events (in-memory only)."""
        return len(self._events)


# ── Singleton ────────────────────────────────────────────────────────

_analytics: Optional[AgentUsageAnalytics] = None


def get_usage_analytics(
    identity_store: Optional[AgentIdentityStore] = None,
    supabase_client: Any = None,
) -> AgentUsageAnalytics:
    """Return (or create) the global :class:`AgentUsageAnalytics`."""
    global _analytics
    if _analytics is None:
        _analytics = AgentUsageAnalytics(identity_store, supabase_client)
    return _analytics


def reset_usage_analytics() -> None:
    """Reset the singleton (for tests)."""
    global _analytics
    _analytics = None
