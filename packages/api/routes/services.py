"""Service-related routes — queries Supabase for live data."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from routes._supabase import cached_query, supabase_count, supabase_fetch
from services.service_slugs import canonicalize_service_slug

router = APIRouter()
_READ_CACHE_TTL_SECONDS = 60.0


async def _cached_fetch(table: str, path: str, ttl: float = _READ_CACHE_TTL_SECONDS) -> Any | None:
    return await cached_query(table, lambda: supabase_fetch(path), cache_key=path, ttl=ttl)


async def _cached_count(table: str, path: str, ttl: float = _READ_CACHE_TTL_SECONDS) -> int:
    result = await cached_query(
        table,
        lambda: supabase_count(path),
        cache_key=f"count:{path}",
        ttl=ttl,
    )
    return 0 if result is None else int(result)


def _build_in_filter(values: set[str]) -> str:
    """Build a PostgREST `in.(...)` filter from a set of string identifiers."""
    return ",".join(f'"{value}"' for value in sorted(values))


def _not_found_response(
    raw_request: Request,
    *,
    error: str,
    message: str,
    resolution: str,
) -> JSONResponse:
    """Return a standardized route-level 404 envelope."""
    request_id = getattr(raw_request.state, "request_id", None) or "unknown"
    return JSONResponse(
        status_code=404,
        content={
            "error": error,
            "message": message,
            "resolution": resolution,
            "request_id": request_id,
        },
    )


@router.get("/services")
async def list_services(
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    category: str | None = Query(default=None),
) -> dict:
    """List indexed services with optional category filter.

    Only returns services that have at least one score.
    Scoreless/ghost services are excluded to prevent 404 cascades
    when users click through from search or API results.
    """
    effective_limit = min(limit, 500)

    # Fetch the set of slugs that actually have scores.
    scored_rows = await _cached_fetch("scores", "scores?select=service_slug")
    if scored_rows is None:
        return {
            "data": {"items": [], "total": 0, "limit": effective_limit, "offset": offset},
            "error": "Unable to load services.",
        }

    scored_slugs = {
        str(row["service_slug"])
        for row in scored_rows
        if row.get("service_slug")
    }
    if not scored_slugs:
        return {
            "data": {"items": [], "total": 0, "limit": effective_limit, "offset": offset},
            "error": None,
        }

    path = (
        "services?select=slug,name,category,description"
        f"&slug=in.({_build_in_filter(scored_slugs)})"
        "&order=name.asc"
    )
    if category:
        path += f"&category=eq.{quote(category)}"

    total = await _cached_count("services", path)
    paginated_path = f"{path}&limit={effective_limit}&offset={offset}"
    data = await _cached_fetch("services", paginated_path)
    if data is None:
        return {
            "data": {"items": [], "total": 0, "limit": effective_limit, "offset": offset},
            "error": "Unable to load services.",
        }

    items = data

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
            "total": total,
            "limit": effective_limit,
            "offset": offset,
        },
        "error": None,
    }


@router.get("/services/{slug}")
async def get_service(slug: str, raw_request: Request):
    """Fetch a service profile by slug, including latest score."""
    canonical_slug = canonicalize_service_slug(slug)

    # Get service info
    services = await _cached_fetch(
        "services",
        f"services?slug=eq.{quote(canonical_slug)}&select=slug,name,category,description&limit=1"
    )
    if not services:
        return _not_found_response(
            raw_request,
            error="service_not_found",
            message=f"No service found with slug '{slug}'",
            resolution="Check available services at GET /v1/services or /v1/search?q=...",
        )

    service = services[0]

    # Get latest score
    scores = await _cached_fetch(
        "scores",
        f"scores?service_slug=eq.{quote(canonical_slug)}&order=calculated_at.desc&limit=1"
    )
    score: dict[str, Any] = {}
    if scores:
        sc = scores[0]
        score = {
            "an_score": sc.get("aggregate_recommendation_score"),
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
        # First get same-category services
        alt_services = await _cached_fetch(
            "services",
            f"services?category=eq.{quote(service['category'])}"
            f"&slug=neq.{quote(canonical_slug)}&select=slug,name"
        )
        if alt_services:
            alt_slugs = {s["slug"] for s in alt_services}
            alt_names = {s["slug"]: s["name"] for s in alt_services}
            # Build an IN filter for scores query — fetch only same-category scores
            slug_filter = ",".join(quote(s) for s in sorted(alt_slugs))
            alt_scores = await _cached_fetch(
                "scores",
                f"scores?service_slug=in.({slug_filter})"
                f"&order=aggregate_recommendation_score.desc.nullslast&limit=5"
            )
            if alt_scores:
                for asc in alt_scores:
                    alternatives.append({
                        "slug": asc["service_slug"],
                        "name": alt_names.get(asc["service_slug"], asc["service_slug"]),
                        "an_score": asc.get("aggregate_recommendation_score"),
                        "score": asc.get("aggregate_recommendation_score"),
                        "tier": asc.get("tier"),
                    })

    return {
        "data": {
            **service,
            **score,
            "alternatives": alternatives,
        },
        "error": None,
    }


@router.get("/services/{slug}/score", response_model=None)
async def get_service_score(slug: str, raw_request: Request):
    """Get the latest AN score for a service (Supabase REST)."""
    canonical_slug = canonicalize_service_slug(slug)
    service_rows = await _cached_fetch(
        "services",
        f"services?slug=eq.{quote(canonical_slug)}"
        f"&select=slug,official_docs&limit=1"
    )
    if not service_rows:
        from routes import scores as score_routes

        try:
            return await score_routes.get_score(canonical_slug)
        except HTTPException:
            return _not_found_response(
                raw_request,
                error="service_not_found",
                message=f"No service found with slug '{slug}'",
                resolution="Check available services at GET /v1/services or /v1/search?q=...",
            )
    service = service_rows[0]

    scores = await _cached_fetch(
        "scores",
        f"scores?service_slug=eq.{quote(canonical_slug)}&order=calculated_at.desc&limit=1"
    )
    if not scores:
        return {
            "service_slug": canonical_slug,
            "an_score": None,
            "score": None,
            "execution_score": None,
            "access_readiness_score": None,
            "confidence": 0,
            "tier": "unknown",
            "tier_label": "Unknown",
            "explanation": f"No score found for '{slug}'",
            "an_score_version": "0.3",
            "dimension_snapshot": {},
            "calculated_at": None,
            "base_url": None,
            "docs_url": service.get("official_docs"),
            "openapi_url": None,
            "mcp_server_url": None,
        }

    sc = scores[0]
    probe_metadata = sc.get("probe_metadata") or {}

    # Synthesize explanation from available rationale fields
    parts: list[str] = []
    agg = sc.get("aggregate_recommendation_score")
    exec_s = sc.get("execution_score")
    access_s = sc.get("access_readiness_score")
    if agg is not None:
        parts.append(f"Scores {agg:.1f}/10 overall")
    if exec_s is not None and access_s is not None:
        parts.append(f"with execution at {exec_s:.1f} and access readiness at {access_s:.1f}")
    # Add rationale snippets
    for field, label in [
        ("payment_autonomy_rationale", "Payment"),
        ("governance_readiness_rationale", "Governance"),
        ("web_accessibility_rationale", "Web accessibility"),
    ]:
        val = sc.get(field)
        if val:
            # Take first sentence only
            first_sentence = val.split(". ")[0].rstrip(".")
            parts.append(f"{label}: {first_sentence}")
    explanation = ". ".join(parts) + "." if parts else ""

    # Fetch active failure modes
    failures = await _cached_fetch(
        "failure_modes",
        f"failure_modes?service_slug=eq.{quote(canonical_slug)}"
        f"&resolved_at=is.null"
        f"&order=severity.asc"
        f"&select=title,description,severity,frequency,agent_impact,workaround"
    )
    failure_modes = []
    if failures:
        failure_modes = [
            {
                "pattern": f.get("title", ""),
                "impact": f.get("agent_impact", f.get("description", "")),
                "frequency": f.get("frequency", "unknown"),
                "workaround": f.get("workaround", ""),
            }
            for f in failures
        ]

    return {
        "service_slug": sc.get("service_slug", slug),
        "an_score": sc.get("aggregate_recommendation_score"),
        "score": sc.get("aggregate_recommendation_score"),
        "execution_score": sc.get("execution_score"),
        "access_readiness_score": sc.get("access_readiness_score"),
        "autonomy_score": sc.get("autonomy_score"),
        "an_score_version": "0.3",
        "confidence": sc.get("confidence", 0),
        "tier": sc.get("tier", "unknown"),
        "tier_label": sc.get("tier_label", "Unknown"),
        "explanation": explanation,
        "dimension_snapshot": {
            "probe_freshness": probe_metadata.get("freshness"),
        },
        "calculated_at": sc.get("calculated_at"),
        "payment_autonomy": sc.get("payment_autonomy"),
        "governance_readiness": sc.get("governance_readiness"),
        "web_accessibility": sc.get("web_accessibility"),
        "failure_modes": failure_modes,
        "base_url": None,
        "docs_url": service.get("official_docs"),
        "openapi_url": None,
        "mcp_server_url": None,
    }


@router.get("/services/{slug}/failures")
async def get_failures(slug: str) -> dict:
    """Fetch active failure modes for a service."""
    canonical_slug = canonicalize_service_slug(slug)
    failures = await _cached_fetch(
        "failure_modes",
        f"failure_modes?service_slug=eq.{quote(canonical_slug)}"
        f"&resolved_at=is.null"
        f"&order=severity.asc,frequency.asc"
        f"&select=id,category,title,description,severity,frequency,agent_impact,workaround,first_detected,last_verified,evidence_count"
    )
    if failures is None:
        return {"data": {"slug": canonical_slug, "failures": []}, "error": "Unable to load failure modes."}

    return {
        "data": {
            "slug": canonical_slug,
            "failure_modes": [
                {
                    "pattern": f.get("title", ""),
                    "impact": f.get("agent_impact", f.get("description", "")),
                    "frequency": f.get("frequency", "unknown"),
                    "workaround": f.get("workaround", ""),
                    "category": f.get("category", ""),
                    "severity": f.get("severity", ""),
                    "description": f.get("description", ""),
                    "last_verified": f.get("last_verified"),
                    "evidence_count": f.get("evidence_count", 0),
                }
                for f in failures
            ],
        },
        "error": None,
    }


@router.get("/services/{slug}/history")
async def get_history(slug: str, limit: int = Query(default=20, ge=1, le=100)) -> dict:
    """Fetch historical AN score entries for a service."""
    canonical_slug = canonicalize_service_slug(slug)
    scores = await _cached_fetch(
        "scores",
        f"scores?service_slug=eq.{quote(canonical_slug)}"
        f"&order=calculated_at.desc&limit={limit}"
        f"&select=aggregate_recommendation_score,execution_score,access_readiness_score,"
        f"confidence,tier,tier_label,calculated_at"
    )
    if scores is None:
        return {"data": {"slug": canonical_slug, "history": []}, "error": "Unable to load history."}

    return {
        "data": {
            "slug": canonical_slug,
            "history": [
                {
                    "an_score": sc.get("aggregate_recommendation_score"),
                    "execution_score": sc.get("execution_score"),
                    "access_readiness_score": sc.get("access_readiness_score"),
                    "confidence": sc.get("confidence"),
                    "tier": sc.get("tier"),
                    "tier_label": sc.get("tier_label"),
                    "calculated_at": sc.get("calculated_at"),
                }
                for sc in scores
            ],
        },
        "error": None,
    }


@router.get("/services/{slug}/schema")
async def get_schema(slug: str) -> dict:
    """Fetch the latest schema snapshot for a service."""
    canonical_slug = canonicalize_service_slug(slug)
    return {"data": {"slug": canonical_slug, "schema": None}, "error": None}


@router.post("/services/{slug}/report")
async def report_failure(slug: str) -> dict:
    """Submit a failure report for a service."""
    canonical_slug = canonicalize_service_slug(slug)
    return {"data": {"slug": canonical_slug, "accepted": True}, "error": None}
