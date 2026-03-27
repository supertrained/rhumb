"""Integration tests for x402 payment flow in the execute route.

Tests the end-to-end flow of:
- X-Payment header with valid USDC payment → 200 + X-Payment-Response header
- X-Payment with invalid transaction → 402
- X-Payment with already-used transaction → 402 "already used"
- No X-Payment → normal credit flow (existing behavior unchanged)
- No X-Payment + no credits → 402 x402 response (existing behavior)
"""

from __future__ import annotations

import base64
import json
import logging
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app
from schemas.agent_identity import AgentIdentitySchema

FAKE_RHUMB_KEY = "rhumb_test_key_x402_flow"
WALLET = "0xEA63eF9B4FaC31DB058977065C8Fe12fdCa02623"
PAYER_WALLET = "0x1234567890abcdef1234567890abcdef12345678"
TX_HASH = "0xabc123def456abc123def456abc123def456abc123def456abc123def456abc1"


def _mock_agent() -> AgentIdentitySchema:
    return AgentIdentitySchema(
        agent_id="agent_x402_flow_test",
        name="x402-flow-test",
        organization_id="org_x402_flow_test",
    )


@pytest.fixture
def app():
    """Create test app with lifespan disabled."""
    return create_app()


@pytest.fixture(autouse=True)
def _mock_identity_store():
    """Bypass API key verification for x402 flow tests."""
    mock_store = MagicMock()
    mock_store.verify_api_key_with_agent = AsyncMock(return_value=_mock_agent())
    with patch("routes.capability_execute._get_identity_store", return_value=mock_store):
        yield mock_store


# ---------------------------------------------------------------------------
# Sample data (reuse from test_capability_execute.py patterns)
# ---------------------------------------------------------------------------

SAMPLE_CAP = [
    {"id": "email.send", "domain": "email", "action": "send",
     "description": "Send transactional email"},
]

SAMPLE_MAPPINGS = [
    {"service_slug": "sendgrid", "credential_modes": ["byo"],
     "auth_method": "api_key", "endpoint_pattern": "POST /v3/mail/send",
     "cost_per_call": "0.01", "cost_currency": "USD", "free_tier_calls": 100},
]

SAMPLE_SCORES = [
    {"service_slug": "sendgrid", "aggregate_recommendation_score": 6.35},
]


def _mock_supabase_factory(
    existing_receipt: list | None = None,
    org_credits: list | None = None,
):
    """Build a supabase_fetch side_effect with configurable usdc_receipts and org_credits."""
    def _mock_supabase(path: str):
        if path.startswith("capabilities?"):
            return SAMPLE_CAP
        if path.startswith("capability_services?"):
            return SAMPLE_MAPPINGS
        if path.startswith("scores?"):
            return SAMPLE_SCORES
        if path.startswith("services?"):
            return [{"slug": "sendgrid", "api_domain": "api.sendgrid.com"}]
        if path.startswith("capability_executions?"):
            return []
        if path.startswith("usdc_receipts?"):
            return existing_receipt if existing_receipt is not None else []
        if path.startswith("org_credits?"):
            return org_credits if org_credits is not None else []
        return []
    return _mock_supabase


def _mock_supabase_default(path: str):
    """Default supabase mock — no existing receipts."""
    return _mock_supabase_factory()(path)


def _make_mock_response(status_code: int = 202, json_body: dict | None = None):
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_body or {"message": "accepted"}
    resp.text = '{"message": "accepted"}'
    return resp


def _make_budget_allowed():
    from services.budget_enforcer import BudgetCheckResult
    return BudgetCheckResult(allowed=True, remaining_usd=10.0)


def _make_budget_denied():
    from services.budget_enforcer import BudgetCheckResult
    return BudgetCheckResult(
        allowed=False, remaining_usd=0,
        reason="Budget exceeded",
    )


def _make_credit_allowed():
    from services.credit_deduction import CreditDeductionResult
    return CreditDeductionResult(allowed=True, remaining_cents=10000)


def _make_credit_denied():
    from services.credit_deduction import CreditDeductionResult
    return CreditDeductionResult(
        allowed=False, remaining_cents=0,
        reason="Insufficient org credits",
    )


def _verification_success() -> dict:
    return {
        "valid": True,
        "from_address": PAYER_WALLET,
        "to_address": WALLET,
        "amount_atomic": "100000",
        "block_number": 420,
        "tx_hash": TX_HASH,
    }


def _verification_failed(error: str = "Transaction reverted") -> dict:
    return {"valid": False, "error": error}


def _x_payment_header(
    tx_hash: str = TX_HASH,
    network: str = "base-sepolia",
    wallet_address: str = PAYER_WALLET,
) -> str:
    """Build a raw JSON X-Payment header value."""
    return json.dumps(
        {"tx_hash": tx_hash, "network": network, "wallet_address": wallet_address}
    )


def _x_payment_header_b64(
    tx_hash: str = TX_HASH,
    network: str = "base-sepolia",
    wallet_address: str = PAYER_WALLET,
) -> str:
    """Build a base64-encoded X-Payment header value."""
    payload = json.dumps(
        {"tx_hash": tx_hash, "network": network, "wallet_address": wallet_address}
    )
    return base64.b64encode(payload.encode()).decode()


def _x_payment_header_standard() -> str:
    """Build a standard x402 PaymentPayloadV1-style header value."""
    return json.dumps(
        {
            "x402Version": 1,
            "scheme": "exact",
            "network": "base-sepolia",
            "payload": {
                "authorization": {
                    "from": PAYER_WALLET,
                    "to": WALLET,
                    "value": "100000",
                    "validAfter": "1",
                    "validBefore": "2",
                    "nonce": "0xdeadbeef",
                },
                "signature": "0xsigned",
            },
        }
    )


def _x_payment_header_standard_b64(network: str = "base") -> str:
    """Build a base64-encoded Awal-style x402 authorization payload."""
    payload = json.dumps(
        {
            "x402Version": 1,
            "scheme": "exact",
            "network": network,
            "payload": {
                "authorization": {
                    "from": PAYER_WALLET,
                    "to": WALLET,
                    "value": "100000",
                    "validAfter": "1",
                    "validBefore": "2",
                    "nonce": "0xdeadbeef",
                },
                "signature": "0xsigned",
            },
        }
    )
    return base64.b64encode(payload.encode()).decode()


# ---------------------------------------------------------------------------
# Common patches
# ---------------------------------------------------------------------------

def _build_common_patches(
    verification_result=None,
    existing_receipt=None,
    org_credits=None,
    budget_result=None,
    credit_result=None,
):
    """Return a dict of common patches for the x402 flow tests."""
    mock_pool = MagicMock()
    mock_client = AsyncMock()
    mock_client.request.return_value = _make_mock_response()
    mock_pool.acquire = AsyncMock(return_value=mock_client)
    mock_pool.release = AsyncMock()

    mock_enforcer = MagicMock()
    mock_enforcer.check_and_decrement = AsyncMock(
        return_value=budget_result or _make_budget_allowed()
    )
    mock_enforcer.release = AsyncMock()

    mock_credit = MagicMock()
    mock_credit.deduct = AsyncMock(
        return_value=credit_result or _make_credit_allowed()
    )
    mock_credit.release = AsyncMock()

    patches = {
        "supabase_fetch": patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase_factory(existing_receipt, org_credits),
        ),
        "supabase_insert": patch(
            "routes.capability_execute.supabase_insert",
            new_callable=AsyncMock,
            return_value=True,
        ),
        "supabase_patch": patch(
            "routes.capability_execute.supabase_patch",
            new_callable=AsyncMock,
            return_value=[],
        ),
        "inject_auth": patch(
            "routes.capability_execute._inject_auth_headers",
            side_effect=lambda slug, auth, h: h,
        ),
        "pool": patch(
            "routes.capability_execute.get_pool_manager",
            return_value=mock_pool,
        ),
        "budget": patch(
            "routes.capability_execute._budget_enforcer",
            mock_enforcer,
        ),
        "credit": patch(
            "routes.capability_execute._credit_deduction",
            mock_credit,
        ),
    }

    if verification_result is not None:
        patches["verify"] = patch(
            "routes.capability_execute.verify_usdc_payment",
            new_callable=AsyncMock,
            return_value=verification_result,
        )

    return patches


# ---------------------------------------------------------------------------
# Tests: valid x402 payment
# ---------------------------------------------------------------------------


class TestX402ValidPayment:
    """Execute with X-Payment header containing valid USDC payment."""

    @pytest.mark.anyio
    async def test_x402_payment_returns_200_with_receipt(self, app):
        """Valid X-Payment → 200 + X-Payment-Response header + x402_receipt in body."""
        patches = _build_common_patches(
            verification_result=_verification_success(),
            org_credits=[{"balance_usd_cents": 500}],
        )

        with patch.dict(os.environ, {"RHUMB_USDC_WALLET_ADDRESS": WALLET}):
            ctx_managers = [p for p in patches.values()]
            with ctx_managers[0], ctx_managers[1], ctx_managers[2], \
                 ctx_managers[3], ctx_managers[4], ctx_managers[5], \
                 ctx_managers[6], ctx_managers[7]:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.post(
                        "/v1/capabilities/email.send/execute",
                        json={
                            "provider": "sendgrid",
                            "method": "POST",
                            "path": "/v3/mail/send",
                            "body": {"to": "test@example.com"},
                        },
                        headers={
                            "X-Rhumb-Key": FAKE_RHUMB_KEY,
                            "X-Payment": _x_payment_header(),
                        },
                    )

        assert resp.status_code == 200
        # X-Payment-Response header present
        payment_resp = resp.headers.get("x-payment-response")
        assert payment_resp is not None
        payment_resp_data = json.loads(payment_resp)
        assert payment_resp_data["verified"] is True
        assert payment_resp_data["tx_hash"] == TX_HASH
        # Body includes x402_receipt
        data = resp.json()["data"]
        assert data["x402_receipt"]["verified"] is True
        assert data["x402_receipt"]["tx_hash"] == TX_HASH

    @pytest.mark.anyio
    async def test_x402_payment_base64_encoded(self, app):
        """X-Payment with base64-encoded JSON also works."""
        patches = _build_common_patches(
            verification_result=_verification_success(),
            org_credits=[{"balance_usd_cents": 500}],
        )

        with patch.dict(os.environ, {"RHUMB_USDC_WALLET_ADDRESS": WALLET}):
            ctx_managers = [p for p in patches.values()]
            with ctx_managers[0], ctx_managers[1], ctx_managers[2], \
                 ctx_managers[3], ctx_managers[4], ctx_managers[5], \
                 ctx_managers[6], ctx_managers[7]:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.post(
                        "/v1/capabilities/email.send/execute",
                        json={
                            "provider": "sendgrid",
                            "method": "POST",
                            "path": "/v3/mail/send",
                            "body": {"to": "test@example.com"},
                        },
                        headers={
                            "X-Rhumb-Key": FAKE_RHUMB_KEY,
                            "X-Payment": _x_payment_header_b64(),
                        },
                    )

        assert resp.status_code == 200
        assert resp.headers.get("x-payment-response") is not None

    @pytest.mark.anyio
    async def test_standard_x402_payload_returns_structured_compatibility_error(self, app, caplog):
        """Standard x402 authorization payloads should fail with a precise compatibility error."""
        with patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase_default,
        ):
            with caplog.at_level(logging.INFO, logger="routes.capability_execute"):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.post(
                        "/v1/capabilities/email.send/execute",
                        json={
                            "provider": "sendgrid",
                            "method": "POST",
                            "path": "/v3/mail/send",
                            "body": {"to": "test@example.com"},
                        },
                        headers={"X-Payment": _x_payment_header_standard_b64()},
                    )

        assert resp.status_code == 422
        body = resp.json()
        assert body["error"] == "x402_proof_format_unsupported"
        assert body["compatibility"]["detected_format"] == "standard_authorization_payload"
        assert body["compatibility"]["supported_formats"] == ["legacy_tx_hash"]
        assert body["compatibility"]["network"] == "base"
        assert body["compatibility"]["payer"] == PAYER_WALLET
        assert body["compatibility"]["pay_to"] == WALLET
        assert "tx_hash" in body["message"]
        assert "Base mainnet" in body["resolution"]

        traces = [
            getattr(record, "x402_interop", None)
            for record in caplog.records
            if getattr(record, "x402_interop", None)
        ]
        assert traces, "expected x402 interop trace log"
        trace = traces[-1]
        assert trace["x_payment_parse_mode"] == "x402_payload"
        assert trace["x_payment_proof_format"] == "standard_authorization_payload"
        assert trace["branch_outcome"] == "standard_authorization_unsupported"
        assert trace["response_status"] == 422
        assert trace["payment_headers_set"] is False

    @pytest.mark.anyio
    async def test_execute_get_payment_signature_returns_structured_compatibility_error(self, app):
        """GET discovery should also surface unsupported standard proofs instead of a 402 loop."""
        with patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase_default,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/v1/capabilities/email.send/execute",
                    headers={"PAYMENT-SIGNATURE": _x_payment_header_standard_b64()},
                )

        assert resp.status_code == 422
        body = resp.json()
        assert body["error"] == "x402_proof_format_unsupported"
        assert body["compatibility"]["detected_format"] == "standard_authorization_payload"
        assert body["compatibility"]["network"] == "base"

    @pytest.mark.anyio
    async def test_x402_payment_bypasses_billing_health_gate(self, app):
        """Verified x402 payment proceeds even when Supabase billing health is down."""
        patches = _build_common_patches(
            verification_result=_verification_success(),
            org_credits=[{"balance_usd_cents": 500}],
        )

        with patch.dict(os.environ, {"RHUMB_USDC_WALLET_ADDRESS": WALLET}):
            ctx_managers = [p for p in patches.values()]
            with (
                patch(
                    "routes.capability_execute.check_billing_health",
                    new_callable=AsyncMock,
                    return_value=(False, "connection_error"),
                ),
                ctx_managers[0],
                ctx_managers[1],
                ctx_managers[2],
                ctx_managers[3],
                ctx_managers[4],
                ctx_managers[5],
                ctx_managers[6],
                ctx_managers[7],
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.post(
                        "/v1/capabilities/email.send/execute",
                        json={
                            "provider": "sendgrid",
                            "method": "POST",
                            "path": "/v3/mail/send",
                            "body": {"to": "test@example.com"},
                        },
                        headers={
                            "X-Rhumb-Key": FAKE_RHUMB_KEY,
                            "X-Payment": _x_payment_header(),
                        },
                    )

        assert resp.status_code == 200
        assert resp.json()["data"]["x402_receipt"]["verified"] is True


# ---------------------------------------------------------------------------
# Tests: invalid x402 payment
# ---------------------------------------------------------------------------


class TestX402InvalidPayment:
    """Execute with X-Payment containing invalid transaction."""

    @pytest.mark.anyio
    async def test_invalid_tx_returns_402(self, app):
        """Invalid on-chain verification → 402."""
        patches = _build_common_patches(
            verification_result=_verification_failed("Transaction reverted"),
        )

        with patch.dict(os.environ, {"RHUMB_USDC_WALLET_ADDRESS": WALLET}):
            ctx_managers = [p for p in patches.values()]
            with ctx_managers[0], ctx_managers[1], ctx_managers[2], \
                 ctx_managers[3], ctx_managers[4], ctx_managers[5], \
                 ctx_managers[6], ctx_managers[7]:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.post(
                        "/v1/capabilities/email.send/execute",
                        json={
                            "provider": "sendgrid",
                            "method": "POST",
                            "path": "/v3/mail/send",
                            "body": {},
                        },
                        headers={
                            "X-Rhumb-Key": FAKE_RHUMB_KEY,
                            "X-Payment": _x_payment_header(),
                        },
                    )

        assert resp.status_code == 402
        assert "verification failed" in resp.json()["detail"].lower()

    @pytest.mark.anyio
    async def test_amount_check_uses_actual_provider_cost_not_cheapest_estimate(self, app):
        """Explicit provider cost is used for x402 validation, not the cheapest mapping."""

        async def mock_verify(*args, **kwargs):
            if kwargs["expected_amount_atomic"] == "1200000":
                return {
                    "valid": False,
                    "error": "Underpayment detected: paid 100000 atomic, expected at least 1200000",
                }
            return _verification_success()

        expensive_mappings = [
            {
                "service_slug": "sendgrid",
                "credential_modes": ["byo"],
                "auth_method": "api_key",
                "endpoint_pattern": "POST /v3/mail/send",
                "cost_per_call": "0.01",
                "cost_currency": "USD",
                "free_tier_calls": 100,
            },
            {
                "service_slug": "resend",
                "credential_modes": ["byo"],
                "auth_method": "api_key",
                "endpoint_pattern": "POST /emails",
                "cost_per_call": "1.00",
                "cost_currency": "USD",
                "free_tier_calls": 0,
            },
        ]

        def mock_supabase(path: str):
            if path.startswith("capabilities?"):
                return SAMPLE_CAP
            if path.startswith("capability_services?"):
                return expensive_mappings
            if path.startswith("scores?"):
                return [
                    {"service_slug": "sendgrid", "aggregate_recommendation_score": 6.35},
                    {"service_slug": "resend", "aggregate_recommendation_score": 7.10},
                ]
            if path.startswith("services?"):
                return [{"slug": "resend", "api_domain": "api.resend.com"}]
            if path.startswith("capability_executions?"):
                return []
            if path.startswith("usdc_receipts?"):
                return []
            if path.startswith("org_credits?"):
                return []
            return []

        patches = _build_common_patches()
        patches["supabase_fetch"] = patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=mock_supabase,
        )
        patches["verify"] = patch(
            "routes.capability_execute.verify_usdc_payment",
            new_callable=AsyncMock,
            side_effect=mock_verify,
        )

        with patch.dict(os.environ, {"RHUMB_USDC_WALLET_ADDRESS": WALLET}):
            ctx_managers = [p for p in patches.values()]
            with ctx_managers[0], ctx_managers[1], ctx_managers[2], \
                 ctx_managers[3], ctx_managers[4], ctx_managers[5], \
                 ctx_managers[6], ctx_managers[7]:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.post(
                        "/v1/capabilities/email.send/execute",
                        json={
                            "provider": "resend",
                            "method": "POST",
                            "path": "/emails",
                            "body": {},
                        },
                        headers={
                            "X-Rhumb-Key": FAKE_RHUMB_KEY,
                            "X-Payment": _x_payment_header(),
                        },
                    )

        assert resp.status_code == 402
        assert "underpayment" in resp.json()["detail"].lower()

    @pytest.mark.anyio
    async def test_wallet_not_configured_returns_402(self, app):
        """Missing RHUMB_USDC_WALLET_ADDRESS → 402."""
        patches = _build_common_patches()

        with patch.dict(os.environ, {"RHUMB_USDC_WALLET_ADDRESS": ""}):
            ctx_managers = [p for p in patches.values()]
            with ctx_managers[0], ctx_managers[1], ctx_managers[2], \
                 ctx_managers[3], ctx_managers[4], ctx_managers[5], \
                 ctx_managers[6]:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.post(
                        "/v1/capabilities/email.send/execute",
                        json={
                            "provider": "sendgrid",
                            "method": "POST",
                            "path": "/v3/mail/send",
                            "body": {},
                        },
                        headers={
                            "X-Rhumb-Key": FAKE_RHUMB_KEY,
                            "X-Payment": _x_payment_header(),
                        },
                    )

        assert resp.status_code == 402
        assert "wallet not configured" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Tests: replay protection
# ---------------------------------------------------------------------------


class TestX402ReplayProtection:
    """Execute with X-Payment containing already-used tx_hash."""

    @pytest.mark.anyio
    async def test_already_used_tx_returns_402(self, app):
        """Previously used tx_hash → 402 'already used'."""
        patches = _build_common_patches(
            existing_receipt=[{"id": "receipt-1"}],
        )

        with patch.dict(os.environ, {"RHUMB_USDC_WALLET_ADDRESS": WALLET}):
            ctx_managers = [p for p in patches.values()]
            with ctx_managers[0], ctx_managers[1], ctx_managers[2], \
                 ctx_managers[3], ctx_managers[4], ctx_managers[5], \
                 ctx_managers[6]:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.post(
                        "/v1/capabilities/email.send/execute",
                        json={
                            "provider": "sendgrid",
                            "method": "POST",
                            "path": "/v3/mail/send",
                            "body": {},
                        },
                        headers={
                            "X-Rhumb-Key": FAKE_RHUMB_KEY,
                            "X-Payment": _x_payment_header(),
                        },
                    )

        assert resp.status_code == 402
        assert "already used" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Tests: existing flow unchanged
# ---------------------------------------------------------------------------


class TestExistingFlowUnchanged:
    """Verify that requests WITHOUT X-Payment still work normally."""

    @pytest.mark.anyio
    async def test_no_x_payment_normal_flow(self, app):
        """No X-Payment header → normal credit flow → 200."""
        patches = _build_common_patches()

        ctx_managers = [p for p in patches.values()]
        with ctx_managers[0], ctx_managers[1], ctx_managers[2], \
             ctx_managers[3], ctx_managers[4], ctx_managers[5], \
             ctx_managers[6]:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/v1/capabilities/email.send/execute",
                    json={
                        "provider": "sendgrid",
                        "method": "POST",
                        "path": "/v3/mail/send",
                        "body": {"to": "test@example.com"},
                    },
                    headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
                )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["provider_used"] == "sendgrid"
        # No x402_receipt in response
        assert "x402_receipt" not in data
        # No X-Payment-Response header
        assert resp.headers.get("x-payment-response") is None

    @pytest.mark.anyio
    async def test_no_x_payment_no_credits_returns_402(self, app):
        """No X-Payment + no credits → 402 with x402 format."""
        patches = _build_common_patches(budget_result=_make_budget_denied())

        ctx_managers = [p for p in patches.values()]
        with ctx_managers[0], ctx_managers[1], ctx_managers[2], \
             ctx_managers[3], ctx_managers[4], ctx_managers[5], \
             ctx_managers[6]:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/v1/capabilities/email.send/execute",
                    json={
                        "provider": "sendgrid",
                        "method": "POST",
                        "path": "/v3/mail/send",
                        "body": {},
                    },
                    headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
                )

        assert resp.status_code == 402
        body = resp.json()
        assert body["x402Version"] == 1
        assert "accepts" in body


# ---------------------------------------------------------------------------
# Tests: x402 records are written
# ---------------------------------------------------------------------------


class TestX402Recording:
    """Verify that x402 payments are properly recorded."""

    @pytest.mark.anyio
    async def test_receipt_and_ledger_recorded(self, app):
        """Valid x402 payment records both usdc_receipts and credit_ledger."""
        insert_calls: list[dict] = []

        async def capture_insert(table: str, payload: dict) -> bool:
            insert_calls.append({"table": table, "payload": payload})
            return True

        patches = _build_common_patches(
            verification_result=_verification_success(),
            org_credits=[{"balance_usd_cents": 500}],
        )
        # Override supabase_insert to capture calls
        patches["supabase_insert"] = patch(
            "routes.capability_execute.supabase_insert",
            new_callable=AsyncMock,
            side_effect=capture_insert,
        )

        with patch.dict(os.environ, {"RHUMB_USDC_WALLET_ADDRESS": WALLET}):
            ctx_managers = [p for p in patches.values()]
            with ctx_managers[0], ctx_managers[1], ctx_managers[2], \
                 ctx_managers[3], ctx_managers[4], ctx_managers[5], \
                 ctx_managers[6], ctx_managers[7]:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.post(
                        "/v1/capabilities/email.send/execute",
                        json={
                            "provider": "sendgrid",
                            "method": "POST",
                            "path": "/v3/mail/send",
                            "body": {},
                        },
                        headers={
                            "X-Rhumb-Key": FAKE_RHUMB_KEY,
                            "X-Payment": _x_payment_header(),
                        },
                    )

        assert resp.status_code == 200

        # Check that usdc_receipts was inserted
        receipt_inserts = [c for c in insert_calls if c["table"] == "usdc_receipts"]
        assert len(receipt_inserts) == 1
        receipt = receipt_inserts[0]["payload"]
        assert receipt["tx_hash"] == TX_HASH
        assert receipt["org_id"] == "org_x402_flow_test"
        assert receipt["status"] == "confirmed"

        # Check that credit_ledger was inserted
        ledger_inserts = [c for c in insert_calls if c["table"] == "credit_ledger"]
        assert len(ledger_inserts) == 1
        ledger = ledger_inserts[0]["payload"]
        assert ledger["org_id"] == "org_x402_flow_test"
        assert ledger["event_type"] == "x402_payment"

        # Check that capability_executions was inserted (the normal flow)
        exec_inserts = [c for c in insert_calls if c["table"] == "capability_executions"]
        assert len(exec_inserts) == 2
        assert exec_inserts[0]["payload"]["billing_status"] == "pending"
        assert exec_inserts[1]["payload"]["billing_status"] == "billed"
