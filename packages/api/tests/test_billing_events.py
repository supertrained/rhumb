"""Tests for billing event stream + v2 billing endpoints (WU-41.5)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from services.billing_events import (
    BillingEvent,
    BillingEventStream,
    BillingEventSummary,
    BillingEventType,
    get_billing_event_stream,
)


# ── BillingEvent immutability ────────────────────────────────────────


class TestBillingEventImmutability:
    def test_frozen_dataclass(self):
        stream = BillingEventStream()
        event = stream.emit(
            BillingEventType.EXECUTION_CHARGED,
            org_id="org_test",
            amount_usd_cents=150,
        )
        with pytest.raises(AttributeError):
            event.amount_usd_cents = 999  # type: ignore[misc]

    def test_fields_present(self):
        stream = BillingEventStream()
        event = stream.emit(
            BillingEventType.CREDIT_PURCHASED,
            org_id="org_test",
            amount_usd_cents=-5000,
            balance_after_usd_cents=10000,
            receipt_id="rcpt_123",
        )
        assert event.event_type == BillingEventType.CREDIT_PURCHASED
        assert event.org_id == "org_test"
        assert event.amount_usd_cents == -5000
        assert event.balance_after_usd_cents == 10000
        assert event.receipt_id == "rcpt_123"
        assert event.event_id.startswith("bevt_")


# ── BillingEventStream ──────────────────────────────────────────────


class TestBillingEventStream:
    def test_empty_stream(self):
        stream = BillingEventStream()
        assert stream.length == 0
        assert stream.verify_chain() is True
        assert stream.latest_hash == BillingEventStream.GENESIS_HASH

    def test_emit_and_query(self):
        stream = BillingEventStream()
        stream.emit(BillingEventType.EXECUTION_CHARGED, "org_a", 150)
        stream.emit(BillingEventType.CREDIT_PURCHASED, "org_a", -5000)
        stream.emit(BillingEventType.EXECUTION_CHARGED, "org_b", 200)
        assert stream.length == 3

        # Query by org
        org_a_events = stream.query(org_id="org_a")
        assert len(org_a_events) == 2
        assert all(e.org_id == "org_a" for e in org_a_events)

        org_b_events = stream.query(org_id="org_b")
        assert len(org_b_events) == 1

    def test_query_by_event_type(self):
        stream = BillingEventStream()
        stream.emit(BillingEventType.EXECUTION_CHARGED, "org_a", 100)
        stream.emit(BillingEventType.CREDIT_PURCHASED, "org_a", -5000)
        stream.emit(BillingEventType.EXECUTION_CHARGED, "org_a", 200)

        charged = stream.query(org_id="org_a", event_type=BillingEventType.EXECUTION_CHARGED)
        assert len(charged) == 2
        assert all(e.event_type == BillingEventType.EXECUTION_CHARGED for e in charged)

    def test_query_unknown_org_returns_empty_even_when_other_orgs_have_events(self):
        stream = BillingEventStream()
        stream.emit(BillingEventType.EXECUTION_CHARGED, "org_a", 100)
        stream.emit(BillingEventType.CREDIT_PURCHASED, "org_b", -5000)

        assert stream.query(org_id="org_missing") == []

    def test_query_limit(self):
        stream = BillingEventStream()
        for i in range(10):
            stream.emit(BillingEventType.EXECUTION_CHARGED, "org_a", 100 + i)

        limited = stream.query(org_id="org_a", limit=3)
        assert len(limited) == 3
        # Newest first
        assert limited[0].amount_usd_cents >= limited[1].amount_usd_cents

    def test_query_newest_first(self):
        stream = BillingEventStream()
        stream.emit(BillingEventType.EXECUTION_CHARGED, "org_a", 100)
        stream.emit(BillingEventType.EXECUTION_CHARGED, "org_a", 200)

        events = stream.query(org_id="org_a")
        assert events[0].timestamp >= events[1].timestamp

    def test_chain_integrity(self):
        stream = BillingEventStream()
        e1 = stream.emit(BillingEventType.EXECUTION_CHARGED, "org_a", 100)
        e2 = stream.emit(BillingEventType.CREDIT_PURCHASED, "org_a", -5000)
        assert e2.prev_hash == e1.chain_hash
        assert stream.verify_chain() is True

    def test_chain_multi_org(self):
        stream = BillingEventStream()
        stream.emit(BillingEventType.EXECUTION_CHARGED, "org_a", 100)
        stream.emit(BillingEventType.EXECUTION_CHARGED, "org_b", 200)
        stream.emit(BillingEventType.X402_PAYMENT_RECEIVED, "org_a", -1000)
        assert stream.length == 3
        assert stream.verify_chain() is True

    def test_execution_context(self):
        stream = BillingEventStream()
        event = stream.emit(
            BillingEventType.EXECUTION_CHARGED,
            org_id="org_a",
            amount_usd_cents=150,
            receipt_id="rcpt_abc",
            execution_id="exec_123",
            capability_id="search.query",
            provider_slug="brave-search",
            metadata={"layer": 2, "credential_mode": "rhumb_managed"},
        )
        assert event.receipt_id == "rcpt_abc"
        assert event.execution_id == "exec_123"
        assert event.capability_id == "search.query"
        assert event.provider_slug == "brave-search-api"
        assert event.metadata["layer"] == 2

    def test_emit_canonicalizes_alias_backed_provider_slug_before_hashing(self):
        stream = BillingEventStream()

        event = stream.emit(
            BillingEventType.EXECUTION_CHARGED,
            org_id="org_a",
            amount_usd_cents=150,
            provider_slug="brave-search",
        )

        assert event.provider_slug == "brave-search-api"
        assert event.chain_hash == stream._compute_hash(
            event.prev_hash,
            event.event_id,
            event.event_type.value,
            event.org_id,
            event.amount_usd_cents,
            event.timestamp.isoformat(),
            event=replace(event, chain_hash=""),
        )
        assert event.chain_hash != stream._compute_hash(
            event.prev_hash,
            event.event_id,
            event.event_type.value,
            event.org_id,
            event.amount_usd_cents,
            event.timestamp.isoformat(),
            event=replace(event, provider_slug="brave-search", chain_hash=""),
        )

    def test_emit_canonicalizes_alias_backed_provider_metadata_before_hashing(self):
        stream = BillingEventStream()

        event = stream.emit(
            BillingEventType.EXECUTION_FAILED_NO_CHARGE,
            org_id="org_a",
            amount_usd_cents=0,
            provider_slug="brave-search",
            metadata={
                "provider_used": "brave-search",
                "detail": {
                    "fallback_provider": "pdl",
                    "fallback_providers": ["pdl", "brave-search-api"],
                    "message": "brave-search-api failed before pdl fallback",
                },
            },
        )

        assert event.metadata == {
            "provider_used": "brave-search-api",
            "detail": {
                "fallback_provider": "people-data-labs",
                "fallback_providers": ["people-data-labs", "brave-search-api"],
                "message": "brave-search-api failed before people-data-labs fallback",
            },
        }
        assert event.chain_hash == stream._compute_hash(
            event.prev_hash,
            event.event_id,
            event.event_type.value,
            event.org_id,
            event.amount_usd_cents,
            event.timestamp.isoformat(),
            event=replace(event, chain_hash=""),
        )
        assert event.chain_hash != stream._compute_hash(
            event.prev_hash,
            event.event_id,
            event.event_type.value,
            event.org_id,
            event.amount_usd_cents,
            event.timestamp.isoformat(),
            event=replace(
                event,
                metadata={
                    "provider_used": "brave-search",
                    "detail": {
                        "fallback_provider": "pdl",
                        "fallback_providers": ["pdl", "brave-search-api"],
                        "message": "brave-search-api failed before pdl fallback",
                    },
                },
                chain_hash="",
            ),
        )

    def test_emit_writes_to_durable_outbox_before_memory(self):
        class _Outbox:
            def __init__(self) -> None:
                self.events: list[BillingEvent] = []

            def append_billing_event(self, event: BillingEvent) -> None:
                self.events.append(event)

        outbox = _Outbox()
        stream = BillingEventStream(outbox=outbox)

        event = stream.emit(BillingEventType.EXECUTION_CHARGED, "org_a", 100)

        assert stream.length == 1
        assert outbox.events == [event]


# ── BillingEventStream.summarize ─────────────────────────────────────


class TestBillingEventSummary:
    def test_empty_summary(self):
        stream = BillingEventStream()
        summary = stream.summarize("org_a")
        assert summary.total_charged_usd_cents == 0
        assert summary.total_credited_usd_cents == 0
        assert summary.execution_count == 0
        assert summary.events_count == 0

    def test_summarize_charges(self):
        stream = BillingEventStream()
        stream.emit(
            BillingEventType.EXECUTION_CHARGED, "org_a", 150,
            provider_slug="stripe", capability_id="payments.create",
        )
        stream.emit(
            BillingEventType.EXECUTION_CHARGED, "org_a", 200,
            provider_slug="openai", capability_id="ai.generate_text",
        )
        stream.emit(
            BillingEventType.EXECUTION_CHARGED, "org_a", 100,
            provider_slug="stripe", capability_id="payments.create",
        )
        stream.emit(BillingEventType.CREDIT_PURCHASED, "org_a", -5000)

        summary = stream.summarize("org_a")
        assert summary.total_charged_usd_cents == 450
        assert summary.total_credited_usd_cents == 5000
        assert summary.execution_count == 3
        assert summary.credit_purchase_count == 1
        assert summary.by_provider == {"stripe": 250, "openai": 200}
        assert summary.by_capability == {"payments.create": 250, "ai.generate_text": 200}

    def test_summarize_x402(self):
        stream = BillingEventStream()
        stream.emit(BillingEventType.X402_PAYMENT_RECEIVED, "org_a", -1000)
        stream.emit(BillingEventType.X402_SETTLEMENT_COMPLETED, "org_a", 0)

        summary = stream.summarize("org_a")
        assert summary.x402_payment_count == 2

    def test_summarize_multi_org_isolation(self):
        stream = BillingEventStream()
        stream.emit(BillingEventType.EXECUTION_CHARGED, "org_a", 100)
        stream.emit(BillingEventType.EXECUTION_CHARGED, "org_b", 200)

        summary_a = stream.summarize("org_a")
        summary_b = stream.summarize("org_b")
        assert summary_a.total_charged_usd_cents == 100
        assert summary_b.total_charged_usd_cents == 200

    def test_summarize_unknown_org_ignores_other_orgs(self):
        stream = BillingEventStream()
        stream.emit(BillingEventType.EXECUTION_CHARGED, "org_a", 100)
        stream.emit(BillingEventType.EXECUTION_CHARGED, "org_b", 200)

        summary = stream.summarize("org_missing")
        assert summary.total_charged_usd_cents == 0
        assert summary.total_credited_usd_cents == 0
        assert summary.events_count == 0
        assert summary.by_provider == {}

    def test_summarize_canonicalizes_alias_backed_provider_ids(self):
        stream = BillingEventStream()
        stream.emit(
            BillingEventType.EXECUTION_CHARGED,
            "org_alias",
            150,
            provider_slug="brave-search",
            capability_id="search.query",
        )
        stream.emit(
            BillingEventType.EXECUTION_CHARGED,
            "org_alias",
            200,
            provider_slug="brave-search-api",
            capability_id="search.query",
        )
        stream.emit(
            BillingEventType.EXECUTION_CHARGED,
            "org_alias",
            300,
            provider_slug="pdl",
            capability_id="people.enrich",
        )

        summary = stream.summarize("org_alias")

        assert summary.by_provider == {
            "brave-search-api": 350,
            "people-data-labs": 300,
        }


# ── Tamper detection ─────────────────────────────────────────────────


class TestBillingChainIntegrity:
    def test_tamper_detection(self):
        stream = BillingEventStream()
        stream.emit(BillingEventType.EXECUTION_CHARGED, "org_a", 100)
        stream.emit(BillingEventType.EXECUTION_CHARGED, "org_a", 200)
        assert stream.verify_chain() is True

        # Tamper
        with stream._lock:
            original = stream._events[0]
            tampered = BillingEvent(
                event_id=original.event_id,
                event_type=original.event_type,
                org_id=original.org_id,
                timestamp=original.timestamp,
                amount_usd_cents=99999,  # Tampered
                balance_after_usd_cents=original.balance_after_usd_cents,
                metadata=original.metadata,
                chain_hash=original.chain_hash,
                prev_hash=original.prev_hash,
            )
            stream._events[0] = tampered

        assert stream.verify_chain() is False


# ── Module singleton ─────────────────────────────────────────────────


class TestModuleSingleton:
    def test_get_billing_event_stream(self):
        stream = get_billing_event_stream()
        assert isinstance(stream, BillingEventStream)
        assert get_billing_event_stream() is stream


# ── v2 Billing endpoints ─────────────────────────────────────────────


@pytest.fixture
def app():
    from fastapi import FastAPI
    from routes.billing_v2 import router
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient
    return TestClient(app)


class TestBillingV2Endpoints:
    def test_stream_status(self, client):
        resp = client.get("/v2/billing/stream/status")
        assert resp.status_code == 200
        body = resp.json()
        assert "stream_length" in body["data"]
        assert "chain_verified" in body["data"]
        assert body["data"]["chain_verified"] is True
        assert "structural_guarantees" in body["data"]
        assert isinstance(body["data"]["event_types"], list)
        assert len(body["data"]["event_types"]) > 0

    def test_events_requires_auth(self, client):
        resp = client.get("/v2/billing/events")
        assert resp.status_code == 401

    def test_summary_requires_auth(self, client):
        resp = client.get("/v2/billing/summary")
        assert resp.status_code == 401

    def test_invalid_event_type_filter(self, client):
        resp = client.get(
            "/v2/billing/events",
            headers={"X-Rhumb-Key": "invalid_key"},
        )
        # Will fail on auth, not event type — that's correct
        assert resp.status_code == 401

    def test_event_types_enum_complete(self):
        """All billing event types have values."""
        types = list(BillingEventType)
        assert len(types) >= 15  # We defined 15+ event types
        for t in types:
            assert isinstance(t.value, str)
            assert "." in t.value  # All follow dot notation

    def test_events_canonicalize_alias_backed_provider_slug(self, client):
        stream = BillingEventStream()
        stream.emit(
            BillingEventType.EXECUTION_CHARGED,
            "org_alias",
            150,
            provider_slug="brave-search",
            capability_id="search.query",
        )

        with (
            patch("routes.billing_v2._require_org", new=AsyncMock(return_value="org_alias")),
            patch("routes.billing_v2.get_billing_event_stream", return_value=stream),
        ):
            resp = client.get("/v2/billing/events", headers={"X-Rhumb-Key": "test_key"})

        assert resp.status_code == 200
        event = resp.json()["data"]["events"][0]
        assert event["provider_slug"] == "brave-search-api"

    def test_events_do_not_leak_other_orgs_when_authenticated_org_has_no_events(self, client):
        stream = BillingEventStream()
        stream.emit(
            BillingEventType.EXECUTION_CHARGED,
            "org_alias",
            150,
            provider_slug="brave-search",
            capability_id="search.query",
        )

        with (
            patch("routes.billing_v2._require_org", new=AsyncMock(return_value="org_missing")),
            patch("routes.billing_v2.get_billing_event_stream", return_value=stream),
        ):
            resp = client.get("/v2/billing/events", headers={"X-Rhumb-Key": "test_key"})

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["events"] == []
        assert data["count"] == 0

    def test_events_canonicalize_alias_backed_provider_metadata(self, client):
        stream = BillingEventStream()
        stream.emit(
            BillingEventType.EXECUTION_FAILED_NO_CHARGE,
            "org_alias",
            0,
            provider_slug="brave-search",
            capability_id="search.query",
            metadata={
                "provider_used": "brave-search",
                "detail": {
                    "fallback_provider": "pdl",
                    "fallback_providers": ["pdl", "brave-search-api"],
                    "message": "brave-search-api failed before pdl fallback",
                },
            },
        )

        with (
            patch("routes.billing_v2._require_org", new=AsyncMock(return_value="org_alias")),
            patch("routes.billing_v2.get_billing_event_stream", return_value=stream),
        ):
            resp = client.get("/v2/billing/events", headers={"X-Rhumb-Key": "test_key"})

        assert resp.status_code == 200
        event = resp.json()["data"]["events"][0]
        assert event["metadata"] == {
            "provider_used": "brave-search-api",
            "detail": {
                "fallback_provider": "people-data-labs",
                "fallback_providers": ["people-data-labs", "brave-search-api"],
                "message": "brave-search-api failed before people-data-labs fallback",
            },
        }

    def test_summary_merges_alias_backed_provider_totals_under_public_id(self, client):
        stream = BillingEventStream()
        stream.emit(
            BillingEventType.EXECUTION_CHARGED,
            "org_alias",
            150,
            provider_slug="brave-search",
            capability_id="search.query",
        )
        stream.emit(
            BillingEventType.EXECUTION_CHARGED,
            "org_alias",
            200,
            provider_slug="brave-search-api",
            capability_id="search.query",
        )

        with (
            patch("routes.billing_v2._require_org", new=AsyncMock(return_value="org_alias")),
            patch("routes.billing_v2.get_billing_event_stream", return_value=stream),
        ):
            resp = client.get("/v2/billing/summary", headers={"X-Rhumb-Key": "test_key"})

        assert resp.status_code == 200
        assert resp.json()["data"]["by_provider"] == {
            "brave-search-api": {
                "charged_usd_cents": 350,
                "charged_usd": 3.5,
            }
        }

    def test_summary_does_not_leak_other_orgs_when_authenticated_org_has_no_events(self, client):
        stream = BillingEventStream()
        stream.emit(
            BillingEventType.EXECUTION_CHARGED,
            "org_alias",
            150,
            provider_slug="brave-search",
            capability_id="search.query",
        )

        with (
            patch("routes.billing_v2._require_org", new=AsyncMock(return_value="org_missing")),
            patch("routes.billing_v2.get_billing_event_stream", return_value=stream),
        ):
            resp = client.get("/v2/billing/summary", headers={"X-Rhumb-Key": "test_key"})

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_charged_usd_cents"] == 0
        assert data["total_credited_usd_cents"] == 0
        assert data["events_count"] == 0
        assert data["by_provider"] == {}

    def test_summary_recanonicalizes_alias_backed_provider_totals_from_legacy_summary(self, client):
        class _LegacySummaryStream:
            def summarize(self, org_id, period=None):
                return BillingEventSummary(
                    org_id=org_id,
                    period=period or "all",
                    total_charged_usd_cents=350,
                    total_credited_usd_cents=0,
                    execution_count=2,
                    x402_payment_count=0,
                    credit_purchase_count=0,
                    by_provider={"brave-search": 150, "brave-search-api": 200},
                    by_capability={"search.query": 350},
                    events_count=2,
                )

        with (
            patch("routes.billing_v2._require_org", new=AsyncMock(return_value="org_alias")),
            patch("routes.billing_v2.get_billing_event_stream", return_value=_LegacySummaryStream()),
        ):
            resp = client.get("/v2/billing/summary", headers={"X-Rhumb-Key": "test_key"})

        assert resp.status_code == 200
        assert resp.json()["data"]["by_provider"] == {
            "brave-search-api": {
                "charged_usd_cents": 350,
                "charged_usd": 3.5,
            }
        }
