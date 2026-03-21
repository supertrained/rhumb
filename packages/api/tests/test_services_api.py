"""Tests for service listing pagination and score lookup edge cases."""

from __future__ import annotations

from urllib.parse import parse_qs
from unittest.mock import AsyncMock, patch


ALL_SERVICES = [
    {
        "slug": f"service-{index:04d}",
        "name": f"Service {index:04d}",
        "category": "payments" if index % 2 == 0 else "email",
        "description": f"Description {index:04d}",
    }
    for index in range(600)
]
SCORED_ROWS = [{"service_slug": service["slug"]} for service in ALL_SERVICES]


def _parse_query(path: str) -> dict[str, list[str]]:
    if "?" not in path:
        return {}
    return parse_qs(path.split("?", 1)[1], keep_blank_values=True)


def _filtered_services(path: str) -> list[dict[str, str]]:
    query = _parse_query(path)
    category = query.get("category", [None])[0]
    if category and category.startswith("eq."):
        category_value = category.removeprefix("eq.")
        return [service for service in ALL_SERVICES if service["category"] == category_value]
    return ALL_SERVICES


async def _mock_supabase_fetch(path: str):
    if path == "scores?select=service_slug":
        return SCORED_ROWS

    if path.startswith(
        "services?slug=eq.unknown-service"
        "&select=slug,base_url,docs_url,openapi_url,mcp_server_url&limit=1"
    ):
        return []

    if path.startswith("services?select=slug,name,category,description"):
        query = _parse_query(path)
        filtered = _filtered_services(path)
        offset = int(query.get("offset", ["0"])[0])
        limit = int(query.get("limit", [str(len(filtered))])[0])
        return filtered[offset : offset + limit]

    if path.startswith("scores?service_slug=eq."):
        return []

    raise AssertionError(f"Unexpected Supabase fetch path: {path}")


async def _mock_supabase_count(path: str) -> int:
    if path.startswith("services?select=slug,name,category,description"):
        return len(_filtered_services(path))
    raise AssertionError(f"Unexpected Supabase count path: {path}")


def test_unknown_service_slug_returns_404(client) -> None:
    """Unknown services should return a route-level 404 envelope."""
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase_fetch,
    ):
        resp = client.get(
            "/v1/services/unknown-service/score",
            headers={"X-Request-ID": "req-service-404"},
        )

    assert resp.status_code == 404
    assert resp.json() == {
        "error": "service_not_found",
        "message": "No service found with slug 'unknown-service'",
        "resolution": "Check available services at GET /v1/services or /v1/search?q=...",
        "request_id": "req-service-404",
    }


def test_services_endpoint_returns_paginated_results_with_total_count(client) -> None:
    """GET /v1/services returns the new paginated envelope with total count."""
    with (
        patch(
            "routes.services.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase_fetch,
        ),
        patch(
            "routes.services.supabase_count",
            new_callable=AsyncMock,
            side_effect=_mock_supabase_count,
        ),
    ):
        resp = client.get("/v1/services")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["error"] is None
    assert payload["data"]["total"] == 600
    assert payload["data"]["limit"] == 50
    assert payload["data"]["offset"] == 0
    assert len(payload["data"]["items"]) == 50
    assert payload["data"]["items"][0]["slug"] == "service-0000"
    assert payload["data"]["items"][-1]["slug"] == "service-0049"


def test_services_limit_and_offset_params_work(client) -> None:
    """Requested limit and offset are honored in both the response and query path."""
    captured_paths: list[str] = []

    async def _capturing_fetch(path: str):
        captured_paths.append(path)
        return await _mock_supabase_fetch(path)

    with (
        patch(
            "routes.services.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_capturing_fetch,
        ),
        patch(
            "routes.services.supabase_count",
            new_callable=AsyncMock,
            side_effect=_mock_supabase_count,
        ),
    ):
        resp = client.get("/v1/services", params={"limit": 10, "offset": 20})

    assert resp.status_code == 200
    payload = resp.json()["data"]
    assert payload["limit"] == 10
    assert payload["offset"] == 20
    assert len(payload["items"]) == 10
    assert payload["items"][0]["slug"] == "service-0020"
    assert payload["items"][-1]["slug"] == "service-0029"
    assert any(
        path.startswith("services?select=slug,name,category,description")
        and "limit=10" in path
        and "offset=20" in path
        for path in captured_paths
    )


def test_services_limit_above_max_is_capped(client) -> None:
    """Limits above 500 are accepted but capped server-side."""
    captured_paths: list[str] = []

    async def _capturing_fetch(path: str):
        captured_paths.append(path)
        return await _mock_supabase_fetch(path)

    with (
        patch(
            "routes.services.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_capturing_fetch,
        ),
        patch(
            "routes.services.supabase_count",
            new_callable=AsyncMock,
            side_effect=_mock_supabase_count,
        ),
    ):
        resp = client.get("/v1/services", params={"limit": 999})

    assert resp.status_code == 200
    payload = resp.json()["data"]
    assert payload["limit"] == 500
    assert payload["offset"] == 0
    assert len(payload["items"]) == 500
    assert payload["total"] == 600
    assert any(
        path.startswith("services?select=slug,name,category,description")
        and "limit=500" in path
        for path in captured_paths
    )
