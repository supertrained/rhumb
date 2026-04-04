"""Tests for AUD-1: durable event persistence."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from services.durable_event_persistence import (
    DurableAuditPersistence,
    DurableBillingPersistence,
    DurableChainCheckpointPersistence,
    DurableEventOutbox,
    DurableKillSwitchPersistence,
)
from services.principal_auth import extract_principal_from_session


class MockQueryResult:
    def __init__(self, data=None):
        self.data = data


class MockQueryBuilder:
    def __init__(self, data=None):
        self._data = data
        self.inserted: list[dict] = []
        self.upserted: list[dict] = []

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
        self.inserted.append(data)
        return self

    def upsert(self, data):
        self.upserted.append(data)
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


MOCK_CHAIN_CHECKPOINT = {
    "checkpoint_id": "chk_test1",
    "stream_name": "audit_events",
    "reason": "retention_purge",
    "source_head_hash": "head123",
    "source_head_sequence": 5,
    "source_key_version": 1,
    "checkpoint_hash": "chkhash456",
    "key_version": 1,
    "metadata": {"purged_count": 2, "surviving_count": 3},
    "created_at": "2026-04-04T18:51:00+00:00",
}


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


class TestDurableChainCheckpointPersistence:
    @pytest.mark.asyncio
    async def test_persist_payload_succeeds(self, mock_db):
        checkpoint_table = MockQueryBuilder()
        mock_db.set_table("chain_checkpoints", checkpoint_table)
        cp = DurableChainCheckpointPersistence(mock_db)
        result = await cp.persist_payload(MOCK_CHAIN_CHECKPOINT)
        assert result is True
        assert checkpoint_table.inserted[0]["checkpoint_id"] == "chk_test1"
        assert checkpoint_table.inserted[0]["stream_name"] == "audit_events"

    @pytest.mark.asyncio
    async def test_persist_payload_survives_failure(self, mock_db):
        class FailingBuilder(MockQueryBuilder):
            def insert(self, data):
                return self
            async def execute(self):
                raise ConnectionError("DB down")

        mock_db.set_table("chain_checkpoints", FailingBuilder())
        cp = DurableChainCheckpointPersistence(mock_db)
        result = await cp.persist_payload(MOCK_CHAIN_CHECKPOINT)
        assert result is False


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


class TestDurableEventOutbox:
    @pytest.mark.asyncio
    async def test_flushes_and_replays_across_restart(self, mock_db, tmp_path):
        billing_table = MockQueryBuilder()
        audit_table = MockQueryBuilder()
        checkpoint_table = MockQueryBuilder()
        mock_db.set_table("billing_events", billing_table)
        mock_db.set_table("audit_events", audit_table)
        mock_db.set_table("chain_checkpoints", checkpoint_table)

        sqlite_path = tmp_path / "event-outbox.sqlite3"
        outbox = DurableEventOutbox(
            billing_persistence=DurableBillingPersistence(mock_db),
            audit_persistence=DurableAuditPersistence(mock_db),
            checkpoint_persistence=DurableChainCheckpointPersistence(mock_db),
            sqlite_path=str(sqlite_path),
            max_pending_count=10,
        )
        outbox.append_billing_event(MockBillingEvent())
        outbox.append_audit_event(MockAuditEvent())
        outbox.append_chain_checkpoint(MOCK_CHAIN_CHECKPOINT)

        replayed = DurableEventOutbox(sqlite_path=str(sqlite_path), max_pending_count=10)
        assert len(replayed.load_billing_payloads()) == 1
        assert len(replayed.load_audit_payloads()) == 1
        replayed.close()

        flushed = await outbox.flush_once()
        assert flushed == 3
        assert len(billing_table.inserted) == 1
        assert len(audit_table.inserted) == 1
        assert len(checkpoint_table.inserted) == 1
        assert outbox.health().pending_count == 0
        outbox.close()

    def test_health_fails_closed_when_backlog_exceeds_threshold(self, tmp_path):
        sqlite_path = tmp_path / "event-outbox.sqlite3"
        outbox = DurableEventOutbox(sqlite_path=str(sqlite_path), max_pending_count=1)
        first = type("BillingEventOne", (), dict(MockBillingEvent.__dict__, event_id="bevt_1"))()
        second = type("BillingEventTwo", (), dict(MockBillingEvent.__dict__, event_id="bevt_2"))()

        outbox.append_billing_event(first)
        outbox.append_billing_event(second)

        health = outbox.health()
        assert health.pending_count == 2
        assert health.allows_risky_writes is False
        assert "threshold" in health.reason.lower()
        outbox.close()
