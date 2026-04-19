"""Focused durable-event coverage for capability execute."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import json
import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app
from middleware import rate_limit as rate_limit_middleware
from schemas.agent_identity import AgentIdentitySchema
from services.audit_trail import AuditEventType, AuditTrail
from services.billing_events import BillingEventStream, BillingEventType

FAKE_RHUMB_KEY = "rhumb_test_key_cap_exec"


@pytest.fixture
def app():
    return create_app()


def _mock_agent() -> AgentIdentitySchema:
    return AgentIdentitySchema(
        agent_id="agent_cap_exec_test",
        name="cap-exec-test",
        organization_id="org_cap_exec_test",
    )


@pytest.fixture(autouse=True)
def _reset_http_rate_limit_buckets():
    rate_limit_middleware._buckets.clear()
    yield
    rate_limit_middleware._buckets.clear()


@pytest.fixture(autouse=True)
def _mock_identity_store():
    mock_store = MagicMock()
    mock_store.verify_api_key_with_agent = AsyncMock(return_value=_mock_agent())
    with patch("routes.capability_execute._get_identity_store", return_value=mock_store):
        yield mock_store


@pytest.fixture(autouse=True)
def _mock_rate_limiter():
    mock_limiter = MagicMock()
    mock_limiter.check_and_increment = AsyncMock(return_value=(True, 29))
    with patch(
        "routes.capability_execute._get_rate_limiter",
        new_callable=AsyncMock,
        return_value=mock_limiter,
    ):
        yield mock_limiter


@pytest.fixture(autouse=True)
def _mock_kill_switch_registry():
    mock_registry = MagicMock()
    mock_registry.is_blocked.return_value = (False, None)
    with patch(
        "routes.capability_execute.init_kill_switch_registry",
        new_callable=AsyncMock,
        return_value=mock_registry,
    ):
        yield mock_registry


@pytest.fixture(autouse=True)
def _mock_billing_health():
    with patch(
        "routes.capability_execute.check_billing_health",
        new_callable=AsyncMock,
        return_value=(True, "ok"),
    ):
        yield


@pytest.fixture(autouse=True)
def _mock_required_execution_insert():
    with patch(
        "routes.capability_execute.supabase_insert_required",
        new_callable=AsyncMock,
        return_value=None,
    ):
        yield


@pytest.fixture(autouse=True)
def _mock_required_execution_patch():
    with patch(
        "routes.capability_execute.supabase_patch_required",
        new_callable=AsyncMock,
        return_value=[{}],
    ):
        yield


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

MANAGED_SAMPLE_MAPPINGS = [
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
        "credential_modes": ["byo", "rhumb_managed"],
        "auth_method": "api_key",
        "endpoint_pattern": "POST /emails",
        "cost_per_call": None,
        "cost_currency": "USD",
        "free_tier_calls": 100,
    },
]

SEARCH_CAP = [
    {
        "id": "search.query",
        "domain": "search",
        "action": "query",
        "description": "Web search",
    },
]

SEARCH_MAPPINGS = [
    {
        "service_slug": "brave-search",
        "credential_modes": ["byo"],
        "auth_method": "api_key",
        "endpoint_pattern": "GET /res/v1/web/search",
        "cost_per_call": "0.01",
        "cost_currency": "USD",
        "free_tier_calls": 100,
    },
]

SEARCH_SCORES = [{"service_slug": "brave-search", "aggregate_recommendation_score": 8.9}]

SEARCH_SERVICE_DOMAIN = [{"slug": "brave-search", "api_domain": "api.search.brave.com"}]


def _mock_supabase(path: str):
    if path.startswith("capabilities?"):
        if "id=eq.email.send" in path:
            return SAMPLE_CAP
        return []
    if path.startswith("capability_services?"):
        if "capability_id=eq.email.send" in path:
            return SAMPLE_MAPPINGS
        return []
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


def _mock_supabase_with_managed_option(path: str):
    if path.startswith("capability_services?") and "capability_id=eq.email.send" in path:
        return MANAGED_SAMPLE_MAPPINGS
    return _mock_supabase(path)


def _mock_search_supabase(path: str):
    if path.startswith("capabilities?"):
        if "id=eq.search.query" in path:
            return SEARCH_CAP
        return []
    if path.startswith("capability_services?"):
        if "capability_id=eq.search.query" in path:
            return SEARCH_MAPPINGS
        return []
    if path.startswith("scores?"):
        return SEARCH_SCORES
    if path.startswith("services?"):
        if "slug=eq.brave-search" in path:
            return SEARCH_SERVICE_DOMAIN
        return SEARCH_SERVICE_DOMAIN
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
    return mock_response, mock_pool


@pytest.mark.anyio
async def test_execute_emits_billing_and_audit_events_on_success(app):
    _, mock_pool = _build_patches()
    mock_billing_stream = MagicMock()
    mock_audit_trail = MagicMock()
    mock_receipt_service = MagicMock()
    mock_receipt_service.create_receipt = AsyncMock(
        return_value=MagicMock(receipt_id="rcpt_test_success")
    )

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase,
        ),
        patch(
            "routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True
        ),
        patch(
            "routes.capability_execute._inject_auth_request_parts",
            side_effect=lambda slug, auth, h, body, params: (h, body, params),
        ),
        patch(
            "routes.capability_execute.check_agent_exec_rate_limit",
            new_callable=AsyncMock,
            return_value=(True, 29),
        ),
        patch("routes.capability_execute.get_pool_manager", return_value=mock_pool),
        patch("routes.capability_execute.get_billing_event_stream", return_value=mock_billing_stream),
        patch("routes.capability_execute.get_audit_trail", return_value=mock_audit_trail),
        patch("routes.capability_execute.get_receipt_service", return_value=mock_receipt_service),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
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

    mock_billing_stream.emit.assert_called_once_with(
        BillingEventType.EXECUTION_CHARGED,
        org_id="org_cap_exec_test",
        amount_usd_cents=1,
        receipt_id="rcpt_test_success",
        execution_id=data["execution_id"],
        capability_id="email.send",
        provider_slug="sendgrid",
        metadata={
            "layer": 2,
            "credential_mode": "byok",
            "interface": "rest",
            "billing_status": "billed",
        },
    )

    mock_audit_trail.record.assert_called_once()
    args, kwargs = mock_audit_trail.record.call_args
    assert args == (AuditEventType.EXECUTION_COMPLETED, "capability.execute")
    assert kwargs["org_id"] == "org_cap_exec_test"
    assert kwargs["agent_id"] == "agent_cap_exec_test"
    assert kwargs["principal"] == "agent_cap_exec_test"
    assert kwargs["resource_type"] == "capability_execution"
    assert kwargs["resource_id"] == data["execution_id"]
    assert kwargs["receipt_id"] == "rcpt_test_success"
    assert kwargs["execution_id"] == data["execution_id"]
    assert kwargs["provider_slug"] == "sendgrid"
    assert kwargs["detail"]["capability_id"] == "email.send"
    assert kwargs["detail"]["credential_mode"] == "byok"
    assert kwargs["detail"]["interface"] == "rest"
    assert kwargs["detail"]["upstream_status"] == 202
    assert kwargs["detail"]["billing_status"] == "billed"


@pytest.mark.anyio
async def test_execute_emits_billing_and_audit_events_on_upstream_failure(app):
    _, mock_pool = _build_patches()
    mock_pool.acquire.return_value.request.return_value = _make_mock_response(
        status_code=500,
        json_body={"error": "upstream boom"},
    )
    mock_billing_stream = MagicMock()
    mock_audit_trail = MagicMock()
    mock_receipt_service = MagicMock()
    mock_receipt_service.create_receipt = AsyncMock(
        return_value=MagicMock(receipt_id="rcpt_test_failure")
    )

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase,
        ),
        patch(
            "routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True
        ),
        patch(
            "routes.capability_execute._inject_auth_request_parts",
            side_effect=lambda slug, auth, h, body, params: (h, body, params),
        ),
        patch(
            "routes.capability_execute.check_agent_exec_rate_limit",
            new_callable=AsyncMock,
            return_value=(True, 29),
        ),
        patch("routes.capability_execute.get_pool_manager", return_value=mock_pool),
        patch("routes.capability_execute.get_billing_event_stream", return_value=mock_billing_stream),
        patch("routes.capability_execute.get_audit_trail", return_value=mock_audit_trail),
        patch("routes.capability_execute.get_receipt_service", return_value=mock_receipt_service),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
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
    assert data["upstream_status"] == 500

    mock_billing_stream.emit.assert_called_once_with(
        BillingEventType.EXECUTION_FAILED_NO_CHARGE,
        org_id="org_cap_exec_test",
        amount_usd_cents=0,
        receipt_id="rcpt_test_failure",
        execution_id=data["execution_id"],
        capability_id="email.send",
        provider_slug="sendgrid",
        metadata={
            "layer": 2,
            "credential_mode": "byok",
            "interface": "rest",
            "billing_status": "refunded",
            "error": "upstream boom",
        },
    )

    mock_audit_trail.record.assert_called_once()
    args, kwargs = mock_audit_trail.record.call_args
    assert args == (AuditEventType.EXECUTION_FAILED, "capability.execute")
    assert kwargs["receipt_id"] == "rcpt_test_failure"
    assert kwargs["provider_slug"] == "sendgrid"
    assert kwargs["detail"]["credential_mode"] == "byok"
    assert kwargs["detail"]["upstream_status"] == 500
    assert kwargs["detail"]["billing_status"] == "refunded"
    assert kwargs["detail"]["error"] == "upstream boom"


@pytest.mark.anyio
async def test_execute_managed_emits_billing_and_audit_events(app):
    managed_mapping = dict(MANAGED_SAMPLE_MAPPINGS[1])
    managed_mapping["cost_per_call"] = "0.02"

    async def mock_execute(
        self,
        capability_id,
        agent_id,
        body=None,
        params=None,
        service_slug=None,
        interface="rest",
        execution_id=None,
    ):
        return {
            "capability_id": capability_id,
            "provider_used": "resend",
            "credential_mode": "rhumb_managed",
            "upstream_status": 200,
            "upstream_response": {"id": "msg_managed_emit"},
            "latency_ms": 15.0,
            "execution_id": execution_id,
        }

    mock_billing_stream = MagicMock()
    mock_audit_trail = MagicMock()
    mock_receipt_service = MagicMock()
    mock_receipt_service.create_receipt = AsyncMock(
        return_value=MagicMock(receipt_id="rcpt_managed_success")
    )

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase_with_managed_option,
        ),
        patch(
            "routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True
        ),
        patch(
            "routes.capability_execute._resolve_managed_provider_mapping",
            new_callable=AsyncMock,
            return_value=managed_mapping,
        ),
        patch(
            "routes.capability_execute.check_agent_exec_rate_limit",
            new_callable=AsyncMock,
            return_value=(True, 29),
        ),
        patch(
            "routes.capability_execute.check_managed_daily_limit",
            new_callable=AsyncMock,
            return_value=(True, 199),
        ),
        patch(
            "services.upstream_budget.claim_provider_budget",
            new_callable=AsyncMock,
            return_value=(True, "ok"),
        ),
        patch("services.rhumb_managed.RhumbManagedExecutor.execute", mock_execute),
        patch("routes.capability_execute.get_billing_event_stream", return_value=mock_billing_stream),
        patch("routes.capability_execute.get_audit_trail", return_value=mock_audit_trail),
        patch("routes.capability_execute.get_receipt_service", return_value=mock_receipt_service),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/email.send/execute",
                json={"body": {"to": "test@example.com"}},
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]

    mock_billing_stream.emit.assert_called_once_with(
        BillingEventType.EXECUTION_CHARGED,
        org_id="org_cap_exec_test",
        amount_usd_cents=2,
        receipt_id="rcpt_managed_success",
        execution_id=data["execution_id"],
        capability_id="email.send",
        provider_slug="resend",
        metadata={
            "layer": 2,
            "credential_mode": "rhumb_managed",
            "interface": "rest",
            "billing_status": "billed",
        },
    )

    mock_audit_trail.record.assert_called_once()
    args, kwargs = mock_audit_trail.record.call_args
    assert args == (AuditEventType.EXECUTION_COMPLETED, "capability.execute")
    assert kwargs["receipt_id"] == "rcpt_managed_success"
    assert kwargs["provider_slug"] == "resend"
    assert kwargs["detail"]["credential_mode"] == "rhumb_managed"
    assert kwargs["detail"]["upstream_status"] == 200
    assert kwargs["detail"]["billing_status"] == "billed"


@pytest.mark.anyio
async def test_execute_upstream_failure_canonicalizes_alias_text_in_durable_billing_and_audit_events(app):
    raw_upstream_response = {
        "provider_used": "brave-search-api",
        "selected_provider": "brave-search-api",
        "fallback_provider": "people-data-labs",
        "message": "brave-search-api upstream failed after pdl fallback warmed",
        "error_message": "brave-search-api failed before pdl fallback",
        "result": {
            "provider_slug": "brave-search-api",
            "fallback_provider": "people-data-labs",
            "supported_provider_slugs": ["brave-search-api", "people-data-labs"],
            "detail": "Retry brave-search-api later or switch to pdl",
        },
    }
    mock_response, mock_pool = _build_patches()
    mock_response.status_code = 502
    mock_response.json.return_value = raw_upstream_response
    mock_response.text = json.dumps(raw_upstream_response)

    billing_stream = BillingEventStream()
    audit_trail = AuditTrail()
    mock_receipt_service = MagicMock()
    mock_receipt_service.create_receipt = AsyncMock(
        return_value=MagicMock(receipt_id="rcpt_durable_canonical_context_failure")
    )
    mock_attribution = MagicMock()
    mock_attribution.to_rhumb_block.return_value = {"provider": {"id": "brave-search-api"}}
    mock_attribution.to_response_headers.return_value = {"X-Rhumb-Provider": "brave-search-api"}

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_search_supabase,
        ),
        patch(
            "routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True
        ),
        patch(
            "routes.capability_execute._inject_auth_request_parts",
            side_effect=lambda slug, auth, h, body, params: (h, body, params),
        ),
        patch(
            "routes.capability_execute.check_agent_exec_rate_limit",
            new_callable=AsyncMock,
            return_value=(True, 29),
        ),
        patch("routes.capability_execute.get_pool_manager", return_value=mock_pool),
        patch("routes.capability_execute.get_billing_event_stream", return_value=billing_stream),
        patch("routes.capability_execute.get_audit_trail", return_value=audit_trail),
        patch("routes.capability_execute.get_receipt_service", return_value=mock_receipt_service),
        patch(
            "routes.capability_execute.build_attribution",
            new_callable=AsyncMock,
            return_value=mock_attribution,
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/search.query/execute",
                json={
                    "provider": "brave-search-api",
                    "credential_mode": "byok",
                    "method": "GET",
                    "path": "/res/v1/web/search",
                    "body": {"q": "Rhumb API agent infrastructure"},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["provider_used"] == "brave-search-api"
    assert data["upstream_status"] == 502
    assert data["receipt_id"] == "rcpt_durable_canonical_context_failure"
    assert resp.headers["X-Rhumb-Provider"] == "brave-search-api"

    billing_event = billing_stream.query(org_id="org_cap_exec_test", limit=1)[0]
    assert billing_event.event_type == BillingEventType.EXECUTION_FAILED_NO_CHARGE
    assert billing_event.provider_slug == "brave-search-api"
    assert billing_event.metadata == {
        "layer": 2,
        "credential_mode": "byok",
        "interface": "rest",
        "billing_status": "refunded",
        "error": "brave-search-api failed before people-data-labs fallback",
    }

    audit_event = audit_trail.query(org_id="org_cap_exec_test", limit=1)[0]
    assert audit_event.event_type == AuditEventType.EXECUTION_FAILED
    assert audit_event.provider_slug == "brave-search-api"
    assert audit_event.detail == {
        "capability_id": "search.query",
        "credential_mode": "byok",
        "interface": "rest",
        "upstream_status": 502,
        "billing_status": "refunded",
        "latency_ms": 0.1,
        "error": "brave-search-api failed before people-data-labs fallback",
    }


@pytest.mark.anyio
async def test_execute_upstream_failure_canonicalizes_same_provider_alias_text_in_durable_billing_and_audit_events(app):
    raw_upstream_response = {
        "provider_used": "brave-search-api",
        "selected_provider": "brave-search-api",
        "fallback_provider": "people-data-labs",
        "message": "brave-search upstream failed after people-data-labs fallback warmed",
        "error_message": "brave-search failed before people-data-labs fallback",
        "result": {
            "provider_slug": "brave-search-api",
            "fallback_provider": "people-data-labs",
            "supported_provider_slugs": ["brave-search-api", "people-data-labs"],
            "detail": "Retry brave-search later or switch to people-data-labs",
        },
    }
    mock_response, mock_pool = _build_patches()
    mock_response.status_code = 502
    mock_response.json.return_value = raw_upstream_response
    mock_response.text = json.dumps(raw_upstream_response)

    billing_stream = BillingEventStream()
    audit_trail = AuditTrail()
    mock_receipt_service = MagicMock()
    mock_receipt_service.create_receipt = AsyncMock(
        return_value=MagicMock(receipt_id="rcpt_durable_same_provider_context_failure")
    )
    mock_attribution = MagicMock()
    mock_attribution.to_rhumb_block.return_value = {"provider": {"id": "brave-search-api"}}
    mock_attribution.to_response_headers.return_value = {"X-Rhumb-Provider": "brave-search-api"}

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_search_supabase,
        ),
        patch(
            "routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True
        ),
        patch(
            "routes.capability_execute._inject_auth_request_parts",
            side_effect=lambda slug, auth, h, body, params: (h, body, params),
        ),
        patch(
            "routes.capability_execute.check_agent_exec_rate_limit",
            new_callable=AsyncMock,
            return_value=(True, 29),
        ),
        patch("routes.capability_execute.get_pool_manager", return_value=mock_pool),
        patch("routes.capability_execute.get_billing_event_stream", return_value=billing_stream),
        patch("routes.capability_execute.get_audit_trail", return_value=audit_trail),
        patch("routes.capability_execute.get_receipt_service", return_value=mock_receipt_service),
        patch(
            "routes.capability_execute.build_attribution",
            new_callable=AsyncMock,
            return_value=mock_attribution,
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/search.query/execute",
                json={
                    "provider": "brave-search-api",
                    "credential_mode": "byok",
                    "method": "GET",
                    "path": "/res/v1/web/search",
                    "body": {"q": "Rhumb API agent infrastructure"},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["provider_used"] == "brave-search-api"
    assert data["upstream_status"] == 502
    assert data["receipt_id"] == "rcpt_durable_same_provider_context_failure"
    assert resp.headers["X-Rhumb-Provider"] == "brave-search-api"

    billing_event = billing_stream.query(org_id="org_cap_exec_test", limit=1)[0]
    assert billing_event.event_type == BillingEventType.EXECUTION_FAILED_NO_CHARGE
    assert billing_event.provider_slug == "brave-search-api"
    assert billing_event.metadata == {
        "layer": 2,
        "credential_mode": "byok",
        "interface": "rest",
        "billing_status": "refunded",
        "error": "brave-search-api failed before people-data-labs fallback",
    }

    audit_event = audit_trail.query(org_id="org_cap_exec_test", limit=1)[0]
    assert audit_event.event_type == AuditEventType.EXECUTION_FAILED
    assert audit_event.provider_slug == "brave-search-api"
    assert audit_event.detail == {
        "capability_id": "search.query",
        "credential_mode": "byok",
        "interface": "rest",
        "upstream_status": 502,
        "billing_status": "refunded",
        "latency_ms": 0.1,
        "error": "brave-search-api failed before people-data-labs fallback",
    }
