"""Tests for warehouse capability execution route."""

from __future__ import annotations

import json
import asyncio
from importlib import import_module
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app
from schemas.agent_identity import AgentIdentitySchema
from schemas.warehouse_capabilities import (
    WarehouseColumnSchema,
    WarehouseQueryBounds,
    WarehouseQueryReadResponse,
    WarehouseQuerySummary,
)

FAKE_RHUMB_KEY = "rhumb_test_key_warehouse_exec"

warehouse_execute_route = import_module("routes.warehouse_execute")


def _mock_agent() -> AgentIdentitySchema:
    return AgentIdentitySchema(
        agent_id="agent_warehouse_test",
        name="warehouse-test-agent",
        organization_id="org_warehouse_test",
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
    with patch.object(warehouse_execute_route, "supabase_insert", new_callable=AsyncMock) as mock_insert:
        yield mock_insert


@pytest.fixture(autouse=True)
def _mock_receipt_service():
    mock_receipt = MagicMock()
    mock_receipt.receipt_id = "rcpt_test_warehouse_00000001"
    mock_service = MagicMock()
    mock_service.create_receipt = AsyncMock(return_value=mock_receipt)
    with patch.object(warehouse_execute_route, "get_receipt_service", return_value=mock_service):
        yield mock_service


@pytest.mark.asyncio
async def test_warehouse_query_read_success(app, monkeypatch) -> None:
    monkeypatch.setenv(
        "RHUMB_WAREHOUSE_BQ_MAIN",
        json.dumps(
            {
                "provider": "bigquery",
                "auth_mode": "service_account_json",
                "service_account_json": {
                    "type": "service_account",
                    "project_id": "proj",
                    "client_email": "rhumb@example.iam.gserviceaccount.com",
                    "private_key": "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n",
                },
                "allowed_dataset_refs": ["proj.analytics"],
                "allowed_table_refs": ["proj.analytics.events"],
                "billing_project_id": "proj",
                "location": "US",
            }
        ),
    )

    response_model = WarehouseQueryReadResponse(
        provider_used="bigquery",
        credential_mode="byok",
        capability_id="warehouse.query.read",
        receipt_id="pending",
        execution_id="pending",
        warehouse_ref="bq_main",
        billing_project_id="proj",
        location="US",
        bounded_by=WarehouseQueryBounds(
            row_limit_applied=2,
            timeout_ms_applied=5000,
            max_bytes_billed_applied=50000000,
            result_bytes_limit_applied=262144,
        ),
        query_summary=WarehouseQuerySummary(
            statement_type="select",
            tables_referenced=["proj.analytics.events"],
            dry_run_performed=True,
            dry_run_bytes_processed=1234,
            truncated=False,
        ),
        columns=[WarehouseColumnSchema(name="user_id", type="STRING", nullable=True, mode="NULLABLE")],
        rows=[{"user_id": "u_1"}],
        row_count_returned=1,
        truncated=False,
        dry_run_bytes_estimate=1234,
        actual_bytes_billed=1111,
        duration_ms=12,
    )

    with patch.object(
        warehouse_execute_route,
        "execute_read_query",
        new=AsyncMock(return_value=response_model),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v1/capabilities/warehouse.query.read/execute",
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
                json={
                    "warehouse_ref": "bq_main",
                    "query": "SELECT user_id FROM proj.analytics.events",
                },
            )

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["data"]["warehouse_ref"] == "bq_main"
    assert body["data"]["provider_used"] == "bigquery"
    assert body["data"]["billing_project_id"] == "proj"
    assert body["data"]["dry_run_bytes_estimate"] == 1234
    assert body["data"]["actual_bytes_billed"] == 1111
    assert body["data"]["receipt_id"] == "rcpt_test_warehouse_00000001"
    assert "Read 1 warehouse row" in body["summary"]


@pytest.mark.asyncio
async def test_warehouse_execute_rejects_missing_bundle(
    app,
    monkeypatch,
    _mock_receipt_service,
    _mock_supabase_writes,
) -> None:
    monkeypatch.delenv("RHUMB_WAREHOUSE_BQ_MAIN", raising=False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/capabilities/warehouse.query.read/execute",
            headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            json={
                "warehouse_ref": "bq_main",
                "query": "SELECT user_id FROM proj.analytics.events",
            },
        )

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "warehouse_ref_invalid"
    assert body["warehouse_ref"] == "bq_main"


def test_warehouse_execute_rejects_non_object_body_before_warehouse_reads(
    app,
    _mock_receipt_service,
    _mock_supabase_writes,
) -> None:
    async def _run():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post(
                "/v1/capabilities/warehouse.query.read/execute",
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
                json=["not", "an", "object"],
            )

    with (
        patch.object(warehouse_execute_route, "resolve_warehouse_bundle") as mock_resolve,
        patch.object(warehouse_execute_route, "execute_read_query", new=AsyncMock()) as mock_execute,
    ):
        response = asyncio.run(_run())

    assert response.status_code == 400
    assert response.json()["error"] == "warehouse_request_invalid"
    assert response.json()["message"] == "JSON body must be an object"
    mock_resolve.assert_not_called()
    mock_execute.assert_not_called()

    _mock_receipt_service.create_receipt.assert_called_once()
    receipt_input = _mock_receipt_service.create_receipt.call_args[0][0]
    assert receipt_input.status == "failure"
    assert receipt_input.error_code == "warehouse_request_invalid"

    table_name, payload = _mock_supabase_writes.await_args.args
    assert table_name == "capability_executions"
    assert payload["upstream_status"] == 400
    assert payload["success"] is False


@pytest.mark.asyncio
async def test_warehouse_execute_rejects_non_byok_credential_mode(
    app,
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "RHUMB_WAREHOUSE_BQ_MAIN",
        json.dumps(
            {
                "provider": "bigquery",
                "auth_mode": "service_account_json",
                "service_account_json": {
                    "type": "service_account",
                    "project_id": "proj",
                    "client_email": "rhumb@example.iam.gserviceaccount.com",
                    "private_key": "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n",
                },
                "billing_project_id": "proj",
                "location": "US",
                "allowed_dataset_refs": ["proj.analytics"],
                "allowed_table_refs": ["proj.analytics.events"],
            }
        ),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/capabilities/warehouse.query.read/execute",
            headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            json={
                "credential_mode": "agent_vault",
                "warehouse_ref": "bq_main",
                "query": "SELECT user_id FROM proj.analytics.events",
            },
        )

    assert response.status_code == 400
    assert response.json()["error"] == "warehouse_credential_mode_invalid"


@pytest.mark.asyncio
async def test_warehouse_execute_maps_request_validation_to_contract_code(
    app,
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "RHUMB_WAREHOUSE_BQ_MAIN",
        json.dumps(
            {
                "provider": "bigquery",
                "auth_mode": "service_account_json",
                "service_account_json": {
                    "type": "service_account",
                    "project_id": "proj",
                    "client_email": "rhumb@example.iam.gserviceaccount.com",
                    "private_key": "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n",
                },
                "billing_project_id": "proj",
                "location": "US",
                "allowed_dataset_refs": ["proj.analytics"],
                "allowed_table_refs": ["proj.analytics.events"],
            }
        ),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/capabilities/warehouse.query.read/execute",
            headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            json={
                "warehouse_ref": "bq_main",
                "query": "SELECT user_id FROM proj.analytics.events",
                "max_rows": 101,
            },
        )

    assert response.status_code == 400
    assert response.json()["error"] == "warehouse_request_invalid"
