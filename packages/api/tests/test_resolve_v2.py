"""Tests for the initial Resolve v2 compatibility gateway."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app
from schemas.agent_identity import AgentIdentitySchema
from services.budget_enforcer import BudgetStatus

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
    {"slug": "sendgrid", "api_domain": "api.sendgrid.com"},
    {"slug": "resend", "api_domain": "api.resend.com"},
]


def _mock_supabase(path: str):
    if path.startswith("capabilities?"):
        if "id=eq.email.send" in path:
            return SAMPLE_CAP
        return SAMPLE_CAP
    if path.startswith("capability_services?"):
        if "capability_id=eq.email.send" in path:
            return SAMPLE_MAPPINGS
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


@pytest.mark.anyio
async def test_v2_health(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v2/health")

    assert resp.status_code == 200
    assert resp.json() == {
        "status": "ok",
        "version": "2026-03-30",
        "compat_mode": "v1-translate",
        "layer": 2,
    }


@pytest.mark.anyio
async def test_v2_execute_translates_provider_preference_and_wraps_metadata(app):
    _, mock_pool, budget_state = _build_patches()

    with (
        patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase),
        patch("routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True),
        patch("routes.capability_execute._inject_auth_headers", side_effect=lambda slug, auth, h: h),
        patch("routes.capability_execute.get_pool_manager", return_value=mock_pool),
        patch("routes.capability_execute._budget_enforcer.get_budget", new_callable=AsyncMock, return_value=budget_state),
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
    assert resp.headers["X-Rhumb-Compat"] == "v1-translate"
    assert resp.headers["X-Rhumb-Version"] == "2026-03-30"

    body = resp.json()
    assert body["error"] is None
    data = body["data"]
    assert data["provider_used"] == "sendgrid"
    assert data["credential_mode"] == "byo"
    assert data["upstream_status"] == 202
    assert data["_rhumb_v2"]["compat_mode"] == "v1-translate"
    assert data["_rhumb_v2"]["selected_provider"] == "sendgrid"
    assert data["_rhumb_v2"]["policy_applied"] is True
    assert data["_rhumb_v2"]["policy_selected_reason"] == "policy_preference_match"
    assert data["_rhumb_v2"]["policy_candidates"] == ["sendgrid", "resend"]
    assert data["_rhumb_v2"]["receipt_id"] == data.get("receipt_id") or f"rcpt_compat_{data['execution_id']}"

    request_call = mock_pool.acquire.return_value.request.await_args
    assert request_call.kwargs["json"] == {"to": "test@example.com"}
    assert request_call.args == ()


@pytest.mark.anyio
async def test_v2_execute_respects_provider_deny_and_uses_next_allowed_preference(app):
    _, mock_pool, budget_state = _build_patches()

    with (
        patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase),
        patch("routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True),
        patch("routes.capability_execute._inject_auth_headers", side_effect=lambda slug, auth, h: h),
        patch("routes.capability_execute.get_pool_manager", return_value=mock_pool),
        patch("routes.capability_execute._budget_enforcer.get_budget", new_callable=AsyncMock, return_value=budget_state),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v2/capabilities/email.send/execute",
                json={
                    "parameters": {"to": "test@example.com"},
                    "policy": {
                        "provider_preference": ["sendgrid", "resend"],
                        "provider_deny": ["sendgrid"],
                    },
                    "credential_mode": "byo",
                    "interface": "rest",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    body = resp.json()
    data = body["data"]
    assert data["provider_used"] == "resend"
    assert data["_rhumb_v2"]["selected_provider"] == "resend"
    assert data["_rhumb_v2"]["policy_selected_reason"] == "policy_preference_match"
    assert data["_rhumb_v2"]["policy_candidates"] == ["resend"]
    assert data["_rhumb_v2"]["policy_summary"]["provider_deny"] == ["sendgrid"]


@pytest.mark.anyio
async def test_v2_execute_rejects_when_policy_filters_remove_all_providers(app):
    _, mock_pool, budget_state = _build_patches()

    with (
        patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase),
        patch("routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True),
        patch("routes.capability_execute._inject_auth_headers", side_effect=lambda slug, auth, h: h),
        patch("routes.capability_execute.get_pool_manager", return_value=mock_pool),
        patch("routes.capability_execute._budget_enforcer.get_budget", new_callable=AsyncMock, return_value=budget_state),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v2/capabilities/email.send/execute",
                json={
                    "parameters": {"to": "test@example.com"},
                    "policy": {
                        "allow_only": ["mailchimp"],
                    },
                    "credential_mode": "byo",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["code"] == "NO_PROVIDER_AVAILABLE"
    assert "satisfy the execution policy" in body["error"]["message"].lower()
    assert mock_pool.acquire.return_value.request.await_count == 0


@pytest.mark.anyio
async def test_v2_execute_enforces_max_cost_ceiling_before_execution(app):
    _, mock_pool, budget_state = _build_patches()

    with (
        patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase),
        patch("routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True),
        patch("routes.capability_execute._inject_auth_headers", side_effect=lambda slug, auth, h: h),
        patch("routes.capability_execute.get_pool_manager", return_value=mock_pool),
        patch("routes.capability_execute._budget_enforcer.get_budget", new_callable=AsyncMock, return_value=budget_state),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v2/capabilities/email.send/execute",
                json={
                    "parameters": {"to": "test@example.com"},
                    "policy": {
                        "provider_preference": ["sendgrid"],
                        "max_cost_usd": 0.001,
                    },
                    "credential_mode": "byo",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 402  # BUDGET_EXCEEDED per Resolve spec
    body = resp.json()
    assert body["error"]["code"] == "BUDGET_EXCEEDED"
    assert "exceeds policy ceiling" in body["error"]["message"].lower()
    assert mock_pool.acquire.return_value.request.await_count == 0


@pytest.mark.anyio
async def test_v2_execute_rejects_when_durable_agent_budget_is_exhausted(app, _mock_v2_budget_enforcer):
    _, mock_pool, budget_state = _build_patches()
    budget_state.remaining_usd = 0.001
    budget_state.budget_usd = 0.001
    budget_state.spent_usd = 9.999
    budget_state.period = "monthly"
    budget_state.hard_limit = True

    _mock_v2_budget_enforcer.get_budget.return_value = BudgetStatus(
        allowed=False,
        remaining_usd=0.001,
        budget_usd=10.0,
        spent_usd=9.999,
        period="monthly",
        hard_limit=True,
        alert_threshold_pct=80,
        alert_fired=True,
    )

    with (
        patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase),
        patch("routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True),
        patch("routes.capability_execute._inject_auth_headers", side_effect=lambda slug, auth, h: h),
        patch("routes.capability_execute.get_pool_manager", return_value=mock_pool),
        patch("routes.capability_execute._budget_enforcer.get_budget", new_callable=AsyncMock, return_value=budget_state),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v2/capabilities/email.send/execute",
                json={
                    "parameters": {"to": "test@example.com"},
                    "policy": {"provider_preference": ["sendgrid"]},
                    "credential_mode": "byo",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 402
    body = resp.json()
    assert body["error"]["code"] == "BUDGET_EXCEEDED"
    assert "remaining monthly budget" in body["error"]["message"].lower()
    assert body["error"]["budget"] == {
        "budget_usd": 10.0,
        "spent_usd": 9.999,
        "remaining_usd": 0.001,
        "period": "monthly",
        "hard_limit": True,
        "alert_threshold_pct": 80,
        "alert_fired": True,
    }
    assert mock_pool.acquire.return_value.request.await_count == 0


@pytest.mark.anyio
async def test_v2_policy_put_and_get_round_trip(app, _mock_policy_store):
    stored_policy = SimpleNamespace(
        org_id="org_v2_test",
        pin=None,
        provider_preference=["sendgrid"],
        provider_deny=["mailchimp"],
        allow_only=[],
        max_cost_usd=0.01,
        updated_at="2026-03-31T07:00:00Z",
    )
    _mock_policy_store.put_policy.return_value = stored_policy
    _mock_policy_store.get_policy.return_value = stored_policy

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        put_resp = await client.put(
            "/v2/policy",
            json={
                "provider_preference": ["sendgrid"],
                "provider_deny": ["mailchimp"],
                "max_cost_usd": 0.01,
            },
            headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
        )
        get_resp = await client.get("/v2/policy", headers={"X-Rhumb-Key": FAKE_RHUMB_KEY})

    assert put_resp.status_code == 200
    put_body = put_resp.json()
    assert put_body["error"] is None
    assert put_body["data"]["organization_id"] == "org_v2_test"
    assert put_body["data"]["policy"]["provider_preference"] == ["sendgrid"]
    assert put_body["data"]["policy"]["provider_deny"] == ["mailchimp"]
    assert put_body["data"]["policy"]["max_cost_usd"] == 0.01
    assert put_body["data"]["has_policy"] is True
    assert put_body["data"]["_rhumb_v2"]["supported_policy_fields"] == [
        "pin",
        "provider_preference",
        "provider_deny",
        "allow_only",
        "max_cost_usd",
    ]

    _mock_policy_store.put_policy.assert_awaited_once_with(
        "org_v2_test",
        pin=None,
        provider_preference=["sendgrid"],
        provider_deny=["mailchimp"],
        allow_only=[],
        max_cost_usd=0.01,
    )

    assert get_resp.status_code == 200
    get_body = get_resp.json()
    assert get_body["error"] is None
    assert get_body["data"]["policy"]["provider_preference"] == ["sendgrid"]
    assert get_body["data"]["policy"]["provider_deny"] == ["mailchimp"]
    assert get_body["data"]["updated_at"] == "2026-03-31T07:00:00Z"


@pytest.mark.anyio
async def test_v2_execute_merges_account_policy_with_inline_override(app, _mock_policy_store):
    _, mock_pool, budget_state = _build_patches()
    _mock_policy_store.get_policy.return_value = SimpleNamespace(
        org_id="org_v2_test",
        pin=None,
        provider_preference=["sendgrid"],
        provider_deny=[],
        allow_only=[],
        max_cost_usd=None,
        updated_at="2026-03-31T07:00:00Z",
    )

    with (
        patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase),
        patch("routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True),
        patch("routes.capability_execute._inject_auth_headers", side_effect=lambda slug, auth, h: h),
        patch("routes.capability_execute.get_pool_manager", return_value=mock_pool),
        patch("routes.capability_execute._budget_enforcer.get_budget", new_callable=AsyncMock, return_value=budget_state),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v2/capabilities/email.send/execute",
                json={
                    "parameters": {"to": "test@example.com"},
                    "policy": {"provider_deny": ["sendgrid"]},
                    "credential_mode": "byo",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["provider_used"] == "resend"
    assert data["_rhumb_v2"]["selected_provider"] == "resend"
    assert data["_rhumb_v2"]["policy_selected_reason"] == "policy_single_candidate"
    assert data["_rhumb_v2"]["policy_summary"]["provider_preference"] == ["sendgrid"]
    assert data["_rhumb_v2"]["policy_summary"]["provider_deny"] == ["sendgrid"]
    assert data["_rhumb_v2"]["policy_source"] == {
        "scope": "organization",
        "has_account_policy": True,
        "organization_fields": ["provider_preference"],
        "inline_fields": ["provider_deny"],
    }


@pytest.mark.anyio
async def test_v2_execute_inline_empty_list_clears_stored_preference(app, _mock_policy_store):
    _, mock_pool, budget_state = _build_patches()
    _mock_policy_store.get_policy.return_value = SimpleNamespace(
        org_id="org_v2_test",
        pin=None,
        provider_preference=["sendgrid"],
        provider_deny=[],
        allow_only=[],
        max_cost_usd=None,
        updated_at="2026-03-31T07:00:00Z",
    )

    with (
        patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase),
        patch("routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True),
        patch("routes.capability_execute._inject_auth_headers", side_effect=lambda slug, auth, h: h),
        patch("routes.capability_execute.get_pool_manager", return_value=mock_pool),
        patch("routes.capability_execute._budget_enforcer.get_budget", new_callable=AsyncMock, return_value=budget_state),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v2/capabilities/email.send/execute",
                json={
                    "parameters": {"to": "test@example.com"},
                    "policy": {"provider_preference": []},
                    "credential_mode": "byo",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["provider_used"] == "resend"
    assert data["_rhumb_v2"]["policy_applied"] is False
    assert data["_rhumb_v2"]["policy_summary"]["provider_preference"] == []
    assert data["_rhumb_v2"]["policy_source"] == {
        "scope": "organization",
        "has_account_policy": True,
        "organization_fields": [],
        "inline_fields": ["provider_preference"],
    }
