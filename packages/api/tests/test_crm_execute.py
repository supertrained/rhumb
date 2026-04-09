"""Tests for HubSpot CRM read-first capability execution route."""

from __future__ import annotations

import json
from importlib import import_module
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app
from schemas.agent_identity import AgentIdentitySchema
from schemas.crm_capabilities import CrmRecordSearchResponse, HubSpotCrmRecordSummary

FAKE_RHUMB_KEY = "rhumb_test_key_crm_exec"

crm_execute_route = import_module("routes.crm_execute")


def _mock_agent() -> AgentIdentitySchema:
    return AgentIdentitySchema(
        agent_id="agent_crm_test",
        name="crm-test-agent",
        organization_id="org_crm_test",
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
    with patch.object(crm_execute_route, "supabase_insert", new_callable=AsyncMock) as mock_insert:
        yield mock_insert


@pytest.fixture(autouse=True)
def _mock_receipt_service():
    mock_receipt = MagicMock()
    mock_receipt.receipt_id = "rcpt_test_crm_00000001"
    mock_service = MagicMock()
    mock_service.create_receipt = AsyncMock(return_value=mock_receipt)
    with patch.object(crm_execute_route, "get_receipt_service", return_value=mock_service):
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
    assert receipt_input.provider_id == "hubspot"
    assert receipt_input.credential_mode == credential_mode

    table_name, payload = mock_supabase_writes.await_args.args
    assert table_name == "capability_executions"
    assert payload["upstream_status"] == status_code
    assert payload["success"] is False
    assert payload["provider_used"] == "hubspot"


@pytest.mark.asyncio
async def test_crm_record_search_success(app, monkeypatch) -> None:
    monkeypatch.setenv(
        "RHUMB_CRM_HS_MAIN",
        json.dumps(
            {
                "provider": "hubspot",
                "auth_mode": "private_app_token",
                "private_app_token": "secret",
                "allowed_object_types": ["contacts"],
                "allowed_properties_by_object": {"contacts": ["email"]},
            }
        ),
    )

    response_model = CrmRecordSearchResponse(
        provider_used="hubspot",
        credential_mode="byok",
        capability_id="crm.record.search",
        receipt_id="pending",
        execution_id="pending",
        crm_ref="hs_main",
        object_type="contacts",
        records=[
            HubSpotCrmRecordSummary(
                record_id="101",
                archived=False,
                created_at="2026-04-09T17:00:00Z",
                updated_at="2026-04-09T17:01:00Z",
                properties={"email": "ada@example.com"},
            )
        ],
        record_count_returned=1,
        next_after=None,
    )

    with patch.object(crm_execute_route, "search_records", new=AsyncMock(return_value=response_model)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v1/capabilities/crm.record.search/execute",
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
                json={
                    "crm_ref": "hs_main",
                    "object_type": "contacts",
                },
            )

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["data"]["crm_ref"] == "hs_main"
    assert body["data"]["provider_used"] == "hubspot"
    assert body["data"]["receipt_id"] == "rcpt_test_crm_00000001"
    assert "Found 1 HubSpot contact via crm_ref hs_main" == body["summary"]


@pytest.mark.asyncio
async def test_crm_record_search_rejects_missing_crm_ref_env(
    app,
    monkeypatch,
    _mock_receipt_service,
    _mock_supabase_writes,
) -> None:
    monkeypatch.delenv("RHUMB_CRM_HS_MAIN", raising=False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/capabilities/crm.record.search/execute",
            headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            json={
                "crm_ref": "hs_main",
                "object_type": "contacts",
            },
        )

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "crm_ref_invalid"
    assert body["crm_ref"] == "hs_main"
    _assert_failure_audit(
        _mock_receipt_service,
        _mock_supabase_writes,
        status_code=400,
        error_code="crm_ref_invalid",
    )


@pytest.mark.asyncio
async def test_crm_record_search_rejects_non_byok_credential_mode(
    app,
    monkeypatch,
    _mock_receipt_service,
    _mock_supabase_writes,
) -> None:
    monkeypatch.setenv(
        "RHUMB_CRM_HS_MAIN",
        json.dumps(
            {
                "provider": "hubspot",
                "auth_mode": "private_app_token",
                "private_app_token": "secret",
                "allowed_object_types": ["contacts"],
                "allowed_properties_by_object": {"contacts": ["email"]},
            }
        ),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/capabilities/crm.record.search/execute",
            headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            json={
                "credential_mode": "agent_vault",
                "crm_ref": "hs_main",
                "object_type": "contacts",
            },
        )

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "crm_credential_mode_invalid"
    _assert_failure_audit(
        _mock_receipt_service,
        _mock_supabase_writes,
        status_code=400,
        error_code="crm_credential_mode_invalid",
        credential_mode="agent_vault",
    )


@pytest.mark.asyncio
async def test_crm_record_search_validation_error_maps_to_request_invalid(
    app,
    monkeypatch,
    _mock_receipt_service,
    _mock_supabase_writes,
) -> None:
    monkeypatch.setenv(
        "RHUMB_CRM_HS_MAIN",
        json.dumps(
            {
                "provider": "hubspot",
                "auth_mode": "private_app_token",
                "private_app_token": "secret",
                "allowed_object_types": ["contacts"],
                "allowed_properties_by_object": {"contacts": ["email"]},
            }
        ),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/capabilities/crm.record.search/execute",
            headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            json={
                "crm_ref": "hs_main",
                "object_type": "contacts",
                "limit": 99,
            },
        )

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "crm_request_invalid"
    _assert_failure_audit(
        _mock_receipt_service,
        _mock_supabase_writes,
        status_code=400,
        error_code="crm_request_invalid",
    )


@pytest.mark.asyncio
async def test_crm_record_search_rejects_nested_filter_group_shape(
    app,
    monkeypatch,
    _mock_receipt_service,
    _mock_supabase_writes,
) -> None:
    monkeypatch.setenv(
        "RHUMB_CRM_HS_MAIN",
        json.dumps(
            {
                "provider": "hubspot",
                "auth_mode": "private_app_token",
                "private_app_token": "secret",
                "allowed_object_types": ["contacts"],
                "allowed_properties_by_object": {"contacts": ["email"]},
            }
        ),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/capabilities/crm.record.search/execute",
            headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            json={
                "crm_ref": "hs_main",
                "object_type": "contacts",
                "filter_groups": [{"filters": [{"property": "email", "operator": "EQ", "value": "ada@example.com"}]}],
            },
        )

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "crm_request_invalid"
    _assert_failure_audit(
        _mock_receipt_service,
        _mock_supabase_writes,
        status_code=400,
        error_code="crm_request_invalid",
    )
