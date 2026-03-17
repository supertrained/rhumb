"""Tests for x402 protocol compliance — services/x402.py and execute route integration."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app
from schemas.agent_identity import AgentIdentitySchema
from services.x402 import (
    USDC_BASE_MAINNET,
    USDC_BASE_SEPOLIA,
    PaymentRequiredException,
    build_x402_response,
)


# ---------------------------------------------------------------------------
# Unit tests: build_x402_response
# ---------------------------------------------------------------------------


class TestBuildX402Response:
    """Unit tests for the x402 response builder."""

    def test_basic_structure(self):
        """Response includes x402Version, accepts, error, and balance fields."""
        resp = build_x402_response(
            capability_id="email.send",
            cost_usd_cents=15,
            resource_url="https://api.rhumb.dev/v1/capabilities/email.send/execute",
        )
        assert resp["x402Version"] == 1
        assert isinstance(resp["accepts"], list)
        assert len(resp["accepts"]) >= 1
        assert "error" in resp
        assert resp["balanceRequired"] == 15
        assert resp["balanceRequiredUsd"] == 0.15

    def test_stripe_option_always_present(self):
        """Stripe checkout option is always included regardless of env vars."""
        # Ensure no wallet address is set
        with patch.dict(os.environ, {"RHUMB_USDC_WALLET_ADDRESS": ""}, clear=False):
            resp = build_x402_response(
                capability_id="email.send",
                cost_usd_cents=50,
                resource_url="https://api.rhumb.dev/v1/capabilities/email.send/execute",
            )
        stripe_opts = [a for a in resp["accepts"] if a["scheme"] == "stripe_checkout"]
        assert len(stripe_opts) == 1
        assert "checkoutUrl" in stripe_opts[0]
        assert "email.send" in stripe_opts[0]["description"]

    def test_stripe_min_amount(self):
        """Stripe checkout minAmountUsd is at least $5.00."""
        resp = build_x402_response(
            capability_id="email.send",
            cost_usd_cents=1,  # $0.01
            resource_url="https://api.rhumb.dev/v1/capabilities/email.send/execute",
        )
        stripe_opt = next(a for a in resp["accepts"] if a["scheme"] == "stripe_checkout")
        assert stripe_opt["minAmountUsd"] >= 5.0

    def test_usdc_absent_without_wallet(self):
        """USDC option is NOT included when RHUMB_USDC_WALLET_ADDRESS is empty."""
        with patch.dict(os.environ, {"RHUMB_USDC_WALLET_ADDRESS": ""}, clear=False):
            resp = build_x402_response(
                capability_id="email.send",
                cost_usd_cents=15,
                resource_url="https://api.rhumb.dev/v1/capabilities/email.send/execute",
            )
        usdc_opts = [a for a in resp["accepts"] if a["scheme"] == "exact"]
        assert len(usdc_opts) == 0

    def test_usdc_present_with_wallet(self):
        """USDC option is included when wallet address is configured."""
        with patch.dict(
            os.environ,
            {"RHUMB_USDC_WALLET_ADDRESS": "0xAbC123", "RAILWAY_ENVIRONMENT": ""},
            clear=False,
        ):
            resp = build_x402_response(
                capability_id="email.send",
                cost_usd_cents=15,
                resource_url="https://api.rhumb.dev/v1/capabilities/email.send/execute",
            )
        usdc_opts = [a for a in resp["accepts"] if a["scheme"] == "exact"]
        assert len(usdc_opts) == 1
        assert usdc_opts[0]["payTo"] == "0xAbC123"

    def test_usdc_amount_conversion(self):
        """USDC atomic units = cents × 10000 (6 decimal places)."""
        with patch.dict(
            os.environ,
            {"RHUMB_USDC_WALLET_ADDRESS": "0xAbC123", "RAILWAY_ENVIRONMENT": ""},
            clear=False,
        ):
            resp = build_x402_response(
                capability_id="email.send",
                cost_usd_cents=15,  # $0.15
                resource_url="https://api.rhumb.dev/v1/capabilities/email.send/execute",
            )
        usdc_opt = next(a for a in resp["accepts"] if a["scheme"] == "exact")
        # 15 cents × 10000 = 150000
        assert usdc_opt["maxAmountRequired"] == "150000"

    def test_network_testnet_by_default(self):
        """Non-production env uses base-sepolia and testnet USDC contract."""
        with patch.dict(
            os.environ,
            {"RHUMB_USDC_WALLET_ADDRESS": "0xAbC123", "RAILWAY_ENVIRONMENT": ""},
            clear=False,
        ):
            resp = build_x402_response(
                capability_id="email.send",
                cost_usd_cents=15,
                resource_url="https://api.rhumb.dev/v1/capabilities/email.send/execute",
            )
        usdc_opt = next(a for a in resp["accepts"] if a["scheme"] == "exact")
        assert usdc_opt["network"] == "base-sepolia"
        assert usdc_opt["asset"] == USDC_BASE_SEPOLIA

    def test_network_production(self):
        """Production env uses base-mainnet and mainnet USDC contract."""
        with patch.dict(
            os.environ,
            {
                "RHUMB_USDC_WALLET_ADDRESS": "0xAbC123",
                "RAILWAY_ENVIRONMENT": "production",
            },
            clear=False,
        ):
            resp = build_x402_response(
                capability_id="email.send",
                cost_usd_cents=15,
                resource_url="https://api.rhumb.dev/v1/capabilities/email.send/execute",
            )
        usdc_opt = next(a for a in resp["accepts"] if a["scheme"] == "exact")
        assert usdc_opt["network"] == "base-mainnet"
        assert usdc_opt["asset"] == USDC_BASE_MAINNET

    def test_custom_error_message(self):
        """Custom error message flows through to the response."""
        resp = build_x402_response(
            capability_id="email.send",
            cost_usd_cents=15,
            resource_url="https://api.rhumb.dev/v1/capabilities/email.send/execute",
            error="Budget exceeded. Estimated cost: $0.15.",
        )
        assert resp["error"] == "Budget exceeded. Estimated cost: $0.15."

    def test_backward_compat_fields(self):
        """Response includes balanceRequired and balanceRequiredUsd for backward compat."""
        resp = build_x402_response(
            capability_id="email.send",
            cost_usd_cents=250,
            resource_url="https://api.rhumb.dev/v1/capabilities/email.send/execute",
        )
        assert resp["balanceRequired"] == 250
        assert resp["balanceRequiredUsd"] == 2.5


# ---------------------------------------------------------------------------
# Integration tests: execute route 402 responses
# ---------------------------------------------------------------------------

FAKE_RHUMB_KEY = "rhumb_test_key_x402"


def _mock_agent() -> AgentIdentitySchema:
    return AgentIdentitySchema(
        agent_id="agent_x402_test",
        name="x402-test",
        organization_id="org_x402_test",
    )


SAMPLE_CAP = [
    {
        "id": "email.send",
        "domain": "email",
        "action": "send",
        "description": "Send transactional email",
    },
]

SAMPLE_MAPPINGS = [
    {
        "service_slug": "sendgrid",
        "credential_modes": ["byo"],
        "auth_method": "api_key",
        "endpoint_pattern": "POST /v3/mail/send",
        "cost_per_call": "0.01",
        "cost_currency": "USD",
        "free_tier_calls": 100,
    },
]


def _mock_supabase(path: str):
    """Route supabase_fetch calls to sample data."""
    if path.startswith("capabilities?"):
        return SAMPLE_CAP
    if path.startswith("capability_services?"):
        return SAMPLE_MAPPINGS
    if path.startswith("scores?"):
        return [{"service_slug": "sendgrid", "aggregate_recommendation_score": 6.35}]
    if path.startswith("services?"):
        return [{"slug": "sendgrid", "api_domain": "api.sendgrid.com"}]
    if path.startswith("capability_executions?"):
        return []
    return []


@pytest.fixture
def app():
    """Create test app with lifespan disabled."""
    return create_app()


@pytest.fixture(autouse=True)
def _mock_identity_store():
    """Bypass API key verification for x402 route tests."""
    mock_store = MagicMock()
    mock_store.verify_api_key_with_agent = AsyncMock(return_value=_mock_agent())
    with patch("routes.capability_execute._get_identity_store", return_value=mock_store):
        yield mock_store


def _make_budget_denied():
    """Return a BudgetCheckResult that denies execution."""
    from services.budget_enforcer import BudgetCheckResult

    return BudgetCheckResult(
        allowed=False,
        remaining_usd=0,
        reason="Budget exceeded. Estimated cost: $0.01. Agent budget exhausted.",
    )


def _make_credit_denied():
    """Return a CreditDeductionResult that denies execution."""
    from services.credit_deduction import CreditDeductionResult

    return CreditDeductionResult(
        allowed=False,
        remaining_cents=0,
        reason="Insufficient org credits",
    )


def _make_budget_allowed():
    """Return a BudgetCheckResult that allows execution."""
    from services.budget_enforcer import BudgetCheckResult

    return BudgetCheckResult(allowed=True, remaining_usd=10.0)


@pytest.mark.anyio
async def test_budget_402_has_x_payment_header(app):
    """Budget exceeded 402 includes X-Payment: required header."""
    mock_enforcer = MagicMock()
    mock_enforcer.check_and_decrement = AsyncMock(return_value=_make_budget_denied())

    with (
        patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase),
        patch("routes.capability_execute._budget_enforcer", mock_enforcer),
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
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 402
    assert resp.headers.get("x-payment") == "required"


@pytest.mark.anyio
async def test_budget_402_has_x402_version(app):
    """Budget exceeded 402 body includes x402Version: 1."""
    mock_enforcer = MagicMock()
    mock_enforcer.check_and_decrement = AsyncMock(return_value=_make_budget_denied())

    with (
        patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase),
        patch("routes.capability_execute._budget_enforcer", mock_enforcer),
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
                    "body": {},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 402
    body = resp.json()
    assert body["x402Version"] == 1
    assert "accepts" in body
    assert len(body["accepts"]) >= 1


@pytest.mark.anyio
async def test_budget_402_includes_balance_fields(app):
    """Budget 402 includes balanceRequired and balanceRequiredUsd for backward compat."""
    mock_enforcer = MagicMock()
    mock_enforcer.check_and_decrement = AsyncMock(return_value=_make_budget_denied())

    with (
        patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase),
        patch("routes.capability_execute._budget_enforcer", mock_enforcer),
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
                    "body": {},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 402
    body = resp.json()
    assert "balanceRequired" in body
    assert "balanceRequiredUsd" in body


@pytest.mark.anyio
async def test_credit_402_has_x402_format(app):
    """Org credit insufficient 402 also returns x402-compliant response."""
    mock_enforcer = MagicMock()
    mock_enforcer.check_and_decrement = AsyncMock(return_value=_make_budget_allowed())
    mock_enforcer.release = AsyncMock(return_value=None)

    mock_credit = MagicMock()
    mock_credit.deduct = AsyncMock(return_value=_make_credit_denied())

    with (
        patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase),
        patch("routes.capability_execute._budget_enforcer", mock_enforcer),
        patch("routes.capability_execute._credit_deduction", mock_credit),
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
                    "body": {},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 402
    assert resp.headers.get("x-payment") == "required"
    body = resp.json()
    assert body["x402Version"] == 1
    assert body["error"] == "Insufficient org credits"
    assert "accepts" in body


@pytest.mark.anyio
async def test_402_stripe_option_always_present_in_route(app):
    """Execute route 402 always includes a stripe_checkout accept option."""
    mock_enforcer = MagicMock()
    mock_enforcer.check_and_decrement = AsyncMock(return_value=_make_budget_denied())

    with (
        patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase),
        patch("routes.capability_execute._budget_enforcer", mock_enforcer),
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
                    "body": {},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 402
    body = resp.json()
    stripe_opts = [a for a in body["accepts"] if a["scheme"] == "stripe_checkout"]
    assert len(stripe_opts) == 1
