"""Billing-oriented usage metering — durable-first (GAP-3).

One proxy call produces exactly one durable usage event.  When a Supabase
client is available (production), writes go to ``agent_usage_events`` and
reads query the same table.  Without Supabase (dev/test), an in-memory
event list is used as a fallback.

No double-write path: ``AgentUsageAnalytics.record_event()`` is *not*
called for event persistence.  The identity-store side-effect
(``record_usage``) is invoked directly.
"""

from __future__ import annotations

import logging
import math
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Tuple

from schemas.agent_identity import AgentIdentityStore, get_agent_identity_store

logger = logging.getLogger(__name__)

COST_PER_CALL_USD = 0.001

# Canonical result values — kept explicit per GAP-3 contract.
VALID_RESULTS = frozenset({"success", "error", "rate_limited", "auth_failed"})


@dataclass
class MeteredUsageEvent:
    """Single metered proxy call event."""

    event_id: str
    agent_id: str
    service: str
    result: str
    latency_ms: float
    response_size_bytes: int
    created_at: datetime


@dataclass
class UsageMeterSnapshot:
    """Usage and latency snapshot for an agent/service over a period."""

    agent_id: str
    service: str
    period_days: int
    call_count: int
    success_count: int
    failed_count: int
    rate_limited_count: int
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    avg_response_size_bytes: float


@dataclass
class ServiceMonthlyUsage:
    """Per-service monthly usage and cost for an agent or organization."""

    call_count: int
    cost_estimate: float


@dataclass
class MonthlyUsageSummary:
    """Monthly usage summary for one agent."""

    agent_id: str
    month: str
    total_calls: int
    by_service: Dict[str, ServiceMonthlyUsage]
    cost_estimate: float


@dataclass
class OrgMonthlyUsage:
    """Monthly usage summary for one organization."""

    organization_id: str
    month: str
    total_calls: int
    by_service: Dict[str, ServiceMonthlyUsage]
    by_agent: Dict[str, MonthlyUsageSummary]
    cost_estimate: float


class UsageMeterEngine:
    """Metering engine — single durable writer for ``agent_usage_events``.

    When ``supabase_client`` is provided, all writes go to Supabase and
    reads query Supabase.  Otherwise falls back to an in-memory event
    list for dev/test.
    """

    def __init__(
        self,
        identity_store: Optional[AgentIdentityStore] = None,
        supabase_client: Any = None,
        # Legacy parameter — accepted but no longer used for event persistence.
        usage_analytics: Any = None,
    ) -> None:
        self._identity_store = identity_store
        self._supabase = supabase_client
        self._events: List[MeteredUsageEvent] = []

    # ── Properties ───────────────────────────────────────────────────

    @property
    def supabase(self) -> Any:
        """Public accessor kept for backward compat (tests inspect this)."""
        return self._supabase

    @supabase.setter
    def supabase(self, value: Any) -> None:
        self._supabase = value

    @property
    def identity_store(self) -> AgentIdentityStore:
        """Get identity store dependency."""
        if self._identity_store is None:
            self._identity_store = get_agent_identity_store()
        return self._identity_store

    @property
    def _is_durable(self) -> bool:
        """True when a Supabase client is available."""
        return self._supabase is not None

    # ── Lazy Supabase (follows QueryLogger pattern) ──────────────────

    async def ensure_supabase(self) -> bool:
        """Attempt to resolve a Supabase client if none was injected.

        Call this once at application startup — not on every request.
        Returns True if a client is now available.
        """
        if self._supabase is not None:
            return True
        try:
            from db.client import get_supabase_client

            self._supabase = await get_supabase_client()
            return True
        except Exception:
            logger.debug("Supabase not available — using in-memory metering")
            return False

    # ── Write ────────────────────────────────────────────────────────

    async def record_metered_call(
        self,
        agent_id: str,
        service: str,
        success: bool,
        latency_ms: float,
        response_size_bytes: int,
        *,
        result: Optional[str] = None,
    ) -> str:
        """Record a metered proxy call.

        Writes exactly **one** event — either to Supabase or in-memory.
        Also updates the identity store ``last_used_at`` / ``last_used_result``.

        Args:
            agent_id: Agent identifier.
            service: Service name (e.g. ``"openai"``).
            success: Convenience boolean; ignored when *result* is provided.
            latency_ms: Round-trip latency in milliseconds.
            response_size_bytes: Response payload size.
            result: Explicit result string.  When ``None``, derived from
                *success* (``"success"`` / ``"error"``).

        Returns:
            Event ID (UUID string).
        """
        if result is None:
            result = "success" if success else "error"

        event = MeteredUsageEvent(
            event_id=str(uuid.uuid4()),
            agent_id=agent_id,
            service=service,
            result=result,
            latency_ms=latency_ms,
            response_size_bytes=max(0, int(response_size_bytes)),
            created_at=datetime.now(tz=UTC),
        )

        if self._is_durable:
            self._supabase.table("agent_usage_events").insert(
                {
                    "event_id": event.event_id,
                    "agent_id": event.agent_id,
                    "service": event.service,
                    "result": event.result,
                    "latency_ms": event.latency_ms,
                    "response_size_bytes": event.response_size_bytes,
                    "created_at": event.created_at.isoformat(),
                }
            ).execute()
        else:
            self._events.append(event)

        # Side-effect: update identity store (not a second event insert)
        try:
            await self.identity_store.record_usage(agent_id, service, result)
        except Exception:
            logger.debug("identity_store.record_usage failed — non-fatal", exc_info=True)

        return event.event_id

    # ── Reads ────────────────────────────────────────────────────────

    async def get_usage_snapshot(
        self,
        agent_id: str,
        service: str,
        period_days: int,
    ) -> Optional[UsageMeterSnapshot]:
        """Get a usage snapshot for one agent/service over ``period_days``."""
        cutoff = datetime.now(tz=UTC).timestamp() - (period_days * 86400)
        cutoff_iso = datetime.fromtimestamp(cutoff, tz=UTC).isoformat()

        if self._is_durable:
            rows = (
                self._supabase.table("agent_usage_events")
                .select("result,latency_ms,response_size_bytes")
                .eq("agent_id", agent_id)
                .eq("service", service)
                .gte("created_at", cutoff_iso)
                .execute()
            ).data or []

            if not rows:
                return None

            latencies = [float(r["latency_ms"]) for r in rows]
            response_sizes = [int(r["response_size_bytes"]) for r in rows]
            success_count = sum(1 for r in rows if r["result"] == "success")
            rate_limited_count = sum(1 for r in rows if r["result"] == "rate_limited")
            failed_count = sum(
                1 for r in rows if r["result"] in ("error", "auth_failed")
            )
        else:
            events = [
                e
                for e in self._events
                if e.agent_id == agent_id
                and e.service == service
                and e.created_at.timestamp() >= cutoff
            ]

            if not events:
                return None

            latencies = [e.latency_ms for e in events]
            response_sizes = [e.response_size_bytes for e in events]
            success_count = sum(1 for e in events if e.result == "success")
            rate_limited_count = sum(1 for e in events if e.result == "rate_limited")
            failed_count = sum(
                1 for e in events if e.result in ("error", "auth_failed")
            )

        return UsageMeterSnapshot(
            agent_id=agent_id,
            service=service,
            period_days=period_days,
            call_count=len(latencies),
            success_count=success_count,
            failed_count=failed_count,
            rate_limited_count=rate_limited_count,
            p50_latency_ms=self._percentile(latencies, 50),
            p95_latency_ms=self._percentile(latencies, 95),
            p99_latency_ms=self._percentile(latencies, 99),
            avg_response_size_bytes=(sum(response_sizes) / len(response_sizes)),
        )

    async def get_monthly_usage(self, agent_id: str, month: str) -> MonthlyUsageSummary:
        """Get monthly usage summary for one agent."""
        month_start, month_end = _month_bounds(month)

        if self._is_durable:
            rows = (
                self._supabase.table("agent_usage_events")
                .select("service")
                .eq("agent_id", agent_id)
                .gte("created_at", month_start.isoformat())
                .lt("created_at", month_end.isoformat())
                .execute()
            ).data or []

            by_service_counts: Dict[str, int] = defaultdict(int)
            for r in rows:
                by_service_counts[r["service"]] += 1
            total_calls = len(rows)
        else:
            month_events = [
                e
                for e in self._events
                if e.agent_id == agent_id and month_start <= e.created_at < month_end
            ]

            by_service_counts = defaultdict(int)
            for e in month_events:
                by_service_counts[e.service] += 1
            total_calls = len(month_events)

        by_service: Dict[str, ServiceMonthlyUsage] = {
            svc: ServiceMonthlyUsage(
                call_count=count,
                cost_estimate=round(count * COST_PER_CALL_USD, 6),
            )
            for svc, count in by_service_counts.items()
        }

        return MonthlyUsageSummary(
            agent_id=agent_id,
            month=month,
            total_calls=total_calls,
            by_service=by_service,
            cost_estimate=round(total_calls * COST_PER_CALL_USD, 6),
        )

    async def get_org_monthly_usage(self, organization_id: str, month: str) -> OrgMonthlyUsage:
        """Aggregate monthly usage across all agents in an organization."""
        agents = await self.identity_store.list_agents(organization_id=organization_id)

        by_agent: Dict[str, MonthlyUsageSummary] = {}
        by_service_counts: Dict[str, int] = defaultdict(int)
        total_calls = 0

        for agent in agents:
            summary = await self.get_monthly_usage(agent.agent_id, month)
            by_agent[agent.agent_id] = summary
            total_calls += summary.total_calls

            for svc, svc_summary in summary.by_service.items():
                by_service_counts[svc] += svc_summary.call_count

        by_service: Dict[str, ServiceMonthlyUsage] = {
            svc: ServiceMonthlyUsage(
                call_count=count,
                cost_estimate=round(count * COST_PER_CALL_USD, 6),
            )
            for svc, count in by_service_counts.items()
        }

        return OrgMonthlyUsage(
            organization_id=organization_id,
            month=month,
            total_calls=total_calls,
            by_service=by_service,
            by_agent=by_agent,
            cost_estimate=round(total_calls * COST_PER_CALL_USD, 6),
        )

    async def get_org_daily_average_calls(
        self,
        organization_id: str,
        days: int = 7,
    ) -> Tuple[int, float]:
        """Return ``(window_calls, daily_average_calls)`` for an organization."""
        cutoff = datetime.now(tz=UTC).timestamp() - (days * 86400)
        cutoff_iso = datetime.fromtimestamp(cutoff, tz=UTC).isoformat()
        agents = await self.identity_store.list_agents(organization_id=organization_id)
        agent_ids = {agent.agent_id for agent in agents}

        if self._is_durable and agent_ids:
            window_calls = 0
            for aid in agent_ids:
                rows = (
                    self._supabase.table("agent_usage_events")
                    .select("event_id", count="exact")
                    .eq("agent_id", aid)
                    .gte("created_at", cutoff_iso)
                    .execute()
                )
                window_calls += rows.count if rows.count is not None else len(rows.data or [])
        else:
            window_calls = sum(
                1
                for e in self._events
                if e.agent_id in agent_ids and e.created_at.timestamp() >= cutoff
            )

        return window_calls, (window_calls / days if days > 0 else 0.0)

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _percentile(values: List[float], percentile: int) -> float:
        """Nearest-rank percentile for a list of values."""
        if not values:
            return 0.0

        ordered = sorted(values)
        if len(ordered) == 1:
            return float(ordered[0])

        rank = int(math.ceil((percentile / 100.0) * len(ordered))) - 1
        rank = max(0, min(rank, len(ordered) - 1))
        return float(ordered[rank])


def _month_bounds(month: str) -> Tuple[datetime, datetime]:
    """Return UTC datetime bounds ``[start, end)`` for ``YYYY-MM``."""
    start = datetime.strptime(month, "%Y-%m").replace(tzinfo=UTC)

    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)

    return start, end


_meter_engine: Optional[UsageMeterEngine] = None


def get_usage_meter_engine(
    identity_store: Optional[AgentIdentityStore] = None,
    supabase_client: Any = None,
    # Legacy parameter — accepted for backward compat, not used.
    usage_analytics: Any = None,
) -> UsageMeterEngine:
    """Return (or create) the global :class:`UsageMeterEngine`."""
    global _meter_engine
    if _meter_engine is None:
        _meter_engine = UsageMeterEngine(
            identity_store=identity_store,
            supabase_client=supabase_client,
        )
    return _meter_engine


def reset_usage_meter_engine() -> None:
    """Reset usage meter singleton (for tests)."""
    global _meter_engine
    _meter_engine = None
