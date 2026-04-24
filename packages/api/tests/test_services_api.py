"""Tests for service listing pagination and score lookup edge cases."""

from __future__ import annotations

import re
from urllib.parse import parse_qs
from urllib.parse import unquote
from unittest.mock import AsyncMock, patch

import pytest

from routes.services import (
    _canonicalize_service_rows,
    _validated_service_history_limit,
    _validated_service_list_offset,
)
from services.error_envelope import RhumbError


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

RUNTIME_ALIAS_SERVICES = [
    {
        "slug": "brave-search",
        "name": "Brave Search API",
        "category": "search",
        "description": "Web search API",
        "official_docs": "https://api.search.brave.com/app/documentation",
    },
    {
        "slug": "pdl",
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
        "autonomy_score": 8.4,
        "confidence": 0.91,
        "tier": "L4",
        "tier_label": "Strong",
        "probe_metadata": {"freshness": "5 minutes ago"},
        "payment_autonomy": 8.8,
        "payment_autonomy_rationale": "Direct billing and retry-safe checkout path.",
        "payment_autonomy_confidence": 0.89,
        "governance_readiness": 8.0,
        "governance_readiness_rationale": "Team controls and audit history are available.",
        "governance_readiness_confidence": 0.86,
        "web_accessibility": 8.3,
        "web_accessibility_rationale": "Docs and dashboard flows stay scriptable.",
        "web_accessibility_confidence": 0.82,
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

    decoded = unquote(path)

    if decoded.startswith("services?slug=in.(") and "&select=slug,name,category,description" in decoded:
        slugs = _parse_in_filter(decoded, "slug") or set()
        if "unknown-service" in slugs:
            return []
        if "stripe" in slugs:
            return [{
                "slug": "stripe",
                "name": "Stripe",
                "category": "payments",
                "description": "Payment API",
            }]
        return []

    if decoded.startswith("services?slug=in.(") and "&select=slug,official_docs" in decoded:
        slugs = _parse_in_filter(decoded, "slug") or set()
        if "unknown-service" in slugs:
            return []
        if "stripe" in slugs:
            return [{"slug": "stripe", "official_docs": "https://docs.stripe.com"}]
        return []

    if path.startswith("services?select=slug,name,category,description"):
        query = _parse_query(path)
        filtered = _filtered_services(path)
        offset = int(query.get("offset", ["0"])[0])
        limit = int(query.get("limit", [str(len(filtered))])[0])
        return filtered[offset : offset + limit]

    if path.startswith("scores?service_slug=in.("):
        slugs = _parse_in_filter(path, "service_slug") or set()
        if "stripe" in slugs:
            return [
                {
                    "service_slug": "stripe",
                    "aggregate_recommendation_score": 8.9,
                    "execution_score": 9.1,
                    "access_readiness_score": 8.4,
                    "autonomy_score": 9.0,
                    "confidence": 0.98,
                    "tier": "L4",
                    "tier_label": "Agent Native",
                    "probe_metadata": {"freshness": "12 minutes ago"},
                    "payment_autonomy": 10.0,
                    "payment_autonomy_rationale": "x402 / API-native payments",
                    "payment_autonomy_confidence": 0.9,
                    "governance_readiness": 9.0,
                    "governance_readiness_rationale": "RBAC + audit logs",
                    "governance_readiness_confidence": 0.85,
                    "web_accessibility": 8.0,
                    "web_accessibility_rationale": "AAG AA navigable UI",
                    "web_accessibility_confidence": 0.8,
                    "calculated_at": "2026-03-13T00:00:00Z",
                }
            ]
        return []

    if path.startswith("failure_modes?service_slug=in.("):
        slugs = _parse_in_filter(path, "service_slug") or set()
        if "stripe" in slugs:
            return []
        return []

    raise AssertionError(f"Unexpected Supabase fetch path: {path}")


async def _mock_supabase_count(path: str) -> int:
    if path.startswith("services?select=slug,name,category,description"):
        return len(_filtered_services(path))
    raise AssertionError(f"Unexpected Supabase count path: {path}")


async def _mock_empty_alias_score_supabase_fetch(path: str):
    decoded = unquote(path)

    if decoded.startswith("services?slug=in.(") and "&select=slug,official_docs" in decoded:
        slugs = _parse_in_filter(decoded, "slug") or set()
        if {"brave-search", "brave-search-api"} & slugs:
            return [{
                "slug": "brave-search-api",
                "official_docs": "https://api.search.brave.com/app/documentation",
            }]
        return []

    if decoded.startswith("scores?service_slug=in.("):
        return []

    return await _mock_supabase_fetch(path)


async def _mock_known_service_without_history_supabase_fetch(path: str):
    decoded = unquote(path)

    if decoded.startswith("services?slug=in.(") and "&select=slug,name,category,description" in decoded:
        slugs = _parse_in_filter(decoded, "slug") or set()
        if "service-no-history" in slugs:
            return [
                {
                    "slug": "service-no-history",
                    "name": "Service No History",
                    "category": "payments",
                    "description": "Known service without a stored score yet.",
                }
            ]

    if decoded.startswith("scores?service_slug=in.("):
        slugs = _parse_in_filter(decoded, "service_slug") or set()
        if "service-no-history" in slugs:
            return []

    return await _mock_supabase_fetch(path)


async def _mock_alias_supabase_fetch(path: str):
    decoded = unquote(path)

    if decoded == "scores?select=service_slug":
        return [{"service_slug": row["service_slug"]} for row in ALIAS_SCORE_ROWS]

    if decoded.startswith("services?slug=in.(") and "&select=slug,name,category,description" in decoded:
        slugs = _parse_in_filter(decoded, "slug") or {service["slug"] for service in ALIAS_SERVICES}
        filtered = [service for service in ALIAS_SERVICES if service["slug"] in slugs]
        return [
            {
                "slug": service["slug"],
                "name": service["name"],
                "category": service["category"],
                "description": service["description"],
            }
            for service in filtered
        ]

    if decoded.startswith("services?slug=in.(") and "&select=slug,official_docs" in decoded:
        slugs = _parse_in_filter(decoded, "slug") or {service["slug"] for service in ALIAS_SERVICES}
        filtered = [service for service in ALIAS_SERVICES if service["slug"] in slugs]
        return [
            {
                "slug": service["slug"],
                "official_docs": service["official_docs"],
            }
            for service in filtered
        ]

    if decoded.startswith("services?category=eq.search&select=slug,name"):
        return [
            {"slug": "brave-search-api", "name": "Brave Search API"},
            {"slug": "people-data-labs", "name": "People Data Labs"},
        ]

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


async def _mock_runtime_alias_service_supabase_fetch(path: str):
    decoded = unquote(path)

    if decoded == "scores?select=service_slug":
        return [{"service_slug": row["service_slug"]} for row in ALIAS_SCORE_ROWS]

    if decoded.startswith("services?slug=in.(") and "&select=slug,name,category,description" in decoded:
        slugs = _parse_in_filter(decoded, "slug") or {service["slug"] for service in RUNTIME_ALIAS_SERVICES}
        return [
            {
                "slug": service["slug"],
                "name": service["name"],
                "category": service["category"],
                "description": service["description"],
            }
            for service in RUNTIME_ALIAS_SERVICES
            if service["slug"] in slugs
        ]

    if decoded.startswith("services?slug=in.(") and "&select=slug,official_docs" in decoded:
        slugs = _parse_in_filter(decoded, "slug") or {service["slug"] for service in RUNTIME_ALIAS_SERVICES}
        return [
            {
                "slug": service["slug"],
                "official_docs": service["official_docs"],
            }
            for service in RUNTIME_ALIAS_SERVICES
            if service["slug"] in slugs
        ]

    if decoded.startswith("services?category=eq.search&select=slug,name"):
        return [
            {"slug": service["slug"], "name": service["name"]}
            for service in RUNTIME_ALIAS_SERVICES
        ]

    if decoded.startswith("services?select=slug,name,category,description&slug=in.("):
        slugs = _parse_in_filter(decoded, "slug") or {service["slug"] for service in RUNTIME_ALIAS_SERVICES}
        return [
            {
                "slug": service["slug"],
                "name": service["name"],
                "category": service["category"],
                "description": service["description"],
            }
            for service in RUNTIME_ALIAS_SERVICES
            if service["slug"] in slugs
        ]

    if decoded.startswith("scores?service_slug=in.("):
        slugs = _parse_in_filter(decoded, "service_slug") or set()
        return [row for row in ALIAS_SCORE_ROWS if row["service_slug"] in slugs]

    if decoded.startswith("failure_modes?service_slug=in.("):
        slugs = _parse_in_filter(decoded, "service_slug") or set()
        return [row for row in ALIAS_FAILURE_ROWS if row["service_slug"] in slugs]

    raise AssertionError(f"Unexpected Supabase fetch path: {path}")


async def _mock_alias_failure_text_supabase_fetch(path: str):
    decoded = unquote(path)
    if decoded.startswith("failure_modes?service_slug=in.("):
        slugs = _parse_in_filter(decoded, "service_slug") or set()
        rows = [
            {
                "service_slug": "brave-search",
                "id": "fm-brave-alias-text",
                "category": "auth",
                "title": "brave-search session tokens expire early",
                "description": "brave-search sessions can lose auth unexpectedly.",
                "severity": "medium",
                "frequency": "intermittent",
                "agent_impact": "Agents using brave-search may need to retry search requests.",
                "workaround": "Refresh brave-search credentials before multi-step browse loops.",
                "last_verified": "2026-04-16T15:45:00Z",
                "evidence_count": 2,
            }
        ]
        return [row for row in rows if row["service_slug"] in slugs]
    return await _mock_alias_supabase_fetch(path)


async def _mock_canonical_failure_text_supabase_fetch(path: str):
    decoded = unquote(path)
    if decoded.startswith("failure_modes?service_slug=in.("):
        slugs = _parse_in_filter(decoded, "service_slug") or set()
        rows = [
            {
                "service_slug": "people-data-labs",
                "id": "fm-pdl-canonical-text",
                "category": "auth",
                "title": "PDL session windows are short",
                "description": "PDL sessions can time out during long imports.",
                "severity": "medium",
                "frequency": "intermittent",
                "agent_impact": "Agents using PDL may need to re-run enrichment steps.",
                "workaround": "Re-authenticate PDL before long imports.",
                "last_verified": "2026-04-16T15:45:00Z",
                "evidence_count": 1,
            }
        ]
        return [row for row in rows if row["service_slug"] in slugs]
    raise AssertionError(f"Unexpected Supabase fetch path: {path}")


async def _mock_alias_score_text_supabase_fetch(path: str):
    decoded = unquote(path)
    if decoded.startswith("scores?service_slug=in.(") and "&order=calculated_at.desc&limit=1" in decoded:
        slugs = _parse_in_filter(decoded, "service_slug") or set()
        if {"brave-search", "brave-search-api"} & slugs:
            return [
                {
                    **ALIAS_SCORE_ROWS[0],
                    "service_slug": "brave-search",
                    "payment_autonomy_rationale": "brave-search supports direct billing.",
                    "governance_readiness_rationale": "brave-search audit history is available.",
                    "web_accessibility_rationale": "brave-search docs stay scriptable.",
                    "dimension_snapshot": {
                        "notes": {"summary": "brave-search stays easy to script."},
                        "autonomy": {
                            "avg": 8.4,
                            "confidence": 0.85,
                            "dimensions": [
                                {
                                    "code": "P1",
                                    "name": "payment_autonomy",
                                    "score": 8.8,
                                    "rationale": "brave-search supports direct billing.",
                                    "confidence": 0.89,
                                }
                            ],
                        },
                    },
                }
            ]
        return []
    return await _mock_alias_supabase_fetch(path)


async def _mock_canonical_score_text_supabase_fetch(path: str):
    decoded = unquote(path)
    if decoded.startswith("scores?service_slug=in.(") and "&order=calculated_at.desc&limit=1" in decoded:
        slugs = _parse_in_filter(decoded, "service_slug") or set()
        if {"people-data-labs", "pdl"} & slugs:
            return [
                {
                    **ALIAS_SCORE_ROWS[2],
                    "service_slug": "people-data-labs",
                    "payment_autonomy_rationale": "PDL supports direct billing.",
                    "governance_readiness_rationale": "PDL audit history is available.",
                    "web_accessibility_rationale": "PDL docs stay scriptable.",
                    "dimension_snapshot": {
                        "notes": {"summary": "PDL stays easy to script."},
                        "autonomy": {
                            "avg": 7.9,
                            "confidence": 0.87,
                            "dimensions": [
                                {
                                    "code": "P1",
                                    "name": "payment_autonomy",
                                    "score": 7.9,
                                    "rationale": "PDL supports direct billing.",
                                    "confidence": 0.87,
                                }
                            ],
                        },
                    },
                }
            ]
        return []
    return await _mock_alias_supabase_fetch(path)


async def _mock_alias_score_alternate_text_supabase_fetch(path: str):
    decoded = unquote(path)
    if decoded.startswith("scores?service_slug=in.(") and "&order=calculated_at.desc&limit=1" in decoded:
        slugs = _parse_in_filter(decoded, "service_slug") or set()
        if {"brave-search", "brave-search-api"} & slugs:
            return [
                {
                    **ALIAS_SCORE_ROWS[0],
                    "service_slug": "brave-search",
                    "payment_autonomy_rationale": "brave-search outperforms pdl on direct billing handoff.",
                    "governance_readiness_rationale": "brave-search audit history is stronger than pdl.",
                    "web_accessibility_rationale": "brave-search docs stay scriptable even when pdl docs lag.",
                    "dimension_snapshot": {
                        "notes": {
                            "summary": "brave-search stays easy to script and can replace pdl for quick checks."
                        },
                        "autonomy": {
                            "avg": 8.4,
                            "confidence": 0.85,
                            "dimensions": [
                                {
                                    "code": "P1",
                                    "name": "payment_autonomy",
                                    "score": 8.8,
                                    "rationale": "brave-search can fall back to pdl when needed.",
                                    "confidence": 0.89,
                                }
                            ],
                        },
                    },
                }
            ]
        return []
    return await _mock_alias_supabase_fetch(path)


async def _mock_canonical_score_and_failure_alternate_text_supabase_fetch(path: str):
    decoded = unquote(path)
    if decoded.startswith("scores?service_slug=in.(") and "&order=calculated_at.desc&limit=1" in decoded:
        slugs = _parse_in_filter(decoded, "service_slug") or set()
        if {"brave-search", "brave-search-api"} & slugs:
            return [
                {
                    **ALIAS_SCORE_ROWS[0],
                    "service_slug": "brave-search-api",
                    "payment_autonomy_rationale": "brave-search-api outperforms pdl on direct billing handoff.",
                    "governance_readiness_rationale": "brave-search-api audit history is stronger than pdl.",
                    "web_accessibility_rationale": "brave-search-api docs stay scriptable even when pdl docs lag.",
                    "dimension_snapshot": {
                        "notes": {
                            "summary": "brave-search-api stays easy to script and can replace pdl for quick checks."
                        },
                        "autonomy": {
                            "avg": 8.4,
                            "confidence": 0.85,
                            "dimensions": [
                                {
                                    "code": "P1",
                                    "name": "payment_autonomy",
                                    "score": 8.8,
                                    "rationale": "brave-search-api can fall back to pdl when needed.",
                                    "confidence": 0.89,
                                }
                            ],
                        },
                    },
                }
            ]
        return []

    if decoded.startswith("failure_modes?service_slug=in.("):
        slugs = _parse_in_filter(decoded, "service_slug") or set()
        rows = [
            {
                "service_slug": "brave-search-api",
                "id": "fm-brave-canonical-alt-text",
                "category": "auth",
                "title": "brave-search-api session tokens expire early after pdl fallback",
                "description": "brave-search-api sessions can lose auth unexpectedly when pdl fallback is triggered.",
                "severity": "medium",
                "frequency": "intermittent",
                "agent_impact": "Agents using brave-search-api may need to retry after pdl fallback.",
                "workaround": "Refresh brave-search-api credentials before multi-step flows that may hit pdl fallback.",
                "last_verified": "2026-04-16T15:45:00Z",
                "evidence_count": 2,
            }
        ]
        return [row for row in rows if row["service_slug"] in slugs]

    return await _mock_alias_supabase_fetch(path)


async def _mock_preferred_canonical_service_row_supabase_fetch(path: str):
    decoded = unquote(path)
    services = [
        {
            "slug": "brave-search",
            "name": "Legacy brave-search",
            "category": "search",
            "description": "Legacy brave-search docs.",
            "official_docs": "https://legacy.example/brave-search",
        },
        {
            "slug": "brave-search-api",
            "name": "Brave Search API",
            "category": "search",
            "description": "Canonical brave-search-api docs.",
            "official_docs": "https://api.search.brave.com/app/documentation",
        },
        {
            "slug": "people-data-labs",
            "name": "People Data Labs",
            "category": "search",
            "description": "PDL data API.",
            "official_docs": "https://docs.peopledatalabs.com/docs",
        },
    ]

    if decoded == "scores?select=service_slug":
        return [
            {"service_slug": "brave-search"},
            {"service_slug": "pdl"},
        ]

    if decoded.startswith("services?slug=in.(") and "&select=slug,name,category,description" in decoded:
        slugs = _parse_in_filter(decoded, "slug") or {service["slug"] for service in services}
        return [
            {
                "slug": service["slug"],
                "name": service["name"],
                "category": service["category"],
                "description": service["description"],
            }
            for service in services
            if service["slug"] in slugs
        ]

    if decoded.startswith("services?slug=in.(") and "&select=slug,official_docs" in decoded:
        slugs = _parse_in_filter(decoded, "slug") or {service["slug"] for service in services}
        return [
            {
                "slug": service["slug"],
                "official_docs": service["official_docs"],
            }
            for service in services
            if service["slug"] in slugs
        ]

    if decoded.startswith("services?category=eq.search&select=slug,name"):
        return [
            {"slug": service["slug"], "name": service["name"]}
            for service in services
        ]

    if decoded.startswith("services?select=slug,name,category,description"):
        slugs = _parse_in_filter(decoded, "slug") or {service["slug"] for service in services}
        query = _parse_query(decoded)
        offset = int(query.get("offset", ["0"])[0])
        limit = int(query.get("limit", [str(len(services))])[0])
        filtered = [service for service in services if service["slug"] in slugs]
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


def test_unknown_service_score_alias_input_returns_canonical_404(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase_fetch,
    ):
        resp = client.get(
            "/v1/services/Brave-Search/score",
            headers={"X-Request-ID": "req-service-alias-404"},
        )

    assert resp.status_code == 404
    assert resp.json() == {
        "error": "service_not_found",
        "message": "No service found with slug 'brave-search-api'",
        "resolution": "Check available services at GET /v1/services or /v1/search?q=...",
        "request_id": "req-service-alias-404",
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


def test_unknown_service_detail_alias_input_returns_canonical_404(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase_fetch,
    ):
        resp = client.get(
            "/v1/services/Brave-Search",
            headers={"X-Request-ID": "req-service-detail-alias-404"},
        )

    assert resp.status_code == 404
    assert resp.json() == {
        "error": "service_not_found",
        "message": "No service found with slug 'brave-search-api'",
        "resolution": "Check available services at GET /v1/services or /v1/search?q=...",
        "request_id": "req-service-detail-alias-404",
    }


def test_unknown_service_history_returns_404(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase_fetch,
    ):
        resp = client.get(
            "/v1/services/unknown-service/history",
            headers={"X-Request-ID": "req-service-history-404"},
        )

    assert resp.status_code == 404
    assert resp.json() == {
        "error": "service_not_found",
        "message": "No service found with slug 'unknown-service'",
        "resolution": "Check available services at GET /v1/services or /v1/search?q=...",
        "request_id": "req-service-history-404",
    }


def test_unknown_service_history_alias_input_returns_canonical_404(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase_fetch,
    ):
        resp = client.get(
            "/v1/services/Brave-Search/history",
            headers={"X-Request-ID": "req-service-history-alias-404"},
        )

    assert resp.status_code == 404
    assert resp.json() == {
        "error": "service_not_found",
        "message": "No service found with slug 'brave-search-api'",
        "resolution": "Check available services at GET /v1/services or /v1/search?q=...",
        "request_id": "req-service-history-alias-404",
    }


def test_unknown_service_failures_returns_404(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase_fetch,
    ):
        resp = client.get(
            "/v1/services/unknown-service/failures",
            headers={"X-Request-ID": "req-service-failures-404"},
        )

    assert resp.status_code == 404
    assert resp.json() == {
        "error": "service_not_found",
        "message": "No service found with slug 'unknown-service'",
        "resolution": "Check available services at GET /v1/services or /v1/search?q=...",
        "request_id": "req-service-failures-404",
    }


def test_unknown_service_failures_alias_input_returns_canonical_404(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase_fetch,
    ):
        resp = client.get(
            "/v1/services/Brave-Search/failures",
            headers={"X-Request-ID": "req-service-failures-alias-404"},
        )

    assert resp.status_code == 404
    assert resp.json() == {
        "error": "service_not_found",
        "message": "No service found with slug 'brave-search-api'",
        "resolution": "Check available services at GET /v1/services or /v1/search?q=...",
        "request_id": "req-service-failures-alias-404",
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


def test_service_score_exposes_autonomy_contract_fields(client) -> None:
    """GET /v1/services/{slug}/score should expose the nested autonomy contract on stored rows."""
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase_fetch,
    ):
        resp = client.get("/v1/services/stripe/score")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["autonomy_score"] == 9.0
    assert payload["autonomy"]["avg"] == 9.0
    assert payload["autonomy"]["confidence"] == 0.85
    assert len(payload["autonomy"]["dimensions"]) == 3
    assert payload["autonomy"]["dimensions"][0]["code"] == "P1"
    assert payload["dimension_snapshot"]["autonomy"]["avg"] == 9.0


def test_service_score_empty_state_canonicalizes_alias_input(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_empty_alias_score_supabase_fetch,
    ):
        resp = client.get("/v1/services/Brave-Search/score")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["service_slug"] == "brave-search-api"
    assert payload["explanation"] == "No score found for 'brave-search-api'"
    assert payload["docs_url"] == "https://api.search.brave.com/app/documentation"


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
        for path in captured_paths
    )


def test_services_reject_limit_above_max(client) -> None:
    """Limits above 500 should fail explicitly instead of being silently capped."""
    mock_fetch = AsyncMock(side_effect=_mock_supabase_fetch)
    mock_count = AsyncMock(side_effect=_mock_supabase_count)

    with (
        patch("routes.services.supabase_fetch", mock_fetch),
        patch("routes.services.supabase_count", mock_count),
    ):
        resp = client.get("/v1/services", params={"limit": 999})

    assert resp.status_code == 400
    payload = resp.json()
    assert payload["error"]["code"] == "INVALID_PARAMETERS"
    assert payload["error"]["message"] == "Invalid 'limit' filter."
    assert payload["error"]["detail"] == "Provide an integer between 1 and 500."
    assert mock_fetch.await_count == 0
    assert mock_count.await_count == 0


def test_services_reject_invalid_offset_directly() -> None:
    with pytest.raises(RhumbError) as exc_info:
        _validated_service_list_offset(-1)

    assert exc_info.value.code == "INVALID_PARAMETERS"
    assert exc_info.value.message == "Invalid 'offset' filter."
    assert exc_info.value.detail == "Provide an integer greater than or equal to 0."


def test_services_http_rejects_invalid_offset_with_canonical_envelope(client) -> None:
    mock_fetch = AsyncMock(side_effect=_mock_supabase_fetch)
    mock_count = AsyncMock(side_effect=_mock_supabase_count)

    with (
        patch("routes.services.supabase_fetch", mock_fetch),
        patch("routes.services.supabase_count", mock_count),
    ):
        resp = client.get("/v1/services", params={"offset": -1})

    assert resp.status_code == 400
    payload = resp.json()
    assert payload["error"]["code"] == "INVALID_PARAMETERS"
    assert payload["error"]["message"] == "Invalid 'offset' filter."
    assert payload["error"]["detail"] == "Provide an integer greater than or equal to 0."
    assert mock_fetch.await_count == 0
    assert mock_count.await_count == 0


def test_services_rejects_invalid_category_filter(client) -> None:
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
        resp = client.get("/v1/services", params={"category": "search"})

    assert resp.status_code == 400
    payload = resp.json()
    assert payload["error"]["code"] == "INVALID_PARAMETERS"
    assert payload["error"]["message"] == "Invalid 'category' filter."
    assert payload["error"]["detail"] == "Use one of: email, payments."


def test_services_normalizes_category_filter_casing_and_whitespace(client) -> None:
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
        resp = client.get("/v1/services", params={"category": " Payments  "})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["error"] is None
    assert payload["data"]["total"] == 300
    assert all(item["category"] == "payments" for item in payload["data"]["items"])
    assert payload["data"]["items"][0]["slug"] == "service-0000"


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


def test_services_endpoint_canonicalizes_runtime_alias_service_rows(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_runtime_alias_service_supabase_fetch,
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
    assert payload["data"]["autonomy_score"] == 8.4
    assert payload["data"]["autonomy"]["avg"] == 8.4
    assert payload["data"]["an_score_version"] == "0.3"
    assert payload["data"]["dimension_snapshot"]["autonomy"]["avg"] == 8.4
    assert payload["data"]["dimension_snapshot"]["probe_freshness"] == "5 minutes ago"
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


def test_service_detail_reads_runtime_alias_service_rows(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_runtime_alias_service_supabase_fetch,
    ):
        resp = client.get("/v1/services/Brave-Search-Api")

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



def test_services_list_prefers_canonical_service_row_copy_and_preserves_shorthand(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_preferred_canonical_service_row_supabase_fetch,
    ):
        resp = client.get("/v1/services")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["error"] is None
    brave = next(item for item in payload["data"]["items"] if item["slug"] == "brave-search-api")
    pdl = next(item for item in payload["data"]["items"] if item["slug"] == "people-data-labs")
    assert brave["name"] == "Brave Search API"
    assert brave["description"] == "Canonical brave-search-api docs."
    assert pdl["description"] == "PDL data API."



def test_canonicalize_service_rows_canonicalizes_same_service_alias_text_for_canonical_rows() -> None:
    rows = _canonicalize_service_rows([
        {
            "slug": "brave-search-api",
            "name": "Brave Search (brave-search)",
            "category": "search",
            "description": "Legacy brave-search docs.",
            "official_docs": "https://api.search.brave.com/app/documentation",
        }
    ])

    assert rows[0]["slug"] == "brave-search-api"
    assert rows[0]["name"] == "Brave Search (brave-search-api)"
    assert rows[0]["description"] == "Legacy brave-search-api docs."



def test_service_detail_prefers_canonical_service_row_copy_when_alias_row_also_exists(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_preferred_canonical_service_row_supabase_fetch,
    ):
        resp = client.get("/v1/services/brave-search-api")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["error"] is None
    assert payload["data"]["slug"] == "brave-search-api"
    assert payload["data"]["name"] == "Brave Search API"
    assert payload["data"]["description"] == "Canonical brave-search-api docs."



def test_service_detail_canonicalizes_alias_backed_score_rationales(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_alias_score_text_supabase_fetch,
    ):
        resp = client.get("/v1/services/brave-search-api")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["error"] is None
    assert payload["data"]["slug"] == "brave-search-api"
    assert payload["data"]["payment_autonomy_rationale"] == "brave-search-api supports direct billing."
    assert payload["data"]["autonomy"]["dimensions"][0]["rationale"] == "brave-search-api supports direct billing."
    assert payload["data"]["dimension_snapshot"]["notes"]["summary"] == "brave-search-api stays easy to script."



def test_service_detail_preserves_human_shorthand_on_canonical_score_rows(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_canonical_score_text_supabase_fetch,
    ):
        resp = client.get("/v1/services/people-data-labs")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["error"] is None
    assert payload["data"]["slug"] == "people-data-labs"
    assert payload["data"]["payment_autonomy_rationale"] == "PDL supports direct billing."
    assert payload["data"]["autonomy"]["dimensions"][0]["rationale"] == "PDL supports direct billing."
    assert payload["data"]["dimension_snapshot"]["notes"]["summary"] == "PDL stays easy to script."



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


def test_service_history_preserves_empty_state_for_known_services(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_known_service_without_history_supabase_fetch,
    ):
        resp = client.get("/v1/services/service-no-history/history")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["error"] is None
    assert payload["data"] == {"slug": "service-no-history", "history": []}


def test_service_history_rejects_invalid_limit_directly() -> None:
    with pytest.raises(RhumbError) as exc_info:
        _validated_service_history_limit(101)

    assert exc_info.value.code == "INVALID_PARAMETERS"
    assert exc_info.value.message == "Invalid 'limit' filter."
    assert exc_info.value.detail == "Provide an integer between 1 and 100."


def test_service_history_http_rejects_invalid_limit_with_canonical_envelope(client) -> None:
    mock_fetch = AsyncMock(side_effect=_mock_alias_supabase_fetch)

    with patch("routes.services.supabase_fetch", mock_fetch):
        resp = client.get("/v1/services/brave-search-api/history", params={"limit": 101})

    assert resp.status_code == 400
    payload = resp.json()
    assert payload["error"]["code"] == "INVALID_PARAMETERS"
    assert payload["error"]["message"] == "Invalid 'limit' filter."
    assert payload["error"]["detail"] == "Provide an integer between 1 and 100."
    assert mock_fetch.await_count == 0


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


def test_service_score_reads_runtime_alias_service_docs(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_runtime_alias_service_supabase_fetch,
    ):
        resp = client.get("/v1/services/brave-search-api/score")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["service_slug"] == "brave-search-api"
    assert payload["docs_url"] == "https://api.search.brave.com/app/documentation"
    assert payload["an_score"] == 8.7


def test_service_score_canonicalizes_alias_backed_score_explanation_and_snapshot(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_alias_score_text_supabase_fetch,
    ):
        resp = client.get("/v1/services/brave-search-api/score")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["service_slug"] == "brave-search-api"
    assert "Payment: brave-search-api supports direct billing" in payload["explanation"]
    assert payload["autonomy"]["dimensions"][0]["rationale"] == "brave-search-api supports direct billing."
    assert payload["dimension_snapshot"]["notes"]["summary"] == "brave-search-api stays easy to script."



def test_service_score_canonicalizes_alternate_provider_aliases_in_score_copy(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_alias_score_alternate_text_supabase_fetch,
    ):
        resp = client.get("/v1/services/brave-search-api/score")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["service_slug"] == "brave-search-api"
    assert (
        "Payment: brave-search-api outperforms people-data-labs on direct billing handoff"
        in payload["explanation"]
    )
    assert payload["autonomy"]["dimensions"][0]["rationale"] == (
        "brave-search-api can fall back to people-data-labs when needed."
    )
    assert payload["dimension_snapshot"]["notes"]["summary"] == (
        "brave-search-api stays easy to script and can replace people-data-labs for quick checks."
    )



def test_service_score_canonicalizes_alternate_provider_aliases_in_canonical_score_copy(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_canonical_score_and_failure_alternate_text_supabase_fetch,
    ):
        resp = client.get("/v1/services/brave-search-api/score")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["service_slug"] == "brave-search-api"
    assert (
        "Payment: brave-search-api outperforms people-data-labs on direct billing handoff"
        in payload["explanation"]
    )
    assert payload["autonomy"]["dimensions"][0]["rationale"] == (
        "brave-search-api can fall back to people-data-labs when needed."
    )
    assert payload["dimension_snapshot"]["notes"]["summary"] == (
        "brave-search-api stays easy to script and can replace people-data-labs for quick checks."
    )



def test_service_score_canonicalizes_legacy_alias_mentions_in_failure_copy(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_alias_failure_text_supabase_fetch,
    ):
        resp = client.get("/v1/services/brave-search-api/score")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["service_slug"] == "brave-search-api"
    assert payload["failure_modes"] == [
        {
            "pattern": "brave-search-api session tokens expire early",
            "impact": "Agents using brave-search-api may need to retry search requests.",
            "frequency": "intermittent",
            "workaround": "Refresh brave-search-api credentials before multi-step browse loops.",
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



def test_service_failures_preserve_human_shorthand_on_canonical_rows(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_canonical_failure_text_supabase_fetch,
    ):
        resp = client.get("/v1/services/people-data-labs/failures")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["data"]["slug"] == "people-data-labs"
    assert payload["data"]["failure_modes"] == [
        {
            "pattern": "PDL session windows are short",
            "impact": "Agents using PDL may need to re-run enrichment steps.",
            "frequency": "intermittent",
            "workaround": "Re-authenticate PDL before long imports.",
            "category": "auth",
            "severity": "medium",
            "description": "PDL sessions can time out during long imports.",
            "last_verified": "2026-04-16T15:45:00Z",
            "evidence_count": 1,
        }
    ]



def test_service_detail_and_failures_canonicalize_alternate_provider_aliases_in_canonical_rows(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_canonical_score_and_failure_alternate_text_supabase_fetch,
    ):
        detail_resp = client.get("/v1/services/brave-search-api")
        failures_resp = client.get("/v1/services/brave-search-api/failures")

    assert detail_resp.status_code == 200
    detail_payload = detail_resp.json()
    assert detail_payload["data"]["payment_autonomy_rationale"] == (
        "brave-search-api outperforms people-data-labs on direct billing handoff."
    )
    assert detail_payload["data"]["autonomy"]["dimensions"][0]["rationale"] == (
        "brave-search-api can fall back to people-data-labs when needed."
    )
    assert detail_payload["data"]["dimension_snapshot"]["notes"]["summary"] == (
        "brave-search-api stays easy to script and can replace people-data-labs for quick checks."
    )

    assert failures_resp.status_code == 200
    failures_payload = failures_resp.json()
    assert failures_payload["data"]["slug"] == "brave-search-api"
    assert failures_payload["data"]["failure_modes"] == [
        {
            "pattern": "brave-search-api session tokens expire early after people-data-labs fallback",
            "impact": "Agents using brave-search-api may need to retry after people-data-labs fallback.",
            "frequency": "intermittent",
            "workaround": "Refresh brave-search-api credentials before multi-step flows that may hit people-data-labs fallback.",
            "category": "auth",
            "severity": "medium",
            "description": "brave-search-api sessions can lose auth unexpectedly when people-data-labs fallback is triggered.",
            "last_verified": "2026-04-16T15:45:00Z",
            "evidence_count": 2,
        }
    ]



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



def test_service_failures_preserve_empty_state_for_known_services(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase_fetch,
    ):
        resp = client.get("/v1/services/stripe/failures")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["error"] is None
    assert payload["data"] == {"slug": "stripe", "failure_modes": []}



def test_service_schema_and_report_preserve_known_service_empty_states(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase_fetch,
    ):
        schema_resp = client.get("/v1/services/stripe/schema")
        report_resp = client.post("/v1/services/stripe/report")

    assert schema_resp.status_code == 200
    assert schema_resp.json()["error"] is None
    assert schema_resp.json()["data"] == {"slug": "stripe", "schema": None}
    assert report_resp.status_code == 200
    assert report_resp.json()["error"] is None
    assert report_resp.json()["data"] == {"slug": "stripe", "accepted": True}



def test_service_schema_and_report_normalize_mixed_case_alias_inputs(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_alias_supabase_fetch,
    ):
        schema_resp = client.get("/v1/services/Brave-Search-Api/schema")
        report_resp = client.post("/v1/services/PDL/report")

    assert schema_resp.status_code == 200
    assert schema_resp.json()["data"]["slug"] == "brave-search-api"
    assert report_resp.status_code == 200
    assert report_resp.json()["data"]["slug"] == "people-data-labs"



def test_service_schema_and_report_return_not_found_for_unknown_services(client) -> None:
    with patch(
        "routes.services.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase_fetch,
    ):
        schema_resp = client.get("/v1/services/unknown-service/schema")
        report_resp = client.post("/v1/services/unknown-service/report")

    assert schema_resp.status_code == 404
    assert schema_resp.json()["error"] == "service_not_found"
    assert schema_resp.json()["message"] == "No service found with slug 'unknown-service'"
    assert report_resp.status_code == 404
    assert report_resp.json()["error"] == "service_not_found"
    assert report_resp.json()["message"] == "No service found with slug 'unknown-service'"
