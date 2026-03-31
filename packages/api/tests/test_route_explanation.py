"""Tests for the Route Explanation Engine (WU-41.3)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app
from schemas.agent_identity import AgentIdentitySchema
from services.budget_enforcer import BudgetStatus
from services.route_explanation import (
    CandidateExplanation,
    CandidateFactor,
    RouteExplanation,
    RouteExplanationEngine,
    _normalize_an_score,
    _normalize_availability,
    _normalize_cost,
    _normalize_credential_preference,
    _normalize_latency,
    get_explanation_engine,
)

FAKE_RHUMB_KEY = "rhumb_test_key_v2"


def _mock_agent() -> AgentIdentitySchema:
    return AgentIdentitySchema(
        agent_id="agent_v2_test",
        name="v2-test",
        organization_id="org_v2_test",
    )


@pytest.fixture
def app():
    return create_app()


@pytest.fixture(autouse=True)
def _mock_identity_store():
    mock_store = MagicMock()
    mock_store.verify_api_key_with_agent = AsyncMock(return_value=_mock_agent())
    with patch("routes.capability_execute._get_identity_store", return_value=mock_store):
        yield mock_store


@pytest.fixture(autouse=True)
def _mock_policy_store():
    mock_store = MagicMock()
    mock_store.get_policy = AsyncMock(return_value=None)
    mock_store.put_policy = AsyncMock()
    with patch("routes.resolve_v2.get_resolve_policy_store", return_value=mock_store):
        yield mock_store


@pytest.fixture(autouse=True)
def _mock_v2_budget_enforcer():
    mock_enforcer = MagicMock()
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
    with patch("routes.resolve_v2._v2_budget_enforcer", mock_enforcer):
        yield mock_enforcer


# ---------------------------------------------------------------------------
# Unit tests: factor normalization
# ---------------------------------------------------------------------------


class TestFactorNormalization:
    """Test the individual scoring factor normalization functions."""

    def test_an_score_normal(self):
        assert _normalize_an_score(8.5) == pytest.approx(0.85, abs=0.001)

    def test_an_score_zero(self):
        assert _normalize_an_score(0.0) == 0.0

    def test_an_score_ten(self):
        assert _normalize_an_score(10.0) == 1.0

    def test_an_score_none(self):
        assert _normalize_an_score(None) == 0.0

    def test_an_score_over_ten_clamped(self):
        assert _normalize_an_score(12.0) == 1.0

    def test_availability_full(self):
        assert _normalize_availability(99.9) == pytest.approx(0.999, abs=0.001)

    def test_availability_none_returns_neutral(self):
        assert _normalize_availability(None) == 0.5

    def test_cost_cheaper_scores_higher(self):
        cheap = _normalize_cost(0.001, 0.01)
        expensive = _normalize_cost(0.009, 0.01)
        assert cheap > expensive

    def test_cost_none_returns_neutral(self):
        assert _normalize_cost(None, None) == 0.5

    def test_latency_faster_scores_higher(self):
        fast = _normalize_latency(100, 5000)
        slow = _normalize_latency(4000, 5000)
        assert fast > slow

    def test_latency_none_returns_neutral(self):
        assert _normalize_latency(None, None) == 0.5

    def test_credential_auto_always_full(self):
        assert _normalize_credential_preference(["byo"], "auto") == 1.0

    def test_credential_match(self):
        assert _normalize_credential_preference(["byo", "rhumb_managed"], "byo") == 1.0

    def test_credential_mismatch(self):
        assert _normalize_credential_preference(["byo"], "rhumb_managed") == 0.3


# ---------------------------------------------------------------------------
# Unit tests: explanation engine
# ---------------------------------------------------------------------------


class TestExplanationEngine:
    """Test the RouteExplanationEngine build logic."""

    def _sample_mappings(self):
        return [
            {
                "service_slug": "sendgrid",
                "credential_modes": ["byo"],
                "cost_per_call": "0.01",
            },
            {
                "service_slug": "resend",
                "credential_modes": ["byo", "rhumb_managed"],
                "cost_per_call": "0.005",
            },
            {
                "service_slug": "mailchimp",
                "credential_modes": ["byo"],
                "cost_per_call": "0.008",
            },
        ]

    def _sample_provider_details(self):
        return {
            "sendgrid": {
                "name": "SendGrid",
                "aggregate_recommendation_score": 6.5,
                "category": "email",
            },
            "resend": {
                "name": "Resend",
                "aggregate_recommendation_score": 7.8,
                "category": "email",
            },
            "mailchimp": {
                "name": "Mailchimp",
                "aggregate_recommendation_score": 5.2,
                "category": "email",
            },
        }

    def test_build_explanation_basic(self):
        engine = RouteExplanationEngine()
        mappings = self._sample_mappings()

        explanation = engine.build_explanation(
            receipt_id="rcpt_test123",
            capability_id="email.send",
            winner_provider_id="resend",
            winner_reason="routing_with_policy_filters",
            all_mappings=mappings,
            eligible_mappings=mappings,
            policy_summary={},
            credential_mode="byo",
            provider_details=self._sample_provider_details(),
        )

        assert explanation.explanation_id.startswith("rexp_")
        assert explanation.receipt_id == "rcpt_test123"
        assert explanation.capability_id == "email.send"
        assert explanation.winner_provider_id == "resend"
        assert explanation.winner_reason == "routing_with_policy_filters"
        assert len(explanation.candidates) == 3
        assert explanation.human_summary  # Not empty
        assert explanation.evaluation_ms is not None

    def test_build_explanation_all_eligible_scored(self):
        engine = RouteExplanationEngine()
        mappings = self._sample_mappings()

        explanation = engine.build_explanation(
            receipt_id="rcpt_test123",
            capability_id="email.send",
            winner_provider_id="resend",
            winner_reason="routing_with_policy_filters",
            all_mappings=mappings,
            eligible_mappings=mappings,
            policy_summary={},
            credential_mode="byo",
            provider_details=self._sample_provider_details(),
        )

        for c in explanation.candidates:
            assert c.eligible is True
            assert c.composite_score > 0
            assert len(c.factors) == 5
            factor_names = {f.name for f in c.factors}
            assert factor_names == {
                "an_score",
                "availability",
                "estimated_cost_usd",
                "latency_p50_ms",
                "credential_mode_preference",
            }

    def test_build_explanation_with_denied_provider(self):
        engine = RouteExplanationEngine()
        all_mappings = self._sample_mappings()
        eligible_mappings = [m for m in all_mappings if m["service_slug"] != "mailchimp"]

        explanation = engine.build_explanation(
            receipt_id="rcpt_test456",
            capability_id="email.send",
            winner_provider_id="resend",
            winner_reason="policy_preference_match",
            all_mappings=all_mappings,
            eligible_mappings=eligible_mappings,
            policy_summary={
                "provider_deny": ["mailchimp"],
                "provider_preference": ["resend"],
            },
            credential_mode="byo",
            provider_details=self._sample_provider_details(),
        )

        eligible = [c for c in explanation.candidates if c.eligible]
        ineligible = [c for c in explanation.candidates if not c.eligible]

        assert len(eligible) == 2
        assert len(ineligible) == 1
        assert ineligible[0].provider_id == "mailchimp"
        assert ineligible[0].ineligibility_reason == "denied_by_policy"
        assert ineligible[0].policy_checks["denied"] is True

    def test_build_explanation_pinned(self):
        engine = RouteExplanationEngine()
        all_mappings = self._sample_mappings()

        explanation = engine.build_explanation(
            receipt_id="rcpt_pin",
            capability_id="email.send",
            winner_provider_id="sendgrid",
            winner_reason="policy_pin",
            all_mappings=all_mappings,
            eligible_mappings=all_mappings,
            policy_summary={"pin": "sendgrid"},
            credential_mode="byo",
            provider_details=self._sample_provider_details(),
        )

        assert explanation.winner_reason == "policy_pin"
        assert "pinned by policy" in explanation.human_summary.lower()

    def test_build_explanation_single_candidate(self):
        engine = RouteExplanationEngine()
        all_mappings = self._sample_mappings()
        eligible = [all_mappings[1]]  # Only resend

        explanation = engine.build_explanation(
            receipt_id="rcpt_single",
            capability_id="email.send",
            winner_provider_id="resend",
            winner_reason="policy_single_candidate",
            all_mappings=all_mappings,
            eligible_mappings=eligible,
            policy_summary={
                "allow_only": ["resend"],
            },
            credential_mode="byo",
            provider_details=self._sample_provider_details(),
        )

        assert explanation.winner_reason == "policy_single_candidate"
        assert "only eligible candidate" in explanation.human_summary.lower()

    def test_to_dict_shape(self):
        engine = RouteExplanationEngine()
        mappings = self._sample_mappings()

        explanation = engine.build_explanation(
            receipt_id="rcpt_dict",
            capability_id="email.send",
            winner_provider_id="resend",
            winner_reason="routing_with_policy_filters",
            all_mappings=mappings,
            eligible_mappings=mappings,
            policy_summary={},
            credential_mode="byo",
            provider_details=self._sample_provider_details(),
        )

        d = explanation.to_dict()
        assert "explanation_id" in d
        assert "receipt_id" in d
        assert "winner" in d
        assert d["winner"]["provider_id"] == "resend"
        assert d["winner"]["composite_score"] is not None
        assert d["winner"]["selection_reason"] == "routing_with_policy_filters"
        assert "candidates" in d
        assert "human_summary" in d
        assert "evaluation_ms" in d

        # Check candidate shape
        for candidate in d["candidates"]:
            assert "provider_id" in candidate
            assert "eligible" in candidate
            assert "composite_score" in candidate
            if candidate["eligible"]:
                assert "factors" in candidate
                assert "an_score" in candidate["factors"]

    def test_composite_score_respects_weights(self):
        """Higher AN score should contribute more to composite when weighted."""
        engine = RouteExplanationEngine()
        mappings = [
            {"service_slug": "high_an", "credential_modes": ["byo"], "cost_per_call": "0.01"},
            {"service_slug": "low_an", "credential_modes": ["byo"], "cost_per_call": "0.01"},
        ]
        details = {
            "high_an": {"name": "High AN", "aggregate_recommendation_score": 9.5},
            "low_an": {"name": "Low AN", "aggregate_recommendation_score": 3.0},
        }

        explanation = engine.build_explanation(
            receipt_id="rcpt_weights",
            capability_id="test.cap",
            winner_provider_id="high_an",
            winner_reason="routing_with_policy_filters",
            all_mappings=mappings,
            eligible_mappings=mappings,
            policy_summary={},
            credential_mode="byo",
            provider_details=details,
        )

        high = next(c for c in explanation.candidates if c.provider_id == "high_an")
        low = next(c for c in explanation.candidates if c.provider_id == "low_an")

        # High AN score provider should have higher AN factor contribution
        high_an_factor = next(f for f in high.factors if f.name == "an_score")
        low_an_factor = next(f for f in low.factors if f.name == "an_score")
        assert high_an_factor.weighted_contribution > low_an_factor.weighted_contribution


# ---------------------------------------------------------------------------
# Integration tests: explanation in v2 execute response
# ---------------------------------------------------------------------------


SAMPLE_CAP = [
    {
        "id": "email.send",
        "domain": "email",
        "action": "send",
        "description": "Send transactional email",
    }
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
    {
        "service_slug": "resend",
        "credential_modes": ["byo"],
        "auth_method": "api_key",
        "endpoint_pattern": "POST /emails",
        "cost_per_call": None,
        "cost_currency": "USD",
        "free_tier_calls": 100,
    },
]

SAMPLE_SCORES = [
    {"service_slug": "resend", "aggregate_recommendation_score": 7.79},
    {"service_slug": "sendgrid", "aggregate_recommendation_score": 6.35},
]

SAMPLE_SERVICE_DOMAIN = [
    {"slug": "sendgrid", "api_domain": "api.sendgrid.com", "name": "SendGrid", "aggregate_recommendation_score": 6.35, "category": "email", "tier_label": "managed", "official_docs": "https://docs.sendgrid.com"},
    {"slug": "resend", "api_domain": "api.resend.com", "name": "Resend", "aggregate_recommendation_score": 7.79, "category": "email", "tier_label": "managed", "official_docs": "https://resend.com/docs"},
]


def _mock_supabase(path: str):
    if path.startswith("capabilities?"):
        return SAMPLE_CAP
    if path.startswith("capability_services?"):
        return SAMPLE_MAPPINGS
    if path.startswith("scores?"):
        return SAMPLE_SCORES
    if path.startswith("services?"):
        if "slug=eq.sendgrid" in path:
            return [SAMPLE_SERVICE_DOMAIN[0]]
        if "slug=eq.resend" in path:
            return [SAMPLE_SERVICE_DOMAIN[1]]
        return SAMPLE_SERVICE_DOMAIN
    if path.startswith("capability_executions?"):
        return []
    if path.startswith("route_explanations?"):
        return []
    return []


def _make_mock_response(status_code: int = 202, json_body: dict | None = None):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_body or {"message": "accepted"}
    resp.text = '{"message": "accepted"}'
    return resp


def _build_patches():
    mock_response = _make_mock_response()

    mock_client = AsyncMock()
    mock_client.request.return_value = mock_response

    mock_pool = MagicMock()
    mock_pool.acquire = AsyncMock(return_value=mock_client)
    mock_pool.release = AsyncMock()

    budget_state = SimpleNamespace(
        budget_usd=None,
        remaining_usd=None,
        period="monthly",
        hard_limit=False,
    )

    return mock_response, mock_pool, budget_state


@pytest.fixture(autouse=True)
def _clear_provider_cache():
    """Clear provider attribution cache between tests to avoid stale state."""
    from services.provider_attribution import clear_provider_cache
    clear_provider_cache()
    yield
    clear_provider_cache()


@pytest.mark.anyio
async def test_v2_execute_includes_explanation_id(app):
    """Verify that v2 execute responses include an explanation_id in _rhumb_v2 metadata."""
    _, mock_pool, budget_state = _build_patches()

    with (
        patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase),
        patch("routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True),
        patch("routes.capability_execute._inject_auth_headers", side_effect=lambda slug, auth, h: h),
        patch("routes.capability_execute.get_pool_manager", return_value=mock_pool),
        patch("routes.capability_execute._budget_enforcer.get_budget", new_callable=AsyncMock, return_value=budget_state),
        patch("services.route_explanation.supabase_insert", new_callable=AsyncMock, return_value=True),
        patch("services.route_explanation.supabase_fetch", new_callable=AsyncMock, return_value=[]),
        patch("services.provider_attribution.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v2/capabilities/email.send/execute",
                json={
                    "parameters": {"to": "test@example.com"},
                    "policy": {"provider_preference": ["sendgrid"]},
                    "credential_mode": "byo",
                    "interface": "rest",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    body = resp.json()
    v2_meta = body["data"]["_rhumb_v2"]
    assert "explanation_id" in v2_meta
    assert v2_meta["explanation_id"] is not None
    assert v2_meta["explanation_id"].startswith("rexp_")


@pytest.mark.anyio
async def test_v2_execute_explanation_persisted(app):
    """Verify that the explanation engine attempts to persist the explanation."""
    _, mock_pool, budget_state = _build_patches()

    with (
        patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase),
        patch("routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True),
        patch("routes.capability_execute._inject_auth_headers", side_effect=lambda slug, auth, h: h),
        patch("routes.capability_execute.get_pool_manager", return_value=mock_pool),
        patch("routes.capability_execute._budget_enforcer.get_budget", new_callable=AsyncMock, return_value=budget_state),
        patch("services.route_explanation.supabase_insert", new_callable=AsyncMock, return_value=True) as mock_supabase_insert,
        patch("services.route_explanation.supabase_fetch", new_callable=AsyncMock, return_value=[]),
        patch("services.provider_attribution.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v2/capabilities/email.send/execute",
                json={
                    "parameters": {"to": "test@example.com"},
                    "credential_mode": "byo",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    # Verify explanation persistence was attempted
    mock_supabase_insert.assert_called()
    # Find the route_explanations insert call
    explanation_calls = [
        call for call in mock_supabase_insert.call_args_list
        if call.args and call.args[0] == "route_explanations"
    ]
    assert len(explanation_calls) >= 1
    row = explanation_calls[0].args[1]
    assert row["explanation_id"].startswith("rexp_")
    assert row["candidates_json"]  # Not empty
    assert row["human_summary"]


@pytest.mark.anyio
async def test_receipt_explanation_endpoint_returns_layer1_message(app):
    """Verify that Layer 1 receipts return a descriptive message, not an explanation."""
    mock_receipt = {
        "receipt_id": "rcpt_l1_test",
        "layer": 1,
        "provider_id": "openai",
    }

    with (
        patch("services.receipt_service.supabase_fetch", new_callable=AsyncMock, return_value=[mock_receipt]),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v2/receipts/rcpt_l1_test/explanation")

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["layer"] == 1
    assert body["data"]["explanation"] is None
    assert "layer 1" in body["data"]["message"].lower()


@pytest.mark.anyio
async def test_receipt_explanation_endpoint_not_found(app):
    """Verify that nonexistent receipt returns a proper error."""
    with (
        patch("services.receipt_service.supabase_fetch", new_callable=AsyncMock, return_value=[]),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v2/receipts/rcpt_nonexistent/explanation")

    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "CAPABILITY_NOT_FOUND"


@pytest.mark.anyio
async def test_receipt_explanation_endpoint_no_explanation_available(app):
    """Verify that a Layer 2 receipt without a stored explanation returns gracefully."""
    mock_receipt = {
        "receipt_id": "rcpt_old_test",
        "layer": 2,
        "provider_id": "resend",
    }

    with (
        patch("services.receipt_service.supabase_fetch", new_callable=AsyncMock, return_value=[mock_receipt]),
        patch("services.route_explanation.supabase_fetch", new_callable=AsyncMock, return_value=[]),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v2/receipts/rcpt_old_test/explanation")

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["explanation"] is None
    assert "predate" in body["data"]["message"].lower()


@pytest.mark.anyio
async def test_receipt_explanation_endpoint_with_stored_explanation(app):
    """Verify that a stored explanation is returned with the spec shape."""
    mock_receipt = {
        "receipt_id": "rcpt_explained",
        "layer": 2,
        "provider_id": "resend",
    }
    mock_explanation = {
        "explanation_id": "rexp_abc123",
        "receipt_id": "rcpt_explained",
        "capability_id": "email.send",
        "created_at": "2026-03-31T11:00:00Z",
        "winner_provider_id": "resend",
        "winner_composite_score": 0.72,
        "winner_reason": "routing_with_policy_filters",
        "candidates_json": json.dumps([
            {
                "provider_id": "resend",
                "eligible": True,
                "composite_score": 0.72,
                "factors": {"an_score": {"value": 7.79, "normalized_score": 0.779, "weight": 0.2, "weighted_contribution": 0.1558}},
            },
            {
                "provider_id": "sendgrid",
                "eligible": True,
                "composite_score": 0.65,
                "factors": {"an_score": {"value": 6.35, "normalized_score": 0.635, "weight": 0.2, "weighted_contribution": 0.127}},
            },
        ]),
        "human_summary": "Resend selected over 1 other candidate.",
        "evaluation_ms": 0.42,
    }

    def _mock_fetch(path: str):
        if path.startswith("execution_receipts?"):
            return [mock_receipt]
        if path.startswith("route_explanations?"):
            return [mock_explanation]
        return []

    with (
        patch("services.receipt_service.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_fetch),
        patch("services.route_explanation.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_fetch),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v2/receipts/rcpt_explained/explanation")

    assert resp.status_code == 200
    body = resp.json()
    data = body["data"]
    assert data["explanation_id"] == "rexp_abc123"
    assert data["receipt_id"] == "rcpt_explained"
    assert data["winner"]["provider_id"] == "resend"
    assert data["winner"]["composite_score"] == 0.72
    assert data["winner"]["selection_reason"] == "routing_with_policy_filters"
    assert len(data["candidates"]) == 2
    assert data["human_summary"] == "Resend selected over 1 other candidate."
