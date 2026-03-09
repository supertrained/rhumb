"""Billing-oriented usage metering built on top of Round 11 analytics.

Tracks metered proxy calls and exposes billing-friendly snapshots and
monthly aggregates per agent and organization.
"""

from __future__ import annotations

import math
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Tuple

from schemas.agent_identity import AgentIdentityStore, get_agent_identity_store
from services.agent_usage_analytics import AgentUsageAnalytics, get_usage_analytics

COST_PER_CALL_USD = 0.001


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
    """Metering engine that wraps :class:`AgentUsageAnalytics`.

    Uses in-memory storage in v1; production persistence can be routed
    to Supabase in later rounds.
    """

    def __init__(
        self,
        usage_analytics: Optional[AgentUsageAnalytics] = None,
        identity_store: Optional[AgentIdentityStore] = None,
        supabase_client: Any = None,
    ) -> None:
        self._analytics = usage_analytics
        self._identity_store = identity_store
        self.supabase = supabase_client
        self._events: List[MeteredUsageEvent] = []

    @property
    def analytics(self) -> AgentUsageAnalytics:
        """Get usage analytics dependency."""
        if self._analytics is None:
            self._analytics = get_usage_analytics(self.identity_store, self.supabase)
        return self._analytics

    @property
    def identity_store(self) -> AgentIdentityStore:
        """Get identity store dependency."""
        if self._identity_store is None:
            self._identity_store = get_agent_identity_store()
        return self._identity_store

    async def record_metered_call(
        self,
        agent_id: str,
        service: str,
        success: bool,
        latency_ms: float,
        response_size_bytes: int,
    ) -> str:
        """Record a metered proxy call.

        Also records into Round 11 analytics to preserve a single source
        of truth for general usage telemetry.

        Returns:
            Metered event ID.
        """
        result = "success" if success else "error"
        await self.analytics.record_event(
            agent_id=agent_id,
            service=service,
            result=result,
            latency_ms=latency_ms,
        )

        event = MeteredUsageEvent(
            event_id=str(uuid.uuid4()),
            agent_id=agent_id,
            service=service,
            result=result,
            latency_ms=latency_ms,
            response_size_bytes=max(0, int(response_size_bytes)),
            created_at=datetime.now(tz=UTC),
        )

        if self.supabase is not None:
            self.supabase.table("agent_usage_events").insert(
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

        return event.event_id

    async def get_usage_snapshot(
        self,
        agent_id: str,
        service: str,
        period_days: int,
    ) -> Optional[UsageMeterSnapshot]:
        """Get a usage snapshot for one agent/service over ``period_days``."""
        cutoff = datetime.now(tz=UTC).timestamp() - (period_days * 86400)
        events = [
            event
            for event in self._events
            if event.agent_id == agent_id
            and event.service == service
            and event.created_at.timestamp() >= cutoff
        ]

        if not events:
            return None

        latencies = [event.latency_ms for event in events]
        response_sizes = [event.response_size_bytes for event in events]

        success_count = sum(1 for event in events if event.result == "success")
        rate_limited_count = sum(1 for event in events if event.result == "rate_limited")
        failed_count = sum(
            1 for event in events if event.result in ("error", "auth_failed")
        )

        return UsageMeterSnapshot(
            agent_id=agent_id,
            service=service,
            period_days=period_days,
            call_count=len(events),
            success_count=success_count,
            failed_count=failed_count,
            rate_limited_count=rate_limited_count,
            p50_latency_ms=self._percentile(latencies, 50),
            p95_latency_ms=self._percentile(latencies, 95),
            p99_latency_ms=self._percentile(latencies, 99),
            avg_response_size_bytes=(sum(response_sizes) / len(response_sizes)),
        )

    async def get_monthly_usage(self, agent_id: str, month: str) -> MonthlyUsageSummary:
        """Get monthly usage summary for one agent.

        Args:
            agent_id: Agent identifier.
            month: Month key in ``YYYY-MM`` format.
        """
        month_start, month_end = _month_bounds(month)
        month_events = [
            event
            for event in self._events
            if event.agent_id == agent_id and month_start <= event.created_at < month_end
        ]

        by_service_counts: Dict[str, int] = defaultdict(int)
        for event in month_events:
            by_service_counts[event.service] += 1

        by_service: Dict[str, ServiceMonthlyUsage] = {
            service: ServiceMonthlyUsage(
                call_count=count,
                cost_estimate=round(count * COST_PER_CALL_USD, 6),
            )
            for service, count in by_service_counts.items()
        }

        total_calls = len(month_events)
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

            for service, service_summary in summary.by_service.items():
                by_service_counts[service] += service_summary.call_count

        by_service: Dict[str, ServiceMonthlyUsage] = {
            service: ServiceMonthlyUsage(
                call_count=count,
                cost_estimate=round(count * COST_PER_CALL_USD, 6),
            )
            for service, count in by_service_counts.items()
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
        agents = await self.identity_store.list_agents(organization_id=organization_id)
        agent_ids = {agent.agent_id for agent in agents}

        window_calls = sum(
            1
            for event in self._events
            if event.agent_id in agent_ids and event.created_at.timestamp() >= cutoff
        )
        return window_calls, (window_calls / days if days > 0 else 0.0)

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
    usage_analytics: Optional[AgentUsageAnalytics] = None,
    identity_store: Optional[AgentIdentityStore] = None,
    supabase_client: Any = None,
) -> UsageMeterEngine:
    """Return (or create) the global :class:`UsageMeterEngine`."""
    global _meter_engine
    if _meter_engine is None:
        _meter_engine = UsageMeterEngine(usage_analytics, identity_store, supabase_client)
    return _meter_engine


def reset_usage_meter_engine() -> None:
    """Reset usage meter singleton (for tests)."""
    global _meter_engine
    _meter_engine = None
