"""Tests for Resolve v2 recipe endpoints (WU-42.3)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app
from schemas.agent_identity import AgentIdentitySchema
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
        patch("routes.recipes_v2.supabase_insert", new_callable=AsyncMock, return_value=True) as mock_insert,
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
    assert mock_insert.await_count == 3  # recipe_executions + 2 recipe_step_executions rows


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
