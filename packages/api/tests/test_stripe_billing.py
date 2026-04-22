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

from app import app as _shared_app
from services.stripe_billing import _stripe_to_dict


# ── Helpers ──────────────────────────────────────────────────────────


def _stripe_signature(payload: bytes, secret: str) -> str:
    """Build a valid Stripe-Signature header for testing."""
    timestamp = str(int(time.time()))
    signed_payload = f"{timestamp}.{payload.decode()}"
    signature = hmac.new(
        secret.encode(), signed_payload.encode(), hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={signature}"


_BYPASS_KEY = "rhumb_test_bypass_key_0000"

@pytest.fixture
def billing_client() -> TestClient:
    """Fresh test client with no admin auth needed."""
    return TestClient(_shared_app, headers={"X-Rhumb-Key": _BYPASS_KEY})


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
    client = TestClient(_shared_app)
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


def test_stripe_to_dict_supports_to_dict_recursive() -> None:
    class LegacyStripeObject:
        def to_dict_recursive(self) -> dict[str, Any]:
            return {"id": "cs_legacy"}

    assert _stripe_to_dict(LegacyStripeObject()) == {"id": "cs_legacy"}


def test_stripe_to_dict_supports_to_dict_only() -> None:
    class ModernStripeObject:
        def to_dict(self) -> dict[str, Any]:
            return {"id": "cs_modern"}

    assert _stripe_to_dict(ModernStripeObject()) == {"id": "cs_modern"}


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


@patch("routes.billing.supabase_count", new_callable=AsyncMock)
@patch("routes.billing.supabase_fetch", new_callable=AsyncMock)
def test_ledger_returns_entries(
    mock_fetch: AsyncMock, mock_count: AsyncMock, billing_client: TestClient
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
    mock_fetch.return_value = entries
    mock_count.return_value = 1

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
    return TestClient(_shared_app)


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
    client = TestClient(_shared_app, raise_server_exceptions=False)
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

    client = TestClient(_shared_app)

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
    with (
        patch("services.stripe_billing._sb_get", new_callable=AsyncMock) as mock_get,
        patch("stripe.Customer.retrieve", return_value=MagicMock(id="cus_existing_123")) as mock_retrieve,
    ):
        mock_get.return_value = [{"stripe_customer_id": "cus_existing_123"}]

        from services.stripe_billing import get_or_create_stripe_customer
        result = await get_or_create_stripe_customer("org_1", "test@example.com")

    assert result == "cus_existing_123"
    mock_get.assert_called_once()
    mock_retrieve.assert_called_once_with("cus_existing_123")


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
async def test_get_or_create_customer_repairs_test_mode_customer_mapping() -> None:
    """Should replace a stale test-mode customer when prod switches to live keys."""
    from stripe._error import InvalidRequestError

    stale_exc = InvalidRequestError(
        message="Request req_123: No such customer: 'cus_test_old'; a similar object exists in test mode, but a live mode key was used to make this request.",
        param="customer",
    )

    mock_customer = MagicMock()
    mock_customer.id = "cus_live_456"

    with (
        patch("services.stripe_billing._sb_get", new_callable=AsyncMock) as mock_get,
        patch("services.stripe_billing._sb_patch", new_callable=AsyncMock) as mock_patch,
        patch("stripe.Customer.retrieve", side_effect=stale_exc) as mock_retrieve,
        patch("stripe.Customer.create", return_value=mock_customer) as mock_create,
    ):
        mock_get.return_value = [{"stripe_customer_id": "cus_test_old"}]
        mock_patch.return_value = True

        from services.stripe_billing import get_or_create_stripe_customer
        result = await get_or_create_stripe_customer("org_live", "live@example.com")

    assert result == "cus_live_456"
    mock_retrieve.assert_called_once_with("cus_test_old")
    mock_create.assert_called_once_with(email="live@example.com", metadata={"org_id": "org_live"})
    mock_patch.assert_called_once_with(
        "stripe_customers?org_id=eq.org_live",
        {"stripe_customer_id": "cus_live_456"},
    )


@pytest.mark.anyio
async def test_create_checkout_session_saves_payment_method_for_future_reloads() -> None:
    mock_session = MagicMock()
    mock_session.id = "cs_checkout_123"
    mock_session.url = "https://checkout.stripe.com/pay/cs_checkout_123"

    with (
        patch("services.stripe_billing.ensure_org_billing_bootstrap", new_callable=AsyncMock),
        patch("services.stripe_billing._sb_get", new_callable=AsyncMock) as mock_get,
        patch("services.stripe_billing.get_or_create_stripe_customer", new_callable=AsyncMock) as mock_customer,
        patch("stripe.checkout.Session.create", return_value=mock_session) as mock_checkout,
    ):
        mock_get.return_value = [{"email": "billing@example.com"}]
        mock_customer.return_value = "cus_saved_card"

        from services.stripe_billing import create_checkout_session
        result = await create_checkout_session(
            org_id="org_checkout",
            amount_cents=2500,
            success_url="https://rhumb.dev/dashboard?checkout=success",
            cancel_url="https://rhumb.dev/dashboard?checkout=cancel",
        )

    assert result == {
        "checkout_url": "https://checkout.stripe.com/pay/cs_checkout_123",
        "session_id": "cs_checkout_123",
    }
    assert mock_checkout.call_args.kwargs["payment_intent_data"] == {
        "setup_future_usage": "off_session"
    }


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
async def test_handle_checkout_completed_persists_payment_method() -> None:
    session = {
        "id": "cs_test_credit_pm",
        "payment_intent": "pi_saved_card_1",
        "metadata": {"org_id": "org_credit_pm", "amount_cents": "2500"},
    }

    payment_intent = MagicMock()
    payment_intent.payment_method = "pm_saved_123"

    with (
        patch("services.stripe_billing._sb_get", new_callable=AsyncMock) as mock_get,
        patch("services.stripe_billing._sb_post", new_callable=AsyncMock) as mock_post,
        patch("services.stripe_billing._sb_patch", new_callable=AsyncMock) as mock_patch,
        patch("stripe.PaymentIntent.retrieve", return_value=payment_intent),
    ):
        mock_get.side_effect = [[], [{"balance_usd_cents": 0}]]
        mock_patch.return_value = True
        mock_post.return_value = [{}]

        from services.stripe_billing import handle_checkout_completed
        result = await handle_checkout_completed(session)

    assert result is True
    assert mock_patch.call_args[0][1]["stripe_payment_method_id"] == "pm_saved_123"


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


@pytest.mark.anyio
async def test_confirm_checkout_session_rejects_mismatched_org() -> None:
    session_payload = {
        "id": "cs_test_confirm",
        "status": "complete",
        "payment_status": "paid",
        "payment_intent": "pi_test",
        "metadata": {"org_id": "org_other", "amount_cents": "2500"},
    }

    mock_session = MagicMock()
    mock_session.to_dict_recursive.return_value = session_payload

    with (
        patch("stripe.checkout.Session.retrieve", return_value=mock_session),
        patch("services.stripe_billing.handle_checkout_completed", new_callable=AsyncMock) as mock_handle,
    ):
        from services.stripe_billing import confirm_checkout_session_detailed

        result = await confirm_checkout_session_detailed("cs_test_confirm", expected_org_id="org_expected")

    assert result["processed"] is False
    assert result["reason"] == "org_mismatch"
    mock_handle.assert_not_called()


@pytest.mark.anyio
async def test_confirm_checkout_session_applies_checkout_when_paid() -> None:
    session_payload = {
        "id": "cs_test_confirm_ok",
        "status": "complete",
        "payment_status": "paid",
        "payment_intent": {"id": "pi_test_ok"},
        "metadata": {"org_id": "org_expected", "amount_cents": "2500"},
    }

    mock_session = MagicMock()
    mock_session.to_dict_recursive.return_value = session_payload

    with (
        patch("stripe.checkout.Session.retrieve", return_value=mock_session),
        patch("services.stripe_billing._checkout_credit_exists", new_callable=AsyncMock, side_effect=[False, False]),
        patch("services.stripe_billing.handle_checkout_completed", new_callable=AsyncMock, return_value=True) as mock_handle,
    ):
        from services.stripe_billing import confirm_checkout_session_detailed

        result = await confirm_checkout_session_detailed("cs_test_confirm_ok", expected_org_id="org_expected")

    assert result["processed"] is True
    assert result["reason"] == "credited"
    called_session = mock_handle.await_args.args[0]
    assert called_session["id"] == "cs_test_confirm_ok"
    assert called_session["payment_intent"] == "pi_test_ok"


@pytest.mark.anyio
async def test_confirm_checkout_session_reports_already_credited_before_apply() -> None:
    session_payload = {
        "id": "cs_test_confirm_existing",
        "status": "complete",
        "payment_status": "paid",
        "payment_intent": "pi_test_existing",
        "metadata": {"org_id": "org_expected", "amount_cents": "2500"},
    }

    mock_session = MagicMock()
    mock_session.to_dict_recursive.return_value = session_payload

    with (
        patch("stripe.checkout.Session.retrieve", return_value=mock_session),
        patch("services.stripe_billing._checkout_credit_exists", new_callable=AsyncMock, return_value=True),
        patch("services.stripe_billing.handle_checkout_completed", new_callable=AsyncMock) as mock_handle,
    ):
        from services.stripe_billing import confirm_checkout_session_detailed

        result = await confirm_checkout_session_detailed(
            "cs_test_confirm_existing", expected_org_id="org_expected"
        )

    assert result["processed"] is True
    assert result["reason"] == "already_credited"
    mock_handle.assert_not_called()


@pytest.mark.anyio
async def test_confirm_checkout_session_reports_already_credited_after_apply_race() -> None:
    session_payload = {
        "id": "cs_test_confirm_race",
        "status": "complete",
        "payment_status": "paid",
        "payment_intent": "pi_test_race",
        "metadata": {"org_id": "org_expected", "amount_cents": "2500"},
    }

    mock_session = MagicMock()
    mock_session.to_dict_recursive.return_value = session_payload

    with (
        patch("stripe.checkout.Session.retrieve", return_value=mock_session),
        patch("services.stripe_billing._checkout_credit_exists", new_callable=AsyncMock, side_effect=[False, True]),
        patch("services.stripe_billing.handle_checkout_completed", new_callable=AsyncMock, return_value=False) as mock_handle,
    ):
        from services.stripe_billing import confirm_checkout_session_detailed

        result = await confirm_checkout_session_detailed(
            "cs_test_confirm_race", expected_org_id="org_expected"
        )

    assert result["processed"] is True
    assert result["reason"] == "already_credited"
    mock_handle.assert_awaited_once()
