"""GAP-3 metering durability tests.

Tests cover:
- Durable write path (mock Supabase) — exactly one row per proxy call
- Durable read path — get_usage_snapshot, get_monthly_usage,
  get_org_monthly_usage, get_org_daily_average_calls all query Supabase
- Duplicate-write regression — one call must NOT produce two durable rows
- In-memory fallback still works (existing behavior)
- Explicit result semantics (success, error, rate_limited, auth_failed)
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

import pytest

from schemas.agent_identity import AgentIdentityStore, reset_identity_store
from services.agent_usage_analytics import AgentUsageAnalytics, reset_usage_analytics
from services.usage_metering import (
    COST_PER_CALL_USD,
    MeteredUsageEvent,
    UsageMeterEngine,
    reset_usage_meter_engine,
)


def _run(coro):  # type: ignore[no-untyped-def]
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Mock Supabase ────────────────────────────────────────────────────


class _MockQueryBuilder:
    """Minimal Supabase query-builder mock that stores rows in a dict-of-lists."""

    def __init__(self, tables: Dict[str, List[Dict[str, Any]]]) -> None:
        self._tables = tables
        self._table_name: str = ""
        self._insert_data: Optional[Dict[str, Any]] = None
        self._select_columns: Optional[str] = None
        self._count_mode: Optional[str] = None
        self._filters: List[tuple] = []
        self._order_col: Optional[str] = None
        self._order_desc: bool = False
        self._limit_val: Optional[int] = None

    def table(self, name: str) -> "_MockQueryBuilder":
        qb = _MockQueryBuilder(self._tables)
        qb._table_name = name
        self._tables.setdefault(name, [])
        return qb

    def insert(self, data: Dict[str, Any]) -> "_MockQueryBuilder":
        self._insert_data = data
        return self

    def select(self, columns: str = "*", *, count: Optional[str] = None) -> "_MockQueryBuilder":
        self._select_columns = columns
        self._count_mode = count
        return self

    def eq(self, col: str, val: Any) -> "_MockQueryBuilder":
        self._filters.append(("eq", col, val))
        return self

    def gte(self, col: str, val: Any) -> "_MockQueryBuilder":
        self._filters.append(("gte", col, val))
        return self

    def lt(self, col: str, val: Any) -> "_MockQueryBuilder":
        self._filters.append(("lt", col, val))
        return self

    def order(self, col: str, *, desc: bool = False) -> "_MockQueryBuilder":
        self._order_col = col
        self._order_desc = desc
        return self

    def limit(self, n: int) -> "_MockQueryBuilder":
        self._limit_val = n
        return self

    async def execute(self) -> "_MockResult":
        rows = self._tables.get(self._table_name, [])

        if self._insert_data is not None:
            rows.append(dict(self._insert_data))
            return _MockResult(data=[self._insert_data], count=1)

        # Apply filters
        filtered = list(rows)
        for op, col, val in self._filters:
            if op == "eq":
                filtered = [r for r in filtered if r.get(col) == val]
            elif op == "gte":
                filtered = [r for r in filtered if r.get(col, "") >= val]
            elif op == "lt":
                filtered = [r for r in filtered if r.get(col, "") < val]

        # Select columns
        if self._select_columns and self._select_columns != "*":
            cols = [c.strip() for c in self._select_columns.split(",")]
            filtered = [{c: r.get(c) for c in cols} for r in filtered]

        # Order
        if self._order_col:
            filtered.sort(key=lambda r: r.get(self._order_col, ""), reverse=self._order_desc)

        # Limit
        if self._limit_val is not None:
            filtered = filtered[: self._limit_val]

        return _MockResult(data=filtered, count=len(filtered))


class _MockResult:
    def __init__(self, data: List[Dict[str, Any]], count: int) -> None:
        self.data = data
        self.count = count


class MockSupabaseClient:
    """Supabase client mock that tracks all table writes."""

    def __init__(self) -> None:
        self._tables: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    def table(self, name: str) -> _MockQueryBuilder:
        qb = _MockQueryBuilder(self._tables)
        return qb.table(name)

    def rows(self, table: str) -> List[Dict[str, Any]]:
        """Test helper — return all rows in a table."""
        return list(self._tables.get(table, []))

    def row_count(self, table: str) -> int:
        return len(self._tables.get(table, []))


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_identity_store()
    reset_usage_analytics()
    reset_usage_meter_engine()
    yield  # type: ignore[misc]
    reset_identity_store()
    reset_usage_analytics()
    reset_usage_meter_engine()


@pytest.fixture
def identity_store() -> AgentIdentityStore:
    return AgentIdentityStore(supabase_client=None)


@pytest.fixture
def mock_sb() -> MockSupabaseClient:
    return MockSupabaseClient()


@pytest.fixture
def durable_meter(identity_store: AgentIdentityStore, mock_sb: MockSupabaseClient) -> UsageMeterEngine:
    """UsageMeterEngine wired to mock Supabase (durable mode)."""
    return UsageMeterEngine(identity_store=identity_store, supabase_client=mock_sb)


@pytest.fixture
def inmem_meter(identity_store: AgentIdentityStore) -> UsageMeterEngine:
    """UsageMeterEngine without Supabase (in-memory fallback)."""
    return UsageMeterEngine(identity_store=identity_store)


def _register(identity_store: AgentIdentityStore, org: str = "org_1") -> str:
    agent_id, _ = _run(identity_store.register_agent(name="test-agent", organization_id=org))
    return agent_id


# ═══════════════════════════════════════════════════════════════════════
# 1. DURABLE WRITE PATH
# ═══════════════════════════════════════════════════════════════════════


class TestDurableWrite:
    """Durable write to Supabase produces exactly one row."""

    def test_one_call_one_row(
        self,
        durable_meter: UsageMeterEngine,
        mock_sb: MockSupabaseClient,
        identity_store: AgentIdentityStore,
    ) -> None:
        agent_id = _register(identity_store)
        _run(durable_meter.record_metered_call(agent_id, "openai", True, 100.0, 512))

        rows = mock_sb.rows("agent_usage_events")
        assert len(rows) == 1
        row = rows[0]
        assert row["agent_id"] == agent_id
        assert row["service"] == "openai"
        assert row["result"] == "success"
        assert row["latency_ms"] == 100.0
        assert row["response_size_bytes"] == 512

    def test_row_includes_response_size_bytes(
        self,
        durable_meter: UsageMeterEngine,
        mock_sb: MockSupabaseClient,
        identity_store: AgentIdentityStore,
    ) -> None:
        agent_id = _register(identity_store)
        _run(durable_meter.record_metered_call(agent_id, "anthropic", True, 50.0, 2048))

        row = mock_sb.rows("agent_usage_events")[0]
        assert row["response_size_bytes"] == 2048

    def test_explicit_result_strings(
        self,
        durable_meter: UsageMeterEngine,
        mock_sb: MockSupabaseClient,
        identity_store: AgentIdentityStore,
    ) -> None:
        """Explicit result kwarg is preserved — not collapsed to boolean."""
        agent_id = _register(identity_store)
        for result in ("success", "error", "rate_limited", "auth_failed"):
            _run(
                durable_meter.record_metered_call(
                    agent_id, "openai", True, 10.0, 0, result=result
                )
            )

        rows = mock_sb.rows("agent_usage_events")
        results = {r["result"] for r in rows}
        assert results == {"success", "error", "rate_limited", "auth_failed"}

    def test_multiple_calls_multiple_rows(
        self,
        durable_meter: UsageMeterEngine,
        mock_sb: MockSupabaseClient,
        identity_store: AgentIdentityStore,
    ) -> None:
        agent_id = _register(identity_store)
        for _ in range(5):
            _run(durable_meter.record_metered_call(agent_id, "openai", True, 80.0, 256))

        assert mock_sb.row_count("agent_usage_events") == 5

    def test_durable_does_not_append_to_inmemory(
        self,
        durable_meter: UsageMeterEngine,
        mock_sb: MockSupabaseClient,
        identity_store: AgentIdentityStore,
    ) -> None:
        """Durable path must NOT also write to in-memory list."""
        agent_id = _register(identity_store)
        _run(durable_meter.record_metered_call(agent_id, "openai", True, 100.0, 0))

        assert len(durable_meter._events) == 0  # noqa: SLF001
        assert mock_sb.row_count("agent_usage_events") == 1


# ═══════════════════════════════════════════════════════════════════════
# 2. DUPLICATE-WRITE REGRESSION
# ═══════════════════════════════════════════════════════════════════════


class TestNoDuplicateWrite:
    """One proxy call must never produce two durable rows."""

    def test_record_metered_call_no_double_insert(
        self,
        durable_meter: UsageMeterEngine,
        mock_sb: MockSupabaseClient,
        identity_store: AgentIdentityStore,
    ) -> None:
        """GAP-3 regression: previously analytics + metering each inserted."""
        agent_id = _register(identity_store)
        _run(durable_meter.record_metered_call(agent_id, "stripe", True, 120.0, 1024))

        assert mock_sb.row_count("agent_usage_events") == 1, (
            "Expected exactly 1 durable row per proxy call — "
            f"got {mock_sb.row_count('agent_usage_events')}"
        )

    def test_ten_calls_ten_rows(
        self,
        durable_meter: UsageMeterEngine,
        mock_sb: MockSupabaseClient,
        identity_store: AgentIdentityStore,
    ) -> None:
        """Scale test: N calls → N rows, not 2N."""
        agent_id = _register(identity_store)
        n = 10
        for i in range(n):
            _run(durable_meter.record_metered_call(agent_id, "openai", True, float(i * 10), i * 100))

        assert mock_sb.row_count("agent_usage_events") == n


# ═══════════════════════════════════════════════════════════════════════
# 3. DURABLE READ PATH
# ═══════════════════════════════════════════════════════════════════════


class TestDurableReads:
    """All read methods query Supabase when configured."""

    def test_get_usage_snapshot_durable(
        self,
        durable_meter: UsageMeterEngine,
        identity_store: AgentIdentityStore,
    ) -> None:
        agent_id = _register(identity_store)
        _run(durable_meter.record_metered_call(agent_id, "openai", True, 100.0, 512))
        _run(durable_meter.record_metered_call(agent_id, "openai", False, 200.0, 256))
        _run(
            durable_meter.record_metered_call(
                agent_id, "openai", True, 50.0, 128, result="rate_limited"
            )
        )

        snapshot = _run(durable_meter.get_usage_snapshot(agent_id, "openai", 7))
        assert snapshot is not None
        assert snapshot.call_count == 3
        assert snapshot.success_count == 1
        assert snapshot.failed_count == 1
        assert snapshot.rate_limited_count == 1

    def test_get_monthly_usage_durable(
        self,
        durable_meter: UsageMeterEngine,
        identity_store: AgentIdentityStore,
    ) -> None:
        agent_id = _register(identity_store)
        for _ in range(4):
            _run(durable_meter.record_metered_call(agent_id, "anthropic", True, 50.0, 100))

        month = datetime.now(tz=UTC).strftime("%Y-%m")
        summary = _run(durable_meter.get_monthly_usage(agent_id, month))
        assert summary.total_calls == 4
        assert summary.by_service["anthropic"].call_count == 4
        assert summary.cost_estimate == pytest.approx(4 * COST_PER_CALL_USD)

    def test_get_org_monthly_usage_durable(
        self,
        durable_meter: UsageMeterEngine,
        identity_store: AgentIdentityStore,
    ) -> None:
        a1 = _register(identity_store, "org_d")
        a2 = _register(identity_store, "org_d")
        _run(durable_meter.record_metered_call(a1, "openai", True, 50.0, 100))
        _run(durable_meter.record_metered_call(a1, "openai", True, 60.0, 200))
        _run(durable_meter.record_metered_call(a2, "anthropic", True, 70.0, 300))

        month = datetime.now(tz=UTC).strftime("%Y-%m")
        org = _run(durable_meter.get_org_monthly_usage("org_d", month))
        assert org.total_calls == 3
        assert "openai" in org.by_service
        assert "anthropic" in org.by_service
        assert len(org.by_agent) == 2

    def test_get_org_daily_average_durable(
        self,
        durable_meter: UsageMeterEngine,
        identity_store: AgentIdentityStore,
    ) -> None:
        agent_id = _register(identity_store, "org_avg")
        for _ in range(14):
            _run(durable_meter.record_metered_call(agent_id, "openai", True, 30.0, 50))

        window_calls, daily_avg = _run(
            durable_meter.get_org_daily_average_calls("org_avg", days=7)
        )
        assert window_calls == 14
        assert daily_avg == pytest.approx(2.0)

    def test_snapshot_survives_inmemory_clear(
        self,
        durable_meter: UsageMeterEngine,
        identity_store: AgentIdentityStore,
    ) -> None:
        """Durable reads must not depend on in-memory state."""
        agent_id = _register(identity_store)
        _run(durable_meter.record_metered_call(agent_id, "openai", True, 100.0, 512))

        # Simulate process restart — clear in-memory list
        durable_meter._events.clear()  # noqa: SLF001

        snapshot = _run(durable_meter.get_usage_snapshot(agent_id, "openai", 7))
        assert snapshot is not None
        assert snapshot.call_count == 1

    def test_monthly_usage_survives_inmemory_clear(
        self,
        durable_meter: UsageMeterEngine,
        identity_store: AgentIdentityStore,
    ) -> None:
        agent_id = _register(identity_store)
        _run(durable_meter.record_metered_call(agent_id, "openai", True, 100.0, 512))
        durable_meter._events.clear()  # noqa: SLF001

        month = datetime.now(tz=UTC).strftime("%Y-%m")
        summary = _run(durable_meter.get_monthly_usage(agent_id, month))
        assert summary.total_calls == 1


# ═══════════════════════════════════════════════════════════════════════
# 4. IN-MEMORY FALLBACK
# ═══════════════════════════════════════════════════════════════════════


class TestInMemoryFallback:
    """Without Supabase, everything works via in-memory events."""

    def test_record_and_read_inmemory(
        self,
        inmem_meter: UsageMeterEngine,
        identity_store: AgentIdentityStore,
    ) -> None:
        agent_id = _register(identity_store)
        _run(inmem_meter.record_metered_call(agent_id, "openai", True, 80.0, 256))

        assert len(inmem_meter._events) == 1  # noqa: SLF001
        snapshot = _run(inmem_meter.get_usage_snapshot(agent_id, "openai", 7))
        assert snapshot is not None
        assert snapshot.call_count == 1

    def test_monthly_usage_inmemory(
        self,
        inmem_meter: UsageMeterEngine,
        identity_store: AgentIdentityStore,
    ) -> None:
        agent_id = _register(identity_store)
        _run(inmem_meter.record_metered_call(agent_id, "openai", True, 50.0, 100))

        month = datetime.now(tz=UTC).strftime("%Y-%m")
        summary = _run(inmem_meter.get_monthly_usage(agent_id, month))
        assert summary.total_calls == 1

    def test_org_daily_average_inmemory(
        self,
        inmem_meter: UsageMeterEngine,
        identity_store: AgentIdentityStore,
    ) -> None:
        agent_id = _register(identity_store, "org_im")
        for _ in range(7):
            _run(inmem_meter.record_metered_call(agent_id, "openai", True, 30.0, 50))

        calls, avg = _run(inmem_meter.get_org_daily_average_calls("org_im", days=7))
        assert calls == 7
        assert avg == pytest.approx(1.0)


# ═══════════════════════════════════════════════════════════════════════
# 5. ANALYTICS DURABLE-AWARE READS
# ═══════════════════════════════════════════════════════════════════════


class TestAnalyticsDurableReads:
    """AgentUsageAnalytics reads from Supabase when configured."""

    def test_analytics_query_events_durable(
        self,
        mock_sb: MockSupabaseClient,
        identity_store: AgentIdentityStore,
    ) -> None:
        analytics = AgentUsageAnalytics(
            identity_store=identity_store, supabase_client=mock_sb
        )
        _run(analytics.record_event("agent_1", "stripe", "success", 42.0))

        summary = _run(analytics.get_usage_summary("agent_1"))
        assert summary["total_calls"] == 1
        assert summary["successful_calls"] == 1

    def test_analytics_recent_events_durable(
        self,
        mock_sb: MockSupabaseClient,
        identity_store: AgentIdentityStore,
    ) -> None:
        analytics = AgentUsageAnalytics(
            identity_store=identity_store, supabase_client=mock_sb
        )
        _run(analytics.record_event("agent_1", "stripe", "success", 10.0))
        _run(analytics.record_event("agent_1", "stripe", "error", 20.0))

        recent = _run(analytics.get_recent_events("agent_1", limit=10))
        assert len(recent) == 2

    def test_analytics_inmemory_fallback(
        self,
        identity_store: AgentIdentityStore,
    ) -> None:
        analytics = AgentUsageAnalytics(identity_store=identity_store)
        _run(analytics.record_event("agent_1", "stripe", "success", 10.0))

        summary = _run(analytics.get_usage_summary("agent_1"))
        assert summary["total_calls"] == 1
