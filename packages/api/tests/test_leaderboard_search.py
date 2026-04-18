"""Test leaderboard and search endpoints."""

import pytest
import re
import sys
from pathlib import Path
from urllib.parse import unquote
from unittest.mock import AsyncMock, patch

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from routes.leaderboard import (
    _canonicalize_service_rows as canonicalize_leaderboard_rows,
    get_leaderboard,
    list_categories,
)
from routes.search import _canonicalize_service_rows as canonicalize_search_rows
from routes.search import search_services


_SERVICES = [
    {
        "slug": "resend",
        "name": "Resend",
        "category": "email",
        "description": "Transactional email API",
    },
    {
        "slug": "postmark",
        "name": "Postmark",
        "category": "email",
        "description": "Email delivery for apps",
    },
    {
        "slug": "stripe",
        "name": "Stripe",
        "category": "payments",
        "description": "Accept payments API",
    },
    {
        "slug": "brave-search-api",
        "name": "Brave Search API",
        "category": "search",
        "description": "Web search API",
    },
]

_SCORE_ROWS = [
    {
        "service_slug": "resend",
        "aggregate_recommendation_score": 8.8,
        "execution_score": 8.6,
        "access_readiness_score": 8.7,
        "tier": "L3",
        "tier_label": "Ready",
        "confidence": 0.92,
    },
    {
        "service_slug": "postmark",
        "aggregate_recommendation_score": 8.1,
        "execution_score": 7.9,
        "access_readiness_score": 8.0,
        "tier": "L3",
        "tier_label": "Ready",
        "confidence": 0.88,
    },
    {
        "service_slug": "stripe",
        "aggregate_recommendation_score": 8.2,
        "execution_score": 8.0,
        "access_readiness_score": 8.1,
        "tier": "L3",
        "tier_label": "Ready",
        "confidence": 0.9,
    },
    {
        "service_slug": "brave-search",
        "aggregate_recommendation_score": 8.7,
        "execution_score": 8.5,
        "access_readiness_score": 8.6,
        "tier": "L4",
        "tier_label": "Strong",
        "confidence": 0.91,
    },
]

_ALIAS_BACKED_SERVICES = [
    {
        "slug": "brave-search",
        "name": "Brave Search API",
        "category": "search",
        "description": "Web search API",
    }
]

_MIXED_ORDER_ALIAS_BACKED_SERVICES = [
    {
        "slug": "brave-search",
        "name": "Legacy brave-search",
        "category": "search",
        "description": "Legacy brave-search docs.",
    },
    {
        "slug": "brave-search-api",
        "name": "Brave Search API",
        "category": "search",
        "description": "Canonical brave-search-api docs.",
    },
    {
        "slug": "people-data-labs",
        "name": "People Data Labs",
        "category": "search",
        "description": "PDL data API.",
    },
]

_ALTERNATE_ALIAS_TEXT_SERVICES = [
    {
        "slug": "brave-search",
        "name": "brave-search won after pdl comparison",
        "category": "search",
        "description": "Use brave-search after pdl comparison.",
    }
]

_CANONICAL_ROW_ALTERNATE_ALIAS_TEXT_SERVICES = [
    {
        "slug": "brave-search-api",
        "name": "brave-search-api won after pdl comparison",
        "category": "search",
        "description": "Use brave-search-api after pdl comparison.",
    }
]

_CANONICAL_ROW_SHORTHAND_SERVICES = [
    {
        "slug": "people-data-labs",
        "name": "PDL",
        "category": "search",
        "description": "PDL data API.",
    }
]

_CANONICAL_ROW_ALTERNATE_ALIAS_TEXT_SCORES = [
    {
        "service_slug": "brave-search-api",
        "aggregate_recommendation_score": 8.7,
        "execution_score": 8.5,
        "access_readiness_score": 8.6,
        "tier": "L4",
        "tier_label": "Strong",
        "confidence": 0.91,
    },
]

_CANONICAL_ROW_SHORTHAND_SCORES = [
    {
        "service_slug": "people-data-labs",
        "aggregate_recommendation_score": 8.4,
        "execution_score": 8.1,
        "access_readiness_score": 8.2,
        "tier": "L3",
        "tier_label": "Ready",
        "confidence": 0.89,
    },
]


def _parse_in_filter(path: str, key: str) -> set[str] | None:
    match = re.search(rf"{re.escape(key)}=in\.\(([^)]*)\)", unquote(path))
    if not match:
        return None
    raw_values = match.group(1)
    values = {
        part.strip().strip('"')
        for part in raw_values.split(",")
        if part.strip()
    }
    return values


def _extract_category(path: str) -> str | None:
    match = re.search(r"category=eq\.([^&]+)", unquote(path))
    return match.group(1) if match else None


def _extract_search_query(path: str) -> str | None:
    match = re.search(r"\.ilike\.\*([^*]+)\*", unquote(path))
    return match.group(1).lower() if match else None


def _service_matches_query(service: dict, query: str) -> bool:
    haystacks = [
        service["slug"],
        service["name"],
        service["category"],
        service["description"],
    ]
    query = query.lower()
    return any(query in value.lower() for value in haystacks)


def _mock_catalog_supabase(path: str):
    decoded = unquote(path)

    if decoded.startswith("services?category=eq."):
        category = _extract_category(decoded)
        return [
            {"slug": service["slug"], "name": service["name"]}
            for service in _SERVICES
            if service["category"] == category
        ]

    if decoded.startswith("services?select=category"):
        return [{"category": service["category"]} for service in _SERVICES]

    if decoded.startswith("services?select=slug,category"):
        return [
            {"slug": service["slug"], "category": service["category"]}
            for service in _SERVICES
        ]

    if decoded.startswith("services?slug=in.("):
        slugs = _parse_in_filter(decoded, "slug") or set()
        return [service for service in _SERVICES if service["slug"] in slugs]

    if decoded.startswith("services?or=("):
        query = _extract_search_query(decoded)
        if not query:
            return []
        return [service for service in _SERVICES if _service_matches_query(service, query)]

    if decoded.startswith("scores?select=service_slug"):
        return [{"service_slug": row["service_slug"]} for row in _SCORE_ROWS]

    if decoded.startswith("scores?service_slug=in.("):
        slugs = _parse_in_filter(decoded, "service_slug") or set()
        return [row for row in _SCORE_ROWS if row["service_slug"] in slugs]

    if decoded.startswith("scores?"):
        return list(_SCORE_ROWS)

    return []


def _mock_alias_backed_catalog_supabase(path: str):
    decoded = unquote(path)

    if decoded.startswith("services?category=eq.search"):
        return [{"slug": service["slug"], "name": service["name"]} for service in _ALIAS_BACKED_SERVICES]

    if decoded.startswith("services?select=category"):
        return [{"category": service["category"]} for service in _ALIAS_BACKED_SERVICES]

    if decoded.startswith("services?select=slug,category"):
        return [
            {"slug": service["slug"], "category": service["category"]}
            for service in _ALIAS_BACKED_SERVICES
        ]

    if decoded.startswith("services?or=("):
        query = _extract_search_query(decoded)
        if not query:
            return []
        return [service for service in _ALIAS_BACKED_SERVICES if _service_matches_query(service, query)]

    if decoded.startswith("scores?select=service_slug"):
        return [{"service_slug": "brave-search"}]

    if decoded.startswith("scores?service_slug=in.("):
        slugs = _parse_in_filter(decoded, "service_slug") or set()
        return [row for row in _SCORE_ROWS if row["service_slug"] in slugs]

    if decoded.startswith("scores?"):
        return [row for row in _SCORE_ROWS if row["service_slug"] == "brave-search"]

    return []


def _mock_mixed_order_alias_catalog_supabase(path: str):
    decoded = unquote(path)

    if decoded.startswith("services?category=eq.search"):
        return [
            {"slug": service["slug"], "name": service["name"]}
            for service in _MIXED_ORDER_ALIAS_BACKED_SERVICES
        ]

    if decoded.startswith("services?select=category"):
        return [{"category": service["category"]} for service in _MIXED_ORDER_ALIAS_BACKED_SERVICES]

    if decoded.startswith("services?select=slug,category"):
        return [
            {"slug": service["slug"], "category": service["category"]}
            for service in _MIXED_ORDER_ALIAS_BACKED_SERVICES
        ]

    if decoded.startswith("services?or=("):
        query = _extract_search_query(decoded)
        if not query:
            return []
        return [
            service
            for service in _MIXED_ORDER_ALIAS_BACKED_SERVICES
            if _service_matches_query(service, query)
        ]

    if decoded.startswith("scores?select=service_slug"):
        return [{"service_slug": "brave-search"}, {"service_slug": "pdl"}]

    if decoded.startswith("scores?service_slug=in.("):
        slugs = _parse_in_filter(decoded, "service_slug") or set()
        return [row for row in _SCORE_ROWS if row["service_slug"] in slugs]

    if decoded.startswith("scores?"):
        return [
            row
            for row in _SCORE_ROWS
            if row["service_slug"] in {"brave-search", "pdl"}
        ]

    return []


def _mock_alternate_alias_text_catalog_supabase(path: str):
    decoded = unquote(path)

    if decoded.startswith("services?category=eq.search"):
        return [
            {"slug": service["slug"], "name": service["name"]}
            for service in _ALTERNATE_ALIAS_TEXT_SERVICES
        ]

    if decoded.startswith("services?select=category"):
        return [{"category": service["category"]} for service in _ALTERNATE_ALIAS_TEXT_SERVICES]

    if decoded.startswith("services?select=slug,category"):
        return [
            {"slug": service["slug"], "category": service["category"]}
            for service in _ALTERNATE_ALIAS_TEXT_SERVICES
        ]

    if decoded.startswith("services?or=("):
        query = _extract_search_query(decoded)
        if not query:
            return []
        return [
            service
            for service in _ALTERNATE_ALIAS_TEXT_SERVICES
            if _service_matches_query(service, query)
        ]

    if decoded.startswith("scores?select=service_slug"):
        return [{"service_slug": "brave-search"}]

    if decoded.startswith("scores?service_slug=in.("):
        slugs = _parse_in_filter(decoded, "service_slug") or set()
        return [row for row in _SCORE_ROWS if row["service_slug"] in slugs]

    if decoded.startswith("scores?"):
        return [row for row in _SCORE_ROWS if row["service_slug"] == "brave-search"]

    return []


def _mock_canonical_row_alternate_alias_text_catalog_supabase(path: str):
    decoded = unquote(path)

    if decoded.startswith("services?category=eq.search"):
        return [
            {"slug": service["slug"], "name": service["name"]}
            for service in _CANONICAL_ROW_ALTERNATE_ALIAS_TEXT_SERVICES
        ]

    if decoded.startswith("services?select=category"):
        return [{"category": service["category"]} for service in _CANONICAL_ROW_ALTERNATE_ALIAS_TEXT_SERVICES]

    if decoded.startswith("services?select=slug,category"):
        return [
            {"slug": service["slug"], "category": service["category"]}
            for service in _CANONICAL_ROW_ALTERNATE_ALIAS_TEXT_SERVICES
        ]

    if decoded.startswith("services?or=("):
        query = _extract_search_query(decoded)
        if not query:
            return []
        return [
            service
            for service in _CANONICAL_ROW_ALTERNATE_ALIAS_TEXT_SERVICES
            if _service_matches_query(service, query)
        ]

    if decoded.startswith("scores?select=service_slug"):
        return [{"service_slug": row["service_slug"]} for row in _CANONICAL_ROW_ALTERNATE_ALIAS_TEXT_SCORES]

    if decoded.startswith("scores?service_slug=in.("):
        slugs = _parse_in_filter(decoded, "service_slug") or set()
        return [row for row in _CANONICAL_ROW_ALTERNATE_ALIAS_TEXT_SCORES if row["service_slug"] in slugs]

    if decoded.startswith("scores?"):
        return list(_CANONICAL_ROW_ALTERNATE_ALIAS_TEXT_SCORES)

    return []


def _mock_canonical_row_shorthand_catalog_supabase(path: str):
    decoded = unquote(path)

    if decoded.startswith("services?category=eq.search"):
        return [
            {"slug": service["slug"], "name": service["name"]}
            for service in _CANONICAL_ROW_SHORTHAND_SERVICES
        ]

    if decoded.startswith("services?select=category"):
        return [{"category": service["category"]} for service in _CANONICAL_ROW_SHORTHAND_SERVICES]

    if decoded.startswith("services?select=slug,category"):
        return [
            {"slug": service["slug"], "category": service["category"]}
            for service in _CANONICAL_ROW_SHORTHAND_SERVICES
        ]

    if decoded.startswith("services?or=("):
        query = _extract_search_query(decoded)
        if not query:
            return []
        return [
            service
            for service in _CANONICAL_ROW_SHORTHAND_SERVICES
            if _service_matches_query(service, query)
        ]

    if decoded.startswith("scores?select=service_slug"):
        return [{"service_slug": row["service_slug"]} for row in _CANONICAL_ROW_SHORTHAND_SCORES]

    if decoded.startswith("scores?service_slug=in.("):
        slugs = _parse_in_filter(decoded, "service_slug") or set()
        return [row for row in _CANONICAL_ROW_SHORTHAND_SCORES if row["service_slug"] in slugs]

    if decoded.startswith("scores?"):
        return list(_CANONICAL_ROW_SHORTHAND_SCORES)

    return []


@pytest.fixture
def mock_catalog_supabase():
    with (
        patch("routes.leaderboard.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_catalog_supabase),
        patch("routes.search.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_catalog_supabase),
    ):
        yield


@pytest.mark.asyncio
async def test_list_categories(mock_catalog_supabase):
    """Test /leaderboard endpoint lists all categories."""
    result = await list_categories()
    assert result["error"] is None
    assert "data" in result
    assert "categories" in result["data"]
    assert isinstance(result["data"]["categories"], list)
    assert result["data"]["total"] == 3


@pytest.mark.asyncio
async def test_get_leaderboard_email(mock_catalog_supabase):
    """Test /leaderboard/email returns email services."""
    result = await get_leaderboard("email", limit=5)
    assert result["error"] is None
    assert result["data"]["category"] == "email"
    assert isinstance(result["data"]["items"], list)
    assert result["data"]["count"] <= 5
    assert {item["service_slug"] for item in result["data"]["items"]} == {"resend", "postmark"}

    item = result["data"]["items"][0]
    assert "service_slug" in item
    assert "score" in item
    assert "tier" in item


@pytest.mark.asyncio
async def test_get_leaderboard_canonicalizes_alias_backed_scores(mock_catalog_supabase):
    result = await get_leaderboard("search", limit=5)
    assert result["error"] is None
    assert result["data"]["count"] == 1
    item = result["data"]["items"][0]
    assert item["service_slug"] == "brave-search-api"
    assert item["name"] == "Brave Search API"
    assert item["an_score"] == 8.7


@pytest.mark.asyncio
async def test_get_leaderboard_canonicalizes_alias_backed_service_rows():
    with patch("routes.leaderboard.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_alias_backed_catalog_supabase):
        result = await get_leaderboard("search", limit=5)

    assert result["error"] is None
    assert result["data"]["count"] == 1
    item = result["data"]["items"][0]
    assert item["service_slug"] == "brave-search-api"
    assert item["name"] == "Brave Search API"
    assert item["an_score"] == 8.7


@pytest.mark.asyncio
async def test_get_leaderboard_invalid_category(mock_catalog_supabase):
    """Test /leaderboard/{invalid} returns error."""
    result = await get_leaderboard("nonexistent-category")
    assert result["error"] is not None
    assert result["data"]["items"] == []


@pytest.mark.asyncio
async def test_get_leaderboard_limit(mock_catalog_supabase):
    """Test /leaderboard limit parameter works."""
    result = await get_leaderboard("email", limit=1)
    assert result["data"]["count"] <= 1


@pytest.mark.asyncio
async def test_search_by_slug(mock_catalog_supabase):
    """Test search by service slug."""
    result = await search_services("stripe")
    assert result["error"] is None
    assert len(result["data"]["results"]) > 0

    slugs = [r["service_slug"] for r in result["data"]["results"]]
    assert "stripe" in slugs


@pytest.mark.asyncio
async def test_search_by_name(mock_catalog_supabase):
    """Test search by service name."""
    result = await search_services("Stripe")
    assert result["error"] is None
    assert len(result["data"]["results"]) > 0


@pytest.mark.asyncio
async def test_search_canonicalizes_alias_backed_scores(mock_catalog_supabase):
    result = await search_services("brave")
    assert result["error"] is None
    assert len(result["data"]["results"]) == 1
    item = result["data"]["results"][0]
    assert item["service_slug"] == "brave-search-api"
    assert item["an_score"] == 8.7
    assert item["tier"] == "L4"


@pytest.mark.asyncio
async def test_search_canonicalizes_alias_backed_service_rows():
    with patch("routes.search.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_alias_backed_catalog_supabase):
        result = await search_services("brave")

    assert result["error"] is None
    assert len(result["data"]["results"]) == 1
    item = result["data"]["results"][0]
    assert item["service_slug"] == "brave-search-api"
    assert item["name"] == "Brave Search API"
    assert item["an_score"] == 8.7


@pytest.mark.asyncio
async def test_search_prefers_canonical_service_row_copy_when_alias_row_also_exists():
    with patch("routes.search.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_mixed_order_alias_catalog_supabase):
        result = await search_services("brave")

    assert result["error"] is None
    assert len(result["data"]["results"]) == 1
    item = result["data"]["results"][0]
    assert item["service_slug"] == "brave-search-api"
    assert item["name"] == "Brave Search API"
    assert item["description"] == "Canonical brave-search-api docs."


def test_search_canonicalize_service_rows_canonicalizes_same_service_alias_text_for_canonical_rows():
    rows = canonicalize_search_rows([
        {
            "slug": "brave-search-api",
            "name": "Brave Search (brave-search)",
            "category": "search",
            "description": "Legacy brave-search docs.",
        }
    ])

    assert rows[0]["slug"] == "brave-search-api"
    assert rows[0]["name"] == "Brave Search (brave-search-api)"
    assert rows[0]["description"] == "Legacy brave-search-api docs."


@pytest.mark.asyncio
async def test_search_canonicalizes_alternate_alias_mentions_in_service_row_copy():
    with patch("routes.search.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_alternate_alias_text_catalog_supabase):
        result = await search_services("comparison")

    assert result["error"] is None
    assert len(result["data"]["results"]) == 1
    item = result["data"]["results"][0]
    assert item["service_slug"] == "brave-search-api"
    assert item["name"] == "brave-search-api won after people-data-labs comparison"
    assert item["description"] == "Use brave-search-api after people-data-labs comparison."


@pytest.mark.asyncio
async def test_search_canonicalizes_alternate_alias_mentions_in_canonical_service_rows():
    with patch(
        "routes.search.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_canonical_row_alternate_alias_text_catalog_supabase,
    ):
        result = await search_services("comparison")

    assert result["error"] is None
    assert len(result["data"]["results"]) == 1
    item = result["data"]["results"][0]
    assert item["service_slug"] == "brave-search-api"
    assert item["name"] == "brave-search-api won after people-data-labs comparison"
    assert item["description"] == "Use brave-search-api after people-data-labs comparison."


@pytest.mark.asyncio
async def test_search_preserves_human_shorthand_in_canonical_service_rows():
    with patch(
        "routes.search.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_canonical_row_shorthand_catalog_supabase,
    ):
        result = await search_services("pdl")

    assert result["error"] is None
    assert len(result["data"]["results"]) == 1
    item = result["data"]["results"][0]
    assert item["service_slug"] == "people-data-labs"
    assert item["name"] == "PDL"
    assert item["description"] == "PDL data API."


@pytest.mark.asyncio
async def test_search_by_category(mock_catalog_supabase):
    """Test search by category."""
    result = await search_services("email")
    assert result["error"] is None
    results = result["data"]["results"]
    assert len(results) == 2
    assert all(item["category"] == "email" for item in results)


@pytest.mark.asyncio
async def test_search_empty_query(mock_catalog_supabase):
    """Test search with empty query returns error."""
    result = await search_services("")
    assert result["error"] is not None


@pytest.mark.asyncio
async def test_search_limit(mock_catalog_supabase):
    """Test search limit parameter works."""
    result = await search_services("api", limit=1)
    assert len(result["data"]["results"]) <= 1


@pytest.mark.asyncio
async def test_search_results_have_scores(mock_catalog_supabase):
    """Test search results include score data."""
    result = await search_services("stripe")
    assert len(result["data"]["results"]) > 0

    item = result["data"]["results"][0]
    assert "an_score" in item
    assert "tier" in item
    assert "confidence" in item


@pytest.mark.asyncio
async def test_search_result_schema(mock_catalog_supabase):
    """Search result items have the expected schema fields."""
    result = await search_services("stripe")
    assert result["error"] is None
    if result["data"]["results"]:
        item = result["data"]["results"][0]
        assert "service_slug" in item
        assert "name" in item
        assert "category" in item


@pytest.mark.asyncio
async def test_search_uses_stale_cache_during_catalog_outage():
    with patch("routes.search.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_catalog_supabase):
        warm = await search_services("stripe")

    with patch("routes.search.supabase_fetch", new_callable=AsyncMock, return_value=None):
        degraded = await search_services("stripe")

    assert warm["error"] is None
    assert degraded["error"] is None
    assert degraded["data"]["results"] == warm["data"]["results"]


@pytest.mark.asyncio
async def test_leaderboard_uses_stale_cache_during_catalog_outage():
    with patch("routes.leaderboard.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_catalog_supabase):
        warm = await get_leaderboard("email", limit=5)

    with patch("routes.leaderboard.supabase_fetch", new_callable=AsyncMock, return_value=None):
        degraded = await get_leaderboard("email", limit=5)

    assert warm["error"] is None
    assert degraded["error"] is None
    assert degraded["data"]["items"] == warm["data"]["items"]
    assert degraded["data"]["count"] == warm["data"]["count"]


@pytest.mark.asyncio
async def test_list_categories_canonicalizes_alias_backed_service_rows():
    with patch("routes.leaderboard.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_alias_backed_catalog_supabase):
        result = await list_categories()

    assert result["error"] is None
    assert result["data"]["categories"] == [{"slug": "search", "service_count": 1}]


@pytest.mark.asyncio
async def test_leaderboard_prefers_canonical_service_row_copy_when_alias_row_also_exists():
    with patch("routes.leaderboard.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_mixed_order_alias_catalog_supabase):
        result = await get_leaderboard("search", limit=5)

    assert result["error"] is None
    assert result["data"]["count"] == 1
    item = result["data"]["items"][0]
    assert item["service_slug"] == "brave-search-api"
    assert item["name"] == "Brave Search API"


def test_leaderboard_canonicalize_service_rows_canonicalizes_same_service_alias_text_for_canonical_rows():
    rows = canonicalize_leaderboard_rows([
        {
            "slug": "brave-search-api",
            "name": "Brave Search (brave-search)",
            "category": "search",
            "description": "Legacy brave-search docs.",
        }
    ])

    assert rows[0]["slug"] == "brave-search-api"
    assert rows[0]["name"] == "Brave Search (brave-search-api)"
    assert rows[0]["description"] == "Legacy brave-search-api docs."


@pytest.mark.asyncio
async def test_leaderboard_canonicalizes_alternate_alias_mentions_in_service_row_copy():
    with patch("routes.leaderboard.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_alternate_alias_text_catalog_supabase):
        result = await get_leaderboard("search", limit=5)

    assert result["error"] is None
    assert result["data"]["count"] == 1
    item = result["data"]["items"][0]
    assert item["service_slug"] == "brave-search-api"
    assert item["name"] == "brave-search-api won after people-data-labs comparison"


@pytest.mark.asyncio
async def test_leaderboard_canonicalizes_alternate_alias_mentions_in_canonical_service_rows():
    with patch(
        "routes.leaderboard.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_canonical_row_alternate_alias_text_catalog_supabase,
    ):
        result = await get_leaderboard("search", limit=5)

    assert result["error"] is None
    assert result["data"]["count"] == 1
    item = result["data"]["items"][0]
    assert item["service_slug"] == "brave-search-api"
    assert item["name"] == "brave-search-api won after people-data-labs comparison"


@pytest.mark.asyncio
async def test_leaderboard_preserves_human_shorthand_in_canonical_service_rows():
    with patch(
        "routes.leaderboard.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_canonical_row_shorthand_catalog_supabase,
    ):
        result = await get_leaderboard("search", limit=5)

    assert result["error"] is None
    assert result["data"]["count"] == 1
    item = result["data"]["items"][0]
    assert item["service_slug"] == "people-data-labs"
    assert item["name"] == "PDL"


@pytest.mark.asyncio
async def test_get_service_categories(mock_catalog_supabase):
    """Test category listing works via list_categories."""
    result = await list_categories()
    assert result["error"] is None
    categories = result["data"]["categories"]
    assert isinstance(categories, list)
    assert all("slug" in c and "service_count" in c for c in categories)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
