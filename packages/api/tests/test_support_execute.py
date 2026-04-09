"""Tests for Zendesk support capability execution route."""

from __future__ import annotations

import json
from importlib import import_module
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app
from schemas.agent_identity import AgentIdentitySchema
from schemas.support_capabilities import TicketSearchResponse, ZendeskTicketSummary

FAKE_RHUMB_KEY = "rhumb_test_key_support_exec"

support_execute_route = import_module("routes.support_execute")


def _mock_agent() -> AgentIdentitySchema:
    return AgentIdentitySchema(
        agent_id="agent_support_test",
        name="support-test-agent",
        organization_id="org_support_test",
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
def _mock_supabase_writes():
    with patch.object(support_execute_route, "supabase_insert", new_callable=AsyncMock) as mock_insert:
        yield mock_insert


@pytest.fixture(autouse=True)
def _mock_receipt_service():
    mock_receipt = MagicMock()
    mock_receipt.receipt_id = "rcpt_test_support_00000001"
    mock_service = MagicMock()
    mock_service.create_receipt = AsyncMock(return_value=mock_receipt)
    with patch.object(support_execute_route, "get_receipt_service", return_value=mock_service):
        yield mock_service


def _assert_failure_audit(
    mock_receipt_service,
    mock_supabase_writes,
    *,
    status_code: int,
    error_code: str,
    credential_mode: str = "byok",
) -> None:
    mock_receipt_service.create_receipt.assert_called_once()
    receipt_input = mock_receipt_service.create_receipt.call_args[0][0]
    assert receipt_input.status == "failure"
    assert receipt_input.error_code == error_code
    assert receipt_input.provider_id == "zendesk"
    assert receipt_input.credential_mode == credential_mode

    table_name, payload = mock_supabase_writes.await_args.args
    assert table_name == "capability_executions"
    assert payload["upstream_status"] == status_code
    assert payload["success"] is False
    assert payload["provider_used"] == "zendesk"


@pytest.mark.asyncio
async def test_ticket_search_success(app, monkeypatch) -> None:
    monkeypatch.setenv(
        "RHUMB_SUPPORT_SUP_HELP",
        json.dumps(
            {
                "provider": "zendesk",
                "subdomain": "acme",
                "auth_mode": "bearer_token",
                "bearer_token": "secret",
                "allowed_group_ids": [123],
            }
        ),
    )

    response_model = TicketSearchResponse(
        provider_used="zendesk",
        credential_mode="byok",
        capability_id="ticket.search",
        receipt_id="pending",
        execution_id="pending",
        support_ref="sup_help",
        tickets=[
            ZendeskTicketSummary(
                ticket_id=101,
                subject="Login broken",
                status="open",
                priority="high",
                group_id=123,
                snippet="Customer cannot sign in",
            )
        ],
        result_count_returned=1,
        has_more=False,
        next_page_after=None,
    )

    with patch.object(support_execute_route, "search_tickets", new=AsyncMock(return_value=response_model)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v1/capabilities/ticket.search/execute",
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
                json={
                    "support_ref": "sup_help",
                    "query": "login",
                },
            )

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["data"]["support_ref"] == "sup_help"
    assert body["data"]["provider_used"] == "zendesk"
    assert body["data"]["receipt_id"] == "rcpt_test_support_00000001"
    assert "Searched 1 Zendesk tickets" in body["summary"]


@pytest.mark.asyncio
async def test_ticket_search_rejects_missing_support_ref_env(
    app,
    monkeypatch,
    _mock_receipt_service,
    _mock_supabase_writes,
) -> None:
    monkeypatch.delenv("RHUMB_SUPPORT_SUP_HELP", raising=False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/capabilities/ticket.search/execute",
            headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            json={
                "support_ref": "sup_help",
                "query": "login",
            },
        )

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "support_ref_invalid"
    assert body["support_ref"] == "sup_help"
    _assert_failure_audit(
        _mock_receipt_service,
        _mock_supabase_writes,
        status_code=400,
        error_code="support_ref_invalid",
    )


@pytest.mark.asyncio
async def test_ticket_search_rejects_non_byok_credential_mode(
    app,
    monkeypatch,
    _mock_receipt_service,
    _mock_supabase_writes,
) -> None:
    monkeypatch.setenv(
        "RHUMB_SUPPORT_SUP_HELP",
        json.dumps(
            {
                "provider": "zendesk",
                "subdomain": "acme",
                "auth_mode": "bearer_token",
                "bearer_token": "secret",
                "allowed_group_ids": [123],
            }
        ),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/capabilities/ticket.search/execute",
            headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            json={
                "credential_mode": "agent_vault",
                "support_ref": "sup_help",
                "query": "login",
            },
        )

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "support_credential_mode_invalid"
    _assert_failure_audit(
        _mock_receipt_service,
        _mock_supabase_writes,
        status_code=400,
        error_code="support_credential_mode_invalid",
        credential_mode="agent_vault",
    )
