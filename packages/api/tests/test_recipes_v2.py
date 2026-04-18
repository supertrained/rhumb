"""Tests for Resolve v2 recipe endpoints (WU-42.3)."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app
from routes._supabase import SupabaseWriteUnavailable
from schemas.agent_identity import AgentIdentitySchema
from services.durable_idempotency import IdempotencyUnavailable
from services.recipe_engine import RecipeExecution, RecipeStatus, StepResult, StepStatus
from services.recipe_safety import RecipeSafetyGate

FAKE_RHUMB_KEY = "rhumb_test_key_v2"

RECIPE_ROW = {
    "recipe_id": "transcribe_and_notify",
    "name": "Transcribe and notify",
    "version": "1.0.0",
    "category": "productivity",
    "stability": "beta",
    "tier": "premium",
    "definition": {
        "recipe_id": "transcribe_and_notify",
        "name": "Transcribe and notify",
        "version": "1.0.0",
        "category": "productivity",
        "stability": "beta",
        "tier": "premium",
        "inputs": {"type": "object", "required": ["audio_url", "to"]},
        "outputs": {"type": "object"},
        "steps": [
            {
                "step_id": "transcribe",
                "capability_id": "media.transcribe",
                "parameters": {"audio_url": {"$ref": "inputs.audio_url"}},
                "outputs_captured": {"transcript_text": "result.transcript"},
                "budget": {"max_cost_usd": 0.10},
            },
            {
                "step_id": "notify",
                "capability_id": "email.send",
                "depends_on": ["transcribe"],
                "parameters": {
                    "to": {"$ref": "inputs.to"},
                    "body": {"$ref": "steps.transcribe.outputs.transcript_text"},
                },
                "outputs_captured": {"message_id": "result.id"},
                "budget": {"max_cost_usd": 0.02},
            },
        ],
        "dag": {
            "edges": [
                {"from": "transcribe", "to": "notify"},
            ],
            "critical_path": ["transcribe", "notify"],
        },
        "budget": {
            "max_total_cost_usd": 0.5,
            "per_step_budgets_enforced": True,
            "on_budget_exceeded": "halt_current_step",
        },
    },
    "inputs_schema": {"type": "object", "required": ["audio_url", "to"]},
    "outputs_schema": {"type": "object"},
    "step_count": 2,
    "max_total_cost_usd": 0.5,
    "published": True,
    "updated_at": "2026-03-31T12:00:00Z",
}


class _MockResponse:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body
        self.headers = {}

    def json(self):
        return self._body


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def mock_agent() -> AgentIdentitySchema:
    return AgentIdentitySchema(
        agent_id="agent_recipe_test",
        name="recipe-test",
        organization_id="org_recipe_test",
    )


@pytest.fixture(autouse=True)
def _mock_required_recipe_writes():
    with (
        patch("routes.recipes_v2.supabase_insert_required", new_callable=AsyncMock, return_value=None),
        patch("routes.recipes_v2.supabase_patch_required", new_callable=AsyncMock, return_value=[]),
    ):
        yield


@pytest.fixture(autouse=True)
def _mock_event_outbox_health():
    """Recipe-route tests assume the durable event outbox is healthy unless overridden."""
    with patch(
        "routes.recipes_v2.get_event_outbox_health",
        return_value=type(
            "OutboxHealth",
            (),
            {
                "allows_risky_writes": True,
                "reason": "",
            },
        )(),
    ):
        yield


@pytest.fixture(autouse=True)
def _mock_kill_switch_registry():
    """Default recipe-route tests to an authoritative non-blocking kill-switch registry."""
    mock_registry = MagicMock()
    mock_registry.is_blocked.return_value = (False, None)
    with patch(
        "routes.recipes_v2.init_kill_switch_registry",
        new_callable=AsyncMock,
        return_value=mock_registry,
    ):
        yield mock_registry


@pytest.fixture(autouse=True)
def _mock_recipe_step_rate_limiter():
    """Recipe-route tests assume aggregate fan-out throttles allow steps unless overridden."""
    mock_limiter = MagicMock()
    mock_limiter.check_and_increment = AsyncMock(return_value=(True, 999))
    with patch(
        "routes.recipes_v2._get_recipe_step_rate_limiter",
        new_callable=AsyncMock,
        return_value=mock_limiter,
    ):
        yield mock_limiter


def _mock_supabase_fetch(path: str):
    if path.startswith("recipes?") and "recipe_id=eq.transcribe_and_notify" in path:
        return [RECIPE_ROW]
    if path.startswith("recipes?"):
        return [RECIPE_ROW]
    if path.startswith("recipe_executions?"):
        return []
    if path.startswith("recipe_step_executions?"):
        return []
    return []


@pytest.mark.anyio
async def test_list_recipes_returns_only_published_rows(app):
    with patch("routes.recipes_v2.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/v2/recipes?category=productivity&stability=beta")

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["data"]["count"] == 1
    assert body["data"]["recipes"][0]["recipe_id"] == "transcribe_and_notify"
    assert body["data"]["recipes"][0]["category"] == "productivity"
    assert body["data"]["recipes"][0]["published"] is True


@pytest.mark.anyio
async def test_get_recipe_returns_compiled_definition(app):
    with patch("routes.recipes_v2.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/v2/recipes/transcribe_and_notify")

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["data"]["recipe_id"] == "transcribe_and_notify"
    assert body["data"]["definition"]["steps"][0]["step_id"] == "transcribe"
    assert body["data"]["inputs_schema"]["required"] == ["audio_url", "to"]


@pytest.mark.anyio
async def test_execute_recipe_runs_engine_via_internal_forwarding_and_persists(app, mock_agent):
    forward_calls: list[tuple[str, dict]] = []

    async def _mock_forward(raw_request, *, method: str, path: str, params=None, json_body=None):
        forward_calls.append((path, json_body or {}))
        if path == "/v2/capabilities/media.transcribe/execute":
            return _MockResponse(
                200,
                {
                    "data": {
                        "provider_used": "assemblyai",
                        "upstream_response": {"transcript": "hello world"},
                        "cost_estimate_usd": 0.03,
                        "latency_ms": 120,
                        "receipt_id": "rcpt_step_transcribe",
                        "execution_id": "exec_step_1",
                    },
                    "error": None,
                },
            )
        if path == "/v2/capabilities/email.send/execute":
            return _MockResponse(
                200,
                {
                    "data": {
                        "provider_used": "resend",
                        "upstream_response": {"id": "msg_123"},
                        "cost_estimate_usd": 0.01,
                        "latency_ms": 80,
                        "receipt_id": "rcpt_step_notify",
                        "execution_id": "exec_step_2",
                    },
                    "error": None,
                },
            )
        raise AssertionError(f"unexpected internal forward path: {path}")

    with (
        patch("routes.recipes_v2.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase_fetch),
        patch("routes.recipes_v2.supabase_insert_required", new_callable=AsyncMock, return_value=None) as mock_insert_required,
        patch("routes.recipes_v2.supabase_patch_required", new_callable=AsyncMock, return_value=[]) as mock_patch_required,
        patch("routes.recipes_v2._forward_internal", new_callable=AsyncMock, side_effect=_mock_forward),
        patch("routes.recipes_v2._resolve_policy_agent", new_callable=AsyncMock, return_value=mock_agent),
        patch("routes.recipes_v2.get_safety_gate", return_value=RecipeSafetyGate()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v2/recipes/transcribe_and_notify/execute",
                json={
                    "inputs": {
                        "audio_url": "https://example.com/audio.mp3",
                        "to": "tom@example.com",
                    },
                    "credential_mode": "byo",
                    "policy": {"provider_preference": ["assemblyai", "resend"]},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    data = body["data"]
    assert data["recipe_id"] == "transcribe_and_notify"
    assert data["status"] == "completed"
    assert data["total_cost_usd"] == pytest.approx(0.04)
    assert len(data["step_results"]) == 2
    assert data["step_results"][0]["provider_used"] == "assemblyai"
    assert data["step_results"][0]["outputs"]["transcript_text"] == "hello world"
    assert data["step_results"][1]["provider_used"] == "resend"
    assert data["outputs"]["notify"]["message_id"] == "msg_123"
    assert data["receipt_chain_hash"]

    assert [path for path, _payload in forward_calls] == [
        "/v2/capabilities/media.transcribe/execute",
        "/v2/capabilities/email.send/execute",
    ]
    assert forward_calls[1][1]["parameters"]["body"] == "hello world"
    assert mock_insert_required.await_count == 3  # placeholder + 2 step rows
    assert mock_patch_required.await_count == 1   # final recipe execution patch


@pytest.mark.anyio
async def test_execute_recipe_canonicalizes_alias_backed_provider_ids_on_response_and_persistence(app, mock_agent):
    async def _mock_forward(raw_request, *, method: str, path: str, params=None, json_body=None):
        if path == "/v2/capabilities/media.transcribe/execute":
            return _MockResponse(
                200,
                {
                    "data": {
                        "provider_used": "brave-search",
                        "upstream_response": {"transcript": "hello world"},
                        "cost_estimate_usd": 0.03,
                        "latency_ms": 120,
                        "receipt_id": "rcpt_step_transcribe",
                        "execution_id": "exec_step_1",
                    },
                    "error": None,
                },
            )
        if path == "/v2/capabilities/email.send/execute":
            return _MockResponse(
                200,
                {
                    "data": {
                        "provider_used": "pdl",
                        "upstream_response": {"id": "msg_123"},
                        "cost_estimate_usd": 0.01,
                        "latency_ms": 80,
                        "receipt_id": "rcpt_step_notify",
                        "execution_id": "exec_step_2",
                    },
                    "error": None,
                },
            )
        raise AssertionError(f"unexpected internal forward path: {path}")

    with (
        patch("routes.recipes_v2.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase_fetch),
        patch("routes.recipes_v2.supabase_insert_required", new_callable=AsyncMock, return_value=None) as mock_insert_required,
        patch("routes.recipes_v2.supabase_patch_required", new_callable=AsyncMock, return_value=[]),
        patch("routes.recipes_v2._forward_internal", new_callable=AsyncMock, side_effect=_mock_forward),
        patch("routes.recipes_v2._resolve_policy_agent", new_callable=AsyncMock, return_value=mock_agent),
        patch("routes.recipes_v2.get_safety_gate", return_value=RecipeSafetyGate()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v2/recipes/transcribe_and_notify/execute",
                json={
                    "inputs": {
                        "audio_url": "https://example.com/audio.mp3",
                        "to": "tom@example.com",
                    },
                    "credential_mode": "byo",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["step_results"][0]["provider_used"] == "brave-search-api"
    assert body["data"]["step_results"][1]["provider_used"] == "people-data-labs"

    step_insert_payloads = [call.args[1] for call in mock_insert_required.await_args_list[1:]]
    assert step_insert_payloads[0]["provider_used"] == "brave-search-api"
    assert step_insert_payloads[1]["provider_used"] == "people-data-labs"


@pytest.mark.anyio
async def test_execute_recipe_canonicalizes_alias_backed_provider_outputs_on_response_and_persistence(app, mock_agent):
    recipe_row = deepcopy(RECIPE_ROW)
    recipe_row["definition"]["steps"][1]["outputs_captured"] = {}

    def _mock_supabase_fetch_with_provider_outputs(path: str):
        if path.startswith("recipes?") and "recipe_id=eq.transcribe_and_notify" in path:
            return [recipe_row]
        if path.startswith("recipes?"):
            return [recipe_row]
        if path.startswith("recipe_executions?"):
            return []
        if path.startswith("recipe_step_executions?"):
            return []
        return []

    async def _mock_forward(raw_request, *, method: str, path: str, params=None, json_body=None):
        if path == "/v2/capabilities/media.transcribe/execute":
            return _MockResponse(
                200,
                {
                    "data": {
                        "provider_used": "assemblyai",
                        "upstream_response": {"transcript": "hello world"},
                        "cost_estimate_usd": 0.03,
                        "latency_ms": 120,
                        "receipt_id": "rcpt_step_transcribe",
                        "execution_id": "exec_step_1",
                    },
                    "error": None,
                },
            )
        if path == "/v2/capabilities/email.send/execute":
            return _MockResponse(
                200,
                {
                    "data": {
                        "provider_used": "pdl",
                        "upstream_response": {"id": "msg_123"},
                        "cost_estimate_usd": 0.01,
                        "latency_ms": 80,
                        "receipt_id": "rcpt_step_notify",
                        "execution_id": "exec_step_2",
                    },
                    "error": None,
                },
            )
        raise AssertionError(f"unexpected internal forward path: {path}")

    with (
        patch("routes.recipes_v2.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase_fetch_with_provider_outputs),
        patch("routes.recipes_v2.supabase_insert_required", new_callable=AsyncMock, return_value=None) as mock_insert_required,
        patch("routes.recipes_v2.supabase_patch_required", new_callable=AsyncMock, return_value=[]),
        patch("routes.recipes_v2._forward_internal", new_callable=AsyncMock, side_effect=_mock_forward),
        patch("routes.recipes_v2._resolve_policy_agent", new_callable=AsyncMock, return_value=mock_agent),
        patch("routes.recipes_v2.get_safety_gate", return_value=RecipeSafetyGate()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v2/recipes/transcribe_and_notify/execute",
                json={
                    "inputs": {
                        "audio_url": "https://example.com/audio.mp3",
                        "to": "tom@example.com",
                    },
                    "credential_mode": "byo",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["step_results"][1]["provider_used"] == "people-data-labs"
    assert body["data"]["step_results"][1]["outputs"]["provider_used"] == "people-data-labs"
    assert body["data"]["outputs"]["notify"]["provider_used"] == "people-data-labs"

    step_insert_payloads = [call.args[1] for call in mock_insert_required.await_args_list[1:]]
    assert step_insert_payloads[1]["outputs"]["provider_used"] == "people-data-labs"


@pytest.mark.anyio
async def test_execute_recipe_canonicalizes_alias_backed_captured_provider_payload_fields_on_response_and_persistence(app, mock_agent):
    recipe_row = deepcopy(RECIPE_ROW)
    recipe_row["definition"]["steps"][1]["outputs_captured"] = {
        "winner_provider": "result.provider_slug",
        "selected_provider_capture": "result.selected_provider",
        "fallback_provider_capture": "result.fallback_provider",
        "fallback_provider_candidates": "result.fallback_providers",
    }

    def _mock_supabase_fetch_with_captured_provider_payload_fields(path: str):
        if path.startswith("recipes?") and "recipe_id=eq.transcribe_and_notify" in path:
            return [recipe_row]
        if path.startswith("recipes?"):
            return [recipe_row]
        if path.startswith("recipe_executions?"):
            return []
        if path.startswith("recipe_step_executions?"):
            return []
        return []

    async def _mock_forward(raw_request, *, method: str, path: str, params=None, json_body=None):
        if path == "/v2/capabilities/media.transcribe/execute":
            return _MockResponse(
                200,
                {
                    "data": {
                        "provider_used": "assemblyai",
                        "upstream_response": {"transcript": "hello world"},
                        "cost_estimate_usd": 0.03,
                        "latency_ms": 120,
                        "receipt_id": "rcpt_step_transcribe",
                        "execution_id": "exec_step_1",
                    },
                    "error": None,
                },
            )
        if path == "/v2/capabilities/email.send/execute":
            return _MockResponse(
                200,
                {
                    "data": {
                        "provider_used": "pdl",
                        "upstream_response": {
                            "id": "msg_123",
                            "provider_slug": "pdl",
                            "selected_provider": "pdl",
                            "fallback_provider": "brave-search",
                            "fallback_providers": ["pdl", "brave-search"],
                        },
                        "cost_estimate_usd": 0.01,
                        "latency_ms": 80,
                        "receipt_id": "rcpt_step_notify",
                        "execution_id": "exec_step_2",
                    },
                    "error": None,
                },
            )
        raise AssertionError(f"unexpected internal forward path: {path}")

    with (
        patch("routes.recipes_v2.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase_fetch_with_captured_provider_payload_fields),
        patch("routes.recipes_v2.supabase_insert_required", new_callable=AsyncMock, return_value=None) as mock_insert_required,
        patch("routes.recipes_v2.supabase_patch_required", new_callable=AsyncMock, return_value=[]),
        patch("routes.recipes_v2._forward_internal", new_callable=AsyncMock, side_effect=_mock_forward),
        patch("routes.recipes_v2._resolve_policy_agent", new_callable=AsyncMock, return_value=mock_agent),
        patch("routes.recipes_v2.get_safety_gate", return_value=RecipeSafetyGate()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v2/recipes/transcribe_and_notify/execute",
                json={
                    "inputs": {
                        "audio_url": "https://example.com/audio.mp3",
                        "to": "tom@example.com",
                    },
                    "credential_mode": "byo",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert response.status_code == 200
    body = response.json()
    notify_outputs = body["data"]["step_results"][1]["outputs"]
    assert notify_outputs["winner_provider"] == "people-data-labs"
    assert notify_outputs["selected_provider_capture"] == "people-data-labs"
    assert notify_outputs["fallback_provider_capture"] == "brave-search-api"
    assert notify_outputs["fallback_provider_candidates"] == ["people-data-labs", "brave-search-api"]
    assert body["data"]["outputs"]["notify"] == notify_outputs

    step_insert_payloads = [call.args[1] for call in mock_insert_required.await_args_list[1:]]
    assert step_insert_payloads[1]["outputs"] == notify_outputs


@pytest.mark.anyio
async def test_execute_recipe_canonicalizes_alias_backed_provider_text_fields_in_outputs(app, mock_agent):
    recipe_row = deepcopy(RECIPE_ROW)
    recipe_row["definition"]["steps"][1]["outputs_captured"] = {
        "provider_message": "result.message",
        "provider_detail": "result.detail",
        "provider_error_message": "result.error_message",
        "winner_provider": "result.provider_slug",
        "fallback_provider_capture": "result.fallback_provider",
        "fallback_provider_candidates": "result.fallback_providers",
    }

    def _mock_supabase_fetch_with_provider_text_outputs(path: str):
        if path.startswith("recipes?") and "recipe_id=eq.transcribe_and_notify" in path:
            return [recipe_row]
        if path.startswith("recipes?"):
            return [recipe_row]
        if path.startswith("recipe_executions?"):
            return []
        if path.startswith("recipe_step_executions?"):
            return []
        return []

    async def _mock_forward(raw_request, *, method: str, path: str, params=None, json_body=None):
        if path == "/v2/capabilities/media.transcribe/execute":
            return _MockResponse(
                200,
                {
                    "data": {
                        "provider_used": "assemblyai",
                        "upstream_response": {"transcript": "hello world"},
                        "cost_estimate_usd": 0.03,
                        "latency_ms": 120,
                        "receipt_id": "rcpt_step_transcribe",
                        "execution_id": "exec_step_1",
                    },
                    "error": None,
                },
            )
        if path == "/v2/capabilities/email.send/execute":
            return _MockResponse(
                200,
                {
                    "data": {
                        "provider_used": "pdl",
                        "upstream_response": {
                            "id": "msg_123",
                            "provider_slug": "pdl",
                            "message": "pdl retried after brave-search timeout",
                            "detail": "Fallback from brave-search to pdl succeeded",
                            "error_message": "brave-search timeout before pdl fallback",
                            "fallback_provider": "brave-search",
                            "fallback_providers": ["pdl", "brave-search"],
                        },
                        "cost_estimate_usd": 0.01,
                        "latency_ms": 80,
                        "receipt_id": "rcpt_step_notify",
                        "execution_id": "exec_step_2",
                    },
                    "error": None,
                },
            )
        raise AssertionError(f"unexpected internal forward path: {path}")

    with (
        patch("routes.recipes_v2.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase_fetch_with_provider_text_outputs),
        patch("routes.recipes_v2.supabase_insert_required", new_callable=AsyncMock, return_value=None) as mock_insert_required,
        patch("routes.recipes_v2.supabase_patch_required", new_callable=AsyncMock, return_value=[]),
        patch("routes.recipes_v2._forward_internal", new_callable=AsyncMock, side_effect=_mock_forward),
        patch("routes.recipes_v2._resolve_policy_agent", new_callable=AsyncMock, return_value=mock_agent),
        patch("routes.recipes_v2.get_safety_gate", return_value=RecipeSafetyGate()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v2/recipes/transcribe_and_notify/execute",
                json={
                    "inputs": {
                        "audio_url": "https://example.com/audio.mp3",
                        "to": "tom@example.com",
                    },
                    "credential_mode": "byo",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert response.status_code == 200
    body = response.json()
    notify_outputs = body["data"]["step_results"][1]["outputs"]
    assert notify_outputs["winner_provider"] == "people-data-labs"
    assert notify_outputs["provider_message"] == "people-data-labs retried after brave-search-api timeout"
    assert notify_outputs["provider_detail"] == "Fallback from brave-search-api to people-data-labs succeeded"
    assert notify_outputs["provider_error_message"] == "brave-search-api timeout before people-data-labs fallback"
    assert notify_outputs["fallback_provider_capture"] == "brave-search-api"
    assert notify_outputs["fallback_provider_candidates"] == ["people-data-labs", "brave-search-api"]
    assert body["data"]["outputs"]["notify"] == notify_outputs

    step_insert_payloads = [call.args[1] for call in mock_insert_required.await_args_list[1:]]
    assert step_insert_payloads[1]["outputs"] == notify_outputs


@pytest.mark.anyio
async def test_execute_recipe_canonicalizes_alias_backed_execution_error_text_on_response_and_persistence(app, mock_agent):
    mocked_execution = RecipeExecution(
        execution_id="rexec_mocked",
        recipe_id="transcribe_and_notify",
        status=RecipeStatus.FAILED,
        started_at=datetime(2026, 4, 17, 7, 0, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 4, 17, 7, 0, 2, tzinfo=timezone.utc),
        error="pdl upstream exploded",
        step_results={
            "notify": StepResult(
                step_id="notify",
                status=StepStatus.FAILED,
                provider_used="pdl",
                error="pdl upstream exploded",
                cost_usd=0.01,
                duration_ms=80,
                receipt_id="rcpt_step_notify",
            ),
        },
        total_cost_usd=0.01,
        total_duration_ms=80,
    )

    with (
        patch("routes.recipes_v2.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase_fetch),
        patch("routes.recipes_v2.supabase_insert_required", new_callable=AsyncMock, return_value=None) as mock_insert_required,
        patch("routes.recipes_v2.supabase_patch_required", new_callable=AsyncMock, return_value=[]) as mock_patch_required,
        patch("routes.recipes_v2.RecipeEngine.execute", new_callable=AsyncMock, return_value=mocked_execution),
        patch("routes.recipes_v2._resolve_policy_agent", new_callable=AsyncMock, return_value=mock_agent),
        patch("routes.recipes_v2.get_safety_gate", return_value=RecipeSafetyGate()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v2/recipes/transcribe_and_notify/execute",
                json={
                    "inputs": {
                        "audio_url": "https://example.com/audio.mp3",
                        "to": "tom@example.com",
                    },
                    "credential_mode": "byo",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert response.status_code == 422
    body = response.json()
    assert body["data"]["status"] == "failed"
    assert body["data"]["error"] == "people-data-labs upstream exploded"
    assert body["data"]["step_results"][0]["provider_used"] == "people-data-labs"
    assert body["data"]["step_results"][0]["error"] == "people-data-labs upstream exploded"

    assert mock_patch_required.await_args.args[1]["error"] == "people-data-labs upstream exploded"
    step_insert_payloads = [call.args[1] for call in mock_insert_required.await_args_list[1:]]
    assert step_insert_payloads[0]["provider_used"] == "people-data-labs"
    assert step_insert_payloads[0]["error"] == "people-data-labs upstream exploded"


@pytest.mark.anyio
async def test_execute_recipe_canonicalizes_alias_backed_step_error_text_on_response_and_persistence(app, mock_agent):
    async def _mock_forward(raw_request, *, method: str, path: str, params=None, json_body=None):
        if path == "/v2/capabilities/media.transcribe/execute":
            return _MockResponse(
                200,
                {
                    "data": {
                        "provider_used": "assemblyai",
                        "upstream_response": {"transcript": "hello world"},
                        "cost_estimate_usd": 0.03,
                        "latency_ms": 120,
                        "receipt_id": "rcpt_step_transcribe",
                        "execution_id": "exec_step_1",
                    },
                    "error": None,
                },
            )
        if path == "/v2/capabilities/email.send/execute":
            return _MockResponse(
                422,
                {
                    "data": {
                        "provider_used": "pdl",
                        "cost_estimate_usd": 0.01,
                        "latency_ms": 80,
                        "receipt_id": "rcpt_step_notify",
                        "execution_id": "exec_step_2",
                    },
                    "error": {"message": "pdl upstream exploded"},
                },
            )
        raise AssertionError(f"unexpected internal forward path: {path}")

    with (
        patch("routes.recipes_v2.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase_fetch),
        patch("routes.recipes_v2.supabase_insert_required", new_callable=AsyncMock, return_value=None) as mock_insert_required,
        patch("routes.recipes_v2.supabase_patch_required", new_callable=AsyncMock, return_value=[]),
        patch("routes.recipes_v2._forward_internal", new_callable=AsyncMock, side_effect=_mock_forward),
        patch("routes.recipes_v2._resolve_policy_agent", new_callable=AsyncMock, return_value=mock_agent),
        patch("routes.recipes_v2.get_safety_gate", return_value=RecipeSafetyGate()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v2/recipes/transcribe_and_notify/execute",
                json={
                    "inputs": {
                        "audio_url": "https://example.com/audio.mp3",
                        "to": "tom@example.com",
                    },
                    "credential_mode": "byo",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "partial"
    assert body["data"]["step_results"][1]["provider_used"] == "people-data-labs"
    assert body["data"]["step_results"][1]["error"] == "people-data-labs upstream exploded"

    step_insert_payloads = [call.args[1] for call in mock_insert_required.await_args_list[1:]]
    assert step_insert_payloads[1]["provider_used"] == "people-data-labs"
    assert step_insert_payloads[1]["error"] == "people-data-labs upstream exploded"


@pytest.mark.anyio
async def test_execute_recipe_canonicalizes_alternate_provider_aliases_in_step_error_text(app, mock_agent):
    async def _mock_forward(raw_request, *, method: str, path: str, params=None, json_body=None):
        if path == "/v2/capabilities/media.transcribe/execute":
            return _MockResponse(
                200,
                {
                    "data": {
                        "provider_used": "assemblyai",
                        "upstream_response": {"transcript": "hello world"},
                        "cost_estimate_usd": 0.03,
                        "latency_ms": 120,
                        "receipt_id": "rcpt_step_transcribe",
                        "execution_id": "exec_step_1",
                    },
                    "error": None,
                },
            )
        if path == "/v2/capabilities/email.send/execute":
            return _MockResponse(
                422,
                {
                    "data": {
                        "provider_used": "pdl",
                        "fallback_provider": "brave-search",
                        "fallback_providers": ["pdl", "brave-search"],
                        "cost_estimate_usd": 0.01,
                        "latency_ms": 80,
                        "receipt_id": "rcpt_step_notify",
                        "execution_id": "exec_step_2",
                    },
                    "error": {"message": "pdl upstream exploded after brave-search timeout"},
                },
            )
        raise AssertionError(f"unexpected internal forward path: {path}")

    with (
        patch("routes.recipes_v2.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase_fetch),
        patch("routes.recipes_v2.supabase_insert_required", new_callable=AsyncMock, return_value=None) as mock_insert_required,
        patch("routes.recipes_v2.supabase_patch_required", new_callable=AsyncMock, return_value=[]),
        patch("routes.recipes_v2._forward_internal", new_callable=AsyncMock, side_effect=_mock_forward),
        patch("routes.recipes_v2._resolve_policy_agent", new_callable=AsyncMock, return_value=mock_agent),
        patch("routes.recipes_v2.get_safety_gate", return_value=RecipeSafetyGate()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v2/recipes/transcribe_and_notify/execute",
                json={
                    "inputs": {
                        "audio_url": "https://example.com/audio.mp3",
                        "to": "tom@example.com",
                    },
                    "credential_mode": "byo",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "partial"
    assert body["data"]["step_results"][1]["provider_used"] == "people-data-labs"
    assert body["data"]["step_results"][1]["error"] == (
        "people-data-labs upstream exploded after brave-search-api timeout"
    )

    step_insert_payloads = [call.args[1] for call in mock_insert_required.await_args_list[1:]]
    assert step_insert_payloads[1]["provider_used"] == "people-data-labs"
    assert step_insert_payloads[1]["error"] == (
        "people-data-labs upstream exploded after brave-search-api timeout"
    )


@pytest.mark.anyio
async def test_execute_recipe_propagates_step_idempotency_keys(app, mock_agent):
    forward_calls: list[tuple[str, dict]] = []
    mock_store = MagicMock()
    mock_store.claim = AsyncMock(return_value=None)
    mock_store.store = AsyncMock(return_value=None)

    async def _mock_forward(raw_request, *, method: str, path: str, params=None, json_body=None):
        forward_calls.append((path, json_body or {}))
        return _MockResponse(
            200,
            {
                "data": {
                    "provider_used": "test-provider",
                    "upstream_response": {"ok": True, "path": path},
                    "cost_estimate_usd": 0.01,
                    "latency_ms": 10,
                    "receipt_id": f"rcpt_{path.split('/')[-2]}",
                    "execution_id": f"exec_{path.split('/')[-2]}",
                },
                "error": None,
            },
        )

    with (
        patch("routes.recipes_v2.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase_fetch),
        patch("routes.recipes_v2.supabase_insert", new_callable=AsyncMock, return_value=True),
        patch("routes.recipes_v2._forward_internal", new_callable=AsyncMock, side_effect=_mock_forward),
        patch("routes.recipes_v2._resolve_policy_agent", new_callable=AsyncMock, return_value=mock_agent),
        patch("routes.recipes_v2.get_safety_gate", return_value=RecipeSafetyGate()),
        patch("routes.recipes_v2._get_idempotency_store", new_callable=AsyncMock, return_value=mock_store),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v2/recipes/transcribe_and_notify/execute",
                json={
                    "inputs": {
                        "audio_url": "https://example.com/audio.mp3",
                        "to": "tom@example.com",
                    },
                    "credential_mode": "byo",
                    "idempotency_key": "recipe-idem-1",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert response.status_code == 200
    assert forward_calls[0][1]["idempotency_key"] == "recipe:transcribe_and_notify:recipe-idem-1:transcribe"
    assert forward_calls[1][1]["idempotency_key"] == "recipe:transcribe_and_notify:recipe-idem-1:notify"
    mock_store.claim.assert_awaited_once()
    mock_store.store.assert_awaited_once()


@pytest.mark.anyio
async def test_execute_recipe_blocks_on_aggregate_fanout_limit(app, mock_agent):
    forward_calls: list[tuple[str, dict]] = []
    mock_limiter = MagicMock()
    mock_limiter.check_and_increment = AsyncMock(
        side_effect=[
            (True, 499),
            (True, 1999),
            (False, 0),
        ]
    )

    async def _mock_forward(raw_request, *, method: str, path: str, params=None, json_body=None):
        forward_calls.append((path, json_body or {}))
        return _MockResponse(
            200,
            {
                "data": {
                    "provider_used": "assemblyai",
                    "upstream_response": {"transcript": "hello world", "id": "msg_123"},
                    "cost_estimate_usd": 0.03,
                    "latency_ms": 120,
                    "receipt_id": "rcpt_step",
                    "execution_id": "exec_step",
                },
                "error": None,
            },
        )

    with (
        patch("routes.recipes_v2.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase_fetch),
        patch("routes.recipes_v2._forward_internal", new_callable=AsyncMock, side_effect=_mock_forward),
        patch("routes.recipes_v2._resolve_policy_agent", new_callable=AsyncMock, return_value=mock_agent),
        patch("routes.recipes_v2.get_safety_gate", return_value=RecipeSafetyGate()),
        patch(
            "routes.recipes_v2._get_recipe_step_rate_limiter",
            new_callable=AsyncMock,
            return_value=mock_limiter,
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v2/recipes/transcribe_and_notify/execute",
                json={
                    "inputs": {
                        "audio_url": "https://example.com/audio.mp3",
                        "to": "tom@example.com",
                    },
                    "credential_mode": "byo",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["data"]["status"] == "partial"
    assert len(forward_calls) == 1
    assert "aggregate recipe fan-out limit exceeded" in body["data"]["step_results"][1]["error"].lower()
    assert mock_limiter.check_and_increment.await_count == 3


@pytest.mark.anyio
async def test_execute_recipe_deduplicates_via_durable_store(app, mock_agent):
    mock_store = MagicMock()
    mock_store.claim = AsyncMock(return_value=MagicMock(
        execution_id="rexec_existing123",
        recipe_id="transcribe_and_notify",
        status="completed",
        result_hash="hash123",
    ))

    with (
        patch("routes.recipes_v2.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase_fetch),
        patch("routes.recipes_v2._resolve_policy_agent", new_callable=AsyncMock, return_value=mock_agent),
        patch("routes.recipes_v2._get_idempotency_store", new_callable=AsyncMock, return_value=mock_store),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v2/recipes/transcribe_and_notify/execute",
                json={
                    "inputs": {
                        "audio_url": "https://example.com/audio.mp3",
                        "to": "tom@example.com",
                    },
                    "credential_mode": "byo",
                    "idempotency_key": "recipe-idem-1",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["deduplicated"] is True
    assert body["data"]["execution_id"] == "rexec_existing123"


@pytest.mark.anyio
async def test_execute_recipe_deduplicated_replay_canonicalizes_alias_backed_provider_ids(app, mock_agent):
    mock_store = MagicMock()
    mock_store.claim = AsyncMock(return_value=MagicMock(
        execution_id="rexec_existing123",
        recipe_id="transcribe_and_notify",
        status="completed",
        result_hash="hash123",
    ))

    def _mock_supabase_fetch_with_existing_rows(path: str):
        if path.startswith("recipes?") and "recipe_id=eq.transcribe_and_notify" in path:
            return [RECIPE_ROW]
        if path.startswith("recipe_executions?") and "execution_id=eq.rexec_existing123" in path:
            return [{
                "execution_id": "rexec_existing123",
                "recipe_id": "transcribe_and_notify",
                "status": "completed",
                "inputs": {},
                "total_cost_usd": 0.04,
                "total_duration_ms": 200,
                "step_count": 2,
                "steps_completed": 2,
                "error": None,
                "started_at": "2026-04-17T07:00:00Z",
                "completed_at": "2026-04-17T07:00:02Z",
                "org_id": "org_recipe_test",
                "agent_id": "agent_recipe_test",
                "credential_mode": "byo",
            }]
        if path.startswith("recipe_step_executions?") and "execution_id=eq.rexec_existing123" in path:
            return [
                {
                    "execution_id": "rexec_existing123",
                    "step_id": "transcribe",
                    "capability_id": "media.transcribe",
                    "status": "succeeded",
                    "cost_usd": 0.03,
                    "duration_ms": 120,
                    "receipt_id": "rcpt_step_transcribe",
                    "provider_used": "brave-search",
                    "retries_used": 0,
                    "error": None,
                    "outputs": {"transcript_text": "hello world"},
                },
                {
                    "execution_id": "rexec_existing123",
                    "step_id": "notify",
                    "capability_id": "email.send",
                    "status": "succeeded",
                    "cost_usd": 0.01,
                    "duration_ms": 80,
                    "receipt_id": "rcpt_step_notify",
                    "provider_used": "pdl",
                    "retries_used": 0,
                    "error": None,
                    "outputs": {"message_id": "msg_123"},
                },
            ]
        return _mock_supabase_fetch(path)

    with (
        patch("routes.recipes_v2.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase_fetch_with_existing_rows),
        patch("routes.recipes_v2._resolve_policy_agent", new_callable=AsyncMock, return_value=mock_agent),
        patch("routes.recipes_v2._get_idempotency_store", new_callable=AsyncMock, return_value=mock_store),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v2/recipes/transcribe_and_notify/execute",
                json={
                    "inputs": {
                        "audio_url": "https://example.com/audio.mp3",
                        "to": "tom@example.com",
                    },
                    "credential_mode": "byo",
                    "idempotency_key": "recipe-idem-1",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["deduplicated"] is True
    assert body["data"]["step_results"][0]["provider_used"] == "brave-search-api"
    assert body["data"]["step_results"][1]["provider_used"] == "people-data-labs"


@pytest.mark.anyio
async def test_execute_recipe_deduplicated_replay_canonicalizes_alias_backed_provider_outputs(app, mock_agent):
    recipe_row = deepcopy(RECIPE_ROW)
    recipe_row["definition"]["steps"][1]["outputs_captured"] = {"selected_provider": "provider_used"}

    mock_store = MagicMock()
    mock_store.claim = AsyncMock(return_value=MagicMock(
        execution_id="rexec_existing123",
        recipe_id="transcribe_and_notify",
        status="completed",
        result_hash="hash123",
    ))

    def _mock_supabase_fetch_with_existing_provider_output_rows(path: str):
        if path.startswith("recipes?") and "recipe_id=eq.transcribe_and_notify" in path:
            return [recipe_row]
        if path.startswith("recipe_executions?") and "execution_id=eq.rexec_existing123" in path:
            return [{
                "execution_id": "rexec_existing123",
                "recipe_id": "transcribe_and_notify",
                "status": "completed",
                "inputs": {},
                "total_cost_usd": 0.04,
                "total_duration_ms": 200,
                "step_count": 2,
                "steps_completed": 2,
                "error": None,
                "started_at": "2026-04-17T07:00:00Z",
                "completed_at": "2026-04-17T07:00:02Z",
                "org_id": "org_recipe_test",
                "agent_id": "agent_recipe_test",
                "credential_mode": "byo",
            }]
        if path.startswith("recipe_step_executions?") and "execution_id=eq.rexec_existing123" in path:
            return [
                {
                    "execution_id": "rexec_existing123",
                    "step_id": "transcribe",
                    "capability_id": "media.transcribe",
                    "status": "succeeded",
                    "cost_usd": 0.03,
                    "duration_ms": 120,
                    "receipt_id": "rcpt_step_transcribe",
                    "provider_used": "assemblyai",
                    "retries_used": 0,
                    "error": None,
                    "outputs": {"transcript_text": "hello world"},
                },
                {
                    "execution_id": "rexec_existing123",
                    "step_id": "notify",
                    "capability_id": "email.send",
                    "status": "succeeded",
                    "cost_usd": 0.01,
                    "duration_ms": 80,
                    "receipt_id": "rcpt_step_notify",
                    "provider_used": "pdl",
                    "retries_used": 0,
                    "error": None,
                    "outputs": {"selected_provider": "pdl"},
                },
            ]
        return _mock_supabase_fetch(path)

    with (
        patch("routes.recipes_v2.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase_fetch_with_existing_provider_output_rows),
        patch("routes.recipes_v2._resolve_policy_agent", new_callable=AsyncMock, return_value=mock_agent),
        patch("routes.recipes_v2._get_idempotency_store", new_callable=AsyncMock, return_value=mock_store),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v2/recipes/transcribe_and_notify/execute",
                json={
                    "inputs": {
                        "audio_url": "https://example.com/audio.mp3",
                        "to": "tom@example.com",
                    },
                    "credential_mode": "byo",
                    "idempotency_key": "recipe-idem-1",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["deduplicated"] is True
    assert body["data"]["step_results"][1]["provider_used"] == "people-data-labs"
    assert body["data"]["step_results"][1]["outputs"]["selected_provider"] == "people-data-labs"
    assert body["data"]["outputs"]["notify"]["selected_provider"] == "people-data-labs"


@pytest.mark.anyio
async def test_execute_recipe_deduplicated_replay_canonicalizes_alias_backed_captured_provider_payload_fields(app, mock_agent):
    recipe_row = deepcopy(RECIPE_ROW)
    recipe_row["definition"]["steps"][1]["outputs_captured"] = {
        "winner_provider": "result.provider_slug",
        "selected_provider_capture": "result.selected_provider",
        "fallback_provider_capture": "result.fallback_provider",
        "fallback_provider_candidates": "result.fallback_providers",
    }

    mock_store = MagicMock()
    mock_store.claim = AsyncMock(return_value=MagicMock(
        execution_id="rexec_existing123",
        recipe_id="transcribe_and_notify",
        status="completed",
        result_hash="hash123",
    ))

    def _mock_supabase_fetch_with_existing_captured_provider_output_rows(path: str):
        if path.startswith("recipes?") and "recipe_id=eq.transcribe_and_notify" in path:
            return [recipe_row]
        if path.startswith("recipe_executions?") and "execution_id=eq.rexec_existing123" in path:
            return [{
                "execution_id": "rexec_existing123",
                "recipe_id": "transcribe_and_notify",
                "status": "completed",
                "inputs": {},
                "total_cost_usd": 0.04,
                "total_duration_ms": 200,
                "step_count": 2,
                "steps_completed": 2,
                "error": None,
                "started_at": "2026-04-17T07:00:00Z",
                "completed_at": "2026-04-17T07:00:02Z",
                "org_id": "org_recipe_test",
                "agent_id": "agent_recipe_test",
                "credential_mode": "byo",
            }]
        if path.startswith("recipe_step_executions?") and "execution_id=eq.rexec_existing123" in path:
            return [
                {
                    "execution_id": "rexec_existing123",
                    "step_id": "transcribe",
                    "capability_id": "media.transcribe",
                    "status": "succeeded",
                    "cost_usd": 0.03,
                    "duration_ms": 120,
                    "receipt_id": "rcpt_step_transcribe",
                    "provider_used": "assemblyai",
                    "retries_used": 0,
                    "error": None,
                    "outputs": {"transcript_text": "hello world"},
                },
                {
                    "execution_id": "rexec_existing123",
                    "step_id": "notify",
                    "capability_id": "email.send",
                    "status": "succeeded",
                    "cost_usd": 0.01,
                    "duration_ms": 80,
                    "receipt_id": "rcpt_step_notify",
                    "provider_used": "pdl",
                    "retries_used": 0,
                    "error": None,
                    "outputs": {
                        "winner_provider": "pdl",
                        "selected_provider_capture": "pdl",
                        "fallback_provider_capture": "brave-search",
                        "fallback_provider_candidates": ["pdl", "brave-search"],
                    },
                },
            ]
        return _mock_supabase_fetch(path)

    with (
        patch("routes.recipes_v2.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase_fetch_with_existing_captured_provider_output_rows),
        patch("routes.recipes_v2._resolve_policy_agent", new_callable=AsyncMock, return_value=mock_agent),
        patch("routes.recipes_v2._get_idempotency_store", new_callable=AsyncMock, return_value=mock_store),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v2/recipes/transcribe_and_notify/execute",
                json={
                    "inputs": {
                        "audio_url": "https://example.com/audio.mp3",
                        "to": "tom@example.com",
                    },
                    "credential_mode": "byo",
                    "idempotency_key": "recipe-idem-1",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["deduplicated"] is True
    notify_outputs = body["data"]["step_results"][1]["outputs"]
    assert notify_outputs["winner_provider"] == "people-data-labs"
    assert notify_outputs["selected_provider_capture"] == "people-data-labs"
    assert notify_outputs["fallback_provider_capture"] == "brave-search-api"
    assert notify_outputs["fallback_provider_candidates"] == ["people-data-labs", "brave-search-api"]
    assert body["data"]["outputs"]["notify"] == notify_outputs


@pytest.mark.anyio
async def test_execute_recipe_deduplicated_replay_canonicalizes_alias_backed_provider_text_fields_in_outputs(app, mock_agent):
    recipe_row = deepcopy(RECIPE_ROW)
    recipe_row["definition"]["steps"][1]["outputs_captured"] = {
        "provider_message": "result.message",
        "provider_detail": "result.detail",
        "provider_error_message": "result.error_message",
        "winner_provider": "result.provider_slug",
        "fallback_provider_capture": "result.fallback_provider",
        "fallback_provider_candidates": "result.fallback_providers",
    }

    mock_store = MagicMock()
    mock_store.claim = AsyncMock(return_value=MagicMock(
        execution_id="rexec_existing123",
        recipe_id="transcribe_and_notify",
        status="completed",
        result_hash="hash123",
    ))

    def _mock_supabase_fetch_with_existing_provider_text_output_rows(path: str):
        if path.startswith("recipes?") and "recipe_id=eq.transcribe_and_notify" in path:
            return [recipe_row]
        if path.startswith("recipe_executions?") and "execution_id=eq.rexec_existing123" in path:
            return [{
                "execution_id": "rexec_existing123",
                "recipe_id": "transcribe_and_notify",
                "status": "completed",
                "inputs": {},
                "total_cost_usd": 0.04,
                "total_duration_ms": 200,
                "step_count": 2,
                "steps_completed": 2,
                "error": None,
                "started_at": "2026-04-17T07:00:00Z",
                "completed_at": "2026-04-17T07:00:02Z",
                "org_id": "org_recipe_test",
                "agent_id": "agent_recipe_test",
                "credential_mode": "byo",
            }]
        if path.startswith("recipe_step_executions?") and "execution_id=eq.rexec_existing123" in path:
            return [
                {
                    "execution_id": "rexec_existing123",
                    "step_id": "transcribe",
                    "capability_id": "media.transcribe",
                    "status": "succeeded",
                    "cost_usd": 0.03,
                    "duration_ms": 120,
                    "receipt_id": "rcpt_step_transcribe",
                    "provider_used": "assemblyai",
                    "retries_used": 0,
                    "error": None,
                    "outputs": {"transcript_text": "hello world"},
                },
                {
                    "execution_id": "rexec_existing123",
                    "step_id": "notify",
                    "capability_id": "email.send",
                    "status": "succeeded",
                    "cost_usd": 0.01,
                    "duration_ms": 80,
                    "receipt_id": "rcpt_step_notify",
                    "provider_used": "pdl",
                    "retries_used": 0,
                    "error": None,
                    "outputs": {
                        "provider_message": "pdl retried after brave-search timeout",
                        "provider_detail": "Fallback from brave-search to pdl succeeded",
                        "provider_error_message": "brave-search timeout before pdl fallback",
                        "winner_provider": "pdl",
                        "fallback_provider_capture": "brave-search",
                        "fallback_provider_candidates": ["pdl", "brave-search"],
                    },
                },
            ]
        return _mock_supabase_fetch(path)

    with (
        patch("routes.recipes_v2.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase_fetch_with_existing_provider_text_output_rows),
        patch("routes.recipes_v2._resolve_policy_agent", new_callable=AsyncMock, return_value=mock_agent),
        patch("routes.recipes_v2._get_idempotency_store", new_callable=AsyncMock, return_value=mock_store),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v2/recipes/transcribe_and_notify/execute",
                json={
                    "inputs": {
                        "audio_url": "https://example.com/audio.mp3",
                        "to": "tom@example.com",
                    },
                    "credential_mode": "byo",
                    "idempotency_key": "recipe-idem-1",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["deduplicated"] is True
    notify_outputs = body["data"]["step_results"][1]["outputs"]
    assert notify_outputs["winner_provider"] == "people-data-labs"
    assert notify_outputs["provider_message"] == "people-data-labs retried after brave-search-api timeout"
    assert notify_outputs["provider_detail"] == "Fallback from brave-search-api to people-data-labs succeeded"
    assert notify_outputs["provider_error_message"] == "brave-search-api timeout before people-data-labs fallback"
    assert notify_outputs["fallback_provider_capture"] == "brave-search-api"
    assert notify_outputs["fallback_provider_candidates"] == ["people-data-labs", "brave-search-api"]
    assert body["data"]["outputs"]["notify"] == notify_outputs


@pytest.mark.anyio
async def test_execute_recipe_deduplicated_replay_canonicalizes_alias_backed_execution_error_text(app, mock_agent):
    mock_store = MagicMock()
    mock_store.claim = AsyncMock(return_value=MagicMock(
        execution_id="rexec_existing123",
        recipe_id="transcribe_and_notify",
        status="failed",
        result_hash="hash123",
    ))

    def _mock_supabase_fetch_with_existing_failed_rows(path: str):
        if path.startswith("recipes?") and "recipe_id=eq.transcribe_and_notify" in path:
            return [RECIPE_ROW]
        if path.startswith("recipe_executions?") and "execution_id=eq.rexec_existing123" in path:
            return [{
                "execution_id": "rexec_existing123",
                "recipe_id": "transcribe_and_notify",
                "status": "failed",
                "inputs": {},
                "total_cost_usd": 0.04,
                "total_duration_ms": 200,
                "step_count": 1,
                "steps_completed": 0,
                "error": "pdl upstream exploded",
                "started_at": "2026-04-17T07:00:00Z",
                "completed_at": "2026-04-17T07:00:02Z",
                "org_id": "org_recipe_test",
                "agent_id": "agent_recipe_test",
                "credential_mode": "byo",
            }]
        if path.startswith("recipe_step_executions?") and "execution_id=eq.rexec_existing123" in path:
            return [
                {
                    "execution_id": "rexec_existing123",
                    "step_id": "notify",
                    "capability_id": "email.send",
                    "status": "failed",
                    "cost_usd": 0.01,
                    "duration_ms": 80,
                    "receipt_id": "rcpt_step_notify",
                    "provider_used": "pdl",
                    "retries_used": 0,
                    "error": "pdl upstream exploded",
                    "outputs": {},
                },
            ]
        return _mock_supabase_fetch(path)

    with (
        patch("routes.recipes_v2.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase_fetch_with_existing_failed_rows),
        patch("routes.recipes_v2._resolve_policy_agent", new_callable=AsyncMock, return_value=mock_agent),
        patch("routes.recipes_v2._get_idempotency_store", new_callable=AsyncMock, return_value=mock_store),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v2/recipes/transcribe_and_notify/execute",
                json={
                    "inputs": {
                        "audio_url": "https://example.com/audio.mp3",
                        "to": "tom@example.com",
                    },
                    "credential_mode": "byo",
                    "idempotency_key": "recipe-idem-1",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "failed"
    assert body["data"]["deduplicated"] is True
    assert body["data"]["error"] == "people-data-labs upstream exploded"
    assert body["data"]["step_results"][0]["provider_used"] == "people-data-labs"
    assert body["data"]["step_results"][0]["error"] == "people-data-labs upstream exploded"


@pytest.mark.anyio
async def test_execute_recipe_deduplicated_replay_canonicalizes_alias_backed_step_error_text(app, mock_agent):
    mock_store = MagicMock()
    mock_store.claim = AsyncMock(return_value=MagicMock(
        execution_id="rexec_existing123",
        recipe_id="transcribe_and_notify",
        status="failed",
        result_hash="hash123",
    ))

    def _mock_supabase_fetch_with_existing_failed_rows(path: str):
        if path.startswith("recipes?") and "recipe_id=eq.transcribe_and_notify" in path:
            return [RECIPE_ROW]
        if path.startswith("recipe_executions?") and "execution_id=eq.rexec_existing123" in path:
            return [{
                "execution_id": "rexec_existing123",
                "recipe_id": "transcribe_and_notify",
                "status": "failed",
                "inputs": {},
                "total_cost_usd": 0.04,
                "total_duration_ms": 200,
                "step_count": 2,
                "steps_completed": 1,
                "error": "One or more recipe steps failed",
                "started_at": "2026-04-17T07:00:00Z",
                "completed_at": "2026-04-17T07:00:02Z",
                "org_id": "org_recipe_test",
                "agent_id": "agent_recipe_test",
                "credential_mode": "byo",
            }]
        if path.startswith("recipe_step_executions?") and "execution_id=eq.rexec_existing123" in path:
            return [
                {
                    "execution_id": "rexec_existing123",
                    "step_id": "transcribe",
                    "capability_id": "media.transcribe",
                    "status": "succeeded",
                    "cost_usd": 0.03,
                    "duration_ms": 120,
                    "receipt_id": "rcpt_step_transcribe",
                    "provider_used": "assemblyai",
                    "retries_used": 0,
                    "error": None,
                    "outputs": {"transcript_text": "hello world"},
                },
                {
                    "execution_id": "rexec_existing123",
                    "step_id": "notify",
                    "capability_id": "email.send",
                    "status": "failed",
                    "cost_usd": 0.01,
                    "duration_ms": 80,
                    "receipt_id": "rcpt_step_notify",
                    "provider_used": "pdl",
                    "retries_used": 0,
                    "error": "pdl upstream exploded",
                    "outputs": {},
                },
            ]
        return _mock_supabase_fetch(path)

    with (
        patch("routes.recipes_v2.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase_fetch_with_existing_failed_rows),
        patch("routes.recipes_v2._resolve_policy_agent", new_callable=AsyncMock, return_value=mock_agent),
        patch("routes.recipes_v2._get_idempotency_store", new_callable=AsyncMock, return_value=mock_store),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v2/recipes/transcribe_and_notify/execute",
                json={
                    "inputs": {
                        "audio_url": "https://example.com/audio.mp3",
                        "to": "tom@example.com",
                    },
                    "credential_mode": "byo",
                    "idempotency_key": "recipe-idem-1",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["deduplicated"] is True
    assert body["data"]["step_results"][1]["provider_used"] == "people-data-labs"
    assert body["data"]["step_results"][1]["error"] == "people-data-labs upstream exploded"


@pytest.mark.anyio
async def test_execute_recipe_idempotency_unavailable_fails_closed(app, mock_agent):
    mock_store = MagicMock()
    mock_store.claim = AsyncMock(side_effect=IdempotencyUnavailable("DB down"))

    with (
        patch("routes.recipes_v2.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase_fetch),
        patch("routes.recipes_v2._resolve_policy_agent", new_callable=AsyncMock, return_value=mock_agent),
        patch("routes.recipes_v2._get_idempotency_store", new_callable=AsyncMock, return_value=mock_store),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v2/recipes/transcribe_and_notify/execute",
                json={
                    "inputs": {
                        "audio_url": "https://example.com/audio.mp3",
                        "to": "tom@example.com",
                    },
                    "credential_mode": "byo",
                    "idempotency_key": "recipe-idem-1",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "EXECUTION_DISABLED"
    assert "idempotency protection" in body["error"]["message"].lower()


@pytest.mark.anyio
async def test_execute_recipe_fails_when_placeholder_write_unavailable(app, mock_agent):
    with (
        patch("routes.recipes_v2.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase_fetch),
        patch("routes.recipes_v2._resolve_policy_agent", new_callable=AsyncMock, return_value=mock_agent),
        patch(
            "routes.recipes_v2.supabase_insert_required",
            new_callable=AsyncMock,
            side_effect=SupabaseWriteUnavailable("down"),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v2/recipes/transcribe_and_notify/execute",
                json={
                    "inputs": {
                        "audio_url": "https://example.com/audio.mp3",
                        "to": "tom@example.com",
                    },
                    "credential_mode": "byo",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "EXECUTION_DISABLED"
    assert "control plane" in body["error"]["message"].lower()


@pytest.mark.anyio
async def test_execute_recipe_blocks_when_kill_switch_active(app, mock_agent):
    mock_registry = MagicMock()
    mock_registry.is_blocked.return_value = (
        True,
        "Recipe kill switch active: runaway spend",
    )

    with (
        patch("routes.recipes_v2.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase_fetch),
        patch("routes.recipes_v2._resolve_policy_agent", new_callable=AsyncMock, return_value=mock_agent),
        patch("routes.recipes_v2.init_kill_switch_registry", new_callable=AsyncMock, return_value=mock_registry),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v2/recipes/transcribe_and_notify/execute",
                json={
                    "inputs": {
                        "audio_url": "https://example.com/audio.mp3",
                        "to": "tom@example.com",
                    },
                    "credential_mode": "byo",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "PROVIDER_UNAVAILABLE"
    assert "kill switch" in body["error"]["message"].lower()
    assert "runaway spend" in body["error"]["detail"].lower()
    mock_registry.is_blocked.assert_called_once_with(
        agent_id=mock_agent.agent_id,
        recipe_id="transcribe_and_notify",
        operation_class="financial",
        require_authoritative=True,
    )


@pytest.mark.anyio
async def test_execute_recipe_blocks_when_event_outbox_unhealthy(app, mock_agent):
    with (
        patch("routes.recipes_v2.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase_fetch),
        patch("routes.recipes_v2._resolve_policy_agent", new_callable=AsyncMock, return_value=mock_agent),
        patch(
            "routes.recipes_v2.get_event_outbox_health",
            return_value=type(
                "OutboxHealth",
                (),
                {
                    "allows_risky_writes": False,
                    "reason": "Durable event backlog exceeded safe threshold (1200>1000).",
                },
            )(),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v2/recipes/transcribe_and_notify/execute",
                json={
                    "inputs": {
                        "audio_url": "https://example.com/audio.mp3",
                        "to": "tom@example.com",
                    },
                    "credential_mode": "byo",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "EXECUTION_DISABLED"
    assert "durability" in body["error"]["message"].lower()
    assert "threshold" in body["error"]["detail"].lower()
