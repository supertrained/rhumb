"""Leaderboard route implementation."""

import json
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Query

from services.schema_change_detector import get_schema_change_detector

router = APIRouter()

# Load scored dataset at module load time
DATASET_SCORES_PATH = Path(__file__).parent.parent.parent / "web" / "public" / "data" / "initial-dataset.yaml"
SCORES_PATH = Path(__file__).parent.parent / "artifacts" / "dataset-scores.json"

_cached_scores: dict[str, Any] | None = None


def _schema_freshness_multiplier(service_slug: str) -> tuple[float, float | None]:
    """Return confidence multiplier based on schema stability window."""
    detector = get_schema_change_detector()
    stability_days = detector.get_service_stability_days(service_slug)
    if stability_days is None:
        return 1.0, None
    if stability_days >= 30:
        return 1.05, stability_days
    if stability_days >= 14:
        return 1.02, stability_days
    return 1.0, stability_days


def _load_scores() -> dict[str, Any]:
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
        import yaml  # type: ignore[import-untyped]

        if not DATASET_SCORES_PATH.exists():
            return {}

        with open(DATASET_SCORES_PATH, "r") as f:
            dataset: dict[str, Any] = yaml.safe_load(f) or {}

        categories: dict[str, list[str]] = {}
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

        multiplier, stability_days = _schema_freshness_multiplier(
            str(score_item.get("service_slug"))
        )
        confidence = score_item.get("confidence")
        if isinstance(confidence, (int, float)):
            confidence = round(min(1.0, float(confidence) * multiplier), 4)

        items.append({
            "service_slug": score_item.get("service_slug"),
            "score": score_item.get("aggregate_recommendation_score"),
            "execution_score": score_item.get("execution_score"),
            "access_score": score_item.get("access_readiness_score"),
            "tier": score_item.get("tier"),
            "tier_label": score_item.get("tier_label"),
            "confidence": confidence,
            "freshness": score_item.get("probe_metadata", {}).get("freshness"),
            "schema_stability_days": round(stability_days, 3) if stability_days else None,
            "freshness_multiplier": multiplier,
            "calculated_at": score_item.get("calculated_at"),
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
