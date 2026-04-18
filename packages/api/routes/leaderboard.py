"""Leaderboard route implementation — queries Supabase for live data."""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, Query

from routes._supabase import cached_query, supabase_fetch
from services.service_slugs import (
    CANONICAL_TO_PROXY,
    public_service_slug,
    public_service_slug_candidates,
)

router = APIRouter()
_READ_CACHE_TTL_SECONDS = 60.0


async def _cached_fetch(table: str, path: str, ttl: float = _READ_CACHE_TTL_SECONDS):
    return await cached_query(table, lambda: supabase_fetch(path), cache_key=path, ttl=ttl)


def _score_query_slugs(service_slugs: list[str]) -> list[str]:
    query_slugs: list[str] = []
    for service_slug in service_slugs:
        for candidate in public_service_slug_candidates(service_slug):
            if candidate not in query_slugs:
                query_slugs.append(candidate)
    return query_slugs



def _canonicalize_known_service_aliases(
    text: Any,
    *,
    preserve_canonical: str | None = None,
) -> str | None:
    if text is None:
        return None

    preserved = str(preserve_canonical or "").strip().lower() or None
    replacements: dict[str, str] = {}
    for canonical in CANONICAL_TO_PROXY:
        if preserved and canonical.lower() == preserved:
            continue
        for candidate in public_service_slug_candidates(canonical):
            cleaned = str(candidate or "").strip()
            if not cleaned or cleaned.lower() == canonical.lower():
                continue
            replacements[cleaned.lower()] = canonical

    if not replacements:
        return str(text)

    pattern = re.compile(
        rf"(?<![a-z0-9-])(?:{'|'.join(re.escape(candidate) for candidate in sorted(replacements, key=len, reverse=True))})(?![a-z0-9-])",
        re.IGNORECASE,
    )
    return pattern.sub(lambda match: replacements[match.group(0).lower()], str(text))



def _canonicalize_service_text(
    text: Any,
    response_service_slug: str | None,
    stored_service_slug: str | None,
) -> str | None:
    if text is None:
        return None

    canonical = public_service_slug(response_service_slug)
    if canonical is None:
        return str(text)

    raw_stored_slug = str(stored_service_slug).strip().lower() if stored_service_slug else None

    canonicalized = str(text)
    if raw_stored_slug != canonical.lower():
        for candidate in sorted(public_service_slug_candidates(canonical), key=len, reverse=True):
            if not candidate or candidate == canonical:
                continue
            canonicalized = re.sub(
                rf"(?<![a-z0-9-]){re.escape(candidate)}(?![a-z0-9-])",
                canonical,
                canonicalized,
                flags=re.IGNORECASE,
            )
    return _canonicalize_known_service_aliases(
        canonicalized,
        preserve_canonical=canonical if raw_stored_slug == canonical.lower() else None,
    )



def _merge_service_row_fields(
    preferred: dict[str, Any], fallback: dict[str, Any]
) -> dict[str, Any]:
    merged = dict(preferred)
    for key, value in fallback.items():
        if key == "slug":
            merged[key] = preferred.get("slug") or value
            continue
        if merged.get(key) in (None, "") and value not in (None, ""):
            merged[key] = value
    return merged



def _canonicalize_service_rows(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not rows:
        return []

    canonical_rows: dict[str, dict[str, Any]] = {}
    canonical_sources: dict[str, str] = {}
    for row in rows:
        raw_slug = str(row.get("slug") or "").strip()
        slug = public_service_slug(raw_slug) or raw_slug
        if not slug:
            continue

        normalized_row = {
            **row,
            "slug": slug,
            "name": _canonicalize_service_text(row.get("name"), slug, raw_slug),
            "description": _canonicalize_service_text(row.get("description"), slug, raw_slug),
        }
        existing = canonical_rows.get(slug)
        if existing is None:
            canonical_rows[slug] = normalized_row
            canonical_sources[slug] = raw_slug.lower()
            continue

        raw_source = raw_slug.lower()
        raw_is_canonical = raw_source == slug.lower()
        existing_is_canonical = canonical_sources.get(slug) == slug.lower()
        if raw_is_canonical and not existing_is_canonical:
            canonical_rows[slug] = _merge_service_row_fields(normalized_row, existing)
            canonical_sources[slug] = raw_source
            continue

        canonical_rows[slug] = _merge_service_row_fields(existing, normalized_row)

    return list(canonical_rows.values())


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
    services = await _cached_fetch(
        "services",
        f"services?category=eq.{quote(category)}&select=slug,name"
    )

    if not services:
        # Check if category exists at all
        all_services = await _cached_fetch("services", "services?select=category")
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

    normalized_services = _canonicalize_service_rows(services)

    slugs = [s["slug"] for s in normalized_services]
    name_map = {s["slug"]: s["name"] for s in normalized_services}
    score_query_slugs = _score_query_slugs(slugs)
    slug_filter = ",".join(f'"{s}"' for s in score_query_slugs)

    # Get scores for all services in category
    scores = await _cached_fetch(
        "scores",
        f"scores?service_slug=in.({slug_filter})"
        f"&order=aggregate_recommendation_score.desc.nullslast"
        f"&limit={limit * 2}"  # fetch extra to handle dedup
    )

    if scores is None:
        return {
            "data": {"category": category, "items": []},
            "error": "Unable to load scores.",
        }

    # Deduplicate: keep highest-scored entry per canonical/public service slug
    seen: set[str] = set()
    items: list[dict] = []
    for sc in scores:
        raw_slug = str(sc.get("service_slug") or "").strip()
        slug = public_service_slug(raw_slug) or raw_slug
        if not slug or slug in seen:
            continue
        seen.add(slug)

        freshness = None
        probe_metadata = sc.get("probe_metadata")
        if isinstance(probe_metadata, dict):
            freshness = probe_metadata.get("freshness")

        items.append({
            "service_slug": slug,
            "name": name_map.get(slug, slug),
            "an_score": sc.get("aggregate_recommendation_score"),
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
    scores_data = await _cached_fetch("scores", "scores?select=service_slug")
    if scores_data is None:
        return {"data": {"categories": [], "total": 0}, "error": "Unable to load categories."}

    scored_slugs = {
        public_service_slug(str(row["service_slug"])) or str(row["service_slug"])
        for row in scores_data
        if row.get("service_slug")
    }
    if not scored_slugs:
        return {"data": {"categories": [], "total": 0}, "error": None}

    data = await _cached_fetch("services", "services?select=slug,category")
    if data is None:
        return {"data": {"categories": [], "total": 0}, "error": "Unable to load categories."}

    counts: dict[str, int] = {}
    seen_category_services: set[tuple[str, str]] = set()
    for row in data:
        cat = row.get("category")
        raw_slug = str(row.get("slug") or "").strip()
        slug = public_service_slug(raw_slug) or raw_slug
        if not cat or not slug or slug not in scored_slugs:
            continue
        key = (str(cat), slug)
        if key in seen_category_services:
            continue
        seen_category_services.add(key)
        counts[str(cat)] = counts.get(str(cat), 0) + 1

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
