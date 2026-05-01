"""Tests for AWS S3 read-first capability execution route."""

from __future__ import annotations

import json
import asyncio
from importlib import import_module
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app import create_app
from schemas.agent_identity import AgentIdentitySchema
from schemas.storage_capabilities import ObjectListResponse, StorageObjectSummary

FAKE_RHUMB_KEY = "rhumb_test_key_storage_exec"

storage_execute_route = import_module("routes.storage_execute")


def _mock_agent() -> AgentIdentitySchema:
    return AgentIdentitySchema(
        agent_id="agent_storage_test",
        name="storage-test-agent",
        organization_id="org_storage_test",
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
    with patch.object(storage_execute_route, "supabase_insert", new_callable=AsyncMock) as mock_insert:
        yield mock_insert


@pytest.fixture(autouse=True)
def _mock_receipt_service():
    mock_receipt = MagicMock()
    mock_receipt.receipt_id = "rcpt_test_storage_00000001"
    mock_service = MagicMock()
    mock_service.create_receipt = AsyncMock(return_value=mock_receipt)
    with patch.object(storage_execute_route, "get_receipt_service", return_value=mock_service):
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
    assert receipt_input.provider_id == "aws-s3"
    assert receipt_input.credential_mode == credential_mode

    table_name, payload = mock_supabase_writes.await_args.args
    assert table_name == "capability_executions"
    assert payload["upstream_status"] == status_code
    assert payload["success"] is False
    assert payload["provider_used"] == "aws-s3"


@pytest.mark.asyncio
async def test_object_list_success(app, monkeypatch) -> None:
    monkeypatch.setenv(
        "RHUMB_STORAGE_ST_DOCS",
        json.dumps(
            {
                "provider": "aws-s3",
                "region": "us-west-1",
                "aws_access_key_id": "AKIA...",
                "aws_secret_access_key": "secret",
                "allowed_buckets": ["docs-bucket"],
                "allowed_prefixes": {"docs-bucket": ["reports/"]},
            }
        ),
    )

    response_model = ObjectListResponse(
        provider_used="aws-s3",
        credential_mode="byok",
        capability_id="object.list",
        receipt_id="pending",
        execution_id="pending",
        storage_ref="st_docs",
        bucket="docs-bucket",
        prefix="reports/",
        objects=[
            StorageObjectSummary(
                key="reports/daily.json",
                size=12,
                etag='"abc"',
                last_modified="2026-04-08T12:00:00+00:00",
                storage_class="STANDARD",
            )
        ],
        object_count_returned=1,
        is_truncated=False,
        next_continuation_token=None,
    )

    with patch.object(storage_execute_route, "list_objects", new=AsyncMock(return_value=response_model)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v1/capabilities/object.list/execute",
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
                json={
                    "storage_ref": "st_docs",
                    "bucket": "docs-bucket",
                    "prefix": "reports/",
                },
            )

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["data"]["storage_ref"] == "st_docs"
    assert body["data"]["provider_used"] == "aws-s3"
    assert body["data"]["receipt_id"] == "rcpt_test_storage_00000001"
    assert "Listed 1 objects" in body["summary"]


def test_object_list_normalizes_byok_credential_mode(
    app,
    monkeypatch,
    _mock_receipt_service,
) -> None:
    """Padded/case-varied BYOK mode normalizes before route branching."""
    monkeypatch.setenv(
        "RHUMB_STORAGE_ST_DOCS",
        json.dumps(
            {
                "provider": "aws-s3",
                "region": "us-west-1",
                "aws_access_key_id": "AKIA...",
                "aws_secret_access_key": "secret",
                "allowed_buckets": ["docs-bucket"],
            }
        ),
    )

    response_model = ObjectListResponse(
        provider_used="aws-s3",
        credential_mode="byok",
        capability_id="object.list",
        receipt_id="pending",
        execution_id="pending",
        storage_ref="st_docs",
        bucket="docs-bucket",
        objects=[],
        object_count_returned=0,
        is_truncated=False,
        next_continuation_token=None,
    )

    with patch.object(storage_execute_route, "list_objects", new=AsyncMock(return_value=response_model)):
        response = TestClient(app).post(
            "/v1/capabilities/object.list/execute",
            headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            json={
                "credential_mode": " BYOK ",
                "storage_ref": "st_docs",
                "bucket": "docs-bucket",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["data"]["credential_mode"] == "byok"
    receipt_input = _mock_receipt_service.create_receipt.call_args[0][0]
    assert receipt_input.credential_mode == "byok"


@pytest.mark.asyncio
async def test_object_list_rejects_missing_storage_ref_env(
    app,
    monkeypatch,
    _mock_receipt_service,
    _mock_supabase_writes,
) -> None:
    monkeypatch.delenv("RHUMB_STORAGE_ST_DOCS", raising=False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/capabilities/object.list/execute",
            headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            json={
                "storage_ref": "st_docs",
                "bucket": "docs-bucket",
                "prefix": "reports/",
            },
        )

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "storage_ref_invalid"
    assert body["storage_ref"] == "st_docs"
    _assert_failure_audit(
        _mock_receipt_service,
        _mock_supabase_writes,
        status_code=400,
        error_code="storage_ref_invalid",
    )


def test_object_list_rejects_non_object_body_before_storage_reads(
    app,
    _mock_receipt_service,
    _mock_supabase_writes,
) -> None:
    async def _run():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post(
                "/v1/capabilities/object.list/execute",
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
                json=["not", "an", "object"],
            )

    with (
        patch.object(storage_execute_route, "resolve_storage_bundle") as mock_resolve,
        patch.object(storage_execute_route, "list_objects", new=AsyncMock()) as mock_list,
    ):
        response = asyncio.run(_run())

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "storage_request_invalid"
    assert body["message"] == "JSON body must be an object"
    mock_resolve.assert_not_called()
    mock_list.assert_not_called()
    _assert_failure_audit(
        _mock_receipt_service,
        _mock_supabase_writes,
        status_code=400,
        error_code="storage_request_invalid",
    )


@pytest.mark.asyncio
async def test_object_list_rejects_non_byok_credential_mode(
    app,
    monkeypatch,
    _mock_receipt_service,
    _mock_supabase_writes,
) -> None:
    monkeypatch.setenv(
        "RHUMB_STORAGE_ST_DOCS",
        json.dumps(
            {
                "provider": "aws-s3",
                "region": "us-west-1",
                "aws_access_key_id": "AKIA...",
                "aws_secret_access_key": "secret",
                "allowed_buckets": ["docs-bucket"],
            }
        ),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/capabilities/object.list/execute",
            headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            json={
                "credential_mode": "agent_vault",
                "storage_ref": "st_docs",
                "bucket": "docs-bucket",
            },
        )

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "storage_credential_mode_invalid"
    _assert_failure_audit(
        _mock_receipt_service,
        _mock_supabase_writes,
        status_code=400,
        error_code="storage_credential_mode_invalid",
        credential_mode="agent_vault",
    )
