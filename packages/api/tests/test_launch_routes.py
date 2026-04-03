"""Tests for launch tracking and dashboard routes."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from services.launch_dashboard import build_launch_dashboard
from services.payload_redactor import REDACTED


def test_capture_click_event_logs_payload(client: TestClient, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_insert(table: str, payload: dict[str, object]) -> bool:
        captured["table"] = table
        captured["payload"] = payload
        return True

    monkeypatch.setattr("routes.launch.supabase_insert", fake_insert)

    response = client.post(
        "/v1/clicks",
        json={
            "event_type": "provider_click",
            "destination_url": "https://stripe.com/docs",
            "service_slug": "stripe",
            "page_path": "/service/stripe",
            "source_surface": "service_page",
        },
        headers={"referer": "https://rhumb.dev/service/stripe?utm_source=hn"},
    )

    assert response.status_code == 200
    assert response.json() == {"data": {"logged": True}, "error": None}
    assert captured["table"] == "click_events"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["destination_domain"] == "stripe.com"
    assert payload["referrer_url"] == "https://rhumb.dev/service/stripe?utm_source=hn"


def test_launch_dashboard_route_returns_aggregated_metrics(
    client: TestClient,
    monkeypatch,
) -> None:
    async def fake_fetch(path: str):
        if path.startswith("query_logs?"):
            return [
                {
                    "created_at": "2026-03-13T06:00:00Z",
                    "source": "mcp",
                    "query_type": "score_lookup",
                    "query_text": "stripe",
                    "query_params": {"slug": "stripe"},
                    "agent_id": "rhumb-mcp",
                    "user_agent": "rhumb-mcp/0.0.1",
                },
                {
                    "created_at": "2026-03-13T06:30:00Z",
                    "source": "web",
                    "query_type": "search",
                    "query_text": "payments",
                    "query_params": {"query": "payments"},
                    "agent_id": None,
                    "user_agent": "Mozilla/5.0",
                },
            ]
        if path.startswith("click_events?"):
            return [
                {
                    "created_at": "2026-03-13T07:00:00Z",
                    "event_type": "provider_click",
                    "service_slug": "stripe",
                    "destination_domain": "stripe.com",
                    "source_surface": "service_page",
                    "page_path": "/service/stripe",
                },
                {
                    "created_at": "2026-03-13T08:00:00Z",
                    "event_type": "github_dispute_click",
                    "service_slug": None,
                    "destination_domain": "github.com",
                    "source_surface": "providers_page",
                    "page_path": "/providers",
                },
            ]
        if path == "services?select=slug":
            return [{"slug": "stripe"}, {"slug": "square"}]
        raise AssertionError(f"Unexpected path: {path}")

    monkeypatch.setattr("routes.launch.supabase_fetch", fake_fetch)

    response = client.get("/v1/admin/launch/dashboard?window=launch")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["window"] == "launch"
    assert payload["coverage"]["public_service_count"] == 2
    assert payload["queries"]["total"] == 2
    assert payload["queries"]["machine_total"] == 1
    assert payload["clicks"]["provider_clicks"] == 1
    assert payload["clicks"]["dispute_clicks"]["github"] == 1


def test_build_launch_dashboard_sanitizes_top_searches_and_client_keys() -> None:
    dashboard = build_launch_dashboard(
        query_logs=[
            {
                "created_at": "2026-03-13T01:00:00Z",
                "source": "web",
                "query_type": "search",
                "query_text": "Bearer super-secret-token",
                "query_params": {"query": "Bearer super-secret-token"},
                "agent_id": None,
                "user_agent": "Browser/1.0 " + ("x" * 200),
            },
        ],
        click_events=[],
        service_rows=[{"slug": "stripe"}],
        window="launch",
        now=datetime(2026, 3, 13, 10, 0, tzinfo=UTC),
    )

    assert dashboard["queries"]["top_searches"] == [{"key": REDACTED, "count": 1}]
    assert dashboard["queries"]["unique_clients"] == 1
    assert dashboard["queries"]["repeat_clients"] == 0


def test_build_launch_dashboard_computes_repeat_and_ctr() -> None:
    dashboard = build_launch_dashboard(
        query_logs=[
            {
                "created_at": "2026-03-13T01:00:00Z",
                "source": "mcp",
                "query_type": "score_lookup",
                "query_text": "stripe",
                "query_params": {"slug": "stripe"},
                "agent_id": "mcp-agent-1",
                "user_agent": "rhumb-mcp/0.0.1",
            },
            {
                "created_at": "2026-03-13T02:00:00Z",
                "source": "mcp",
                "query_type": "score_lookup",
                "query_text": "stripe",
                "query_params": {"slug": "stripe"},
                "agent_id": "mcp-agent-1",
                "user_agent": "rhumb-mcp/0.0.1",
            },
        ],
        click_events=[
            {
                "created_at": "2026-03-13T03:00:00Z",
                "event_type": "provider_click",
                "service_slug": "stripe",
                "destination_domain": "stripe.com",
                "source_surface": "service_page",
                "page_path": "/service/stripe",
            }
        ],
        service_rows=[{"slug": "stripe"}],
        window="launch",
        now=datetime(2026, 3, 13, 10, 0, tzinfo=UTC),
    )

    assert dashboard["queries"]["unique_clients"] == 1
    assert dashboard["queries"]["repeat_clients"] == 1
    assert dashboard["clicks"]["provider_ctr"][0] == {
      "service_slug": "stripe",
      "clicks": 1,
      "views": 2,
      "ctr": 0.5,
    }
