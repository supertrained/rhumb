"""Leaderboard route implementation — queries Supabase for live data."""

from __future__ import annotations

from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Query

from routes._supabase import supabase_fetch

router = APIRouter()


@router.get("/leaderboard/{category}")
async def get_leaderboard(
    category: str,
    limit: Optional[int] = Query(default=10, ge=1, le=50),
) -> dict:
    """Fetch ranked services by category.

    Parameters:
    - category: service category slug (e.g., 'payments', 'auth')
    - limit: max results (1-50, default 10)

    Returns leaderboard items ranked by aggregate AN Score.
    """
    # Get services in this category
    services = await supabase_fetch(
        f"services?category=eq.{quote(category)}&select=slug,name"
    )

    if not services:
        # Check if category exists at all
        all_services = await supabase_fetch("services?select=category")
        if all_services:
            categories = sorted(set(s["category"] for s in all_services))
            return {
                "data": {"category": category, "items": []},
                "error": f"Category not found. Available: {', '.join(categories)}",
            }
        return {
            "data": {"category": category, "items": []},
            "error": "Unable to load categories.",
        }

    slugs = [s["slug"] for s in services]
    name_map = {s["slug"]: s["name"] for s in services}
    slug_filter = ",".join(f'"{s}"' for s in slugs)

    # Get scores for all services in category
    scores = await supabase_fetch(
        f"scores?service_slug=in.({slug_filter})"
        f"&order=aggregate_recommendation_score.desc.nullslast"
        f"&limit={limit * 2}"  # fetch extra to handle dedup
    )

    if scores is None:
        return {
            "data": {"category": category, "items": []},
            "error": "Unable to load scores.",
        }

    # Deduplicate: keep highest-scored entry per service_slug
    seen: set[str] = set()
    items: list[dict] = []
    for sc in scores:
        slug = sc.get("service_slug")
        if slug in seen:
            continue
        seen.add(slug)

        freshness = None
        probe_metadata = sc.get("probe_metadata")
        if isinstance(probe_metadata, dict):
            freshness = probe_metadata.get("freshness")

        items.append({
            "service_slug": slug,
            "name": name_map.get(slug, slug),
            "score": sc.get("aggregate_recommendation_score"),
            "execution_score": sc.get("execution_score"),
            "access_score": sc.get("access_readiness_score"),
            "tier": sc.get("tier"),
            "tier_label": sc.get("tier_label"),
            "confidence": sc.get("confidence"),
            "freshness": freshness,
            "calculated_at": sc.get("calculated_at"),
            "payment_autonomy": sc.get("payment_autonomy"),
            "governance_readiness": sc.get("governance_readiness"),
            "web_accessibility": sc.get("web_accessibility"),
        })

    # Apply limit (already partially limited by query)
    items = items[:limit]

    return {
        "data": {
            "category": category,
            "items": items,
            "count": len(items),
        },
        "error": None,
    }


@router.get("/leaderboard")
async def list_categories() -> dict:
    """List all available leaderboard categories with scored service counts.

    Only counts services that have at least one score.
    Categories with zero scored services are excluded.
    """
    # Count by category using scored services only
    scores_data = await supabase_fetch("scores?select=service_slug")
    if scores_data is None:
        return {"data": {"categories": [], "total": 0}, "error": "Unable to load categories."}

    scored_slugs = {str(row["service_slug"]) for row in scores_data if row.get("service_slug")}
    if not scored_slugs:
        return {"data": {"categories": [], "total": 0}, "error": None}

    data = await supabase_fetch("services?select=slug,category")
    if data is None:
        return {"data": {"categories": [], "total": 0}, "error": "Unable to load categories."}

    counts: dict[str, int] = {}
    for row in data:
        cat = row.get("category")
        slug = row.get("slug")
        if cat and slug in scored_slugs:
            counts[cat] = counts.get(cat, 0) + 1

    # Exclude categories with zero scored services
    categories = [
        {"slug": slug, "service_count": count}
        for slug, count in sorted(counts.items())
        if count > 0
    ]

    return {
        "data": {
            "categories": categories,
            "total": len(categories),
        },
        "error": None,
    }
