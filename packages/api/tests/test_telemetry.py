"""Tests for telemetry routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from schemas.agent_identity import AgentIdentitySchema

from app import app


def _execution_row(
    *,
    execution_id: str,
    capability_id: str = "search.web_search",
    provider_used: str = "tavily",
    success: bool = True,
    upstream_status: int = 200,
    cost_usd_cents: int | None = 6,
    total_latency_ms: float = 280.0,
    upstream_latency_ms: float = 250.0,
    created_at: str | None = None,
) -> dict:
    timestamp = created_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "id": execution_id,
        "agent_id": "00000000-0000-0000-0000-bypass000001",
        "capability_id": capability_id,
        "provider_used": provider_used,
        "credential_mode": "auto",
        "method": "POST",
        "path": "/search",
        "upstream_status": upstream_status,
        "success": success,
        "cost_estimate_usd": 0.06 if cost_usd_cents is None else None,
        "cost_usd_cents": cost_usd_cents,
        "upstream_cost_cents": 5 if cost_usd_cents is not None else None,
        "margin_cents": 1 if cost_usd_cents is not None else None,
        "total_latency_ms": total_latency_ms,
        "upstream_latency_ms": upstream_latency_ms,
        "billing_status": "billed",
        "fallback_attempted": False,
        "fallback_provider": None,
        "interface": "rest",
        "error_message": None if success else "upstream failure",
        "executed_at": timestamp,
        "created_at": timestamp,
    }


def _auth_client() -> TestClient:
    return TestClient(app, headers={"X-Rhumb-Key": "rhumb_test_bypass_key_0000"})


def _mock_agent() -> AgentIdentitySchema:
    return AgentIdentitySchema(
        agent_id="00000000-0000-0000-0000-bypass000001",
        name="telemetry-test-agent",
        organization_id="org-test",
    )


def test_protected_telemetry_endpoints_require_auth() -> None:
    unauthenticated = TestClient(app)

    usage_response = unauthenticated.get("/v1/telemetry/usage")
    recent_response = unauthenticated.get("/v1/telemetry/recent")

    assert usage_response.status_code == 401
    assert recent_response.status_code == 401


def test_provider_health_endpoint_works_without_auth() -> None:
    now = datetime.now(timezone.utc)
    rows = [
        _execution_row(
            execution_id="exec_1",
            created_at=(now - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        ),
        _execution_row(
            execution_id="exec_2",
            success=False,
            upstream_status=500,
            total_latency_ms=900.0,
            upstream_latency_ms=860.0,
            created_at=(now - timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
        ),
    ]

    with patch("routes.telemetry.supabase_fetch", new_callable=AsyncMock, return_value=rows):
        response = TestClient(app).get("/v1/telemetry/provider-health")

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    provider = body["data"]["providers"][0]
    assert provider["provider"] == "tavily"
    assert provider["total_calls"] == 2
    assert provider["error_distribution"] == {"500": 1}


def test_usage_endpoint_returns_expected_structure(client: TestClient) -> None:
    now = datetime.now(timezone.utc)
    rows = [
        _execution_row(
            execution_id="exec_a",
            capability_id="search.web_search",
            provider_used="tavily",
            total_latency_ms=200.0,
            upstream_latency_ms=180.0,
            created_at=(now - timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        ),
        _execution_row(
            execution_id="exec_b",
            capability_id="search.web_search",
            provider_used="serpapi",
            success=False,
            upstream_status=502,
            cost_usd_cents=12,
            total_latency_ms=500.0,
            upstream_latency_ms=450.0,
            created_at=(now - timedelta(hours=6)).isoformat().replace("+00:00", "Z"),
        ),
    ]

    mock_store = AsyncMock()
    mock_store.verify_api_key_with_agent = AsyncMock(return_value=_mock_agent())
    with (
        patch("routes.telemetry.supabase_fetch", new_callable=AsyncMock, return_value=rows),
        patch("routes.telemetry.get_agent_identity_store", return_value=mock_store),
    ):
        response = client.get("/v1/telemetry/usage", params={"days": 7})

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    data = body["data"]
    assert data["agent_id"] == "00000000-0000-0000-0000-bypass000001"
    assert data["period_days"] == 7
    assert data["summary"]["total_calls"] == 2
    assert data["summary"]["successful_calls"] == 1
    assert data["summary"]["failed_calls"] == 1
    assert isinstance(data["by_capability"], list)
    assert isinstance(data["by_provider"], list)
    assert isinstance(data["by_time"], list)
    assert data["by_capability"][0]["capability_id"] == "search.web_search"
    assert {item["provider"] for item in data["by_provider"]} == {"tavily", "serpapi"}


def test_usage_time_filtering_excludes_old_rows(client: TestClient) -> None:
    now = datetime.now(timezone.utc)
    rows = [
        _execution_row(
            execution_id="exec_recent",
            created_at=(now - timedelta(days=2)).isoformat().replace("+00:00", "Z"),
        ),
        _execution_row(
            execution_id="exec_old",
            created_at=(now - timedelta(days=20)).isoformat().replace("+00:00", "Z"),
        ),
    ]

    mock_store = AsyncMock()
    mock_store.verify_api_key_with_agent = AsyncMock(return_value=_mock_agent())
    with (
        patch("routes.telemetry.supabase_fetch", new_callable=AsyncMock, return_value=rows),
        patch("routes.telemetry.get_agent_identity_store", return_value=mock_store),
    ):
        response = client.get("/v1/telemetry/usage", params={"days": 7})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["summary"]["total_calls"] == 1
    assert data["by_time"][0]["calls"] == 1


def test_usage_empty_results_return_zeros(client: TestClient) -> None:
    mock_store = AsyncMock()
    mock_store.verify_api_key_with_agent = AsyncMock(return_value=_mock_agent())
    with (
        patch("routes.telemetry.supabase_fetch", new_callable=AsyncMock, return_value=[]),
        patch("routes.telemetry.get_agent_identity_store", return_value=mock_store),
    ):
        response = client.get("/v1/telemetry/usage", params={"days": 7})

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    summary = body["data"]["summary"]
    assert summary == {
        "total_calls": 0,
        "successful_calls": 0,
        "failed_calls": 0,
        "total_cost_usd": 0,
        "avg_latency_ms": 0.0,
        "p50_latency_ms": 0.0,
        "p95_latency_ms": 0.0,
    }
    assert body["data"]["by_capability"] == []
    assert body["data"]["by_provider"] == []
    assert body["data"]["by_time"] == []


def test_usage_endpoint_canonicalizes_alias_backed_provider_ids_and_filters(client: TestClient) -> None:
    now = datetime.now(timezone.utc)
    rows = [
        _execution_row(
            execution_id="exec_alias",
            provider_used="brave-search",
            created_at=(now - timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
        ),
        _execution_row(
            execution_id="exec_other",
            provider_used="tavily",
            created_at=(now - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        ),
    ]
    captured: dict[str, str] = {}

    async def mock_fetch(path: str):
        captured["path"] = path
        return rows

    mock_store = AsyncMock()
    mock_store.verify_api_key_with_agent = AsyncMock(return_value=_mock_agent())
    with (
        patch("routes.telemetry.supabase_fetch", side_effect=mock_fetch),
        patch("routes.telemetry.get_agent_identity_store", return_value=mock_store),
    ):
        response = client.get(
            "/v1/telemetry/usage",
            params={"days": 7, "provider": "brave-search-api"},
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["summary"]["total_calls"] == 1
    assert data["by_provider"] == [
        {
            "provider": "brave-search-api",
            "calls": 1,
            "success_rate": 1.0,
            "avg_latency_ms": 280.0,
            "total_cost_usd": 0.06,
            "error_rate": 0.0,
            "avg_upstream_latency_ms": 250.0,
        }
    ]
    assert data["by_capability"][0]["top_provider"] == "brave-search-api"
    assert "or=(provider_used.eq.brave-search-api,provider_used.eq.brave-search)" in captured["path"]


def test_provider_health_canonicalizes_alias_backed_provider_ids() -> None:
    now = datetime.now(timezone.utc)
    rows = [
        _execution_row(
            execution_id="exec_health_alias",
            provider_used="brave-search",
            created_at=(now - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        )
    ]
    captured: dict[str, str] = {}

    async def mock_fetch(path: str):
        captured["path"] = path
        return rows

    with patch("routes.telemetry.supabase_fetch", side_effect=mock_fetch):
        response = TestClient(app).get(
            "/v1/telemetry/provider-health",
            params={"provider": "brave-search-api"},
        )

    assert response.status_code == 200
    provider = response.json()["data"]["providers"][0]
    assert provider["provider"] == "brave-search-api"
    assert provider["total_calls"] == 1
    assert "or=(provider_used.eq.brave-search-api,provider_used.eq.brave-search)" in captured["path"]


def test_recent_endpoint_canonicalizes_alias_backed_provider_ids(client: TestClient) -> None:
    row = _execution_row(execution_id="exec_recent_alias", provider_used="brave-search")
    row["fallback_attempted"] = True
    row["fallback_provider"] = "brave-search"

    mock_store = AsyncMock()
    mock_store.verify_api_key_with_agent = AsyncMock(return_value=_mock_agent())
    with (
        patch("routes.telemetry.supabase_fetch", new_callable=AsyncMock, return_value=[row]),
        patch("routes.telemetry.get_agent_identity_store", return_value=mock_store),
    ):
        response = client.get("/v1/telemetry/recent", params={"limit": 5})

    assert response.status_code == 200
    record = response.json()["data"][0]
    assert record["provider_used"] == "brave-search-api"
    assert record["fallback_provider"] == "brave-search-api"


def test_recent_endpoint_canonicalizes_alias_backed_error_messages(client: TestClient) -> None:
    row = _execution_row(
        execution_id="exec_recent_error_alias",
        provider_used="brave-search",
        success=False,
        upstream_status=502,
    )
    row["error_message"] = "brave-search upstream exploded"

    mock_store = AsyncMock()
    mock_store.verify_api_key_with_agent = AsyncMock(return_value=_mock_agent())
    with (
        patch("routes.telemetry.supabase_fetch", new_callable=AsyncMock, return_value=[row]),
        patch("routes.telemetry.get_agent_identity_store", return_value=mock_store),
    ):
        response = client.get("/v1/telemetry/recent", params={"limit": 5})

    assert response.status_code == 200
    record = response.json()["data"][0]
    assert record["provider_used"] == "brave-search-api"
    assert record["error_message"] == "brave-search-api upstream exploded"


def test_recent_endpoint_canonicalizes_alternate_provider_aliases_in_error_messages(client: TestClient) -> None:
    row = _execution_row(
        execution_id="exec_recent_error_multi_alias",
        provider_used="brave-search",
        success=False,
        upstream_status=502,
    )
    row["fallback_attempted"] = True
    row["fallback_provider"] = "pdl"
    row["error_message"] = "brave-search failed, then pdl credential lookup failed"

    mock_store = AsyncMock()
    mock_store.verify_api_key_with_agent = AsyncMock(return_value=_mock_agent())
    with (
        patch("routes.telemetry.supabase_fetch", new_callable=AsyncMock, return_value=[row]),
        patch("routes.telemetry.get_agent_identity_store", return_value=mock_store),
    ):
        response = client.get("/v1/telemetry/recent", params={"limit": 5})

    assert response.status_code == 200
    record = response.json()["data"][0]
    assert record["provider_used"] == "brave-search-api"
    assert record["fallback_provider"] == "people-data-labs"
    assert record["error_message"] == (
        "brave-search-api failed, then people-data-labs credential lookup failed"
    )
