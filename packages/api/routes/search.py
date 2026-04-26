"""Search route implementation — queries Supabase for live data."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Query

from routes._supabase import cached_query, supabase_fetch
from services.error_envelope import RhumbError
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
    preserve_human_shorthand = raw_stored_slug == canonical.lower()

    canonicalized = str(text)
    for candidate in sorted(public_service_slug_candidates(canonical), key=len, reverse=True):
        cleaned = str(candidate or "").strip()
        if not cleaned or cleaned.lower() == canonical.lower():
            continue

        pattern = re.compile(
            rf"(?<![a-z0-9-]){re.escape(cleaned)}(?![a-z0-9-])",
            re.IGNORECASE,
        )

        def _replace(match: re.Match[str]) -> str:
            matched = match.group(0)
            if preserve_human_shorthand and cleaned.isalpha() and matched == cleaned.upper():
                return matched
            return canonical

        canonicalized = pattern.sub(_replace, canonicalized)

    return _canonicalize_known_service_aliases(
        canonicalized,
        preserve_canonical=canonical if preserve_human_shorthand else None,
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


def _validated_search_query(query: str) -> str:
    normalized = query.strip()
    if normalized:
        return normalized

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'q' filter.",
        detail="Provide a non-empty search query.",
    )


def _validated_search_limit(limit: int) -> int:
    if 1 <= limit <= 50:
        return limit

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'limit' filter.",
        detail="Use a limit between 1 and 50.",
    )


@router.get("/search")
async def search_services(
    q: str,
    limit: int = Query(default=10),
) -> dict:
    """Search services by free-text query (slug, name, category, description).

    Parameters:
    - q: search query string
    - limit: max results (1-50, default 10)

    Returns matching services ranked by relevance then score.
    """
    # Ensure limit is a plain int. When this function is called directly
    # in tests (not via HTTP), FastAPI's Query FieldInfo object is the default
    # value instead of an integer — extract .default in that case.
    if not isinstance(limit, int):
        limit = getattr(limit, "default", 10)
    limit = _validated_search_limit(limit)
    query_lower = _validated_search_query(q)

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

    services = await _cached_fetch("services", path)
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

    # Normalize matching services onto canonical/public slugs before joining scores.
    normalized_services = _canonicalize_service_rows(services)

    # Get scores for matching services
    slugs = [s["slug"] for s in normalized_services]
    score_query_slugs = _score_query_slugs(slugs)
    slug_filter = ",".join(f'"{s}"' for s in score_query_slugs)

    scores_data = await _cached_fetch(
        "scores",
        f"scores?service_slug=in.({slug_filter})"
        f"&order=aggregate_recommendation_score.desc.nullslast"
    )

    # Index scores by slug (keep best per canonical/public slug)
    scores_by_slug: dict[str, dict] = {}
    if scores_data:
        for sc in scores_data:
            raw_slug = str(sc.get("service_slug") or "").strip()
            slug = public_service_slug(raw_slug) or raw_slug
            if slug and slug not in scores_by_slug:
                scores_by_slug[slug] = sc

    # Build results with scores
    results = []
    for svc in normalized_services:
        slug = svc["slug"]
        sc = scores_by_slug.get(slug, {})
        an_score = sc.get("aggregate_recommendation_score")

        freshness = None
        probe_metadata = sc.get("probe_metadata")
        if isinstance(probe_metadata, dict):
            freshness = probe_metadata.get("freshness")

        results.append({
            "service_slug": slug,
            "name": svc.get("name"),
            "category": svc.get("category"),
            "description": svc.get("description"),
            "an_score": an_score,
            "execution_score": sc.get("execution_score"),
            "access_readiness_score": sc.get("access_readiness_score"),
            "tier": sc.get("tier"),
            "tier_label": sc.get("tier_label"),
            "confidence": sc.get("confidence"),
            "freshness": freshness,
        })

    # Exclude scoreless ghost services (no score = no front-end page = 404)
    results = [r for r in results if r.get("an_score") is not None]

    # Sort: exact name match first, then by score descending
    ql = query_lower.lower()
    results.sort(
        key=lambda x: (
            (x.get("name") or "").lower() != ql,  # exact match first
            -(x.get("an_score") or 0),  # then by score
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
