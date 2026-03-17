"""Tests for WU-0.2+0.3 Stripe billing routes, webhook handler, and service layer."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import create_app


# ── Helpers ──────────────────────────────────────────────────────────


def _stripe_signature(payload: bytes, secret: str) -> str:
    """Build a valid Stripe-Signature header for testing."""
    timestamp = str(int(time.time()))
    signed_payload = f"{timestamp}.{payload.decode()}"
    signature = hmac.new(
        secret.encode(), signed_payload.encode(), hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={signature}"


@pytest.fixture
def billing_client() -> TestClient:
    """Fresh test client with no admin auth needed."""
    app = create_app()
    return TestClient(app, headers={"X-Rhumb-Key": "org_test_123"})


# ── Checkout endpoint tests ──────────────────────────────────────────


def test_checkout_amount_too_low(billing_client: TestClient) -> None:
    resp = billing_client.post("/v1/billing/checkout", json={"amount_usd": 2.00})
    assert resp.status_code == 400
    assert "amount_usd must be between" in resp.json()["detail"]


def test_checkout_amount_too_high(billing_client: TestClient) -> None:
    resp = billing_client.post("/v1/billing/checkout", json={"amount_usd": 10000.00})
    assert resp.status_code == 400
    assert "amount_usd must be between" in resp.json()["detail"]


def test_checkout_missing_auth() -> None:
    app = create_app()
    client = TestClient(app)
    resp = client.post("/v1/billing/checkout", json={"amount_usd": 25.00})
    assert resp.status_code == 401


@patch("routes.billing.create_checkout_session", new_callable=AsyncMock)
def test_checkout_returns_url_and_session_id(
    mock_checkout: AsyncMock, billing_client: TestClient
) -> None:
    mock_checkout.return_value = {
        "checkout_url": "https://checkout.stripe.com/pay/cs_test_abc",
        "session_id": "cs_test_abc",
    }

    resp = billing_client.post("/v1/billing/checkout", json={"amount_usd": 25.00})
    assert resp.status_code == 200
    body = resp.json()
    assert body["checkout_url"].startswith("https://checkout.stripe.com/")
    assert body["session_id"] == "cs_test_abc"

    # Verify we called with correct cents conversion
    mock_checkout.assert_called_once()
    call_kwargs = mock_checkout.call_args
    assert call_kwargs.kwargs["amount_cents"] == 2500


@patch("routes.billing.create_checkout_session", new_callable=AsyncMock)
def test_checkout_custom_urls(
    mock_checkout: AsyncMock, billing_client: TestClient
) -> None:
    mock_checkout.return_value = {
        "checkout_url": "https://checkout.stripe.com/pay/cs_test_xyz",
        "session_id": "cs_test_xyz",
    }

    resp = billing_client.post("/v1/billing/checkout", json={
        "amount_usd": 50.00,
        "success_url": "https://myapp.com/success",
        "cancel_url": "https://myapp.com/cancel",
    })
    assert resp.status_code == 200
    call_kwargs = mock_checkout.call_args
    assert call_kwargs.kwargs["success_url"] == "https://myapp.com/success"
    assert call_kwargs.kwargs["cancel_url"] == "https://myapp.com/cancel"


# ── Balance endpoint tests ───────────────────────────────────────────


@patch("routes.billing.supabase_fetch", new_callable=AsyncMock)
def test_balance_returns_org_credits(
    mock_fetch: AsyncMock, billing_client: TestClient
) -> None:
    mock_fetch.return_value = [{"balance_usd_cents": 2500, "reserved_usd_cents": 100}]

    resp = billing_client.get("/v1/billing/balance")
    assert resp.status_code == 200
    body = resp.json()
    assert body["balance_usd"] == 25.0
    assert body["balance_cents"] == 2500
    assert body["reserved_cents"] == 100


@patch("routes.billing.supabase_fetch", new_callable=AsyncMock)
def test_balance_returns_zero_for_unknown_org(
    mock_fetch: AsyncMock, billing_client: TestClient
) -> None:
    mock_fetch.return_value = []

    resp = billing_client.get("/v1/billing/balance")
    assert resp.status_code == 200
    body = resp.json()
    assert body["balance_usd"] == 0.0
    assert body["balance_cents"] == 0


# ── Ledger endpoint tests ───────────────────────────────────────────


@patch("routes.billing.supabase_fetch", new_callable=AsyncMock)
def test_ledger_returns_entries(
    mock_fetch: AsyncMock, billing_client: TestClient
) -> None:
    entries = [
        {
            "id": "uuid-1",
            "event_type": "credit_added",
            "amount_usd_cents": 2500,
            "balance_after_usd_cents": 2500,
            "stripe_checkout_session_id": "cs_test_1",
            "description": "Credit purchase via Stripe Checkout ($25.00)",
            "created_at": "2026-03-17T00:00:00Z",
        },
    ]
    # First call: entries query, second call: total count query
    mock_fetch.side_effect = [entries, [{"id": "uuid-1"}]]

    resp = billing_client.get("/v1/billing/ledger")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["entries"]) == 1
    assert body["total"] == 1
    assert body["entries"][0]["event_type"] == "credit_added"


# ── Webhook tests ────────────────────────────────────────────────────


WEBHOOK_SECRET = "whsec_test_secret_1234"


@pytest.fixture
def webhook_client() -> TestClient:
    """Test client for webhook route (no auth headers)."""
    import os
    os.environ["STRIPE_WEBHOOK_SECRET"] = WEBHOOK_SECRET
    app = create_app()
    return TestClient(app)


def test_webhook_rejects_bad_signature(webhook_client: TestClient) -> None:
    with patch("config.settings.stripe_webhook_secret", WEBHOOK_SECRET):
        resp = webhook_client.post(
            "/webhooks/stripe",
            content=b'{"type": "checkout.session.completed"}',
            headers={
                "Stripe-Signature": "t=123,v1=badsignature",
                "Content-Type": "application/json",
            },
        )
    assert resp.status_code == 400
    assert "Invalid signature" in resp.json()["detail"]


def test_webhook_missing_signature() -> None:
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/webhooks/stripe",
        content=b'{"type": "test"}',
        headers={"Content-Type": "application/json"},
    )
    # FastAPI returns 422 for missing required header
    assert resp.status_code == 422


@patch("routes.webhooks.handle_checkout_completed", new_callable=AsyncMock)
def test_webhook_processes_checkout_completed(
    mock_handler: AsyncMock,
) -> None:
    mock_handler.return_value = True

    event_payload = {
        "id": "evt_test_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_session_1",
                "payment_intent": "pi_test_1",
                "metadata": {"org_id": "org_test", "amount_cents": "2500"},
            }
        },
    }
    raw_body = json.dumps(event_payload).encode()

    app = create_app()
    client = TestClient(app)

    with patch("config.settings.stripe_webhook_secret", WEBHOOK_SECRET):
        # Mock the construct_event to return the event directly
        with patch("stripe.Webhook.construct_event", return_value=event_payload):
            sig = _stripe_signature(raw_body, WEBHOOK_SECRET)
            resp = client.post(
                "/webhooks/stripe",
                content=raw_body,
                headers={
                    "Stripe-Signature": sig,
                    "Content-Type": "application/json",
                },
            )

    assert resp.status_code == 200
    assert resp.json() == {"received": True}
    mock_handler.assert_called_once()
    session_arg = mock_handler.call_args[0][0]
    assert session_arg["id"] == "cs_test_session_1"


# ── Service layer tests ──────────────────────────────────────────────


@pytest.mark.anyio
async def test_get_or_create_customer_reuses_existing() -> None:
    """Should return existing customer without calling Stripe."""
    with patch("services.stripe_billing._sb_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = [{"stripe_customer_id": "cus_existing_123"}]

        from services.stripe_billing import get_or_create_stripe_customer
        result = await get_or_create_stripe_customer("org_1", "test@example.com")

    assert result == "cus_existing_123"
    mock_get.assert_called_once()


@pytest.mark.anyio
async def test_get_or_create_customer_creates_new() -> None:
    """Should create a new Stripe customer and persist mapping."""
    mock_customer = MagicMock()
    mock_customer.id = "cus_new_456"

    with (
        patch("services.stripe_billing._sb_get", new_callable=AsyncMock) as mock_get,
        patch("services.stripe_billing._sb_post", new_callable=AsyncMock) as mock_post,
        patch("stripe.Customer.create", return_value=mock_customer) as mock_stripe,
    ):
        mock_get.return_value = []  # No existing customer
        mock_post.return_value = [{}]

        from services.stripe_billing import get_or_create_stripe_customer
        result = await get_or_create_stripe_customer("org_2", "new@example.com")

    assert result == "cus_new_456"
    mock_stripe.assert_called_once_with(email="new@example.com", metadata={"org_id": "org_2"})
    mock_post.assert_called_once()


@pytest.mark.anyio
async def test_handle_checkout_completed_credits_org() -> None:
    """Should add credits and write ledger entry."""
    session = {
        "id": "cs_test_credit_1",
        "payment_intent": "pi_test_1",
        "metadata": {"org_id": "org_credit", "amount_cents": "5000"},
    }

    with (
        patch("services.stripe_billing._sb_get", new_callable=AsyncMock) as mock_get,
        patch("services.stripe_billing._sb_post", new_callable=AsyncMock) as mock_post,
        patch("services.stripe_billing._sb_patch", new_callable=AsyncMock) as mock_patch,
    ):
        # First call: idempotency check (no existing entry)
        # Second call: get current balance
        mock_get.side_effect = [[], [{"balance_usd_cents": 1000}]]
        mock_patch.return_value = True
        mock_post.return_value = [{}]

        from services.stripe_billing import handle_checkout_completed
        result = await handle_checkout_completed(session)

    assert result is True
    # Verify balance update: 1000 + 5000 = 6000
    mock_patch.assert_called_once()
    patch_payload = mock_patch.call_args[0][1]
    assert patch_payload["balance_usd_cents"] == 6000

    # Verify ledger entry
    mock_post.assert_called_once()
    ledger_payload = mock_post.call_args[0][1]
    assert ledger_payload["event_type"] == "credit_added"
    assert ledger_payload["amount_usd_cents"] == 5000
    assert ledger_payload["balance_after_usd_cents"] == 6000
    assert ledger_payload["stripe_checkout_session_id"] == "cs_test_credit_1"


@pytest.mark.anyio
async def test_handle_checkout_completed_idempotent() -> None:
    """Should not double-credit if ledger entry already exists."""
    session = {
        "id": "cs_test_dupe_1",
        "payment_intent": "pi_test_dupe",
        "metadata": {"org_id": "org_dupe", "amount_cents": "2500"},
    }

    with patch("services.stripe_billing._sb_get", new_callable=AsyncMock) as mock_get:
        # Idempotency check returns existing entry
        mock_get.return_value = [{"id": "existing-ledger-uuid"}]

        from services.stripe_billing import handle_checkout_completed
        result = await handle_checkout_completed(session)

    assert result is False
    # Only one GET call (the idempotency check), no PATCH/POST
    mock_get.assert_called_once()


@pytest.mark.anyio
async def test_handle_checkout_completed_missing_org_id() -> None:
    """Should return False if session metadata is missing org_id."""
    session = {
        "id": "cs_test_bad",
        "payment_intent": "pi_test_bad",
        "metadata": {},
    }

    from services.stripe_billing import handle_checkout_completed
    result = await handle_checkout_completed(session)
    assert result is False


@pytest.mark.anyio
async def test_handle_checkout_auto_creates_org_credits() -> None:
    """Should create org_credits row if it doesn't exist yet."""
    session = {
        "id": "cs_test_new_org",
        "payment_intent": "pi_test_new",
        "metadata": {"org_id": "org_brand_new", "amount_cents": "1000"},
    }

    with (
        patch("services.stripe_billing._sb_get", new_callable=AsyncMock) as mock_get,
        patch("services.stripe_billing._sb_post", new_callable=AsyncMock) as mock_post,
        patch("services.stripe_billing._sb_patch", new_callable=AsyncMock) as mock_patch,
    ):
        # Idempotency check: no existing entry
        # Balance check: no org_credits row
        mock_get.side_effect = [[], []]
        mock_patch.return_value = True
        mock_post.return_value = [{}]

        from services.stripe_billing import handle_checkout_completed
        result = await handle_checkout_completed(session)

    assert result is True
    # Should have called _sb_post twice: once for auto-create, once for ledger
    assert mock_post.call_count == 2
    # First post: create org_credits with balance 0
    first_post = mock_post.call_args_list[0]
    assert first_post[0][0] == "org_credits"
    assert first_post[0][1]["balance_usd_cents"] == 0
