"""Tests for budget enforcement — R19 Phase 4.

Tests the BudgetEnforcer service and budget route handlers.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from app import create_app
from services.budget_enforcer import BudgetEnforcer, BudgetCheckResult, BudgetStatus


# ---------------------------------------------------------------------------
# BudgetEnforcer unit tests
# ---------------------------------------------------------------------------


class TestBudgetEnforcer:
    """Test BudgetEnforcer service."""

    @pytest.mark.asyncio
    async def test_check_and_decrement_zero_cost(self):
        """Zero-cost executions are always allowed."""
        enforcer = BudgetEnforcer()
        result = await enforcer.check_and_decrement("agent_test", 0)
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_check_and_decrement_no_budget(self):
        """Agents without budget config have unlimited access."""
        enforcer = BudgetEnforcer()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = 999999.0

        with patch("services.budget_enforcer.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await enforcer.check_and_decrement("agent_no_budget", 0.01)
            assert result.allowed is True
            assert result.remaining_usd is None  # unlimited

    @pytest.mark.asyncio
    async def test_check_and_decrement_sufficient_budget(self):
        """Agents with sufficient budget get allowed."""
        enforcer = BudgetEnforcer()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = 49.99

        with patch("services.budget_enforcer.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await enforcer.check_and_decrement("agent_has_budget", 0.01)
            assert result.allowed is True
            assert result.remaining_usd == 49.99

    @pytest.mark.asyncio
    async def test_check_and_decrement_exceeded(self):
        """Budget exceeded → not allowed."""
        enforcer = BudgetEnforcer()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = -1

        with patch("services.budget_enforcer.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await enforcer.check_and_decrement("agent_broke", 10.0)
            assert result.allowed is False
            assert result.remaining_usd == 0
            assert "exceeded" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_check_and_decrement_rpc_failure_fails_open(self):
        """If budget RPC fails, execution is still allowed (fail-open)."""
        enforcer = BudgetEnforcer()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"

        with patch("services.budget_enforcer.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await enforcer.check_and_decrement("agent_any", 5.0)
            assert result.allowed is True  # fail-open

    @pytest.mark.asyncio
    async def test_release_budget(self):
        """Release returns budget on failure."""
        enforcer = BudgetEnforcer()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = 50.0

        with patch("services.budget_enforcer.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            remaining = await enforcer.release("agent_test", 0.01)
            assert remaining == 50.0

    @pytest.mark.asyncio
    async def test_release_zero_cost(self):
        """Releasing zero cost is a no-op."""
        enforcer = BudgetEnforcer()
        remaining = await enforcer.release("agent_test", 0)
        assert remaining is None

    @pytest.mark.asyncio
    async def test_get_budget_no_config(self):
        """Agent with no budget returns unlimited status."""
        enforcer = BudgetEnforcer()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []

        with patch("services.budget_enforcer.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            status = await enforcer.get_budget("agent_no_budget")
            assert status.allowed is True
            assert status.budget_usd is None

    @pytest.mark.asyncio
    async def test_get_budget_with_config(self):
        """Agent with budget returns full status."""
        enforcer = BudgetEnforcer()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{
            "budget_usd": "50.0000",
            "spent_usd": "12.4700",
            "period": "monthly",
            "hard_limit": True,
            "alert_threshold_pct": 80,
            "alert_fired": False,
        }]

        with patch("services.budget_enforcer.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            status = await enforcer.get_budget("agent_has_budget")
            assert status.budget_usd == 50.0
            assert status.spent_usd == 12.47
            assert status.remaining_usd == 37.53
            assert status.period == "monthly"
            assert status.hard_limit is True


# ---------------------------------------------------------------------------
# Budget route integration tests
# ---------------------------------------------------------------------------


class TestBudgetRoutes:
    """Test budget API endpoints."""

    def setup_method(self):
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_get_budget_requires_auth(self):
        """GET /v1/agent/budget requires X-Rhumb-Key."""
        resp = self.client.get("/v1/agent/budget")
        assert resp.status_code == 401

    def test_get_budget_unlimited(self):
        """GET /v1/agent/budget returns unlimited for new agent."""
        with patch("routes.budget._enforcer") as mock_enforcer:
            mock_enforcer.get_budget = AsyncMock(return_value=BudgetStatus(
                allowed=True,
                remaining_usd=None,
                budget_usd=None,
                spent_usd=None,
                period=None,
                hard_limit=None,
                alert_threshold_pct=None,
                alert_fired=None,
            ))
            resp = self.client.get(
                "/v1/agent/budget",
                headers={"X-Rhumb-Key": "test_key_123"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["unlimited"] is True

    def test_get_budget_with_budget(self):
        """GET /v1/agent/budget returns budget status."""
        with patch("routes.budget._enforcer") as mock_enforcer:
            mock_enforcer.get_budget = AsyncMock(return_value=BudgetStatus(
                allowed=True,
                remaining_usd=37.53,
                budget_usd=50.0,
                spent_usd=12.47,
                period="monthly",
                hard_limit=True,
                alert_threshold_pct=80,
                alert_fired=False,
            ))
            resp = self.client.get(
                "/v1/agent/budget",
                headers={"X-Rhumb-Key": "test_key_123"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["budget_usd"] == 50.0
            assert data["spent_usd"] == 12.47
            assert data["remaining_usd"] == 37.53

    def test_set_budget(self):
        """PUT /v1/agent/budget creates/updates budget."""
        with patch("routes.budget._enforcer") as mock_enforcer:
            mock_enforcer.set_budget = AsyncMock(return_value=BudgetStatus(
                allowed=True,
                remaining_usd=100.0,
                budget_usd=100.0,
                spent_usd=0.0,
                period="monthly",
                hard_limit=True,
                alert_threshold_pct=80,
                alert_fired=False,
            ))
            resp = self.client.put(
                "/v1/agent/budget",
                headers={"X-Rhumb-Key": "test_key_123"},
                json={"budget_usd": 100.0, "period": "monthly"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["budget_usd"] == 100.0
            assert data["remaining_usd"] == 100.0

    def test_set_budget_invalid_period(self):
        """PUT /v1/agent/budget rejects invalid period."""
        resp = self.client.put(
            "/v1/agent/budget",
            headers={"X-Rhumb-Key": "test_key_123"},
            json={"budget_usd": 100.0, "period": "yearly"},
        )
        assert resp.status_code == 422

    def test_set_budget_requires_positive_amount(self):
        """PUT /v1/agent/budget rejects zero/negative budget."""
        resp = self.client.put(
            "/v1/agent/budget",
            headers={"X-Rhumb-Key": "test_key_123"},
            json={"budget_usd": 0, "period": "monthly"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Budget enforcement in execute route (integration)
# ---------------------------------------------------------------------------


class TestBudgetInExecuteRoute:
    """Test that execute route checks budget before execution."""

    def setup_method(self):
        self.app = create_app()
        self.client = TestClient(self.app)

    @patch("routes.capability_execute._budget_enforcer")
    @patch("routes.capability_execute.supabase_fetch")
    @patch("routes.capability_execute.supabase_insert")
    def test_execute_rejected_when_over_budget(
        self, mock_insert, mock_fetch, mock_budget
    ):
        """Execute returns 402 when budget is exceeded."""
        # Budget check returns not allowed
        mock_budget.check_and_decrement = AsyncMock(return_value=BudgetCheckResult(
            allowed=False,
            remaining_usd=0,
            reason="Budget exceeded. Estimated cost: $0.0100. Agent budget exhausted.",
        ))
        # Cap services for cost estimate
        mock_fetch.side_effect = [
            [{"cost_per_call": 0.01, "service_slug": "resend", "auth_method": "bearer_token",
              "credential_modes": ["byo"], "endpoint_pattern": "POST /emails",
              "cost_currency": "USD", "free_tier_calls": 0}],
        ]

        resp = self.client.post(
            "/v1/capabilities/email.send/execute",
            headers={"X-Rhumb-Key": "agent_broke"},
            json={
                "method": "POST",
                "path": "/emails",
                "body": {"from": "test@test.com", "to": "dest@test.com"},
            },
        )
        assert resp.status_code == 402
        assert "budget" in resp.json()["detail"].lower()

    @patch("routes.capability_execute._budget_enforcer")
    @patch("routes.capability_execute.supabase_fetch")
    @patch("routes.capability_execute.supabase_insert")
    def test_execute_allowed_when_within_budget(
        self, mock_insert, mock_fetch, mock_budget
    ):
        """Execute proceeds when budget is sufficient (budget_remaining in response)."""
        # Budget check allowed
        mock_budget.check_and_decrement = AsyncMock(return_value=BudgetCheckResult(
            allowed=True, remaining_usd=49.99
        ))
        mock_budget.get_budget = AsyncMock(return_value=BudgetStatus(
            allowed=True, remaining_usd=49.99, budget_usd=50.0,
            spent_usd=0.01, period="monthly", hard_limit=True,
            alert_threshold_pct=80, alert_fired=False,
        ))

        # Supabase fetches: cap_services (budget), capability, cap_services (main), service domain
        mock_fetch.side_effect = [
            # First: _get_capability_services for budget cost estimate
            [{"cost_per_call": 0.01, "service_slug": "resend", "auth_method": "bearer_token",
              "credential_modes": ["byo"], "endpoint_pattern": "POST /emails",
              "cost_currency": "USD", "free_tier_calls": 0}],
            # Second: _resolve_capability
            [{"id": "email.send", "domain": "email", "action": "send", "description": "Send email"}],
            # Third: _get_capability_services for provider selection
            [{"cost_per_call": 0.01, "service_slug": "resend", "auth_method": "bearer_token",
              "credential_modes": ["byo"], "endpoint_pattern": "POST /emails",
              "cost_currency": "USD", "free_tier_calls": 0}],
            # Fourth: _get_service_domain
            [{"slug": "resend", "api_domain": "api.resend.com"}],
        ]
        mock_insert.return_value = True

        # Mock credential store for dynamic service
        with patch("routes.capability_execute.get_credential_store") as mock_store_fn:
            mock_store = MagicMock()
            mock_store.get_credential.return_value = "re_test_key_123"
            mock_store_fn.return_value = mock_store

            # Mock upstream request
            with patch("routes.capability_execute.httpx.AsyncClient") as MockClient:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"id": "msg_123"}

                mock_client = AsyncMock()
                mock_client.request.return_value = mock_resp
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client

                resp = self.client.post(
                    "/v1/capabilities/email.send/execute",
                    headers={"X-Rhumb-Key": "agent_funded"},
                    json={
                        "provider": "resend",
                        "method": "POST",
                        "path": "/emails",
                        "body": {"from": "test@test.com", "to": "dest@test.com"},
                    },
                )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()["data"]
        assert "budget_remaining_usd" in data
