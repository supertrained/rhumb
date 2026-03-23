"""Test leaderboard and search endpoints."""

import pytest
import sys
from pathlib import Path

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from routes.leaderboard import get_leaderboard, list_categories
from routes.search import search_services


@pytest.mark.asyncio
async def test_list_categories():
    """Test /leaderboard endpoint lists all categories."""
    result = await list_categories()
    assert result["error"] is None
    assert "data" in result
    assert "categories" in result["data"]
    assert isinstance(result["data"]["categories"], list)
    assert result["data"]["total"] >= 0


@pytest.mark.asyncio
async def test_get_leaderboard_email():
    """Test /leaderboard/email returns email services."""
    result = await get_leaderboard("email", limit=5)
    assert result["error"] is None
    assert result["data"]["category"] == "email"
    assert isinstance(result["data"]["items"], list)
    assert result["data"]["count"] <= 5
    
    if result["data"]["items"]:
        item = result["data"]["items"][0]
        assert "service_slug" in item
        assert "score" in item
        assert "tier" in item


@pytest.mark.asyncio
async def test_get_leaderboard_invalid_category():
    """Test /leaderboard/{invalid} returns error."""
    result = await get_leaderboard("nonexistent-category")
    assert result["error"] is not None
    assert result["data"]["items"] == []


@pytest.mark.asyncio
async def test_get_leaderboard_limit():
    """Test /leaderboard limit parameter works."""
    result = await get_leaderboard("email", limit=3)
    assert result["data"]["count"] <= 3


@pytest.mark.asyncio
async def test_search_by_slug():
    """Test search by service slug."""
    result = await search_services("stripe")
    assert result["error"] is None
    assert len(result["data"]["results"]) > 0
    
    # Stripe should be in results
    slugs = [r["service_slug"] for r in result["data"]["results"]]
    assert "stripe" in slugs


@pytest.mark.asyncio
async def test_search_by_name():
    """Test search by service name."""
    result = await search_services("Stripe")
    assert result["error"] is None
    assert len(result["data"]["results"]) > 0


@pytest.mark.asyncio
async def test_search_by_category():
    """Test search by category."""
    result = await search_services("email")
    assert result["error"] is None
    # Should return email services
    results = result["data"]["results"]
    assert len(results) > 0


@pytest.mark.asyncio
async def test_search_empty_query():
    """Test search with empty query returns error."""
    result = await search_services("")
    assert result["error"] is not None


@pytest.mark.asyncio
async def test_search_limit():
    """Test search limit parameter works."""
    result = await search_services("api", limit=5)
    assert len(result["data"]["results"]) <= 5


@pytest.mark.asyncio
async def test_search_results_have_scores():
    """Test search results include score data."""
    result = await search_services("stripe")
    assert len(result["data"]["results"]) > 0
    
    item = result["data"]["results"][0]
    assert "an_score" in item
    assert "tier" in item
    assert "confidence" in item


@pytest.mark.asyncio
async def test_search_result_schema():
    """Search result items have the expected schema fields (replaces removed _load_dataset test)."""
    result = await search_services("stripe")
    assert result["error"] is None
    if result["data"]["results"]:
        item = result["data"]["results"][0]
        assert "service_slug" in item
        assert "name" in item
        assert "category" in item


@pytest.mark.asyncio
async def test_get_service_categories():
    """Test category listing works via list_categories (replaces removed _get_service_categories)."""
    result = await list_categories()
    # list_categories returns {"data": {"categories": [...], "total": N}, "error": None}
    assert result["error"] is None
    categories = result["data"]["categories"]
    assert isinstance(categories, list)
    # Each category entry has slug + service_count
    if categories:
        assert all("slug" in c and "service_count" in c for c in categories)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
