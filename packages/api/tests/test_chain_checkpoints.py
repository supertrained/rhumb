"""Tests for AUD-3 follow-on head checkpoints."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import settings
from routes.admin_chain_integrity import router, set_test_chain_integrity_stores
from services.audit_trail import AuditEventType, AuditTrail
from services.billing_events import BillingEventStream, BillingEventType
from services.chain_checkpoints import checkpoint_audit_head, checkpoint_billing_head


class FakeOutbox:
    def __init__(self) -> None:
        self.checkpoints: list[dict] = []
        self.flush_calls = 0

    def append_chain_checkpoint(self, payload: dict) -> None:
        self.checkpoints.append(payload)

    async def flush_once(self) -> int:
        self.flush_calls += 1
        return len(self.checkpoints)


@pytest.fixture(autouse=True)
def _reset_route_tests() -> None:
    set_test_chain_integrity_stores(outbox=None, audit_trail=None, billing_stream=None)
    original_secret = settings.rhumb_admin_secret
    settings.rhumb_admin_secret = None
    yield
    settings.rhumb_admin_secret = original_secret
    set_test_chain_integrity_stores(outbox=None, audit_trail=None, billing_stream=None)


@pytest.mark.asyncio
async def test_checkpoint_audit_head_appends_signed_payload() -> None:
    outbox = FakeOutbox()
    audit = AuditTrail()
    audit.record(
        AuditEventType.EXECUTION_COMPLETED,
        "execute",
        org_id="org_test",
        detail={"ok": True},
    )

    payload = await checkpoint_audit_head(
        reason="external_anchor_candidate",
        metadata={"requested_by": "pedro"},
        outbox=outbox,
        audit_trail=audit,
    )

    assert payload is not None
    assert payload["stream_name"] == "audit_events"
    assert payload["reason"] == "external_anchor_candidate"
    assert payload["source_head_hash"] == audit.latest_hash
    assert payload["source_head_sequence"] == audit.latest_sequence
    assert payload["checkpoint_hash"]
    assert payload["metadata"]["event_count"] == 1
    assert payload["metadata"]["requested_by"] == "pedro"
    assert payload["metadata"]["checkpoint_origin"] == "manual_head_snapshot"
    assert outbox.checkpoints == [payload]
    assert outbox.flush_calls == 1


@pytest.mark.asyncio
async def test_checkpoint_billing_head_skips_empty_stream() -> None:
    payload = await checkpoint_billing_head(
        reason="anchor_ready_snapshot",
        outbox=FakeOutbox(),
        billing_stream=BillingEventStream(),
    )
    assert payload is None


@pytest.mark.asyncio
async def test_checkpoint_head_fails_closed_without_outbox() -> None:
    billing = BillingEventStream()
    billing.emit(
        BillingEventType.EXECUTION_CHARGED,
        org_id="org_test",
        amount_usd_cents=25,
        metadata={"case": "missing_outbox"},
    )

    with pytest.raises(RuntimeError, match="Durable checkpoint outbox is unavailable"):
        await checkpoint_billing_head(
            reason="anchor_ready_snapshot",
            outbox=None,
            billing_stream=billing,
        )


def test_admin_route_creates_audit_checkpoint() -> None:
    settings.rhumb_admin_secret = "test-secret"
    outbox = FakeOutbox()
    audit = AuditTrail()
    audit.record(
        AuditEventType.EXECUTION_STARTED,
        "execute",
        org_id="org_route",
        detail={"provider": "brave-search"},
    )
    set_test_chain_integrity_stores(outbox=outbox, audit_trail=audit)

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/v1/admin/trust/chain-checkpoints/audit_events",
        headers={"X-Rhumb-Admin-Key": "test-secret"},
        json={"reason": "external_anchor_candidate", "metadata": {"operator": "pedro"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "created"
    assert body["checkpoint"]["stream_name"] == "audit_events"
    assert body["checkpoint"]["metadata"]["operator"] == "pedro"
    assert outbox.flush_calls == 1


def test_admin_route_skips_empty_billing_stream() -> None:
    settings.rhumb_admin_secret = "test-secret"
    set_test_chain_integrity_stores(outbox=FakeOutbox(), billing_stream=BillingEventStream())

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/v1/admin/trust/chain-checkpoints/billing_events",
        headers={"X-Rhumb-Admin-Key": "test-secret"},
        json={"reason": "anchor_ready_snapshot"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "skipped"
    assert body["stream_name"] == "billing_events"
