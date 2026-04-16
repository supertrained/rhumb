"""Tests for service listing pagination and score lookup edge cases."""

from __future__ import annotations

import re
from urllib.parse import parse_qs
from urllib.parse import unquote
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

ALIAS_SERVICES = [
    {
        "slug": "brave-search-api",
        "name": "Brave Search API",
        "category": "search",
        "description": "Web search API",
        "official_docs": "https://api.search.brave.com/app/documentation",
    },
    {
        "slug": "people-data-labs",
        "name": "People Data Labs",
        "category": "search",
        "description": "B2B data API",
        "official_docs": "https://docs.peopledatalabs.com/docs",
    },
]

ALIAS_SCORE_ROWS = [
    {
        "service_slug": "brave-search",
        "aggregate_recommendation_score": 8.7,
        "execution_score": 8.5,
        "access_readiness_score": 8.6,
        "confidence": 0.91,
        "tier": "L4",
        "tier_label": "Strong",
        "probe_metadata": {"freshness": "5 minutes ago"},
        "calculated_at": "2026-04-16T16:00:00Z",
    },
    {
        "service_slug": "brave-search",
        "aggregate_recommendation_score": 8.4,
        "execution_score": 8.2,
        "access_readiness_score": 8.3,
        "confidence": 0.88,
        "tier": "L4",
        "tier_label": "Strong",
        "probe_metadata": {"freshness": "1 day ago"},
        "calculated_at": "2026-04-15T16:00:00Z",
    },
    {
        "service_slug": "pdl",
        "aggregate_recommendation_score": 7.9,
        "execution_score": 7.7,
        "access_readiness_score": 7.8,
        "confidence": 0.87,
        "tier": "L3",
        "tier_label": "Ready",
        "probe_metadata": {"freshness": "12 minutes ago"},
        "calculated_at": "2026-04-16T15:30:00Z",
    },
]

ALIAS_FAILURE_ROWS = [
    {
        "service_slug": "brave-search",
        "id": "fm-brave-1",
        "category": "auth",
        "title": "Session tokens expire early",
        "description": "Long-running search sessions can lose auth unexpectedly.",
        "severity": "medium",
        "frequency": "intermittent",
        "agent_impact": "Agents may need to retry search requests.",
        "workaround": "Refresh credentials before multi-step browse loops.",
        "last_verified": "2026-04-16T15:45:00Z",
        "evidence_count": 2,
    }
]


def _parse_query(path: str) -> dict[str, list[str]]:
    if "?" not in path:
        return {}
    return parse_qs(path.split("?", 1)[1], keep_blank_values=True)


def _parse_in_filter(path: str, key: str) -> set[str] | None:
    decoded = unquote(path)
    match = re.search(rf"{re.escape(key)}=in\.\(([^)]*)\)", decoded)
    if not match:
        return None
    return {
        part.strip().strip('"')
        for part in match.group(1).split(",")
        if part.strip()
    }


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
        "&select=slug,name,category,description&limit=1"
    ):
        return []

    if path.startswith(
        "services?slug=eq.unknown-service"
        "&select=slug,official_docs&limit=1"
    ):
        return []

    if path.startswith("services?slug=eq.stripe&select=slug,official_docs&limit=1"):
        return [{"slug": "stripe", "official_docs": "https://docs.stripe.com"}]

    if path.startswith("services?select=slug,name,category,description"):
        query = _parse_query(path)
        filtered = _filtered_services(path)
        offset = int(query.get("offset", ["0"])[0])
        limit = int(query.get("limit", [str(len(filtered))])[0])
        return filtered[offset : offset + limit]

    if path.startswith("scores?service_slug=eq.stripe&order=calculated_at.desc&limit=1"):
        return [
            {
                "service_slug": "stripe",
                "aggregate_recommendation_score": 8.9,
                "execution_score": 9.1,
                "access_readiness_score": 8.4,
                "confidence": 0.98,
                "tier": "L4",
                "tier_label": "Agent Native",
                "probe_metadata": {"freshness": "12 minutes ago"},
                "calculated_at": "2026-03-13T00:00:00Z",
            }
        ]

    if path.startswith("scores?service_slug=in.("):
        slugs = _parse_in_filter(path, "service_slug") or set()
        if "stripe" in slugs:
            return [
                {
                    "service_slug": "stripe",
                    "aggregate_recommendation_score": 8.9,
                    "execution_score": 9.1,
                    "access_readiness_score": 8.4,
                    "confidence": 0.98,
                    "tier": "L4",
                    "tier_label": "Agent Native",
                    "probe_metadata": {"freshness": "12 minutes ago"},
                    "calculated_at": "2026-03-13T00:00:00Z",
                }
            ]
        return []

    if path.startswith("failure_modes?service_slug=in.("):
        slugs = _parse_in_filter(path, "service_slug") or set()
        if "stripe" in slugs:
            return []
        return []

    if path.startswith("scores?service_slug=eq."):
        return []

    raise AssertionError(f"Unexpected Supabase fetch path: {path}")


async def _mock_supabase_count(path: str) -> int:
    if path.startswith("services?select=slug,name,category,description"):
        return len(_filtered_services(path))
    raise AssertionError(f"Unexpected Supabase count path: {path}")


async def _mock_alias_supabase_fetch(path: str):
    decoded = unquote(path)

    if decoded == "scores?select=service_slug":
        return [{"service_slug": row["service_slug"]} for row in ALIAS_SCORE_ROWS]

    if decoded.startswith("services?slug=eq.brave-search-api&select=slug,name,category,description&limit=1"):
        return [
            {
                "slug": "brave-search-api",
                "name": "Brave Search API",
                "category": "search",
                "description": "Web search API",
            }
        ]

    if decoded.startswith("services?slug=eq.brave-search-api&select=slug,official_docs&limit=1"):
        return [
            {
                "slug": "brave-search-api",
                "official_docs": "https://api.search.brave.com/app/documentation",
            }
        ]

    if decoded.startswith("services?category=eq.search&slug=neq.brave-search-api&select=slug,name"):
        return [{"slug": "people-data-labs", "name": "People Data Labs"}]

    if decoded.startswith("services?select=slug,name,category,description"):
        slugs = _parse_in_filter(decoded, "slug") or {service["slug"] for service in ALIAS_SERVICES}
        query = _parse_query(decoded)
        offset = int(query.get("offset", ["0"])[0])
        limit = int(query.get("limit", [str(len(ALIAS_SERVICES))])[0])
        filtered = [service for service in ALIAS_SERVICES if service["slug"] in slugs]
        return [
            {
                "slug": service["slug"],
                "name": service["name"],
                "category": service["category"],
                "description": service["description"],
            }
            for service in filtered[offset : offset + limit]
        ]

    if decoded.startswith("scores?service_slug=in.("):
        slugs = _parse_in_filter(decoded, "service_slug") or set()
        return [row for row in ALIAS_SCORE_ROWS if row["service_slug"] in slugs]

    if decoded.startswith("failure_modes?service_slug=in.("):
        slugs = _parse_in_filter(decoded, "service_slug") or set()
        return [row for row in ALIAS_FAILURE_ROWS if row["service_slug"] in slugs]

    raise AssertionError(f"Unexpected Supabase fetch path: {path}")


async def _mock_alias_supabase_count(path: str) -> int:
    decoded = unquote(path)
    if decoded.startswith("services?select=slug,name,category,description"):
        slugs = _parse_in_filter(decoded, "slug") or {service["slug"] for service in ALIAS_SERVICES}
        return sum(1 for service in ALIAS_SERVICES if service["slug"] in slugs)
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


def test_unknown_service_detail_returns_404(client) -> None:
    """GET /v1/services/{slug} should return the standardized 404 envelope."""
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase_fetch,
    ):
        resp = client.get(
            "/v1/services/unknown-service",
            headers={"X-Request-ID": "req-service-detail-404"},
        )

    assert resp.status_code == 404
    assert resp.json() == {
        "error": "service_not_found",
        "message": "No service found with slug 'unknown-service'",
        "resolution": "Check available services at GET /v1/services or /v1/search?q=...",
        "request_id": "req-service-detail-404",
    }


def test_service_score_uses_official_docs_column(client) -> None:
    """GET /v1/services/{slug}/score should map docs_url from official_docs."""
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase_fetch,
    ):
        resp = client.get("/v1/services/stripe/score")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["service_slug"] == "stripe"
    assert payload["docs_url"] == "https://docs.stripe.com"
    assert payload["base_url"] is None
    assert payload["openapi_url"] is None
    assert payload["mcp_server_url"] is None


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


def test_services_endpoint_keeps_alias_backed_services_visible(client) -> None:
    with (
        patch(
            "routes.services.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_alias_supabase_fetch,
        ),
        patch(
            "routes.services.supabase_count",
            new_callable=AsyncMock,
            side_effect=_mock_alias_supabase_count,
        ),
    ):
        resp = client.get("/v1/services")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["error"] is None
    assert [item["slug"] for item in payload["data"]["items"]] == [
        "brave-search-api",
        "people-data-labs",
    ]


def test_service_detail_canonicalizes_alias_backed_scores_and_alternatives(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_alias_supabase_fetch,
    ):
        resp = client.get("/v1/services/brave-search-api")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["error"] is None
    assert payload["data"]["slug"] == "brave-search-api"
    assert payload["data"]["an_score"] == 8.7
    assert payload["data"]["alternatives"] == [
        {
            "slug": "people-data-labs",
            "name": "People Data Labs",
            "an_score": 7.9,
            "score": 7.9,
            "tier": "L3",
        }
    ]


def test_service_detail_accepts_mixed_case_alias_inputs(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_alias_supabase_fetch,
    ):
        resp = client.get("/v1/services/Brave-Search")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["error"] is None
    assert payload["data"]["slug"] == "brave-search-api"
    assert payload["data"]["an_score"] == 8.7


def test_service_score_canonicalizes_alias_backed_score_rows(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_alias_supabase_fetch,
    ):
        resp = client.get("/v1/services/brave-search-api/score")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["service_slug"] == "brave-search-api"
    assert payload["an_score"] == 8.7
    assert payload["docs_url"] == "https://api.search.brave.com/app/documentation"


def test_service_history_reads_alias_backed_score_rows(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_alias_supabase_fetch,
    ):
        resp = client.get("/v1/services/brave-search-api/history")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["error"] is None
    assert payload["data"]["slug"] == "brave-search-api"
    assert [entry["an_score"] for entry in payload["data"]["history"]] == [8.7, 8.4]


def test_service_history_accepts_mixed_case_alias_inputs(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_alias_supabase_fetch,
    ):
        resp = client.get("/v1/services/Brave-Search-Api/history")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["error"] is None
    assert payload["data"]["slug"] == "brave-search-api"
    assert [entry["an_score"] for entry in payload["data"]["history"]] == [8.7, 8.4]


def test_service_score_reads_alias_backed_failure_modes(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_alias_supabase_fetch,
    ):
        resp = client.get("/v1/services/brave-search-api/score")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["service_slug"] == "brave-search-api"
    assert payload["failure_modes"] == [
        {
            "pattern": "Session tokens expire early",
            "impact": "Agents may need to retry search requests.",
            "frequency": "intermittent",
            "workaround": "Refresh credentials before multi-step browse loops.",
        }
    ]


def test_service_failures_reads_alias_backed_failure_rows(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_alias_supabase_fetch,
    ):
        resp = client.get("/v1/services/brave-search-api/failures")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["error"] is None
    assert payload["data"]["slug"] == "brave-search-api"
    assert payload["data"]["failure_modes"] == [
        {
            "pattern": "Session tokens expire early",
            "impact": "Agents may need to retry search requests.",
            "frequency": "intermittent",
            "workaround": "Refresh credentials before multi-step browse loops.",
            "category": "auth",
            "severity": "medium",
            "description": "Long-running search sessions can lose auth unexpectedly.",
            "last_verified": "2026-04-16T15:45:00Z",
            "evidence_count": 2,
        }
    ]


def test_service_score_accepts_mixed_case_alias_inputs(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_alias_supabase_fetch,
    ):
        resp = client.get("/v1/services/Brave-Search-Api/score")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["service_slug"] == "brave-search-api"
    assert payload["an_score"] == 8.7



def test_service_failures_accept_mixed_case_alias_inputs(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_alias_supabase_fetch,
    ):
        resp = client.get("/v1/services/Brave-Search/failures")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["error"] is None
    assert payload["data"]["slug"] == "brave-search-api"
    assert payload["data"]["failure_modes"][0]["pattern"] == "Session tokens expire early"



def test_service_schema_and_report_normalize_mixed_case_alias_inputs(client) -> None:
    schema_resp = client.get("/v1/services/Brave-Search-Api/schema")
    report_resp = client.post("/v1/services/PDL/report")

    assert schema_resp.status_code == 200
    assert schema_resp.json()["data"]["slug"] == "brave-search-api"
    assert report_resp.status_code == 200
    assert report_resp.json()["data"]["slug"] == "people-data-labs"
