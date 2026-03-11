"""Service-related routes — queries Supabase for live data."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Query

from routes._supabase import supabase_fetch

router = APIRouter()


@router.get("/services")
async def list_services(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    category: str | None = Query(default=None),
) -> dict:
    """List indexed services with optional category filter."""
    path = "services?select=slug,name,category,description&order=name.asc"
    if category:
        path += f"&category=eq.{quote(category)}"

    data = await supabase_fetch(path)
    if data is None:
        return {"data": {"items": [], "limit": limit, "offset": offset}, "error": "Unable to load services."}

    # Apply offset/limit
    items = data[offset : offset + limit]

    return {
        "data": {
            "items": [
                {
                    "slug": s.get("slug"),
                    "name": s.get("name"),
                    "category": s.get("category"),
                    "description": s.get("description"),
                }
                for s in items
            ],
            "total": len(data),
            "limit": limit,
            "offset": offset,
        },
        "error": None,
    }


@router.get("/services/{slug}")
async def get_service(slug: str) -> dict:
    """Fetch a service profile by slug, including latest score."""
    # Get service info
    services = await supabase_fetch(
        f"services?slug=eq.{quote(slug)}&select=slug,name,category,description&limit=1"
    )
    if not services:
        return {"data": None, "error": f"Service '{slug}' not found."}

    service = services[0]

    # Get latest score
    scores = await supabase_fetch(
        f"scores?service_slug=eq.{quote(slug)}&order=calculated_at.desc&limit=1"
    )
    score: dict[str, Any] = {}
    if scores:
        sc = scores[0]
        score = {
            "aggregate_recommendation_score": sc.get("aggregate_recommendation_score"),
            "execution_score": sc.get("execution_score"),
            "access_readiness_score": sc.get("access_readiness_score"),
            "confidence": sc.get("confidence"),
            "tier": sc.get("tier"),
            "tier_label": sc.get("tier_label"),
            "calculated_at": sc.get("calculated_at"),
            "freshness": (sc.get("probe_metadata") or {}).get("freshness"),
            "payment_autonomy": sc.get("payment_autonomy"),
            "governance_readiness": sc.get("governance_readiness"),
            "web_accessibility": sc.get("web_accessibility"),
            "payment_autonomy_rationale": sc.get("payment_autonomy_rationale"),
            "governance_readiness_rationale": sc.get("governance_readiness_rationale"),
            "web_accessibility_rationale": sc.get("web_accessibility_rationale"),
            "autonomy_score": sc.get("autonomy_score"),
        }

    # Get alternatives (same category, different slug, ranked by score)
    alternatives: list[dict] = []
    if service.get("category"):
        alt_scores = await supabase_fetch(
            f"scores?service_slug=neq.{quote(slug)}"
            f"&order=aggregate_recommendation_score.desc.nullslast&limit=5"
        )
        if alt_scores:
            # Filter to same category by cross-referencing services
            alt_services = await supabase_fetch(
                f"services?category=eq.{quote(service['category'])}"
                f"&slug=neq.{quote(slug)}&select=slug,name"
            )
            if alt_services:
                alt_slugs = {s["slug"] for s in alt_services}
                alt_names = {s["slug"]: s["name"] for s in alt_services}
                for asc in alt_scores:
                    if asc.get("service_slug") in alt_slugs:
                        alternatives.append({
                            "slug": asc["service_slug"],
                            "name": alt_names.get(asc["service_slug"], asc["service_slug"]),
                            "score": asc.get("aggregate_recommendation_score"),
                            "tier": asc.get("tier"),
                        })
                        if len(alternatives) >= 5:
                            break

    return {
        "data": {
            **service,
            **score,
            "alternatives": alternatives,
        },
        "error": None,
    }


@router.get("/services/{slug}/failures")
async def get_failures(slug: str) -> dict:
    """Fetch active failure modes for a service."""
    # TODO: Wire to failure_modes table when it exists
    return {"data": {"slug": slug, "failures": []}, "error": None}


@router.get("/services/{slug}/history")
async def get_history(slug: str, limit: int = Query(default=20, ge=1, le=100)) -> dict:
    """Fetch historical AN score entries for a service."""
    scores = await supabase_fetch(
        f"scores?service_slug=eq.{quote(slug)}"
        f"&order=calculated_at.desc&limit={limit}"
        f"&select=aggregate_recommendation_score,execution_score,access_readiness_score,"
        f"confidence,tier,tier_label,calculated_at"
    )
    if scores is None:
        return {"data": {"slug": slug, "history": []}, "error": "Unable to load history."}

    return {
        "data": {
            "slug": slug,
            "history": scores,
        },
        "error": None,
    }


@router.get("/services/{slug}/schema")
async def get_schema(slug: str) -> dict:
    """Fetch the latest schema snapshot for a service."""
    return {"data": {"slug": slug, "schema": None}, "error": None}


@router.post("/services/{slug}/report")
async def report_failure(slug: str) -> dict:
    """Submit a failure report for a service."""
    return {"data": {"slug": slug, "accepted": True}, "error": None}
