"""Search route implementation."""

import json
from pathlib import Path
from typing import Optional
import difflib
from fastapi import APIRouter, Query

router = APIRouter()

# Load scored dataset at module load time
DATASET_SCORES_PATH = Path(__file__).parent.parent.parent / "web" / "public" / "data" / "initial-dataset.yaml"
SCORES_PATH = Path(__file__).parent.parent / "artifacts" / "dataset-scores.json"

_cached_services = None
_cached_scores = None


def _load_dataset() -> list[dict]:
    """Load service dataset from YAML."""
    global _cached_services
    if _cached_services is not None:
        return _cached_services

    try:
        import yaml
        if not DATASET_SCORES_PATH.exists():
            return []

        with open(DATASET_SCORES_PATH, "r") as f:
            data = yaml.safe_load(f)

        _cached_services = data.get("services", [])
        return _cached_services
    except Exception:
        return []


def _load_scores() -> dict:
    """Load scored dataset."""
    global _cached_scores
    if _cached_scores is not None:
        return _cached_scores

    try:
        if not SCORES_PATH.exists():
            return {"metadata": {}, "scores": []}

        with open(SCORES_PATH, "r") as f:
            _cached_scores = json.load(f)
        return _cached_scores
    except Exception:
        return {"metadata": {}, "scores": []}


@router.get("/search")
async def search_services(
    q: str,
    limit: Optional[int] = Query(default=10, ge=1, le=50)
) -> dict:
    """
    Search services by free-text query (slug, name, category, description).

    Parameters:
    - q: search query string
    - limit: max results (1-50, default 10)

    Returns matching services ranked by score match.
    """
    query_lower = q.lower().strip()

    if not query_lower:
        return {
            "data": {
                "query": q,
                "limit": limit,
                "results": []
            },
            "error": "Query cannot be empty"
        }

    dataset = _load_dataset()
    scores_data = _load_scores()

    # Index scores by slug
    scores_by_slug = {}
    for score_item in scores_data.get("scores", []):
        slug = score_item.get("service_slug")
        if slug:
            scores_by_slug[slug] = score_item

    # Search across dataset
    matches = []
    for service in dataset:
        slug = service.get("slug", "")
        name = service.get("name", "")
        category = service.get("category", "")
        description = service.get("description", "")

        # Match criteria
        slug_match = query_lower in slug.lower()
        name_match = query_lower in name.lower()
        category_match = query_lower in category.lower()
        description_match = query_lower in description.lower()

        if not any([slug_match, name_match, category_match, description_match]):
            continue

        # Similarity score for ranking
        similarity = difflib.SequenceMatcher(
            None,
            query_lower,
            f"{slug} {name} {category}".lower()
        ).ratio()

        # Get score data
        score_item = scores_by_slug.get(slug, {})

        matches.append({
            "service_slug": slug,
            "name": name,
            "category": category,
            "description": description,
            "aggregate_recommendation_score": score_item.get("aggregate_recommendation_score"),
            "execution_score": score_item.get("execution_score"),
            "access_readiness_score": score_item.get("access_readiness_score"),
            "tier": score_item.get("tier"),
            "tier_label": score_item.get("tier_label"),
            "confidence": score_item.get("confidence"),
            "freshness": score_item.get("probe_metadata", {}).get("freshness"),
            "_similarity": similarity
        })

    # Sort by: exact name match, similarity, then score
    matches.sort(
        key=lambda x: (
            x["name"].lower() != query_lower,  # Exact match first
            -x["_similarity"],  # Then by similarity
            -(x.get("aggregate_recommendation_score") or 0),  # Then by score
        )
    )

    # Remove similarity score from output
    for match in matches:
        match.pop("_similarity", None)

    # Apply limit
    results = matches[:limit]

    return {
        "data": {
            "query": q,
            "limit": limit,
            "results": results
        },
        "error": None
    }
