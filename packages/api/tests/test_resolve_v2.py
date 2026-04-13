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
from services.policy_engine import PolicyEngine

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


@pytest.fixture(autouse=True)
def _mock_v1_execute_runtime_seams():
    mock_rate_limiter = MagicMock()
    mock_rate_limiter.check_and_increment = AsyncMock(return_value=(True, 29))

    mock_kill_switch_registry = MagicMock()
    mock_kill_switch_registry.is_blocked.return_value = (False, None)

    with (
        patch("routes.capability_execute._get_rate_limiter", new=AsyncMock(return_value=mock_rate_limiter)),
        patch("routes.capability_execute.init_kill_switch_registry", new=AsyncMock(return_value=mock_kill_switch_registry)),
        patch("routes.capability_execute.check_billing_health", new=AsyncMock(return_value=(True, None))),
        patch("routes.capability_execute.supabase_insert_required", new=AsyncMock(return_value=True)),
        patch("routes.capability_execute.supabase_patch_required", new=AsyncMock(return_value=True)),
        patch(
            "routes.capability_execute._budget_enforcer.check_and_decrement",
            new=AsyncMock(
                return_value=BudgetStatus(
                    allowed=True,
                    remaining_usd=None,
                    budget_usd=None,
                    spent_usd=None,
                    period=None,
                    hard_limit=None,
                    alert_threshold_pct=None,
                    alert_fired=None,
                )
            ),
        ),
        patch("routes.capability_execute._budget_enforcer.release", new=AsyncMock(return_value=None)),
        patch(
            "routes.capability_execute._credit_deduction.deduct",
            new=AsyncMock(
                return_value=SimpleNamespace(
                    allowed=True,
                    remaining_cents=10_000,
                    reason=None,
                    billing_unavailable=False,
                )
            ),
        ),
        patch(
            "routes.capability_execute._credit_deduction.release",
            new=AsyncMock(
                return_value=SimpleNamespace(
                    released=True,
                    remaining_cents=10_000,
                    reason=None,
                    billing_unavailable=False,
                )
            ),
        ),
    ):
        yield


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

DB_DIRECT_CAPABILITY = {
    "id": "db.query.read",
    "domain": "database",
    "action": "query_read",
    "description": "Execute a read-only SQL query against a PostgreSQL database",
    "input_hint": "connection_ref, query, params (optional), max_rows, timeout_ms",
    "outcome": "Query results: column metadata + rows, bounded by row limit and timeout",
}


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


def _mock_db_direct_supabase(path: str):
    if path.startswith("capabilities?"):
        return [DB_DIRECT_CAPABILITY]
    if path.startswith("capability_services?"):
        return []
    if path.startswith("scores?"):
        return []
    if path.startswith("services?"):
        return []
    if path.startswith("bundle_capabilities?"):
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
async def test_v2_resolve_wraps_metadata_and_rewrites_nested_urls(app):
    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v2/capabilities/email.send/resolve",
                params={"credential_mode": "byo"},
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    assert resp.headers["X-Rhumb-Compat"] == "v1-translate"

    data = resp.json()["data"]
    assert data["_rhumb_v2"] == {
        "api_version": "v2-alpha",
        "compat_mode": "v1-translate",
        "layer": 2,
    }
    assert data["execute_hint"]["preferred_credential_mode"] == "byok"
    assert data["execute_hint"]["credential_modes_url"] == "/v2/capabilities/email.send/credential-modes"
    assert all(provider["credential_modes"] == ["byok"] for provider in data["providers"])


@pytest.mark.anyio
async def test_v2_resolve_rewrites_nested_recovery_urls_for_alternate_handoff(app):
    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v2/capabilities/email.send/resolve",
                params={"credential_mode": "agent_vault"},
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["_rhumb_v2"] == {
        "api_version": "v2-alpha",
        "compat_mode": "v1-translate",
        "layer": 2,
    }
    assert data["providers"] == []
    assert data["execute_hint"] is None

    recovery_hint = data["recovery_hint"]
    assert recovery_hint["reason"] == "no_providers_match_credential_mode"
    assert recovery_hint["requested_credential_mode"] == "agent_vault"
    assert recovery_hint["resolve_url"] == "/v2/capabilities/email.send/resolve"
    assert recovery_hint["credential_modes_url"] == "/v2/capabilities/email.send/credential-modes"
    assert recovery_hint["supported_provider_slugs"] == ["resend", "sendgrid"]
    assert recovery_hint["supported_credential_modes"] == ["byok"]
    assert recovery_hint["alternate_execute_hint"] == {
        "preferred_provider": "resend",
        "endpoint_pattern": "POST /emails",
        "estimated_cost_usd": None,
        "auth_method": "api_key",
        "credential_modes": ["byok"],
        "configured": False,
        "credential_modes_url": "/v2/capabilities/email.send/credential-modes",
        "preferred_credential_mode": "byok",
        "setup_hint": "Set RHUMB_CREDENTIAL_RESEND_API_KEY environment variable or configure via proxy credentials",
        "selection_reason": "highest_ranked_provider",
        "fallback_providers": ["sendgrid"],
    }


@pytest.mark.anyio
async def test_v2_resolve_preserves_blocker_hints_when_no_alternate_handoff(app):
    async def mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return SAMPLE_CAP
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "sendgrid",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": None,
                    "cost_per_call": "0.001",
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                },
                {
                    "service_slug": "resend",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": None,
                    "cost_per_call": None,
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                },
            ]
        if path.startswith("scores?"):
            return [
                {"service_slug": "resend", "aggregate_recommendation_score": 7.79},
                {"service_slug": "sendgrid", "aggregate_recommendation_score": 6.35},
            ]
        if path.startswith("services?"):
            return [
                {"slug": "sendgrid", "name": "SendGrid"},
                {"slug": "resend", "name": "Resend"},
            ]
        if path.startswith("capability_executions?"):
            return []
        return []

    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v2/capabilities/email.send/resolve",
                params={"credential_mode": "agent_vault"},
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["providers"] == []
    assert data["execute_hint"] is None

    recovery_hint = data["recovery_hint"]
    assert recovery_hint["reason"] == "no_providers_match_credential_mode"
    assert recovery_hint["requested_credential_mode"] == "agent_vault"
    assert recovery_hint["resolve_url"] == "/v2/capabilities/email.send/resolve"
    assert recovery_hint["credential_modes_url"] == "/v2/capabilities/email.send/credential-modes"
    assert recovery_hint["supported_provider_slugs"] == ["resend", "sendgrid"]
    assert recovery_hint["supported_credential_modes"] == ["byok"]
    assert recovery_hint["not_execute_ready_provider_slugs"] == ["resend", "sendgrid"]
    assert recovery_hint["setup_handoff"] == {
        "preferred_provider": "resend",
        "estimated_cost_usd": None,
        "auth_method": "api_key",
        "credential_modes": ["byok"],
        "configured": False,
        "credential_modes_url": "/v2/capabilities/email.send/credential-modes",
        "preferred_credential_mode": "byok",
        "setup_hint": "Set RHUMB_CREDENTIAL_RESEND_API_KEY environment variable or configure via proxy credentials",
        "selection_reason": "highest_ranked_provider",
    }
    assert "alternate_execute_hint" not in recovery_hint


@pytest.mark.anyio
async def test_v2_resolve_rewrites_filtered_no_execute_ready_alternate_handoff(app):
    async def mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return SAMPLE_CAP
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "resend",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": None,
                    "cost_per_call": None,
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                },
                {
                    "service_slug": "gmail",
                    "credential_modes": ["agent_vault"],
                    "auth_method": "oauth",
                    "endpoint_pattern": "POST /gmail/v1/users/me/messages/send",
                    "cost_per_call": None,
                    "cost_currency": "USD",
                    "free_tier_calls": None,
                },
            ]
        if path.startswith("scores?"):
            return [
                {"service_slug": "resend", "aggregate_recommendation_score": 8.79},
                {"service_slug": "gmail", "aggregate_recommendation_score": 7.2},
            ]
        if path.startswith("services?"):
            return [
                {"slug": "resend", "name": "Resend"},
                {"slug": "gmail", "name": "Gmail"},
            ]
        if path.startswith("capability_executions?"):
            return []
        return []

    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v2/capabilities/email.send/resolve",
                params={"credential_mode": "byok"},
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["_rhumb_v2"] == {
        "api_version": "v2-alpha",
        "compat_mode": "v1-translate",
        "layer": 2,
    }
    assert [provider["service_slug"] for provider in data["providers"]] == ["resend"]
    assert data["fallback_chain"] == []
    assert data["execute_hint"] is None

    recovery_hint = data["recovery_hint"]
    assert recovery_hint["reason"] == "no_execute_ready_providers"
    assert recovery_hint["requested_credential_mode"] == "byok"
    assert recovery_hint["resolve_url"] == "/v2/capabilities/email.send/resolve"
    assert recovery_hint["credential_modes_url"] == "/v2/capabilities/email.send/credential-modes"
    assert recovery_hint["supported_provider_slugs"] == ["resend", "gmail"]
    assert recovery_hint["supported_credential_modes"] == ["agent_vault", "byok"]
    assert recovery_hint["not_execute_ready_provider_slugs"] == ["resend"]
    assert recovery_hint["alternate_execute_hint"] == {
        "preferred_provider": "gmail",
        "endpoint_pattern": "POST /gmail/v1/users/me/messages/send",
        "estimated_cost_usd": None,
        "auth_method": "oauth",
        "credential_modes": ["agent_vault"],
        "configured": False,
        "credential_modes_url": "/v2/capabilities/email.send/credential-modes",
        "preferred_credential_mode": "agent_vault",
        "setup_hint": "Complete the ceremony at GET /v1/services/gmail/ceremony, then pass token via X-Agent-Token header",
        "setup_url": "/v1/services/gmail/ceremony",
        "selection_reason": "higher_ranked_provider_not_execute_ready",
        "skipped_provider_slugs": ["resend"],
        "not_execute_ready_provider_slugs": ["resend"],
    }


@pytest.mark.anyio
async def test_v2_resolve_rewrites_direct_execute_endpoint_pattern(app):
    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_db_direct_supabase):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v2/capabilities/db.query.read/resolve")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["_rhumb_v2"] == {
        "api_version": "v2-alpha",
        "compat_mode": "v1-translate",
        "layer": 2,
    }
    assert data["providers"][0]["service_slug"] == "postgresql"
    assert data["providers"][0]["endpoint_pattern"] == "POST /v2/capabilities/db.query.read/execute"
    assert data["execute_hint"] == {
        "preferred_provider": "postgresql",
        "endpoint_pattern": "POST /v2/capabilities/db.query.read/execute",
        "estimated_cost_usd": None,
        "auth_method": "connection_ref",
        "credential_modes": ["byok", "agent_vault"],
        "configured": False,
        "credential_modes_url": "/v2/capabilities/db.query.read/credential-modes",
        "preferred_credential_mode": "agent_vault",
        "setup_hint": "Hosted/default path: set credential_mode to 'agent_vault' and pass either a short-lived signed rhdbv1 DB vault token in X-Agent-Token or, as a compatibility bridge, a transient PostgreSQL DSN in X-Agent-Token. The raw DSN is never stored.",
        "setup_url": "/v1/services/postgresql/ceremony",
        "selection_reason": "highest_ranked_provider",
    }


@pytest.mark.anyio
async def test_v2_resolve_rewrites_direct_recovery_alternate_execute_endpoint_pattern(app):
    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_db_direct_supabase):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v2/capabilities/db.query.read/resolve",
                params={"credential_mode": "rhumb_managed"},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["_rhumb_v2"] == {
        "api_version": "v2-alpha",
        "compat_mode": "v1-translate",
        "layer": 2,
    }
    assert data["providers"] == []
    assert data["execute_hint"] is None

    recovery_hint = data["recovery_hint"]
    assert recovery_hint == {
        "reason": "no_providers_match_credential_mode",
        "requested_credential_mode": "rhumb_managed",
        "resolve_url": "/v2/capabilities/db.query.read/resolve",
        "credential_modes_url": "/v2/capabilities/db.query.read/credential-modes",
        "supported_provider_slugs": ["postgresql"],
        "supported_credential_modes": ["agent_vault", "byok"],
        "alternate_execute_hint": {
            "preferred_provider": "postgresql",
            "endpoint_pattern": "POST /v2/capabilities/db.query.read/execute",
            "estimated_cost_usd": None,
            "auth_method": "connection_ref",
            "credential_modes": ["byok", "agent_vault"],
            "configured": False,
            "credential_modes_url": "/v2/capabilities/db.query.read/credential-modes",
            "preferred_credential_mode": "agent_vault",
            "setup_hint": "Hosted/default path: set credential_mode to 'agent_vault' and pass either a short-lived signed rhdbv1 DB vault token in X-Agent-Token or, as a compatibility bridge, a transient PostgreSQL DSN in X-Agent-Token. The raw DSN is never stored.",
            "setup_url": "/v1/services/postgresql/ceremony",
            "selection_reason": "highest_ranked_provider",
        },
    }


@pytest.mark.anyio
async def test_v2_credential_modes_wraps_metadata(app):
    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v2/capabilities/email.send/credential-modes",
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["_rhumb_v2"] == {
        "api_version": "v2-alpha",
        "compat_mode": "v1-translate",
        "layer": 2,
    }
    assert data["providers"][0]["modes"][0]["mode"] == "byok"


@pytest.mark.anyio
async def test_v2_resolve_not_found_rewrites_search_url(app):
    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, return_value=[]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v2/capabilities/nonexistent/resolve")

    assert resp.status_code == 404
    body = resp.json()
    assert body["search_url"] == "/v2/capabilities?search=nonexistent"


@pytest.mark.anyio
async def test_v2_estimate_rewrites_recovery_urls_and_canonicalizes_mode(app):
    estimate_resp = MagicMock(spec=httpx.Response)
    estimate_resp.status_code = 402
    estimate_resp.json.return_value = {
        "error": "payment_required",
        "message": "Payment required.",
        "resolve_url": "/v1/capabilities/email.send/resolve?credential_mode=byok",
        "estimate_url": "/v1/capabilities/email.send/execute/estimate?provider=sendgrid&credential_mode=byok",
    }
    estimate_resp.headers = {}

    with patch("routes.resolve_v2._forward_internal", new=AsyncMock(return_value=estimate_resp)) as mock_forward:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v2/capabilities/email.send/execute/estimate",
                params={"credential_mode": "byo", "provider": "sendgrid"},
            )

    assert resp.status_code == 402
    body = resp.json()
    assert body["resolve_url"] == "/v2/capabilities/email.send/resolve?credential_mode=byok"
    assert body["estimate_url"] == "/v2/capabilities/email.send/execute/estimate?provider=sendgrid&credential_mode=byok"
    assert mock_forward.await_args.kwargs["params"] == {
        "credential_mode": "byok",
        "provider": "sendgrid",
    }


@pytest.mark.anyio
async def test_policy_engine_matches_provider_preference_aliases():
    engine = PolicyEngine()
    auto_selector = AsyncMock(return_value={"service_slug": "elasticsearch"})
    policy = SimpleNamespace(
        pin=None,
        provider_preference=["brave-search-api"],
        provider_deny=[],
        allow_only=[],
        max_cost_usd=None,
    )

    decision = await engine.resolve_provider(
        mappings=[
            {"service_slug": "elasticsearch"},
            {"service_slug": "brave-search"},
        ],
        agent_id="agent_v2_test",
        policy=policy,
        auto_selector=auto_selector,
    )

    assert decision.selected_provider == "brave-search"
    assert decision.selected_reason == "policy_preference_match"
    auto_selector.assert_not_awaited()


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
    assert data["credential_mode"] == "byok"
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
async def test_v2_execute_uses_single_canonical_receipt_id_and_skips_v1_receipt(app):
    estimate_resp = MagicMock(spec=httpx.Response)
    estimate_resp.status_code = 200
    estimate_resp.json.return_value = {
        "data": {
            "provider": "sendgrid",
            "cost_estimate_usd": 0.01,
            "endpoint_pattern": "POST /v3/mail/send",
        }
    }
    estimate_resp.headers = {}

    execute_resp = MagicMock(spec=httpx.Response)
    execute_resp.status_code = 200
    execute_resp.json.return_value = {
        "data": {
            "execution_id": "exec_v2_test",
            "provider_used": "sendgrid",
            "credential_mode": "byo",
            "upstream_status": 202,
            "result": {"queued": True},
        },
        "error": None,
    }
    execute_resp.headers = {}

    mock_receipt = MagicMock()
    mock_receipt.receipt_id = "rcpt_v2_canonical"

    mock_attribution = MagicMock()
    mock_attribution.to_response_headers.return_value = {
        "X-Rhumb-Receipt-Id": "rcpt_v2_canonical",
        "X-Rhumb-Provider": "sendgrid",
        "X-Rhumb-Layer": "2",
    }
    mock_attribution.to_rhumb_block.return_value = {"receipt_id": "rcpt_v2_canonical"}

    with (
        patch("routes.resolve_v2._forward_internal", new=AsyncMock(side_effect=[estimate_resp, execute_resp])) as mock_forward,
        patch("routes.resolve_v2._evaluate_provider_policy", new=AsyncMock(return_value=SimpleNamespace(decision=None, all_mappings=[], eligible_mappings=[]))),
        patch("routes.resolve_v2.get_receipt_service") as mock_receipt_svc,
        patch("routes.resolve_v2.build_attribution", new=AsyncMock(return_value=mock_attribution)) as mock_build_attribution,
        patch("routes.resolve_v2.build_explanation", return_value=SimpleNamespace(explanation_id="rexp_test")),
        patch("routes.resolve_v2.store_explanation"),
    ):
        mock_receipt_svc.return_value.create_receipt = AsyncMock(return_value=mock_receipt)
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
    data = resp.json()["data"]
    assert data["receipt_id"] == "rcpt_v2_canonical"
    assert data["_rhumb_v2"]["receipt_id"] == "rcpt_v2_canonical"
    assert data["_rhumb"]["receipt_id"] == "rcpt_v2_canonical"

    execute_call = mock_forward.await_args_list[1]
    estimate_call = mock_forward.await_args_list[0]
    assert estimate_call.kwargs["params"]["credential_mode"] == "byok"
    assert execute_call.kwargs["json_body"]["credential_mode"] == "byok"
    assert execute_call.kwargs["extra_headers"] == {"X-Rhumb-Skip-Receipt": "true"}
    assert mock_build_attribution.await_args.kwargs["credential_mode"] == "byok"


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
