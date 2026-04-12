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
        if path.startswith("capability_executions?"):
            return [
                {
                    "executed_at": "2026-03-13T07:30:00Z",
                    "capability_id": "search.query",
                    "success": True,
                    "agent_id": "agent-alpha",
                    "interface": "mcp",
                    "credential_mode": "byo",
                },
                {
                    "executed_at": "2026-03-13T08:30:00Z",
                    "capability_id": "crm.record.search",
                    "success": False,
                    "agent_id": "agent-alpha",
                    "interface": "mcp",
                    "credential_mode": "byok",
                },
                {
                    "executed_at": "2026-03-13T09:00:00Z",
                    "capability_id": "ai.generate_image",
                    "success": True,
                    "agent_id": "agent-beta",
                    "interface": "api",
                    "credential_mode": "rhumb_managed",
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
    assert payload["executions"]["total"] == 3
    assert payload["executions"]["successful"] == 2
    assert payload["executions"]["failed"] == 1
    assert payload["executions"]["unique_callers"] == 2
    assert payload["executions"]["first_time_callers"] == 1
    assert payload["executions"]["repeat_callers"] == 1
    assert payload["executions"]["repeat_caller_rate"] == 0.5
    assert payload["executions"]["caller_cohorts"] == {
        "first_time": {
            "attempts": 2,
            "successful": 2,
            "failed": 0,
            "success_rate": 1.0,
        },
        "repeat": {
            "attempts": 1,
            "successful": 0,
            "failed": 1,
            "success_rate": 0.0,
        },
        "unattributed": {
            "attempts": 0,
            "successful": 0,
            "failed": 0,
            "success_rate": None,
        },
    }
    assert payload["executions"]["credential_modes"] == [
        {"key": "byok", "count": 2},
        {"key": "rhumb_managed", "count": 1},
    ]
    assert payload["executions"]["first_success_modes"] == [
        {"key": "byok", "count": 1},
        {"key": "rhumb_managed", "count": 1},
    ]
    assert payload["executions"]["managed_path"] == {
        "attempts": 1,
        "successful": 1,
        "failed": 0,
        "success_rate": 1.0,
        "first_success_callers": 1,
        "first_success_share": 0.5,
    }
    assert payload["executions"]["top_interfaces"] == [
        {"key": "mcp", "count": 2},
        {"key": "api", "count": 1},
    ]
    assert payload["executions"]["top_capabilities"] == [
        {"key": "search.query", "count": 1},
        {"key": "crm.record.search", "count": 1},
        {"key": "ai.generate_image", "count": 1},
    ]
    assert payload["funnel"]["execute_attempts"] == 3
    assert payload["funnel"]["successful_executes"] == 2
    assert payload["funnel"]["biggest_dropoff"] == {
        "from_stage": "queries",
        "to_stage": "service_views",
        "from_count": 2,
        "to_count": 1,
        "progressed_count": 1,
        "dropoff_count": 1,
        "dropoff_rate": 0.5,
        "conversion_rate": 0.5,
        "overflow_count": 0,
    }


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
        execution_rows=[],
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
        execution_rows=[
            {
                "executed_at": "2026-03-13T04:00:00Z",
                "capability_id": "search.query",
                "success": True,
                "agent_id": "mcp-agent-1",
                "interface": "mcp",
                "credential_mode": "byo",
            },
            {
                "executed_at": "2026-03-13T05:00:00Z",
                "capability_id": "search.query",
                "success": False,
                "agent_id": "mcp-agent-1",
                "interface": "mcp",
                "credential_mode": "byok",
            },
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
    assert dashboard["executions"]["success_rate"] == 0.5
    assert dashboard["executions"]["unique_callers"] == 1
    assert dashboard["executions"]["first_time_callers"] == 0
    assert dashboard["executions"]["repeat_callers"] == 1
    assert dashboard["executions"]["repeat_caller_rate"] == 1.0
    assert dashboard["executions"]["caller_cohorts"] == {
        "first_time": {
            "attempts": 1,
            "successful": 1,
            "failed": 0,
            "success_rate": 1.0,
        },
        "repeat": {
            "attempts": 1,
            "successful": 0,
            "failed": 1,
            "success_rate": 0.0,
        },
        "unattributed": {
            "attempts": 0,
            "successful": 0,
            "failed": 0,
            "success_rate": None,
        },
    }
    assert dashboard["executions"]["credential_modes"] == [{"key": "byok", "count": 2}]
    assert dashboard["executions"]["first_success_modes"] == [{"key": "byok", "count": 1}]
    assert dashboard["executions"]["managed_path"] == {
        "attempts": 0,
        "successful": 0,
        "failed": 0,
        "success_rate": None,
        "first_success_callers": 0,
        "first_success_share": 0.0,
    }
    assert dashboard["executions"]["top_interfaces"] == [{"key": "mcp", "count": 2}]
    assert dashboard["executions"]["top_capabilities"] == [{"key": "search.query", "count": 2}]
    assert dashboard["funnel"] == {
        "queries": 2,
        "service_views": 2,
        "provider_clicks": 1,
        "execute_attempts": 2,
        "successful_executes": 1,
        "stage_transitions": [
            {
                "from_stage": "queries",
                "to_stage": "service_views",
                "from_count": 2,
                "to_count": 2,
                "progressed_count": 2,
                "dropoff_count": 0,
                "dropoff_rate": 0.0,
                "conversion_rate": 1.0,
                "overflow_count": 0,
            },
            {
                "from_stage": "service_views",
                "to_stage": "provider_clicks",
                "from_count": 2,
                "to_count": 1,
                "progressed_count": 1,
                "dropoff_count": 1,
                "dropoff_rate": 0.5,
                "conversion_rate": 0.5,
                "overflow_count": 0,
            },
            {
                "from_stage": "provider_clicks",
                "to_stage": "execute_attempts",
                "from_count": 1,
                "to_count": 2,
                "progressed_count": 1,
                "dropoff_count": 0,
                "dropoff_rate": 0.0,
                "conversion_rate": 1.0,
                "overflow_count": 1,
            },
            {
                "from_stage": "execute_attempts",
                "to_stage": "successful_executes",
                "from_count": 2,
                "to_count": 1,
                "progressed_count": 1,
                "dropoff_count": 1,
                "dropoff_rate": 0.5,
                "conversion_rate": 0.5,
                "overflow_count": 0,
            },
        ],
        "biggest_dropoff": {
            "from_stage": "service_views",
            "to_stage": "provider_clicks",
            "from_count": 2,
            "to_count": 1,
            "progressed_count": 1,
            "dropoff_count": 1,
            "dropoff_rate": 0.5,
            "conversion_rate": 0.5,
            "overflow_count": 0,
        },
    }


def test_build_launch_dashboard_tracks_unattributed_execution_attempts() -> None:
    dashboard = build_launch_dashboard(
        query_logs=[],
        click_events=[],
        execution_rows=[
            {
                "executed_at": "2026-03-13T04:00:00Z",
                "capability_id": "search.query",
                "success": True,
                "agent_id": None,
                "interface": None,
                "credential_mode": "rhumb_managed",
            },
            {
                "executed_at": "2026-03-13T05:00:00Z",
                "capability_id": "search.query",
                "success": False,
                "agent_id": "agent-1",
                "interface": "mcp",
                "credential_mode": "agent_vault",
            },
        ],
        service_rows=[{"slug": "stripe"}],
        window="launch",
        now=datetime(2026, 3, 13, 10, 0, tzinfo=UTC),
    )

    assert dashboard["executions"]["total"] == 2
    assert dashboard["executions"]["unique_callers"] == 1
    assert dashboard["executions"]["first_time_callers"] == 1
    assert dashboard["executions"]["repeat_callers"] == 0
    assert dashboard["executions"]["caller_cohorts"] == {
        "first_time": {
            "attempts": 1,
            "successful": 0,
            "failed": 1,
            "success_rate": 0.0,
        },
        "repeat": {
            "attempts": 0,
            "successful": 0,
            "failed": 0,
            "success_rate": None,
        },
        "unattributed": {
            "attempts": 1,
            "successful": 1,
            "failed": 0,
            "success_rate": 1.0,
        },
    }
    assert dashboard["executions"]["credential_modes"] == [
        {"key": "rhumb_managed", "count": 1},
        {"key": "agent_vault", "count": 1},
    ]
    assert dashboard["executions"]["first_success_modes"] == []
    assert dashboard["executions"]["managed_path"] == {
        "attempts": 1,
        "successful": 1,
        "failed": 0,
        "success_rate": 1.0,
        "first_success_callers": 0,
        "first_success_share": None,
    }
