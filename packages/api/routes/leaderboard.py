"""Leaderboard route implementation."""

import json
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Query

router = APIRouter()

# Load scored dataset at module load time
DATASET_SCORES_PATH = Path(__file__).parent.parent.parent / "web" / "public" / "data" / "initial-dataset.yaml"
SCORES_PATH = Path(__file__).parent.parent / "artifacts" / "dataset-scores.json"

_cached_scores = None


def _load_scores() -> dict:
    """Load cached scores from artifact."""
    global _cached_scores
    if _cached_scores is not None:
        return _cached_scores

    if not SCORES_PATH.exists():
        return {"metadata": {}, "scores": []}

    with open(SCORES_PATH, "r") as f:
        _cached_scores = json.load(f)

    return _cached_scores


def _get_service_categories() -> dict[str, list[str]]:
    """Load service categories from dataset YAML."""
    try:
        import yaml
        if not DATASET_SCORES_PATH.exists():
            return {}

        with open(DATASET_SCORES_PATH, "r") as f:
            dataset = yaml.safe_load(f)

        categories = {}
        for service in dataset.get("services", []):
            slug = service.get("slug")
            category = service.get("category")
            if slug and category:
                if category not in categories:
                    categories[category] = []
                categories[category].append(slug)

        return categories
    except Exception:
        return {}


@router.get("/leaderboard/{category}")
async def get_leaderboard(
    category: str,
    limit: Optional[int] = Query(default=10, ge=1, le=50)
) -> dict:
    """
    Fetch ranked services by category.

    Parameters:
    - category: service category (e.g., 'email', 'api-management')
    - limit: max results (1-50, default 10)

    Returns leaderboard items ranked by aggregate AN Score.
    """
    scores_data = _load_scores()
    categories = _get_service_categories()

    if category not in categories:
        return {
            "data": {
                "category": category,
                "items": []
            },
            "error": f"Category not found. Available: {', '.join(sorted(categories.keys()))}"
        }

    # Get all services in this category
    category_slugs = set(categories[category])

    # Build leaderboard from scores
    items = []
    for score_item in scores_data.get("scores", []):
        if score_item.get("service_slug") not in category_slugs:
            continue

        items.append({
            "service_slug": score_item.get("service_slug"),
            "score": score_item.get("aggregate_recommendation_score"),
            "execution_score": score_item.get("execution_score"),
            "access_score": score_item.get("access_readiness_score"),
            "tier": score_item.get("tier"),
            "tier_label": score_item.get("tier_label"),
            "confidence": score_item.get("confidence"),
            "freshness": score_item.get("probe_metadata", {}).get("freshness"),
            "calculated_at": score_item.get("calculated_at")
        })

    # Sort by aggregate score descending
    items.sort(
        key=lambda x: (x.get("score") or -999, x.get("service_slug")),
        reverse=True
    )

    # Apply limit
    items = items[:limit]

    return {
        "data": {
            "category": category,
            "items": items,
            "count": len(items)
        },
        "error": None
    }


@router.get("/leaderboard")
async def list_categories() -> dict:
    """List all available leaderboard categories."""
    categories = _get_service_categories()
    return {
        "data": {
            "categories": sorted(categories.keys()),
            "total": len(categories)
        },
        "error": None
    }
