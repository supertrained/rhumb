"""Search route implementation — queries Supabase for live data."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Query

from routes._supabase import supabase_fetch

router = APIRouter()


@router.get("/search")
async def search_services(
    q: str,
    limit: int = Query(default=10, ge=1, le=50),
) -> dict:
    """Search services by free-text query (slug, name, category, description).

    Parameters:
    - q: search query string
    - limit: max results (1-50, default 10)

    Returns matching services ranked by relevance then score.
    """
    query_lower = q.strip()

    if not query_lower:
        return {
            "data": {"query": q, "limit": limit, "results": []},
            "error": "Query cannot be empty",
        }

    # Use Supabase PostgREST ilike filter for text search
    encoded = quote(f"*{query_lower}*")
    path = (
        f"services?or=(slug.ilike.{encoded},"
        f"name.ilike.{encoded},"
        f"category.ilike.{encoded},"
        f"description.ilike.{encoded})"
        f"&select=slug,name,category,description"
        f"&order=name.asc"
    )

    services = await supabase_fetch(path)
    if services is None:
        return {
            "data": {"query": q, "limit": limit, "results": []},
            "error": "Search unavailable.",
        }

    if not services:
        return {
            "data": {"query": q, "limit": limit, "results": []},
            "error": None,
        }

    # Get scores for matching services
    slugs = [s["slug"] for s in services]
    slug_filter = ",".join(f'"{s}"' for s in slugs)

    scores_data = await supabase_fetch(
        f"scores?service_slug=in.({slug_filter})"
        f"&order=aggregate_recommendation_score.desc.nullslast"
    )

    # Index scores by slug (keep best per slug)
    scores_by_slug: dict[str, dict] = {}
    if scores_data:
        for sc in scores_data:
            slug = sc.get("service_slug")
            if slug and slug not in scores_by_slug:
                scores_by_slug[slug] = sc

    # Build results with scores
    results = []
    for svc in services:
        slug = svc["slug"]
        sc = scores_by_slug.get(slug, {})

        freshness = None
        probe_metadata = sc.get("probe_metadata")
        if isinstance(probe_metadata, dict):
            freshness = probe_metadata.get("freshness")

        results.append({
            "service_slug": slug,
            "name": svc.get("name"),
            "category": svc.get("category"),
            "description": svc.get("description"),
            "aggregate_recommendation_score": sc.get("aggregate_recommendation_score"),
            "execution_score": sc.get("execution_score"),
            "access_readiness_score": sc.get("access_readiness_score"),
            "tier": sc.get("tier"),
            "tier_label": sc.get("tier_label"),
            "confidence": sc.get("confidence"),
            "freshness": freshness,
        })

    # Sort: exact name match first, then by score descending
    ql = query_lower.lower()
    results.sort(
        key=lambda x: (
            (x.get("name") or "").lower() != ql,  # exact match first
            -(x.get("aggregate_recommendation_score") or 0),  # then by score
        )
    )

    # Apply limit
    results = results[:limit]

    return {
        "data": {
            "query": q,
            "limit": limit,
            "results": results,
        },
        "error": None,
    }
