"""Tests for routing engine + spend visibility — R20 Phase 4."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from app import create_app
from services.routing_engine import RoutingEngine, RoutingStrategy, RoutedProvider


# ---------------------------------------------------------------------------
# RoutingEngine.select_provider unit tests
# ---------------------------------------------------------------------------


class TestRoutingEngineSelectProvider:
    """Test the core provider selection logic."""

    def setup_method(self):
        self.engine = RoutingEngine()
        self.mappings = [
            {"service_slug": "resend", "cost_per_call": 0.01, "auth_method": "bearer_token",
             "credential_modes": ["byo"], "endpoint_pattern": "POST /emails",
             "cost_currency": "USD", "free_tier_calls": 100},
            {"service_slug": "sendgrid", "cost_per_call": 0.005, "auth_method": "bearer_token",
             "credential_modes": ["byo"], "endpoint_pattern": "POST /v3/mail/send",
             "cost_currency": "USD", "free_tier_calls": 100},
            {"service_slug": "postmark", "cost_per_call": 0.001, "auth_method": "bearer_token",
             "credential_modes": ["byo"], "endpoint_pattern": "POST /email",
             "cost_currency": "USD", "free_tier_calls": 0},
        ]
        self.scores = {"resend": 8.0, "sendgrid": 7.5, "postmark": 6.5}
        self.circuits = {"resend": "closed", "sendgrid": "closed", "postmark": "closed"}

    def test_balanced_strategy_selects_best_composite(self):
        """Balanced strategy weighs score + cost + health."""
        strategy = RoutingStrategy(strategy="balanced")
        result = self.engine.select_provider(
            self.mappings, self.scores, self.circuits, strategy
        )
        assert result is not None
        assert result.strategy_used == "balanced"
        # All closed circuits, so health is equal — composite favors high score + low cost
        assert result.service_slug in ("resend", "sendgrid", "postmark")

    def test_cheapest_strategy_picks_lowest_cost(self):
        """Cheapest strategy picks lowest cost above quality floor."""
        strategy = RoutingStrategy(strategy="cheapest", quality_floor=6.0,
                                   weight_score=0.10, weight_cost=0.80, weight_health=0.10)
        result = self.engine.select_provider(
            self.mappings, self.scores, self.circuits, strategy
        )
        assert result is not None
        assert result.service_slug == "postmark"  # $0.001 is cheapest

    def test_highest_quality_picks_highest_score(self):
        """Highest quality strategy picks highest AN score."""
        # Widen score gap to ensure quality dominates over cost
        scores = {"resend": 9.5, "sendgrid": 7.5, "postmark": 6.5}
        strategy = RoutingStrategy(strategy="highest_quality", quality_floor=6.0,
                                   weight_score=0.80, weight_cost=0.10, weight_health=0.10)
        result = self.engine.select_provider(
            self.mappings, scores, self.circuits, strategy
        )
        assert result is not None
        assert result.service_slug == "resend"  # 9.5 is clearly highest

    def test_quality_floor_filters_providers(self):
        """Providers below quality floor are excluded."""
        strategy = RoutingStrategy(strategy="cheapest", quality_floor=7.0,
                                   weight_score=0.10, weight_cost=0.80, weight_health=0.10)
        result = self.engine.select_provider(
            self.mappings, self.scores, self.circuits, strategy
        )
        assert result is not None
        assert result.service_slug != "postmark"  # postmark is 6.5, below 7.0 floor

    def test_max_cost_filter(self):
        """Providers above max cost are excluded."""
        strategy = RoutingStrategy(
            strategy="highest_quality", quality_floor=6.0,
            max_cost_per_call_usd=0.005,
            weight_score=0.80, weight_cost=0.10, weight_health=0.10,
        )
        result = self.engine.select_provider(
            self.mappings, self.scores, self.circuits, strategy
        )
        assert result is not None
        assert result.service_slug != "resend"  # resend is $0.01, above $0.005

    def test_open_circuit_excluded(self):
        """Providers with open circuits are excluded."""
        circuits = {"resend": "open", "sendgrid": "closed", "postmark": "closed"}
        strategy = RoutingStrategy(strategy="highest_quality", quality_floor=6.0,
                                   weight_score=0.80, weight_cost=0.10, weight_health=0.10)
        result = self.engine.select_provider(
            self.mappings, self.scores, circuits, strategy
        )
        assert result is not None
        assert result.service_slug != "resend"  # open circuit

    def test_all_open_returns_none(self):
        """No viable provider when all circuits are open."""
        circuits = {"resend": "open", "sendgrid": "open", "postmark": "open"}
        strategy = RoutingStrategy()
        result = self.engine.select_provider(
            self.mappings, self.scores, circuits, strategy
        )
        assert result is None

    def test_half_open_penalized(self):
        """Half-open circuits get lower health score."""
        circuits = {"resend": "half_open", "sendgrid": "closed", "postmark": "closed"}
        strategy = RoutingStrategy(strategy="fastest", quality_floor=6.0,
                                   weight_score=0.10, weight_cost=0.10, weight_health=0.80)
        result = self.engine.select_provider(
            self.mappings, self.scores, circuits, strategy
        )
        assert result is not None
        assert result.service_slug != "resend"  # penalized health

    def test_empty_mappings_returns_none(self):
        """No mappings → None."""
        result = self.engine.select_provider([], {}, {}, RoutingStrategy())
        assert result is None

    def test_all_below_quality_floor(self):
        """All providers below quality floor → None."""
        strategy = RoutingStrategy(quality_floor=9.0)
        result = self.engine.select_provider(
            self.mappings, self.scores, self.circuits, strategy
        )
        assert result is None


class _MockSpendResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _MockSpendClient:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url, headers=None, timeout=None):
        return self._response


@pytest.mark.anyio
async def test_get_spend_summary_canonicalizes_alias_backed_provider_ids():
    engine = RoutingEngine()
    rows = [
        {
            "capability_id": "search.query",
            "provider_used": "brave-search",
            "cost_estimate_usd": 0.01,
            "success": True,
        },
        {
            "capability_id": "search.query",
            "provider_used": "brave-search-api",
            "cost_estimate_usd": 0.03,
            "success": True,
        },
        {
            "capability_id": "person.enrich",
            "provider_used": "pdl",
            "cost_estimate_usd": 0.02,
            "success": True,
        },
    ]

    with patch(
        "services.routing_engine.httpx.AsyncClient",
        return_value=_MockSpendClient(_MockSpendResponse(200, rows)),
    ):
        summary = await engine.get_spend_summary("agent_test123", "2026-04")

    assert summary["total_spend_usd"] == 0.06
    assert summary["total_executions"] == 3
    assert summary["by_provider"] == [
        {"provider": "brave-search-api", "spend_usd": 0.04, "executions": 2},
        {"provider": "people-data-labs", "spend_usd": 0.02, "executions": 1},
    ]


@pytest.mark.anyio
async def test_get_spend_summary_normalizes_mixed_case_alias_backed_provider_ids():
    engine = RoutingEngine()
    rows = [
        {
            "capability_id": "search.query",
            "provider_used": "Brave-Search",
            "cost_estimate_usd": 0.02,
            "success": True,
        },
        {
            "capability_id": "person.enrich",
            "provider_used": "PDL",
            "cost_estimate_usd": 0.01,
            "success": True,
        },
    ]

    with patch(
        "services.routing_engine.httpx.AsyncClient",
        return_value=_MockSpendClient(_MockSpendResponse(200, rows)),
    ):
        summary = await engine.get_spend_summary("agent_test123", "2026-04")

    assert summary["by_provider"] == [
        {"provider": "brave-search-api", "spend_usd": 0.02, "executions": 1},
        {"provider": "people-data-labs", "spend_usd": 0.01, "executions": 1},
    ]


# ---------------------------------------------------------------------------
# Routing route tests
# ---------------------------------------------------------------------------


class TestRoutingRoutes:
    """Test routing API endpoints."""

    def setup_method(self):
        # Patch identity extraction: accept any non-None key, reject None
        async def _mock_extract(api_key):
            if not api_key:
                from fastapi import HTTPException
                raise HTTPException(401, "Missing X-Rhumb-Key header")
            return "agent_test123"

        self._agent_id_patcher = patch(
            "routes.routing._extract_agent_id",
            side_effect=_mock_extract,
        )
        self._agent_id_patcher.start()
        self.app = create_app()
        self.client = TestClient(self.app)

    def teardown_method(self):
        self._agent_id_patcher.stop()

    def test_get_strategy_requires_auth(self):
        resp = self.client.get("/v1/agent/routing-strategy")
        assert resp.status_code == 401

    def test_get_strategy_default(self):
        with patch("routes.routing._engine") as mock_engine:
            mock_engine.get_strategy = AsyncMock(return_value=RoutingStrategy())
            resp = self.client.get(
                "/v1/agent/routing-strategy",
                headers={"X-Rhumb-Key": "test_key"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["strategy"] == "balanced"
            assert data["quality_floor"] == 6.0

    def test_set_strategy(self):
        with patch("routes.routing._engine") as mock_engine:
            mock_engine.set_strategy = AsyncMock(return_value=RoutingStrategy(
                strategy="cheapest", quality_floor=7.0,
                weight_score=0.10, weight_cost=0.80, weight_health=0.10,
            ))
            resp = self.client.put(
                "/v1/agent/routing-strategy",
                headers={"X-Rhumb-Key": "test_key"},
                json={"strategy": "cheapest", "quality_floor": 7.0},
            )
            assert resp.status_code == 200
            assert resp.json()["strategy"] == "cheapest"

    def test_set_strategy_invalid(self):
        resp = self.client.put(
            "/v1/agent/routing-strategy",
            headers={"X-Rhumb-Key": "test_key"},
            json={"strategy": "yolo"},
        )
        assert resp.status_code == 422

    def test_get_spend_requires_auth(self):
        resp = self.client.get("/v1/agent/spend")
        assert resp.status_code == 401

    def test_get_spend(self):
        with patch("routes.routing._engine") as mock_engine:
            mock_engine.get_spend_summary = AsyncMock(return_value={
                "agent_id": "agent_test",
                "period": "2026-03",
                "total_spend_usd": 12.47,
                "total_executions": 342,
                "by_capability": [
                    {"capability_id": "email.send", "spend_usd": 3.42, "executions": 342, "avg_cost": 0.01}
                ],
                "by_provider": [
                    {"provider": "resend", "spend_usd": 3.42, "executions": 342}
                ],
            })
            resp = self.client.get(
                "/v1/agent/spend",
                headers={"X-Rhumb-Key": "test_key"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_spend_usd"] == 12.47
            assert len(data["by_capability"]) == 1

    def test_get_spend_recanonicalizes_alias_backed_provider_breakdown(self):
        with patch("routes.routing._engine") as mock_engine:
            mock_engine.get_spend_summary = AsyncMock(return_value={
                "agent_id": "agent_test",
                "period": "2026-03",
                "total_spend_usd": 0.06,
                "total_executions": 3,
                "by_capability": [
                    {"capability_id": "search.query", "spend_usd": 0.04, "executions": 2, "avg_cost": 0.02},
                    {"capability_id": "person.enrich", "spend_usd": 0.02, "executions": 1, "avg_cost": 0.02},
                ],
                "by_provider": [
                    {"provider": "Brave-Search", "spend_usd": 0.01, "executions": 1},
                    {"provider": "brave-search-api", "spend_usd": 0.03, "executions": 1},
                    {"provider": "PDL", "spend_usd": 0.02, "executions": 1},
                ],
            })
            resp = self.client.get(
                "/v1/agent/spend",
                headers={"X-Rhumb-Key": "test_key"},
            )

        assert resp.status_code == 200
        assert resp.json()["by_provider"] == [
            {"provider": "brave-search-api", "spend_usd": 0.04, "executions": 2},
            {"provider": "people-data-labs", "spend_usd": 0.02, "executions": 1},
        ]

    def test_get_spend_rejects_invalid_period_filter(self):
        with patch("routes.routing._engine") as mock_engine:
            mock_engine.get_spend_summary = AsyncMock()
            resp = self.client.get(
                "/v1/agent/spend",
                params={"period": "2026-99"},
                headers={"X-Rhumb-Key": "test_key"},
            )

        assert resp.status_code == 400
        error = resp.json()["error"]
        assert error["code"] == "INVALID_PARAMETERS"
        assert error["message"] == "Invalid 'period' filter."
        assert error["detail"] == "Provide a period in YYYY-MM format or omit the filter."
        mock_engine.get_spend_summary.assert_not_awaited()

    def test_get_spend_rejects_blank_period_filter_before_querying_engine(self):
        with patch("routes.routing._engine") as mock_engine:
            mock_engine.get_spend_summary = AsyncMock()
            resp = self.client.get(
                "/v1/agent/spend",
                params={"period": "   "},
                headers={"X-Rhumb-Key": "test_key"},
            )

        assert resp.status_code == 400
        error = resp.json()["error"]
        assert error["code"] == "INVALID_PARAMETERS"
        assert error["message"] == "Invalid 'period' filter."
        assert error["detail"] == "Provide a period in YYYY-MM format or omit the filter."
        mock_engine.get_spend_summary.assert_not_awaited()

    def test_get_spend_rejects_invalid_period_filter_before_auth(self):
        with patch("routes.routing._extract_agent_id", new_callable=AsyncMock) as mock_extract:
            resp = self.client.get(
                "/v1/agent/spend",
                params={"period": "2026-99"},
            )

        assert resp.status_code == 400
        error = resp.json()["error"]
        assert error["code"] == "INVALID_PARAMETERS"
        assert error["message"] == "Invalid 'period' filter."
        assert error["detail"] == "Provide a period in YYYY-MM format or omit the filter."
        mock_extract.assert_not_awaited()

    def test_get_spend_normalizes_valid_period_before_querying_engine(self):
        with patch("routes.routing._engine") as mock_engine:
            mock_engine.get_spend_summary = AsyncMock(return_value={
                "agent_id": "agent_test",
                "period": "2026-03",
                "total_spend_usd": 0.0,
                "total_executions": 0,
                "by_capability": [],
                "by_provider": [],
            })
            resp = self.client.get(
                "/v1/agent/spend",
                params={"period": " 2026-03 "},
                headers={"X-Rhumb-Key": "test_key"},
            )

        assert resp.status_code == 200
        mock_engine.get_spend_summary.assert_awaited_once_with("agent_test123", "2026-03")
