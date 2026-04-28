"""Tests for GitHub Actions workflow-run read-first capability execution route."""

from __future__ import annotations

import json
import asyncio
from importlib import import_module
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app
from schemas.actions_capabilities import WorkflowRunListResponse, GitHubWorkflowRunSummary
from schemas.agent_identity import AgentIdentitySchema

FAKE_RHUMB_KEY = "rhumb_test_key_actions_exec"

actions_execute_route = import_module("routes.actions_execute")


def _mock_agent() -> AgentIdentitySchema:
    return AgentIdentitySchema(
        agent_id="agent_actions_test",
        name="actions-test-agent",
        organization_id="org_actions_test",
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
    with patch.object(actions_execute_route, "supabase_insert", new_callable=AsyncMock) as mock_insert:
        yield mock_insert


@pytest.fixture(autouse=True)
def _mock_receipt_service():
    mock_receipt = MagicMock()
    mock_receipt.receipt_id = "rcpt_test_actions_00000001"
    mock_service = MagicMock()
    mock_service.create_receipt = AsyncMock(return_value=mock_receipt)
    with patch.object(actions_execute_route, "get_receipt_service", return_value=mock_service):
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
    assert receipt_input.provider_id == "github"
    assert receipt_input.credential_mode == credential_mode

    table_name, payload = mock_supabase_writes.await_args.args
    assert table_name == "capability_executions"
    assert payload["upstream_status"] == status_code
    assert payload["success"] is False
    assert payload["provider_used"] == "github"


@pytest.mark.asyncio
async def test_workflow_run_list_success(app, monkeypatch) -> None:
    monkeypatch.setenv(
        "RHUMB_ACTIONS_GH_MAIN",
        json.dumps(
            {
                "provider": "github",
                "auth_mode": "bearer_token",
                "bearer_token": "secret",
                "allowed_repositories": ["openclaw/openclaw"],
            }
        ),
    )

    response_model = WorkflowRunListResponse(
        provider_used="github",
        credential_mode="byok",
        capability_id="workflow_run.list",
        receipt_id="pending",
        execution_id="pending",
        actions_ref="gh_main",
        repository="openclaw/openclaw",
        workflow_runs=[
            GitHubWorkflowRunSummary(
                run_id=101,
                workflow_id=9001,
                repository="openclaw/openclaw",
                workflow_name="CI",
                display_title="Fix lint",
                run_number=55,
                event="push",
                status="completed",
                conclusion="success",
                branch="main",
                head_sha="abc123",
                actor_login="pedro",
                html_url="https://github.com/openclaw/openclaw/actions/runs/101",
                created_at="2026-04-09T16:00:00Z",
                updated_at="2026-04-09T16:01:00Z",
            )
        ],
        run_count_returned=1,
        total_count=1,
        has_more=False,
        next_page=None,
    )

    with patch.object(actions_execute_route, "list_workflow_runs", new=AsyncMock(return_value=response_model)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v1/capabilities/workflow_run.list/execute",
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
                json={
                    "actions_ref": "gh_main",
                    "repository": "openclaw/openclaw",
                },
            )

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["data"]["actions_ref"] == "gh_main"
    assert body["data"]["provider_used"] == "github"
    assert body["data"]["receipt_id"] == "rcpt_test_actions_00000001"
    assert "Listed 1 GitHub Actions workflow runs" in body["summary"]


@pytest.mark.asyncio
async def test_workflow_run_list_rejects_missing_actions_ref_env(
    app,
    monkeypatch,
    _mock_receipt_service,
    _mock_supabase_writes,
) -> None:
    monkeypatch.delenv("RHUMB_ACTIONS_GH_MAIN", raising=False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/capabilities/workflow_run.list/execute",
            headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            json={
                "actions_ref": "gh_main",
                "repository": "openclaw/openclaw",
            },
        )

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "actions_ref_invalid"
    assert body["actions_ref"] == "gh_main"
    _assert_failure_audit(
        _mock_receipt_service,
        _mock_supabase_writes,
        status_code=400,
        error_code="actions_ref_invalid",
    )


def test_workflow_run_list_rejects_non_object_body_before_actions_reads(
    app,
    _mock_receipt_service,
    _mock_supabase_writes,
) -> None:
    async def _run():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post(
                "/v1/capabilities/workflow_run.list/execute",
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
                json=["not", "an", "object"],
            )

    with (
        patch.object(actions_execute_route, "resolve_actions_bundle") as mock_resolve,
        patch.object(actions_execute_route, "list_workflow_runs", new=AsyncMock()) as mock_list,
    ):
        response = asyncio.run(_run())

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "actions_request_invalid"
    assert body["message"] == "JSON body must be an object"
    mock_resolve.assert_not_called()
    mock_list.assert_not_called()
    _assert_failure_audit(
        _mock_receipt_service,
        _mock_supabase_writes,
        status_code=400,
        error_code="actions_request_invalid",
    )


@pytest.mark.asyncio
async def test_workflow_run_list_rejects_non_byok_credential_mode(
    app,
    monkeypatch,
    _mock_receipt_service,
    _mock_supabase_writes,
) -> None:
    monkeypatch.setenv(
        "RHUMB_ACTIONS_GH_MAIN",
        json.dumps(
            {
                "provider": "github",
                "auth_mode": "bearer_token",
                "bearer_token": "secret",
                "allowed_repositories": ["openclaw/openclaw"],
            }
        ),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/capabilities/workflow_run.list/execute",
            headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            json={
                "credential_mode": "agent_vault",
                "actions_ref": "gh_main",
                "repository": "openclaw/openclaw",
            },
        )

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "actions_credential_mode_invalid"
    _assert_failure_audit(
        _mock_receipt_service,
        _mock_supabase_writes,
        status_code=400,
        error_code="actions_credential_mode_invalid",
        credential_mode="agent_vault",
    )
