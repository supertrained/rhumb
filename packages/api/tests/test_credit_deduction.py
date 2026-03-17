"""Tests for org credit deduction service + execute route integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app
from schemas.agent_identity import AgentIdentitySchema
from services.budget_enforcer import BudgetCheckResult
from services.credit_deduction import CreditDeductionService


def _mock_agent(agent_id: str = "agent_credit_test") -> AgentIdentitySchema:
    return AgentIdentitySchema(
        agent_id=agent_id,
        name="credit-test-agent",
        organization_id="org_credit_test",
    )


class TestCreditDeductionService:
    """Unit tests for services/credit_deduction.py."""

    @pytest.mark.asyncio
    async def test_successful_deduction_returns_remaining(self):
        svc = CreditDeductionService()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "allowed": True,
            "remaining_cents": 1234,
            "ledger_id": "ledger_abc",
        }

        with patch("services.credit_deduction.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await svc.deduct("org_1", 200, execution_id="exec_1")

        assert result.allowed is True
        assert result.remaining_cents == 1234
        assert result.ledger_id == "ledger_abc"

    @pytest.mark.asyncio
    async def test_insufficient_credits_returns_not_allowed(self):
        svc = CreditDeductionService()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "allowed": False,
            "reason": "insufficient_credits",
            "balance_cents": 99,
        }

        with patch("services.credit_deduction.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await svc.deduct("org_1", 200, execution_id="exec_1")

        assert result.allowed is False
        assert result.reason == "insufficient_credits"
        assert result.remaining_cents == 99

    @pytest.mark.asyncio
    async def test_fallback_to_budget_when_no_org_credits(self):
        mock_budget = MagicMock()
        mock_budget.check_and_decrement = AsyncMock(
            return_value=BudgetCheckResult(allowed=True, remaining_usd=9.9)
        )
        svc = CreditDeductionService(budget_enforcer=mock_budget)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "allowed": False,
            "reason": "no_org_credits",
            "balance_cents": 0,
        }

        with patch("services.credit_deduction.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await svc.deduct(
                "org_missing",
                120,
                execution_id="exec_1",
                agent_id="agent_1",
                fallback_cost_usd=0.1,
                skip_budget_fallback=False,
            )

        assert result.allowed is True
        assert result.used_budget_fallback is True
        mock_budget.check_and_decrement.assert_awaited_once_with("agent_1", 0.1)

    @pytest.mark.asyncio
    async def test_idempotent_release(self):
        svc = CreditDeductionService()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "released": True,
            "idempotent": True,
            "remaining_cents": 900,
            "ledger_id": None,
        }

        with patch("services.credit_deduction.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            first = await svc.release("org_1", 120, execution_id="exec_1")
            second = await svc.release("org_1", 120, execution_id="exec_1")

        assert first.released is True
        assert first.idempotent is True
        assert second.released is True
        assert second.idempotent is True

    @pytest.mark.asyncio
    async def test_fail_open_on_rpc_error(self):
        svc = CreditDeductionService()

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "rpc down"

        with patch("services.credit_deduction.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await svc.deduct("org_1", 200, execution_id="exec_1")

        assert result.allowed is True
        assert result.remaining_cents is None


@pytest.mark.anyio
async def test_execute_route_releases_budget_and_credits_on_upstream_failure():
    """Execution failure should release both reservations."""
    app = create_app()

    mock_store = MagicMock()
    mock_store.verify_api_key_with_agent = AsyncMock(return_value=_mock_agent())

    with (
        patch("routes.capability_execute._get_identity_store", return_value=mock_store),
        patch("routes.capability_execute._budget_enforcer") as mock_budget,
        patch("routes.capability_execute._credit_deduction") as mock_credit,
        patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock) as mock_fetch,
        patch("routes.capability_execute._inject_auth_headers", side_effect=lambda s, a, h: h),
        patch("routes.capability_execute.get_credential_store") as mock_cred_store,
        patch("routes.capability_execute.httpx.AsyncClient") as MockHttpxClient,
    ):
        mock_budget.check_and_decrement = AsyncMock(
            return_value=BudgetCheckResult(allowed=True, remaining_usd=49.9)
        )
        mock_budget.release = AsyncMock(return_value=50.0)

        mock_credit.deduct = AsyncMock(return_value=MagicMock(allowed=True, remaining_cents=880))
        mock_credit.release = AsyncMock(return_value=MagicMock(released=True, idempotent=False))

        mock_fetch.side_effect = [
            # cost estimate mappings
            [{"cost_per_call": 0.10, "service_slug": "resend", "auth_method": "api_key",
              "credential_modes": ["byo"], "endpoint_pattern": "POST /emails",
              "cost_currency": "USD", "free_tier_calls": 0}],
            # capability exists
            [{"id": "email.send", "domain": "email", "action": "send", "description": "Send email"}],
            # mappings for provider selection
            [{"cost_per_call": 0.10, "service_slug": "resend", "auth_method": "api_key",
              "credential_modes": ["byo"], "endpoint_pattern": "POST /emails",
              "cost_currency": "USD", "free_tier_calls": 0}],
            # service domain
            [{"slug": "resend", "api_domain": "api.resend.com"}],
        ]

        mock_cred = MagicMock()
        mock_cred.get_credential.return_value = "re_test_key"
        mock_cred_store.return_value = mock_cred

        # Upstream network failure
        mock_client = AsyncMock()
        mock_client.request.side_effect = httpx.ConnectError("boom")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockHttpxClient.return_value = mock_client

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/email.send/execute",
                json={
                    "provider": "resend",
                    "method": "POST",
                    "path": "/emails",
                    "body": {"to": "dest@test.com"},
                },
                headers={"X-Rhumb-Key": "rk_test"},
            )

    assert resp.status_code == 502
    mock_budget.release.assert_awaited_once()
    mock_credit.release.assert_awaited_once()


@pytest.mark.anyio
async def test_execute_route_logs_billing_cents_with_markup():
    """Execution log should store upstream/billed/margin cents using 20% markup."""
    app = create_app()

    mock_store = MagicMock()
    mock_store.verify_api_key_with_agent = AsyncMock(return_value=_mock_agent())
    captured_payloads: list[dict] = []

    async def _capture_insert(table: str, payload: dict) -> bool:
        captured_payloads.append({"table": table, "payload": payload})
        return True

    with (
        patch("routes.capability_execute._get_identity_store", return_value=mock_store),
        patch("routes.capability_execute._budget_enforcer") as mock_budget,
        patch("routes.capability_execute._credit_deduction") as mock_credit,
        patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock) as mock_fetch,
        patch("routes.capability_execute.supabase_insert", new_callable=AsyncMock, side_effect=_capture_insert),
        patch("routes.capability_execute._inject_auth_headers", side_effect=lambda s, a, h: h),
        patch("routes.capability_execute.get_credential_store") as mock_cred_store,
        patch("routes.capability_execute.httpx.AsyncClient") as MockHttpxClient,
    ):
        mock_budget.check_and_decrement = AsyncMock(
            return_value=BudgetCheckResult(allowed=True, remaining_usd=49.9)
        )
        mock_budget.release = AsyncMock(return_value=50.0)

        mock_credit.deduct = AsyncMock(return_value=MagicMock(allowed=True, remaining_cents=880))
        mock_credit.release = AsyncMock(return_value=MagicMock(released=True, idempotent=False))

        mock_fetch.side_effect = [
            # cost estimate mappings
            [{"cost_per_call": 0.10, "service_slug": "resend", "auth_method": "api_key",
              "credential_modes": ["byo"], "endpoint_pattern": "POST /emails",
              "cost_currency": "USD", "free_tier_calls": 0}],
            # capability exists
            [{"id": "email.send", "domain": "email", "action": "send", "description": "Send email"}],
            # mappings for provider selection
            [{"cost_per_call": 0.10, "service_slug": "resend", "auth_method": "api_key",
              "credential_modes": ["byo"], "endpoint_pattern": "POST /emails",
              "cost_currency": "USD", "free_tier_calls": 0}],
            # service domain
            [{"slug": "resend", "api_domain": "api.resend.com"}],
        ]

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

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/email.send/execute",
                json={
                    "provider": "resend",
                    "method": "POST",
                    "path": "/emails",
                    "body": {"to": "dest@test.com"},
                },
                headers={"X-Rhumb-Key": "rk_test"},
            )

    assert resp.status_code == 200
    assert captured_payloads, "expected capability execution insert"
    payload = captured_payloads[0]["payload"]
    assert payload["upstream_cost_cents"] == 10
    assert payload["cost_usd_cents"] == 12
    assert payload["margin_cents"] == 2
    assert payload["billing_status"] == "billed"
