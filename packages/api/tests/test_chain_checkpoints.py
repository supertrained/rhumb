"""Tests for AUD-3 follow-on head checkpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import settings
from routes.admin_chain_integrity import router, set_test_chain_integrity_stores
from services.audit_trail import AuditEventType, AuditTrail
from services.billing_events import BillingEventStream, BillingEventType
from services.error_envelope import RhumbError, rhumb_error_handler
from services.chain_checkpoints import (
    checkpoint_audit_head,
    checkpoint_billing_head,
    checkpoint_execution_receipts_head,
    checkpoint_score_audit_head,
)


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
    with patch("services.chain_checkpoints.supabase_fetch", new=AsyncMock(return_value=[])):
        payload = await checkpoint_billing_head(
            reason="anchor_ready_snapshot",
            outbox=FakeOutbox(),
            billing_stream=BillingEventStream(),
        )
    assert payload is None


@pytest.mark.asyncio
async def test_checkpoint_execution_receipts_head_appends_signed_payload() -> None:
    outbox = FakeOutbox()

    payload = await checkpoint_execution_receipts_head(
        reason="anchor_ready_snapshot",
        metadata={"requested_by": "pedro"},
        outbox=outbox,
        latest_row={
            "receipt_id": "rcpt_latest_001",
            "receipt_hash": "ab" * 32,
            "chain_sequence": 376,
            "created_at": "2026-04-06T22:01:00+00:00",
        },
        row_count=376,
    )

    assert payload is not None
    assert payload["stream_name"] == "execution_receipts"
    assert payload["source_head_hash"] == "ab" * 32
    assert payload["source_head_sequence"] == 376
    assert payload["source_key_version"] is None
    assert payload["metadata"]["event_count"] == 376
    assert payload["metadata"]["latest_receipt_id"] == "rcpt_latest_001"
    assert payload["metadata"]["source_hash_mode"] == "receipt_hash_chain_sha256"
    assert payload["metadata"]["source_key_version_semantics"] == "not_applicable"
    assert payload["metadata"]["requested_by"] == "pedro"
    assert outbox.checkpoints[0]["stream_name"] == "execution_receipts"
    assert outbox.flush_calls == 1


@pytest.mark.asyncio
async def test_checkpoint_execution_receipts_head_skips_empty_stream() -> None:
    payload = await checkpoint_execution_receipts_head(
        reason="anchor_ready_snapshot",
        outbox=FakeOutbox(),
        latest_row={},
        row_count=0,
        metadata={},
    )
    assert payload is None


@pytest.mark.asyncio
async def test_checkpoint_audit_head_falls_back_to_durable_table_when_stream_empty() -> None:
    outbox = FakeOutbox()

    with (
        patch("services.chain_checkpoints.supabase_fetch", new=AsyncMock(return_value=[{
            "event_id": "aud_latest_001",
            "chain_hash": "cd" * 32,
            "chain_sequence": 2,
            "timestamp": "2026-04-06T22:01:00+00:00",
            "key_version": 1,
        }])),
    ):
        payload = await checkpoint_audit_head(
            reason="anchor_ready_snapshot",
            metadata={"requested_by": "pedro"},
            outbox=outbox,
            audit_trail=AuditTrail(),
        )

    assert payload is not None
    assert payload["stream_name"] == "audit_events"
    assert payload["source_head_hash"] == "cd" * 32
    assert payload["source_head_sequence"] == 2
    assert payload["source_key_version"] == 1
    assert payload["metadata"]["head_source"] == "durable_table_fallback"
    assert outbox.checkpoints[0]["stream_name"] == "audit_events"


@pytest.mark.asyncio
async def test_checkpoint_billing_head_falls_back_to_durable_table_when_stream_empty() -> None:
    outbox = FakeOutbox()

    with (
        patch("services.chain_checkpoints.supabase_fetch", new=AsyncMock(return_value=[{
            "event_id": "bevt_latest_001",
            "chain_hash": "de" * 32,
            "created_at": "2026-04-06T22:01:01+00:00",
            "key_version": 1,
        }])),
        patch("services.chain_checkpoints.supabase_count", new=AsyncMock(return_value=4)),
    ):
        payload = await checkpoint_billing_head(
            reason="anchor_ready_snapshot",
            metadata={"requested_by": "pedro"},
            outbox=outbox,
            billing_stream=BillingEventStream(),
        )

    assert payload is not None
    assert payload["stream_name"] == "billing_events"
    assert payload["source_head_hash"] == "de" * 32
    assert payload["source_head_sequence"] == 4
    assert payload["source_key_version"] == 1
    assert payload["metadata"]["head_source"] == "durable_table_fallback"
    assert outbox.checkpoints[0]["stream_name"] == "billing_events"


@pytest.mark.asyncio
async def test_checkpoint_score_audit_head_appends_signed_payload() -> None:
    outbox = FakeOutbox()

    payload = await checkpoint_score_audit_head(
        reason="external_anchor_candidate",
        metadata={"requested_by": "pedro"},
        outbox=outbox,
        latest_row={
            "entry_id": "saud_latest_row",
            "chain_hash": "ab" * 32,
            "key_version": 1,
            "created_at": "2026-04-04T18:38:00+00:00",
        },
        row_count=2,
    )

    assert payload is not None
    assert payload["stream_name"] == "score_audit_chain"
    assert payload["reason"] == "external_anchor_candidate"
    assert payload["source_head_hash"] == "ab" * 32
    assert payload["source_head_sequence"] == 2
    assert payload["source_key_version"] == 1
    assert payload["checkpoint_hash"]
    assert payload["metadata"]["event_count"] == 2
    assert payload["metadata"]["requested_by"] == "pedro"
    assert payload["metadata"]["latest_entry_id"] == "saud_latest_row"
    assert payload["metadata"]["selected_head_entry_id"] == "saud_latest_row"
    assert payload["metadata"]["verification_status"] == "verified"
    assert payload["metadata"]["verification_policy_version"] == "2026-04-06"
    assert (
        payload["metadata"]["verification_policy_reference"]
        == "docs/specs/AUD-3-SCORE-AUDIT-QUARANTINE-POLICY-2026-04-06.md"
    )
    assert payload["metadata"]["head_selection_mode"] == "latest_head"
    assert payload["metadata"]["checkpoint_origin"] == "manual_head_snapshot"
    assert payload["metadata"]["latest_event_timestamp"] == "2026-04-04T18:38:00+00:00"
    assert outbox.checkpoints == [payload]
    assert outbox.flush_calls == 1


@pytest.mark.asyncio
async def test_checkpoint_score_audit_head_quarantines_unverifiable_latest_tail() -> None:
    outbox = FakeOutbox()

    payload = await checkpoint_score_audit_head(
        reason="external_anchor_candidate",
        outbox=outbox,
        latest_row={
            "entry_id": "saud_5565e543fcc248dbbe515e38103ac518",
            "chain_hash": "aa" * 32,
            "key_version": None,
            "created_at": "2026-04-04T18:39:00+00:00",
        },
        latest_verified_row={
            "entry_id": "saud_verified_prior_head",
            "chain_hash": "bb" * 32,
            "key_version": 0,
            "created_at": "2026-04-04T18:38:00+00:00",
        },
        row_count=2,
        verified_row_count=1,
    )

    assert payload is not None
    assert payload["source_head_hash"] == "bb" * 32
    assert payload["source_head_sequence"] == 1
    assert payload["source_key_version"] == 0
    assert payload["metadata"]["event_count"] == 1
    assert payload["metadata"]["latest_event_timestamp"] == "2026-04-04T18:38:00+00:00"
    assert payload["metadata"]["verification_status"] == "verified_with_quarantined_tail"
    assert payload["metadata"]["head_selection_mode"] == "latest_verified_head"
    assert payload["metadata"]["selected_head_entry_id"] == "saud_verified_prior_head"
    assert payload["metadata"]["latest_entry_id"] == "saud_5565e543fcc248dbbe515e38103ac518"
    assert payload["metadata"]["latest_observed_entry_id"] == "saud_5565e543fcc248dbbe515e38103ac518"
    assert payload["metadata"]["verification_policy_version"] == "2026-04-06"
    assert (
        payload["metadata"]["verification_policy_reference"]
        == "docs/specs/AUD-3-SCORE-AUDIT-QUARANTINE-POLICY-2026-04-06.md"
    )
    assert (
        payload["metadata"]["latest_observed_forensic_note"]
        == "docs/specs/AUD-3-LEGACY-SCORE-AUDIT-FORENSIC-NOTE-2026-04-04.md"
    )
    assert payload["metadata"]["total_observed_event_count"] == 2
    assert payload["metadata"]["quarantined_tail_count"] == 1
    assert payload["metadata"]["quarantined_tail_entry_ids"] == [
        "saud_5565e543fcc248dbbe515e38103ac518"
    ]
    assert payload["metadata"]["quarantined_tail"][0]["verification_status"] == "unverifiable_legacy"
    assert outbox.checkpoints == [payload]
    assert outbox.flush_calls == 1


@pytest.mark.asyncio
async def test_checkpoint_score_audit_head_quarantines_unverifiable_tail() -> None:
    outbox = FakeOutbox()

    payload = await checkpoint_score_audit_head(
        reason="external_anchor_candidate",
        metadata={"requested_by": "pedro"},
        outbox=outbox,
        latest_row={
            "entry_id": "saud_unverifiable_tail",
            "chain_hash": "ef" * 32,
            "key_version": None,
            "created_at": "2026-04-04T18:39:00+00:00",
        },
        latest_verified_row={
            "entry_id": "saud_verified_head",
            "chain_hash": "ab" * 32,
            "key_version": 0,
            "created_at": "2026-04-04T18:38:00+00:00",
        },
        row_count=2,
        verified_row_count=1,
    )

    assert payload is not None
    assert payload["stream_name"] == "score_audit_chain"
    assert payload["source_head_hash"] == "ab" * 32
    assert payload["source_head_sequence"] == 1
    assert payload["source_key_version"] == 0
    assert payload["metadata"]["event_count"] == 1
    assert payload["metadata"]["verification_status"] == "verified_with_quarantined_tail"
    assert payload["metadata"]["head_selection_mode"] == "latest_verified_head"
    assert payload["metadata"]["selected_head_entry_id"] == "saud_verified_head"
    assert payload["metadata"]["latest_entry_id"] == "saud_unverifiable_tail"
    assert payload["metadata"]["latest_observed_entry_id"] == "saud_unverifiable_tail"
    assert payload["metadata"]["verification_policy_version"] == "2026-04-06"
    assert (
        payload["metadata"]["verification_policy_reference"]
        == "docs/specs/AUD-3-SCORE-AUDIT-QUARANTINE-POLICY-2026-04-06.md"
    )
    assert payload["metadata"]["quarantine_action"] == "excluded_from_verified_head"
    assert payload["metadata"]["latest_observed_verification_status"] == "unattributed_legacy"
    assert payload["metadata"]["total_observed_event_count"] == 2
    assert payload["metadata"]["quarantined_tail_count"] == 1
    assert payload["metadata"]["quarantined_tail_entry_ids"] == ["saud_unverifiable_tail"]
    assert outbox.checkpoints == [payload]
    assert outbox.flush_calls == 1


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


def test_admin_route_rejects_invalid_stream_before_outbox_read() -> None:
    settings.rhumb_admin_secret = "test-secret"

    app = FastAPI()
    app.add_exception_handler(RhumbError, rhumb_error_handler)
    app.include_router(router)
    client = TestClient(app)

    with patch("routes.admin_chain_integrity.get_event_outbox") as get_event_outbox:
        response = client.post(
            "/v1/admin/trust/chain-checkpoints/%20%20%20",
            headers={"X-Rhumb-Admin-Key": "test-secret"},
            json={"reason": "external_anchor_candidate"},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PARAMETERS"
    get_event_outbox.assert_not_called()


def test_admin_route_rejects_blank_checkpoint_reason_before_outbox_read() -> None:
    settings.rhumb_admin_secret = "test-secret"

    app = FastAPI()
    app.add_exception_handler(RhumbError, rhumb_error_handler)
    app.include_router(router)
    client = TestClient(app)

    with patch("routes.admin_chain_integrity.get_event_outbox") as get_event_outbox:
        response = client.post(
            "/v1/admin/trust/chain-checkpoints/audit_events",
            headers={"X-Rhumb-Admin-Key": "test-secret"},
            json={"reason": "   "},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PARAMETERS"
    assert response.json()["error"]["message"] == "Invalid checkpoint reason"
    get_event_outbox.assert_not_called()


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


def test_admin_route_trims_checkpoint_reason_before_write() -> None:
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
        json={"reason": "  external_anchor_candidate  "},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "created"
    assert body["checkpoint"]["reason"] == "external_anchor_candidate"
    assert outbox.checkpoints[0]["reason"] == "external_anchor_candidate"


def test_admin_route_skips_empty_billing_stream() -> None:
    settings.rhumb_admin_secret = "test-secret"
    set_test_chain_integrity_stores(outbox=FakeOutbox(), billing_stream=BillingEventStream())

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    with patch("services.chain_checkpoints.supabase_fetch", new=AsyncMock(return_value=[])):
        response = client.post(
            "/v1/admin/trust/chain-checkpoints/billing_events",
            headers={"X-Rhumb-Admin-Key": "test-secret"},
            json={"reason": "anchor_ready_snapshot"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "skipped"
    assert body["stream_name"] == "billing_events"


def test_admin_route_creates_execution_receipts_checkpoint() -> None:
    settings.rhumb_admin_secret = "test-secret"
    set_test_chain_integrity_stores(
        outbox=FakeOutbox(),
        execution_receipt_row={
            "receipt_id": "rcpt_latest_001",
            "receipt_hash": "ef" * 32,
            "chain_sequence": 376,
            "created_at": "2026-04-06T22:01:00+00:00",
        },
        execution_receipt_count=376,
    )

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/v1/admin/trust/chain-checkpoints/execution_receipts",
        headers={"X-Rhumb-Admin-Key": "test-secret"},
        json={"reason": "external_anchor_candidate", "metadata": {"operator": "pedro"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "created"
    assert body["stream_name"] == "execution_receipts"
    assert body["checkpoint"]["source_head_sequence"] == 376
    assert body["checkpoint"]["source_key_version"] is None
    assert body["checkpoint"]["metadata"]["latest_receipt_id"] == "rcpt_latest_001"


def test_admin_route_creates_score_audit_checkpoint() -> None:
    settings.rhumb_admin_secret = "test-secret"
    outbox = FakeOutbox()
    set_test_chain_integrity_stores(
        outbox=outbox,
        score_audit_row={
            "entry_id": "saud_live_head",
            "chain_hash": "cd" * 32,
            "key_version": 1,
            "created_at": "2026-04-04T18:45:00+00:00",
        },
        score_audit_count=3,
    )

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/v1/admin/trust/chain-checkpoints/score_audit_chain",
        headers={"X-Rhumb-Admin-Key": "test-secret"},
        json={"reason": "external_anchor_candidate", "metadata": {"operator": "pedro"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "created"
    assert body["checkpoint"]["stream_name"] == "score_audit_chain"
    assert body["checkpoint"]["source_head_sequence"] == 3
    assert body["checkpoint"]["metadata"]["operator"] == "pedro"
    assert body["checkpoint"]["metadata"]["latest_entry_id"] == "saud_live_head"
    assert body["checkpoint"]["metadata"]["selected_head_entry_id"] == "saud_live_head"
    assert outbox.flush_calls == 1


def test_admin_route_quarantines_unverifiable_score_tail() -> None:
    settings.rhumb_admin_secret = "test-secret"
    outbox = FakeOutbox()
    set_test_chain_integrity_stores(
        outbox=outbox,
        score_audit_row={
            "entry_id": "saud_unverifiable_tail",
            "chain_hash": "ef" * 32,
            "key_version": None,
            "created_at": "2026-04-04T18:39:00+00:00",
        },
        score_audit_verified_row={
            "entry_id": "saud_verified_head",
            "chain_hash": "ab" * 32,
            "key_version": 0,
            "created_at": "2026-04-04T18:38:00+00:00",
        },
        score_audit_count=2,
        score_audit_verified_count=1,
    )

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/v1/admin/trust/chain-checkpoints/score_audit_chain",
        headers={"X-Rhumb-Admin-Key": "test-secret"},
        json={"reason": "external_anchor_candidate", "metadata": {"operator": "pedro"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "created"
    assert body["checkpoint"]["source_head_sequence"] == 1
    assert body["checkpoint"]["source_key_version"] == 0
    assert body["checkpoint"]["metadata"]["verification_status"] == "verified_with_quarantined_tail"
    assert body["checkpoint"]["metadata"]["verification_policy_version"] == "2026-04-06"
    assert body["checkpoint"]["metadata"]["head_selection_mode"] == "latest_verified_head"
    assert body["checkpoint"]["metadata"]["quarantined_tail_count"] == 1
    assert outbox.flush_calls == 1
