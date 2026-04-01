"""Tests for AUD-1: durable event persistence."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from services.durable_event_persistence import (
    DurableAuditPersistence,
    DurableBillingPersistence,
    DurableKillSwitchPersistence,
)
from services.principal_auth import extract_principal_from_session


class MockQueryResult:
    def __init__(self, data=None):
        self.data = data


class MockQueryBuilder:
    def __init__(self, data=None):
        self._data = data

    def select(self, *args):
        return self

    def eq(self, *args):
        return self

    def gte(self, *args):
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, *args):
        return self

    def insert(self, data):
        return self

    def upsert(self, data):
        return self

    def delete(self):
        return self

    def maybe_single(self):
        return self

    async def execute(self):
        return MockQueryResult(self._data)


class MockSupabase:
    def __init__(self):
        self._tables = {}

    def table(self, name):
        return self._tables.get(name, MockQueryBuilder())

    def set_table(self, name, builder):
        self._tables[name] = builder


class MockBillingEvent:
    event_id = "bevt_test1"
    event_type = type("ET", (), {"value": "execution.charged"})()
    org_id = "org_1"
    timestamp = datetime(2026, 4, 1, tzinfo=timezone.utc)
    amount_usd_cents = 100
    balance_after_usd_cents = 900
    metadata = {"note": "test"}
    receipt_id = "rcpt_1"
    execution_id = "exec_1"
    capability_id = "search.query"
    provider_slug = "brave-search"
    chain_hash = "abc123"
    prev_hash = "000000"


class MockAuditEvent:
    event_id = "aevt_test1"
    event_type = type("ET", (), {"value": "execution.completed"})()
    severity = type("S", (), {"value": "info"})()
    category = "execution"
    timestamp = datetime(2026, 4, 1, tzinfo=timezone.utc)
    org_id = "org_1"
    agent_id = "agt_1"
    principal = "admin"
    resource_type = "capability"
    resource_id = "search.query"
    action = "execute"
    detail = {"latency_ms": 150}
    receipt_id = "rcpt_1"
    execution_id = "exec_1"
    provider_slug = "brave-search"
    chain_sequence = 1
    chain_hash = "def456"
    prev_hash = "000000"


class MockKillEntry:
    switch_id = "ks_test1"
    level = type("L", (), {"value": "L1_agent"})()
    target = "agent_1"
    state = type("S", (), {"value": "killed"})()
    reason = "suspicious activity"
    activated_by = "admin@rhumb.dev"
    activated_at = datetime(2026, 4, 1, tzinfo=timezone.utc)
    second_approver = None
    restoration_phase = None
    chain_hash = ""


class MockPendingGlobal:
    request_id = "gkill_00000001"
    reason = "security breach"
    requester = extract_principal_from_session("tom", email="tom@rhumb.dev")
    requested_at = datetime(2026, 4, 1, tzinfo=timezone.utc)
    expires_at = datetime(2026, 4, 1, 0, 15, tzinfo=timezone.utc)


@pytest.fixture
def mock_db():
    return MockSupabase()


class TestDurableBillingPersistence:
    @pytest.mark.asyncio
    async def test_persist_event_succeeds(self, mock_db):
        mock_db.set_table("billing_events", MockQueryBuilder())
        bp = DurableBillingPersistence(mock_db)
        result = await bp.persist_event(MockBillingEvent())
        assert result is True

    @pytest.mark.asyncio
    async def test_persist_event_survives_failure(self, mock_db):
        class FailingBuilder(MockQueryBuilder):
            def insert(self, data):
                return self
            async def execute(self):
                raise ConnectionError("DB down")

        mock_db.set_table("billing_events", FailingBuilder())
        bp = DurableBillingPersistence(mock_db)
        result = await bp.persist_event(MockBillingEvent())
        assert result is False  # Fail-safe, no exception

    @pytest.mark.asyncio
    async def test_load_recent(self, mock_db):
        mock_db.set_table("billing_events", MockQueryBuilder([
            {"event_id": "bevt_1"}, {"event_id": "bevt_2"}
        ]))
        bp = DurableBillingPersistence(mock_db)
        events = await bp.load_recent(limit=100)
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_load_empty(self, mock_db):
        mock_db.set_table("billing_events", MockQueryBuilder([]))
        bp = DurableBillingPersistence(mock_db)
        events = await bp.load_recent()
        assert events == []


class TestDurableAuditPersistence:
    @pytest.mark.asyncio
    async def test_persist_event_succeeds(self, mock_db):
        mock_db.set_table("audit_events", MockQueryBuilder())
        ap = DurableAuditPersistence(mock_db)
        result = await ap.persist_event(MockAuditEvent())
        assert result is True

    @pytest.mark.asyncio
    async def test_persist_event_survives_failure(self, mock_db):
        class FailingBuilder(MockQueryBuilder):
            def insert(self, data):
                return self
            async def execute(self):
                raise ConnectionError("DB down")

        mock_db.set_table("audit_events", FailingBuilder())
        ap = DurableAuditPersistence(mock_db)
        result = await ap.persist_event(MockAuditEvent())
        assert result is False

    @pytest.mark.asyncio
    async def test_load_recent(self, mock_db):
        mock_db.set_table("audit_events", MockQueryBuilder([{"event_id": "aevt_1"}]))
        ap = DurableAuditPersistence(mock_db)
        events = await ap.load_recent()
        assert len(events) == 1


class TestDurableKillSwitchPersistence:
    @pytest.mark.asyncio
    async def test_persist_switch_succeeds(self, mock_db):
        mock_db.set_table("kill_switch_state", MockQueryBuilder())
        kp = DurableKillSwitchPersistence(mock_db)
        result = await kp.persist_switch_state("agent:agent_1", MockKillEntry())
        assert result is True

    @pytest.mark.asyncio
    async def test_persist_switch_survives_failure(self, mock_db):
        class FailingBuilder(MockQueryBuilder):
            def upsert(self, data):
                return self
            async def execute(self):
                raise ConnectionError("DB down")

        mock_db.set_table("kill_switch_state", FailingBuilder())
        kp = DurableKillSwitchPersistence(mock_db)
        result = await kp.persist_switch_state("agent:agent_1", MockKillEntry())
        assert result is False

    @pytest.mark.asyncio
    async def test_load_active_switches(self, mock_db):
        mock_db.set_table("kill_switch_state", MockQueryBuilder([
            {"switch_key": "agent:agent_1", "state": "killed"}
        ]))
        kp = DurableKillSwitchPersistence(mock_db)
        switches = await kp.load_active_switches()
        assert len(switches) == 1

    @pytest.mark.asyncio
    async def test_remove_switch(self, mock_db):
        mock_db.set_table("kill_switch_state", MockQueryBuilder())
        kp = DurableKillSwitchPersistence(mock_db)
        result = await kp.remove_switch("agent:agent_1")
        assert result is True

    @pytest.mark.asyncio
    async def test_persist_pending_global_succeeds(self, mock_db):
        mock_db.set_table("kill_switch_pending_global", MockQueryBuilder())
        kp = DurableKillSwitchPersistence(mock_db)
        result = await kp.persist_pending_global(MockPendingGlobal())
        assert result is True

    @pytest.mark.asyncio
    async def test_load_pending_globals(self, mock_db):
        mock_db.set_table("kill_switch_pending_global", MockQueryBuilder([
            {"request_id": "gkill_00000001"}
        ]))
        kp = DurableKillSwitchPersistence(mock_db)
        rows = await kp.load_pending_globals()
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_remove_pending_global(self, mock_db):
        mock_db.set_table("kill_switch_pending_global", MockQueryBuilder())
        kp = DurableKillSwitchPersistence(mock_db)
        result = await kp.remove_pending_global("gkill_00000001")
        assert result is True
