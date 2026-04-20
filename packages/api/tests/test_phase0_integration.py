"""Phase 0 integration tests — end-to-end flows through the payment system.

All Stripe interactions are mocked. Tests verify data flow through
routes → services → (mocked) DB → response.
"""

from __future__ import annotations

import json
import time
import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app import app as _shared_app
from app import create_app
from schemas.agent_identity import AgentIdentitySchema
from services.budget_enforcer import BudgetCheckResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# ORG_ID must match the bypass agent's organization_id seeded in conftest
# so that _require_org() resolves the key correctly on billing endpoints.
ORG_ID = "org-test"
_BYPASS_KEY = "rhumb_test_bypass_key_0000"

def _make_execute_mock_fetch(service_slug: str = "resend", api_domain: str = "api.resend.com"):
    """Path-routing supabase_fetch mock for capability execute tests.
    Matches by URL pattern rather than call order so it survives code refactors.
    """
    _cap_svc_row = {
        "cost_per_call": 0.10, "service_slug": service_slug,
        "auth_method": "api_key", "credential_modes": ["byo"],
        "endpoint_pattern": "POST /emails", "cost_currency": "USD", "free_tier_calls": 0,
    }
    _cap_row = [{"id": "email.send", "domain": "email", "action": "send", "description": "Send"}]
    _svc_row = [{"slug": service_slug, "api_domain": api_domain}]

    async def _fetch(path: str):
        if "capabilities?" in path and "id=eq." in path:
            return _cap_row
        if "capability_services?" in path:
            return [_cap_svc_row]
        if "rhumb_managed_capabilities?" in path:
            return []
        if "services?" in path and "capability_services?" not in path:
            return _svc_row
        return []

    return _fetch




def _mock_agent(org_id: str = ORG_ID) -> AgentIdentitySchema:
    return AgentIdentitySchema(
        agent_id="agent_phase0",
        name="phase0-test-agent",
        organization_id=org_id,
    )


@pytest.fixture(autouse=True)
def _mock_execute_runtime():
    mock_limiter = MagicMock()
    mock_limiter.check_and_increment = AsyncMock(return_value=(True, 29))
    mock_registry = MagicMock()
    mock_registry.is_blocked.return_value = (False, None)
    with (
        patch(
            "routes.capability_execute._get_rate_limiter",
            new_callable=AsyncMock,
            return_value=mock_limiter,
        ),
        patch(
            "routes.capability_execute.init_kill_switch_registry",
            new_callable=AsyncMock,
            return_value=mock_registry,
        ),
        patch(
            "routes.capability_execute.check_billing_health",
            new_callable=AsyncMock,
            return_value=(True, "ok"),
        ),
        patch(
            "routes.capability_execute.supabase_insert_required",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "routes.capability_execute.supabase_patch_required",
            new_callable=AsyncMock,
            return_value=[{}],
        ),
    ):
        yield


def _stripe_signature(payload: bytes, secret: str) -> str:
    """Build a valid Stripe-Signature header."""
    timestamp = str(int(time.time()))
    signed_payload = f"{timestamp}.{payload.decode()}"
    signature = hmac.new(
        secret.encode(), signed_payload.encode(), hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={signature}"


WEBHOOK_SECRET = "whsec_phase0_integration_test"


# ---------------------------------------------------------------------------
# 1. Top-up flow: checkout → webhook → balance reflects credits
# ---------------------------------------------------------------------------


class TestTopUpFlow:
    """Checkout session creation and webhook-driven credit application."""

    @patch("routes.billing.create_checkout_session", new_callable=AsyncMock)
    def test_checkout_creates_session(self, mock_checkout: AsyncMock) -> None:
        """POST /billing/checkout returns a Stripe Checkout URL."""
        mock_checkout.return_value = {
            "checkout_url": "https://checkout.stripe.com/pay/cs_test_topup",
            "session_id": "cs_test_topup",
        }

        client = TestClient(_shared_app, headers={"X-Rhumb-Key": _BYPASS_KEY})
        resp = client.post("/v1/billing/checkout", json={"amount_usd": 50.0})

        assert resp.status_code == 200
        body = resp.json()
        assert body["checkout_url"].startswith("https://checkout.stripe.com/")
        assert body["session_id"] == "cs_test_topup"
        mock_checkout.assert_called_once_with(
            org_id=ORG_ID,
            amount_cents=5000,
            success_url="https://rhumb.dev/billing/success",
            cancel_url="https://rhumb.dev/billing/cancel",
        )

    @pytest.mark.anyio
    async def test_webhook_credits_org_and_writes_ledger(self) -> None:
        """Completed checkout webhook credits the org and creates a ledger entry."""
        session = {
            "id": "cs_test_phase0_topup",
            "payment_intent": "pi_test_phase0",
            "metadata": {"org_id": ORG_ID, "amount_cents": "5000"},
        }

        with (
            patch("services.stripe_billing._sb_get", new_callable=AsyncMock) as mock_get,
            patch("services.stripe_billing._sb_post", new_callable=AsyncMock) as mock_post,
            patch("services.stripe_billing._sb_patch", new_callable=AsyncMock) as mock_patch,
        ):
            # Idempotency check: no existing entry; Balance check: existing row
            mock_get.side_effect = [[], [{"balance_usd_cents": 1000}]]
            mock_patch.return_value = True
            mock_post.return_value = [{}]

            from services.stripe_billing import handle_checkout_completed
            result = await handle_checkout_completed(session)

        assert result is True
        # Balance updated: 1000 + 5000 = 6000
        mock_patch.assert_called_once()
        assert mock_patch.call_args[0][1]["balance_usd_cents"] == 6000
        # Ledger entry written
        mock_post.assert_called_once()
        ledger = mock_post.call_args[0][1]
        assert ledger["event_type"] == "credit_added"
        assert ledger["amount_usd_cents"] == 5000
        assert ledger["balance_after_usd_cents"] == 6000


# ---------------------------------------------------------------------------
# 2. Deduction flow: capability execution → balance decreases → ledger entry
# ---------------------------------------------------------------------------


class TestDeductionFlow:
    """Capability execution deducts credits and logs to ledger."""

    @pytest.mark.anyio
    async def test_successful_execution_deducts_credits(self) -> None:
        """Execute route deducts credits and returns remaining balance."""
        app = create_app()
        mock_store = MagicMock()
        mock_store.verify_api_key_with_agent = AsyncMock(return_value=_mock_agent())

        with (
            patch("routes.capability_execute._get_identity_store", return_value=mock_store),
            patch("routes.capability_execute._budget_enforcer") as mock_budget,
            patch("routes.capability_execute._credit_deduction") as mock_credit,
            patch("routes.capability_execute.check_and_trigger_auto_reload", new_callable=AsyncMock, return_value=None),
            patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock) as mock_fetch,
            patch("routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True),
            patch(
                "routes.capability_execute._inject_auth_request_parts",
                side_effect=lambda slug, auth, headers, body, params: (headers, body, params),
            ),
            patch("routes.capability_execute.get_credential_store") as mock_cred_store,
            patch("routes.capability_execute.httpx.AsyncClient") as MockHttpxClient,
        ):
            mock_budget.check_and_decrement = AsyncMock(
                return_value=BudgetCheckResult(allowed=True, remaining_usd=49.9)
            )
            mock_budget.release = AsyncMock()
            mock_budget.get_budget = AsyncMock(return_value=MagicMock(budget_usd=None))
            mock_credit.deduct = AsyncMock(
                return_value=MagicMock(allowed=True, remaining_cents=4880, billing_unavailable=False)
            )
            mock_credit.release = AsyncMock()

            mock_fetch.side_effect = _make_execute_mock_fetch()

            mock_cred = MagicMock()
            mock_cred.get_credential.return_value = "re_test_key"
            mock_cred_store.return_value = mock_cred

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"id": "msg_123"}
            mock_resp.text = "ok"

            mock_client = AsyncMock()
            mock_client.request.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockHttpxClient.return_value = mock_client

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/v1/capabilities/email.send/execute",
                    json={
                        "provider": "resend",
                        "method": "POST",
                        "path": "/emails",
                        "body": {"to": "test@example.com"},
                    },
                    headers={"X-Rhumb-Key": "rk_test"},
                )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["org_credits_remaining_cents"] == 4880
        mock_credit.deduct.assert_awaited_once()


# ---------------------------------------------------------------------------
# 3. Insufficient credits: execution returns 402
# ---------------------------------------------------------------------------


class TestInsufficientCredits:
    """Execution is blocked when org has insufficient credits."""

    @pytest.mark.anyio
    async def test_returns_402_when_credits_insufficient(self) -> None:
        app = create_app()
        mock_store = MagicMock()
        mock_store.verify_api_key_with_agent = AsyncMock(return_value=_mock_agent())

        with (
            patch("routes.capability_execute._get_identity_store", return_value=mock_store),
            patch("routes.capability_execute._budget_enforcer") as mock_budget,
            patch("routes.capability_execute._credit_deduction") as mock_credit,
            patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock) as mock_fetch,
        ):
            mock_budget.check_and_decrement = AsyncMock(
                return_value=BudgetCheckResult(allowed=True, remaining_usd=49.9)
            )
            mock_budget.release = AsyncMock()

            mock_credit.deduct = AsyncMock(
                return_value=MagicMock(
                    allowed=False,
                    remaining_cents=5,
                    reason="insufficient_credits",
                    billing_unavailable=False,
                )
            )

            mock_fetch.side_effect = _make_execute_mock_fetch()

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/v1/capabilities/email.send/execute",
                    json={
                        "provider": "resend",
                        "method": "POST",
                        "path": "/emails",
                        "body": {"to": "test@example.com"},
                    },
                    headers={"X-Rhumb-Key": "rk_test"},
                )

        assert resp.status_code == 402
        body = resp.json()
        # x402 response format: error field contains the detail message
        assert body.get("x402Version") == 1
        error_msg = body["error"].lower()
        assert "insufficient" in error_msg or "credit" in error_msg


# ---------------------------------------------------------------------------
# 4. Idempotency: duplicate webhook doesn't double-credit
# ---------------------------------------------------------------------------


class TestWebhookIdempotency:
    """Duplicate checkout webhooks must not double-credit."""

    @pytest.mark.anyio
    async def test_duplicate_webhook_skipped(self) -> None:
        session = {
            "id": "cs_test_dupe_phase0",
            "payment_intent": "pi_test_dupe",
            "metadata": {"org_id": ORG_ID, "amount_cents": "2500"},
        }

        with patch("services.stripe_billing._sb_get", new_callable=AsyncMock) as mock_get:
            # Idempotency check: entry already exists
            mock_get.return_value = [{"id": "existing-ledger-entry"}]

            from services.stripe_billing import handle_checkout_completed
            first = await handle_checkout_completed(session)

        assert first is False  # skipped, no credit applied

    @pytest.mark.anyio
    async def test_first_webhook_applies_second_skips(self) -> None:
        """First call applies credits, second call with same session_id is a no-op."""
        session = {
            "id": "cs_test_idempotent",
            "payment_intent": "pi_test_idemp",
            "metadata": {"org_id": ORG_ID, "amount_cents": "3000"},
        }

        # First call: no existing entry → credits applied
        with (
            patch("services.stripe_billing._sb_get", new_callable=AsyncMock) as mock_get,
            patch("services.stripe_billing._sb_post", new_callable=AsyncMock) as mock_post,
            patch("services.stripe_billing._sb_patch", new_callable=AsyncMock) as mock_patch,
        ):
            mock_get.side_effect = [[], [{"balance_usd_cents": 2000}]]
            mock_patch.return_value = True
            mock_post.return_value = [{}]

            from services.stripe_billing import handle_checkout_completed
            first = await handle_checkout_completed(session)

        assert first is True

        # Second call: existing entry found → skipped
        with patch("services.stripe_billing._sb_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = [{"id": "existing-ledger-uuid"}]

            second = await handle_checkout_completed(session)

        assert second is False


# ---------------------------------------------------------------------------
# 5. Auto-reload trigger: deduction below threshold triggers reload
# ---------------------------------------------------------------------------


class TestAutoReloadTrigger:
    """Auto-reload fires when balance drops below configured threshold."""

    @pytest.mark.anyio
    async def test_triggers_payment_intent_below_threshold(self) -> None:
        """When balance < threshold and config is active, PaymentIntent is created."""
        from services.auto_reload import check_and_trigger_auto_reload

        with (
            patch("services.auto_reload.supabase_fetch", new_callable=AsyncMock) as mock_fetch,
            patch("services.auto_reload.create_payment_intent", new_callable=AsyncMock) as mock_pi,
        ):
            # Config fetch: auto-reload enabled, threshold 1000, amount 5000
            mock_fetch.side_effect = [
                [{
                    "auto_reload_enabled": True,
                    "auto_reload_threshold_cents": 1000,
                    "auto_reload_amount_cents": 5000,
                    "stripe_payment_method_id": "pm_test_123",
                }],
                # Recent reload check: empty (no recent reload)
                [],
            ]
            mock_pi.return_value = {"id": "pi_auto_reload_1", "status": "succeeded"}

            result = await check_and_trigger_auto_reload(ORG_ID, current_balance_cents=500)

        assert result is not None
        assert result["status"] == "triggered"
        assert result["amount_cents"] == 5000
        assert result["payment_intent_id"] == "pi_auto_reload_1"
        mock_pi.assert_awaited_once_with(
            org_id=ORG_ID,
            amount_cents=5000,
            payment_method_id="pm_test_123",
        )

    @pytest.mark.anyio
    async def test_no_trigger_when_above_threshold(self) -> None:
        """Auto-reload does not fire when balance >= threshold."""
        from services.auto_reload import check_and_trigger_auto_reload

        with patch("services.auto_reload.supabase_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = [{
                "auto_reload_enabled": True,
                "auto_reload_threshold_cents": 1000,
                "auto_reload_amount_cents": 5000,
                "stripe_payment_method_id": "pm_test_123",
            }]

            result = await check_and_trigger_auto_reload(ORG_ID, current_balance_cents=1500)

        assert result is None

    @pytest.mark.anyio
    async def test_no_trigger_when_disabled(self) -> None:
        """Auto-reload does not fire when disabled."""
        from services.auto_reload import check_and_trigger_auto_reload

        with patch("services.auto_reload.supabase_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = [{
                "auto_reload_enabled": False,
                "auto_reload_threshold_cents": 1000,
                "auto_reload_amount_cents": 5000,
                "stripe_payment_method_id": "pm_test_123",
            }]

            result = await check_and_trigger_auto_reload(ORG_ID, current_balance_cents=500)

        assert result is None

    @pytest.mark.anyio
    async def test_skipped_when_no_payment_method(self) -> None:
        """Auto-reload is skipped when no payment method is configured."""
        from services.auto_reload import check_and_trigger_auto_reload

        with patch("services.auto_reload.supabase_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = [
                [{
                    "auto_reload_enabled": True,
                    "auto_reload_threshold_cents": 1000,
                    "auto_reload_amount_cents": 5000,
                    "stripe_payment_method_id": None,
                }],
                [],  # recent reload check
            ]

            result = await check_and_trigger_auto_reload(ORG_ID, current_balance_cents=500)

        assert result is not None
        assert result["status"] == "skipped"
        assert result["reason"] == "no_payment_method"

    @pytest.mark.anyio
    async def test_fails_open_on_exception(self) -> None:
        """Auto-reload returns None (never raises) on unexpected errors."""
        from services.auto_reload import check_and_trigger_auto_reload

        with patch("services.auto_reload.supabase_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = RuntimeError("boom")

            result = await check_and_trigger_auto_reload(ORG_ID, current_balance_cents=500)

        assert result is None

    @pytest.mark.anyio
    async def test_auto_reload_wired_into_execute(self) -> None:
        """Execute route calls check_and_trigger_auto_reload after deduction."""
        app = create_app()
        mock_store = MagicMock()
        mock_store.verify_api_key_with_agent = AsyncMock(return_value=_mock_agent())

        with (
            patch("routes.capability_execute._get_identity_store", return_value=mock_store),
            patch("routes.capability_execute._budget_enforcer") as mock_budget,
            patch("routes.capability_execute._credit_deduction") as mock_credit,
            patch("routes.capability_execute.check_and_trigger_auto_reload", new_callable=AsyncMock) as mock_reload,
            patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock) as mock_fetch,
            patch("routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True),
            patch(
                "routes.capability_execute._inject_auth_request_parts",
                side_effect=lambda slug, auth, headers, body, params: (headers, body, params),
            ),
            patch("routes.capability_execute.get_credential_store") as mock_cred_store,
            patch("routes.capability_execute.httpx.AsyncClient") as MockHttpxClient,
        ):
            mock_budget.check_and_decrement = AsyncMock(
                return_value=BudgetCheckResult(allowed=True, remaining_usd=49.9)
            )
            mock_budget.release = AsyncMock()
            mock_budget.get_budget = AsyncMock(return_value=MagicMock(budget_usd=None))
            mock_credit.deduct = AsyncMock(
                return_value=MagicMock(allowed=True, remaining_cents=800, billing_unavailable=False)
            )
            mock_credit.release = AsyncMock()
            mock_reload.return_value = {"status": "triggered", "amount_cents": 5000}

            mock_fetch.side_effect = _make_execute_mock_fetch()

            mock_cred = MagicMock()
            mock_cred.get_credential.return_value = "re_test_key"
            mock_cred_store.return_value = mock_cred

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"id": "msg_123"}
            mock_resp.text = "ok"

            mock_client = AsyncMock()
            mock_client.request.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockHttpxClient.return_value = mock_client

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/v1/capabilities/email.send/execute",
                    json={
                        "provider": "resend",
                        "method": "POST",
                        "path": "/emails",
                        "body": {"to": "test@example.com"},
                    },
                    headers={"X-Rhumb-Key": "rk_test"},
                )

        assert resp.status_code == 200
        # Auto-reload was called with the org_id and remaining balance
        mock_reload.assert_awaited_once_with(ORG_ID, 800)


# ---------------------------------------------------------------------------
# 6. Auto-reload guard: second deduction within 60s doesn't re-trigger
# ---------------------------------------------------------------------------


class TestAutoReloadGuard:
    """60-second guard prevents concurrent/duplicate reloads."""

    @pytest.mark.anyio
    async def test_skipped_when_recent_reload_exists(self) -> None:
        """Second trigger within 60s is suppressed."""
        from services.auto_reload import check_and_trigger_auto_reload

        with patch("services.auto_reload.supabase_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = [
                # Config fetch
                [{
                    "auto_reload_enabled": True,
                    "auto_reload_threshold_cents": 1000,
                    "auto_reload_amount_cents": 5000,
                    "stripe_payment_method_id": "pm_test_123",
                }],
                # Recent reload check: found a recent entry
                [{"id": "recent-reload-ledger-entry", "event_type": "auto_reload_triggered"}],
            ]

            result = await check_and_trigger_auto_reload(ORG_ID, current_balance_cents=500)

        assert result is not None
        assert result["status"] == "skipped"
        assert result["reason"] == "recent_reload"

    @pytest.mark.anyio
    async def test_allowed_after_60s_guard_expires(self) -> None:
        """Reload fires when no recent reload exists (guard window passed)."""
        from services.auto_reload import check_and_trigger_auto_reload

        with (
            patch("services.auto_reload.supabase_fetch", new_callable=AsyncMock) as mock_fetch,
            patch("services.auto_reload.create_payment_intent", new_callable=AsyncMock) as mock_pi,
        ):
            mock_fetch.side_effect = [
                [{
                    "auto_reload_enabled": True,
                    "auto_reload_threshold_cents": 1000,
                    "auto_reload_amount_cents": 5000,
                    "stripe_payment_method_id": "pm_test_456",
                }],
                # No recent reload found (guard window expired)
                [],
            ]
            mock_pi.return_value = {"id": "pi_after_guard", "status": "succeeded"}

            result = await check_and_trigger_auto_reload(ORG_ID, current_balance_cents=500)

        assert result is not None
        assert result["status"] == "triggered"
        mock_pi.assert_awaited_once()


# ---------------------------------------------------------------------------
# 7. Billing endpoints: balance/ledger/auto-reload return correct data
# ---------------------------------------------------------------------------


class TestBillingEndpointsIntegration:
    """Verify billing endpoints return coherent data after operations."""

    def test_balance_reflects_auto_reload_config(self) -> None:
        """GET /billing/balance includes auto-reload config when set."""
        client = TestClient(_shared_app, headers={"X-Rhumb-Key": _BYPASS_KEY})

        mock_row = {
            "balance_usd_cents": 6000,
            "reserved_usd_cents": 200,
            "auto_reload_enabled": True,
            "auto_reload_threshold_cents": 1000,
            "auto_reload_amount_cents": 5000,
        }

        with patch("routes.billing.supabase_fetch", new_callable=AsyncMock, return_value=[mock_row]):
            resp = client.get("/v1/billing/balance")

        assert resp.status_code == 200
        data = resp.json()
        assert data["balance_usd_cents"] == 6000
        assert data["balance_usd"] == pytest.approx(60.0)
        assert data["available_usd_cents"] == 5800
        assert data["auto_reload_enabled"] is True
        assert data["auto_reload_threshold_usd"] == pytest.approx(10.0)
        assert data["auto_reload_amount_usd"] == pytest.approx(50.0)

    def test_ledger_shows_credit_and_debit_entries(self) -> None:
        """GET /billing/ledger returns both credit_added and debit events."""
        client = TestClient(_shared_app, headers={"X-Rhumb-Key": _BYPASS_KEY})

        entries = [
            {
                "id": "led-1",
                "event_type": "credit_added",
                "amount_usd_cents": 5000,
                "balance_after_usd_cents": 5000,
                "capability_execution_id": None,
                "stripe_checkout_session_id": "cs_test_1",
                "description": "Credit purchase via Stripe Checkout ($50.00)",
                "created_at": "2026-03-17T01:00:00Z",
            },
            {
                "id": "led-2",
                "event_type": "debit",
                "amount_usd_cents": -12,
                "balance_after_usd_cents": 4988,
                "capability_execution_id": "exec_abc",
                "stripe_checkout_session_id": None,
                "description": "Capability execution",
                "created_at": "2026-03-17T02:00:00Z",
            },
        ]

        with (
            patch("routes.billing.supabase_fetch", new_callable=AsyncMock, return_value=entries),
            patch("routes.billing.supabase_count", new_callable=AsyncMock, return_value=2),
        ):
            resp = client.get("/v1/billing/ledger")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["events"]) == 2
        assert data["total"] == 2

        credit_event = data["events"][0]
        assert credit_event["event_type"] == "credit_added"
        assert credit_event["amount_usd"] == pytest.approx(50.0)

        debit_event = data["events"][1]
        assert debit_event["event_type"] == "debit"
        assert debit_event["amount_usd"] == pytest.approx(-0.12)

    def test_auto_reload_config_roundtrip(self) -> None:
        """PUT /billing/auto-reload saves config and returns it correctly."""
        client = TestClient(_shared_app, headers={"X-Rhumb-Key": _BYPASS_KEY})

        returned_row = {
            "auto_reload_enabled": True,
            "auto_reload_threshold_cents": 1000,
            "auto_reload_amount_cents": 5000,
        }

        with patch("routes.billing.supabase_patch", new_callable=AsyncMock, return_value=[returned_row]):
            resp = client.put(
                "/v1/billing/auto-reload",
                json={"enabled": True, "threshold_usd": 10.0, "amount_usd": 50.0},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["auto_reload_enabled"] is True
        assert data["auto_reload_threshold_usd"] == pytest.approx(10.0)
        assert data["auto_reload_amount_usd"] == pytest.approx(50.0)

    def test_disable_auto_reload_clears_thresholds(self) -> None:
        """Disabling auto-reload clears threshold/amount values."""
        client = TestClient(_shared_app, headers={"X-Rhumb-Key": _BYPASS_KEY})

        returned_row = {
            "auto_reload_enabled": False,
            "auto_reload_threshold_cents": None,
            "auto_reload_amount_cents": None,
        }

        with patch("routes.billing.supabase_patch", new_callable=AsyncMock, return_value=[returned_row]):
            resp = client.put(
                "/v1/billing/auto-reload",
                json={"enabled": False},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["auto_reload_enabled"] is False
        assert data["auto_reload_threshold_usd"] is None
        assert data["auto_reload_amount_usd"] is None


# ---------------------------------------------------------------------------
# 8. create_payment_intent service tests
# ---------------------------------------------------------------------------


class TestCreatePaymentIntent:
    """Tests for the create_payment_intent service function."""

    @pytest.mark.anyio
    async def test_creates_intent_with_correct_params(self) -> None:
        """create_payment_intent calls Stripe with off_session=True, confirm=True."""
        mock_intent = MagicMock()
        mock_intent.id = "pi_auto_reload_test"
        mock_intent.status = "succeeded"

        with (
            patch("services.stripe_billing._sb_get", new_callable=AsyncMock) as mock_get,
            patch("stripe.PaymentIntent.create", return_value=mock_intent) as mock_stripe,
        ):
            mock_get.return_value = [{"stripe_customer_id": "cus_test_auto"}]

            from services.stripe_billing import create_payment_intent
            result = await create_payment_intent(
                org_id=ORG_ID,
                amount_cents=5000,
                payment_method_id="pm_test_auto",
            )

        assert result["id"] == "pi_auto_reload_test"
        assert result["status"] == "succeeded"
        mock_stripe.assert_called_once_with(
            amount=5000,
            currency="usd",
            customer="cus_test_auto",
            payment_method="pm_test_auto",
            off_session=True,
            confirm=True,
            metadata={"org_id": ORG_ID, "amount_cents": "5000", "trigger": "auto_reload"},
        )

    @pytest.mark.anyio
    async def test_raises_when_no_customer(self) -> None:
        """create_payment_intent raises ValueError if no Stripe customer exists."""
        with patch("services.stripe_billing._sb_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = []

            from services.stripe_billing import create_payment_intent
            with pytest.raises(ValueError, match="No Stripe customer"):
                await create_payment_intent(
                    org_id="org_unknown",
                    amount_cents=5000,
                    payment_method_id="pm_test",
                )
