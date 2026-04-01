"""Tests for unified audit trail — append-only, chain-hashed, 23 event types (WU-42.5)."""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

import pytest

from services.audit_trail import (
    AuditChainStatus,
    AuditEvent,
    AuditEventType,
    AuditExportResult,
    AuditSeverity,
    AuditTrail,
    get_audit_trail,
)


# ── Basic recording ──────────────────────────────────────────────────


class TestRecordEvent:
    def test_record_returns_immutable_event(self):
        trail = AuditTrail()
        event = trail.record(
            AuditEventType.EXECUTION_STARTED,
            "Capability execution initiated",
            org_id="org_1",
            agent_id="agent_1",
        )
        assert isinstance(event, AuditEvent)
        assert event.event_type == AuditEventType.EXECUTION_STARTED
        assert event.org_id == "org_1"
        assert event.agent_id == "agent_1"
        assert event.event_id.startswith("aud_")

    def test_record_auto_assigns_severity_from_metadata(self):
        trail = AuditTrail()
        info_event = trail.record(AuditEventType.EXECUTION_COMPLETED, "done", org_id="org_1")
        assert info_event.severity == AuditSeverity.INFO

        warn_event = trail.record(AuditEventType.EXECUTION_FAILED, "failed", org_id="org_1")
        assert warn_event.severity == AuditSeverity.WARNING

        crit_event = trail.record(AuditEventType.KILL_SWITCH_ACTIVATED, "killed", org_id="org_1")
        assert crit_event.severity == AuditSeverity.CRITICAL

    def test_record_auto_assigns_category(self):
        trail = AuditTrail()
        event = trail.record(AuditEventType.KILL_SWITCH_ACTIVATED, "killed", org_id="org_1")
        assert event.category == "security"

        event2 = trail.record(AuditEventType.BUDGET_EXCEEDED, "over", org_id="org_1")
        assert event2.category == "billing"

        event3 = trail.record(AuditEventType.POLICY_UPDATED, "changed", org_id="org_1")
        assert event3.category == "governance"

    def test_record_preserves_detail_payload(self):
        trail = AuditTrail()
        detail = {"capability_id": "search.query", "provider": "brave", "cost_usd": 0.002}
        event = trail.record(
            AuditEventType.EXECUTION_COMPLETED,
            "Completed search.query",
            detail=detail,
            org_id="org_1",
        )
        assert event.detail == detail

    def test_record_preserves_linkage_fields(self):
        trail = AuditTrail()
        event = trail.record(
            AuditEventType.EXECUTION_COMPLETED,
            "done",
            org_id="org_1",
            receipt_id="rcpt_123",
            execution_id="exec_456",
            provider_slug="brave-search",
        )
        assert event.receipt_id == "rcpt_123"
        assert event.execution_id == "exec_456"
        assert event.provider_slug == "brave-search"

    def test_record_increments_sequence(self):
        trail = AuditTrail()
        e1 = trail.record(AuditEventType.EXECUTION_STARTED, "a", org_id="org_1")
        e2 = trail.record(AuditEventType.EXECUTION_COMPLETED, "b", org_id="org_1")
        e3 = trail.record(AuditEventType.EXECUTION_FAILED, "c", org_id="org_1")
        assert e1.chain_sequence == 1
        assert e2.chain_sequence == 2
        assert e3.chain_sequence == 3

    def test_record_with_resource_fields(self):
        trail = AuditTrail()
        event = trail.record(
            AuditEventType.SCORE_UPDATED,
            "AN Score updated",
            org_id="org_1",
            resource_type="provider",
            resource_id="stripe",
        )
        assert event.resource_type == "provider"
        assert event.resource_id == "stripe"

    def test_record_writes_to_durable_outbox_before_memory(self):
        class _Outbox:
            def __init__(self) -> None:
                self.events: list[AuditEvent] = []

            def append_audit_event(self, event: AuditEvent) -> None:
                self.events.append(event)

        outbox = _Outbox()
        trail = AuditTrail(outbox=outbox)

        event = trail.record(
            AuditEventType.EXECUTION_STARTED,
            "Capability execution initiated",
            org_id="org_1",
        )

        assert trail.length == 1
        assert outbox.events == [event]


# ── All 23 event types ──────────────────────────────────────────────


class TestAllEventTypes:
    def test_all_types_are_recordable(self):
        trail = AuditTrail()
        for event_type in AuditEventType:
            event = trail.record(event_type, f"Test {event_type.value}", org_id="org_test")
            assert event.event_type == event_type
        assert trail.length == 23

    def test_event_types_count(self):
        assert len(AuditEventType) == 23


# ── Chain integrity ──────────────────────────────────────────────────


class TestChainIntegrity:
    def test_empty_chain_is_valid(self):
        trail = AuditTrail()
        is_valid, count = trail.verify_chain()
        assert is_valid is True
        assert count == 0

    def test_single_event_chain_valid(self):
        trail = AuditTrail()
        trail.record(AuditEventType.EXECUTION_STARTED, "test", org_id="org_1")
        is_valid, count = trail.verify_chain()
        assert is_valid is True
        assert count == 1

    def test_multi_event_chain_valid(self):
        trail = AuditTrail()
        for i in range(10):
            trail.record(AuditEventType.EXECUTION_COMPLETED, f"event {i}", org_id="org_1")
        is_valid, count = trail.verify_chain()
        assert is_valid is True
        assert count == 10

    def test_chain_links_to_genesis(self):
        trail = AuditTrail()
        event = trail.record(AuditEventType.EXECUTION_STARTED, "first", org_id="org_1")
        assert event.prev_hash == AuditTrail.GENESIS_HASH

    def test_chain_links_sequentially(self):
        trail = AuditTrail()
        e1 = trail.record(AuditEventType.EXECUTION_STARTED, "a", org_id="org_1")
        e2 = trail.record(AuditEventType.EXECUTION_COMPLETED, "b", org_id="org_1")
        assert e2.prev_hash == e1.chain_hash

    def test_chain_hashes_are_unique(self):
        trail = AuditTrail()
        events = []
        for i in range(5):
            events.append(trail.record(AuditEventType.EXECUTION_COMPLETED, f"e{i}", org_id="org_1"))
        hashes = [e.chain_hash for e in events]
        assert len(set(hashes)) == 5  # All unique

    def test_latest_hash_updates(self):
        trail = AuditTrail()
        assert trail.latest_hash == AuditTrail.GENESIS_HASH
        event = trail.record(AuditEventType.EXECUTION_STARTED, "test", org_id="org_1")
        assert trail.latest_hash == event.chain_hash


# ── Query ────────────────────────────────────────────────────────────


class TestQuery:
    def _populate(self, trail: AuditTrail) -> list[AuditEvent]:
        """Create a diverse set of events for query testing."""
        events = []
        events.append(trail.record(
            AuditEventType.EXECUTION_STARTED, "exec start",
            org_id="org_a", agent_id="agent_1", provider_slug="brave",
        ))
        events.append(trail.record(
            AuditEventType.EXECUTION_COMPLETED, "exec done",
            org_id="org_a", agent_id="agent_1", provider_slug="brave",
        ))
        events.append(trail.record(
            AuditEventType.EXECUTION_FAILED, "exec fail",
            org_id="org_b", agent_id="agent_2", provider_slug="exa",
        ))
        events.append(trail.record(
            AuditEventType.KILL_SWITCH_ACTIVATED, "agent killed",
            org_id="org_a", resource_type="agent", resource_id="agent_bad",
        ))
        events.append(trail.record(
            AuditEventType.BUDGET_EXCEEDED, "over budget",
            org_id="org_b", agent_id="agent_2",
        ))
        return events

    def test_query_by_org(self):
        trail = AuditTrail()
        self._populate(trail)
        results = trail.query(org_id="org_a")
        assert len(results) == 3  # 2 execution + 1 kill switch
        assert all(e.org_id == "org_a" for e in results)

    def test_query_by_event_type(self):
        trail = AuditTrail()
        self._populate(trail)
        results = trail.query(event_type=AuditEventType.EXECUTION_FAILED)
        assert len(results) == 1
        assert results[0].event_type == AuditEventType.EXECUTION_FAILED

    def test_query_by_severity(self):
        trail = AuditTrail()
        self._populate(trail)
        results = trail.query(severity=AuditSeverity.CRITICAL)
        assert len(results) == 2  # kill_switch.activated + budget.exceeded

    def test_query_by_category(self):
        trail = AuditTrail()
        self._populate(trail)
        results = trail.query(category="security")
        assert len(results) == 1
        assert results[0].event_type == AuditEventType.KILL_SWITCH_ACTIVATED

    def test_query_by_resource(self):
        trail = AuditTrail()
        self._populate(trail)
        results = trail.query(resource_type="agent", resource_id="agent_bad")
        assert len(results) == 1

    def test_query_limit(self):
        trail = AuditTrail()
        self._populate(trail)
        results = trail.query(limit=2)
        assert len(results) == 2

    def test_query_offset(self):
        trail = AuditTrail()
        self._populate(trail)
        all_results = trail.query(limit=100)
        offset_results = trail.query(offset=2, limit=100)
        assert len(offset_results) == len(all_results) - 2

    def test_query_returns_newest_first(self):
        trail = AuditTrail()
        self._populate(trail)
        results = trail.query(limit=100)
        for i in range(len(results) - 1):
            assert results[i].timestamp >= results[i + 1].timestamp

    def test_query_combined_filters(self):
        trail = AuditTrail()
        self._populate(trail)
        results = trail.query(org_id="org_a", event_type=AuditEventType.EXECUTION_STARTED)
        assert len(results) == 1

    def test_count_matches_query(self):
        trail = AuditTrail()
        self._populate(trail)
        count = trail.count(org_id="org_a")
        results = trail.query(org_id="org_a", limit=100)
        assert count == len(results)


# ── Status ───────────────────────────────────────────────────────────


class TestStatus:
    def test_empty_trail_status(self):
        trail = AuditTrail()
        s = trail.status()
        assert isinstance(s, AuditChainStatus)
        assert s.total_events == 0
        assert s.chain_verified is True
        assert s.earliest_event is None
        assert s.latest_event is None

    def test_populated_trail_status(self):
        trail = AuditTrail()
        trail.record(AuditEventType.EXECUTION_STARTED, "a", org_id="org_1")
        trail.record(AuditEventType.KILL_SWITCH_ACTIVATED, "b", org_id="org_1")
        trail.record(AuditEventType.BUDGET_EXCEEDED, "c", org_id="org_1")
        s = trail.status()
        assert s.total_events == 3
        assert s.chain_verified is True
        assert s.latest_sequence == 3
        assert s.events_by_type["execution.started"] == 1
        assert s.events_by_type["kill_switch.activated"] == 1
        assert s.events_by_severity["info"] == 1
        assert s.events_by_severity["critical"] == 2
        assert s.events_by_category["execution"] == 1
        assert s.events_by_category["security"] == 1
        assert s.events_by_category["billing"] == 1


# ── Export ────────────────────────────────────────────────────────────


class TestExport:
    def test_export_json_format(self):
        trail = AuditTrail()
        trail.record(AuditEventType.EXECUTION_STARTED, "test exec", org_id="org_1")
        trail.record(AuditEventType.EXECUTION_COMPLETED, "done", org_id="org_1")

        result = trail.export("json", org_id="org_1")
        assert isinstance(result, AuditExportResult)
        assert result.format == "json"
        assert result.event_count == 2
        assert result.chain_verified is True

        # Parse the JSON
        data = json.loads(result.data)
        assert data["export_version"] == "1.0"
        assert data["event_count"] == 2
        assert data["chain_verified"] is True
        assert len(data["events"]) == 2
        # Oldest first in export
        assert data["events"][0]["event_type"] == "execution.started"
        assert data["events"][1]["event_type"] == "execution.completed"

    def test_export_csv_format(self):
        trail = AuditTrail()
        trail.record(AuditEventType.EXECUTION_STARTED, "test", org_id="org_1")

        result = trail.export("csv", org_id="org_1")
        assert result.format == "csv"
        assert result.event_count == 1
        lines = result.data.strip().split("\n")
        assert len(lines) == 2  # header + 1 event
        assert "event_id" in lines[0]
        assert "execution.started" in lines[1]

    def test_export_with_filters(self):
        trail = AuditTrail()
        trail.record(AuditEventType.EXECUTION_STARTED, "a", org_id="org_1")
        trail.record(AuditEventType.KILL_SWITCH_ACTIVATED, "b", org_id="org_1")
        trail.record(AuditEventType.EXECUTION_COMPLETED, "c", org_id="org_2")

        # Export only security events for org_1
        result = trail.export(
            "json",
            org_id="org_1",
            category="security",
        )
        assert result.event_count == 1
        data = json.loads(result.data)
        assert data["events"][0]["event_type"] == "kill_switch.activated"

    def test_export_empty_result(self):
        trail = AuditTrail()
        result = trail.export("json", org_id="nonexistent")
        assert result.event_count == 0
        data = json.loads(result.data)
        assert data["events"] == []


# ── Singleton ────────────────────────────────────────────────────────


class TestSingleton:
    def test_get_audit_trail_returns_same_instance(self):
        t1 = get_audit_trail()
        t2 = get_audit_trail()
        assert t1 is t2


# ── Route integration (using TestClient) ─────────────────────────────


class TestAuditRoutes:
    """Test the FastAPI route endpoints via TestClient."""

    @pytest.fixture
    def client(self):
        """Create a test client with mocked auth."""
        from unittest.mock import AsyncMock, patch, MagicMock
        from fastapi.testclient import TestClient

        # Reset singleton for test isolation
        import services.audit_trail as at_module
        at_module._audit_trail = AuditTrail()

        # Seed some events
        trail = at_module.get_audit_trail()
        trail.record(
            AuditEventType.EXECUTION_STARTED, "Test execution started",
            org_id="org_test", agent_id="agent_1", provider_slug="brave",
        )
        trail.record(
            AuditEventType.EXECUTION_COMPLETED, "Test execution completed",
            org_id="org_test", agent_id="agent_1", provider_slug="brave",
            receipt_id="rcpt_001", execution_id="exec_001",
        )
        trail.record(
            AuditEventType.KILL_SWITCH_ACTIVATED, "Agent compromised",
            org_id="org_test", resource_type="agent", resource_id="agent_bad",
            principal="admin_1",
        )
        trail.record(
            AuditEventType.EXECUTION_FAILED, "Provider error",
            org_id="org_other", agent_id="agent_3",
        )

        # Mock the auth to return org_test
        mock_agent = MagicMock()
        mock_agent.organization_id = "org_test"
        mock_store = MagicMock()
        mock_store.verify_api_key_with_agent = AsyncMock(return_value=mock_agent)

        with patch("routes.audit_v2._get_identity_store", return_value=mock_store):
            from app import create_app
            app = create_app()
            yield TestClient(app)

        # Clean up singleton
        at_module._audit_trail = None

    def test_list_events(self, client):
        resp = client.get("/v2/audit/events", headers={"X-Rhumb-Key": "test_key"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        # Should only see org_test events (3 of 4)
        assert len(data["events"]) == 3
        assert data["pagination"]["total"] == 3

    def test_list_events_with_type_filter(self, client):
        resp = client.get(
            "/v2/audit/events",
            params={"event_type": "kill_switch.activated"},
            headers={"X-Rhumb-Key": "test_key"},
        )
        assert resp.status_code == 200
        events = resp.json()["data"]["events"]
        assert len(events) == 1
        assert events[0]["event_type"] == "kill_switch.activated"

    def test_list_events_with_severity_filter(self, client):
        resp = client.get(
            "/v2/audit/events",
            params={"severity": "critical"},
            headers={"X-Rhumb-Key": "test_key"},
        )
        assert resp.status_code == 200
        events = resp.json()["data"]["events"]
        assert len(events) == 1  # Only kill_switch.activated is critical for org_test

    def test_list_events_invalid_type(self, client):
        resp = client.get(
            "/v2/audit/events",
            params={"event_type": "bogus.type"},
            headers={"X-Rhumb-Key": "test_key"},
        )
        assert resp.status_code == 400

    def test_get_event_by_id(self, client):
        # First get the list to find an event ID
        resp = client.get("/v2/audit/events", headers={"X-Rhumb-Key": "test_key"})
        events = resp.json()["data"]["events"]
        event_id = events[0]["event_id"]

        # Now fetch by ID
        resp = client.get(
            f"/v2/audit/events/{event_id}",
            headers={"X-Rhumb-Key": "test_key"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["event_id"] == event_id

    def test_get_event_not_found(self, client):
        resp = client.get(
            "/v2/audit/events/aud_nonexistent",
            headers={"X-Rhumb-Key": "test_key"},
        )
        assert resp.status_code == 404

    def test_status_endpoint(self, client):
        resp = client.get("/v2/audit/status", headers={"X-Rhumb-Key": "test_key"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_events"] == 4  # All events, not filtered by org
        assert data["chain_verified"] is True
        assert data["latest_sequence"] == 4
        assert "execution.started" in data["events_by_type"]

    def test_verify_endpoint(self, client):
        resp = client.get("/v2/audit/verify", headers={"X-Rhumb-Key": "test_key"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["chain_verified"] is True
        assert data["events_checked"] == 4
        assert "no tampering" in data["message"].lower()

    def test_export_json(self, client):
        resp = client.post(
            "/v2/audit/export",
            params={"format": "json"},
            headers={"X-Rhumb-Key": "test_key"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["format"] == "json"
        assert data["chain_verified"] is True
        # The export field is a JSON string
        export = json.loads(data["export"])
        assert export["event_count"] == 3  # org_test events only

    def test_export_csv(self, client):
        resp = client.post(
            "/v2/audit/export",
            params={"format": "csv"},
            headers={"X-Rhumb-Key": "test_key"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert resp.headers["x-rhumb-chain-verified"] == "true"
        lines = resp.text.strip().split("\n")
        assert len(lines) == 4  # header + 3 org_test events

    def test_export_invalid_format(self, client):
        resp = client.post(
            "/v2/audit/export",
            params={"format": "xml"},
            headers={"X-Rhumb-Key": "test_key"},
        )
        assert resp.status_code == 400

    def test_unauthenticated_request(self, client):
        resp = client.get("/v2/audit/events")
        assert resp.status_code == 401

    def test_pagination(self, client):
        resp = client.get(
            "/v2/audit/events",
            params={"limit": 2, "offset": 0},
            headers={"X-Rhumb-Key": "test_key"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["events"]) == 2
        assert data["pagination"]["total"] == 3
        assert data["pagination"]["has_more"] is True

        # Page 2
        resp = client.get(
            "/v2/audit/events",
            params={"limit": 2, "offset": 2},
            headers={"X-Rhumb-Key": "test_key"},
        )
        data = resp.json()["data"]
        assert len(data["events"]) == 1
        assert data["pagination"]["has_more"] is False
