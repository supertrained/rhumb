"""Service-related routes — queries Supabase for live data."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from routes._supabase import cached_query, supabase_count, supabase_fetch
from services.service_slugs import public_service_slug, public_service_slug_candidates

router = APIRouter()
_READ_CACHE_TTL_SECONDS = 60.0

_AUTONOMY_DIMENSION_FIELDS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "P1",
        "payment_autonomy",
        "payment_autonomy_rationale",
        "payment_autonomy_confidence",
        "payment_autonomy",
    ),
    (
        "G1",
        "governance_readiness",
        "governance_readiness_rationale",
        "governance_readiness_confidence",
        "governance_readiness",
    ),
    (
        "W1",
        "web_accessibility",
        "web_accessibility_rationale",
        "web_accessibility_confidence",
        "web_accessibility",
    ),
)


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


def _score_query_slugs(service_slugs: list[str]) -> list[str]:
    query_slugs: list[str] = []
    for service_slug in service_slugs:
        for candidate in public_service_slug_candidates(service_slug):
            if candidate not in query_slugs:
                query_slugs.append(candidate)
    return query_slugs


def _canonicalize_service_rows(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not rows:
        return []

    canonical_rows: dict[str, dict[str, Any]] = {}
    for row in rows:
        raw_slug = str(row.get("slug") or "").strip()
        slug = public_service_slug(raw_slug) or raw_slug
        if not slug:
            continue

        canonical_rows.setdefault(
            slug,
            {
                **row,
                "slug": slug,
            },
        )

    return list(canonical_rows.values())


def _coerce_float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _autonomy_section(score_row: dict[str, Any]) -> dict[str, Any] | None:
    dimension_snapshot = score_row.get("dimension_snapshot")
    if isinstance(dimension_snapshot, dict):
        candidate = dimension_snapshot.get("autonomy")
        if isinstance(candidate, dict):
            return candidate

    dimensions: list[dict[str, Any]] = []
    confidence_values: list[float] = []

    for code, value_field, rationale_field, confidence_field, name in _AUTONOMY_DIMENSION_FIELDS:
        score = _coerce_float(score_row.get(value_field))
        if score is None:
            continue

        confidence = _coerce_float(score_row.get(confidence_field))
        if confidence is not None:
            confidence_values.append(confidence)

        dimensions.append(
            {
                "code": code,
                "name": name,
                "score": round(score, 1),
                "rationale": score_row.get(rationale_field) or "",
                "confidence": None if confidence is None else round(confidence, 2),
            }
        )

    if not dimensions:
        return None

    autonomy_score = _coerce_float(score_row.get("autonomy_score"))
    if autonomy_score is None:
        autonomy_score = round(sum(item["score"] for item in dimensions) / len(dimensions), 1)

    confidence = None
    if confidence_values:
        confidence = round(sum(confidence_values) / len(confidence_values), 2)

    return {
        "avg": round(autonomy_score, 1),
        "confidence": confidence,
        "dimensions": dimensions,
    }


def _score_dimension_snapshot(score_row: dict[str, Any]) -> dict[str, Any]:
    snapshot = score_row.get("dimension_snapshot")
    if not isinstance(snapshot, dict):
        snapshot = {}
    else:
        snapshot = dict(snapshot)

    probe_metadata = score_row.get("probe_metadata")
    if isinstance(probe_metadata, dict):
        freshness = probe_metadata.get("freshness")
        if freshness is not None:
            snapshot["probe_freshness"] = freshness

    autonomy = _autonomy_section(score_row)
    if autonomy is not None:
        snapshot["autonomy"] = autonomy
        snapshot.setdefault(
            "autonomy_dimensions",
            {
                item["code"]: item["score"]
                for item in autonomy.get("dimensions", [])
                if item.get("code") is not None
            },
        )

    return snapshot


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
        public_service_slug(str(row["service_slug"])) or str(row["service_slug"])
        for row in scored_rows
        if row.get("service_slug")
    }
    if not scored_slugs:
        return {
            "data": {"items": [], "total": 0, "limit": effective_limit, "offset": offset},
            "error": None,
        }

    query_slugs = set(_score_query_slugs(sorted(scored_slugs)))
    path = (
        "services?select=slug,name,category,description"
        f"&slug=in.({_build_in_filter(query_slugs)})"
    )
    if category:
        path += f"&category=eq.{quote(category)}"

    data = await _cached_fetch("services", path)
    if data is None:
        return {
            "data": {"items": [], "total": 0, "limit": effective_limit, "offset": offset},
            "error": "Unable to load services.",
        }

    items = _canonicalize_service_rows(data)
    items.sort(key=lambda item: str(item.get("name") or item.get("slug") or "").lower())
    paginated_items = items[offset : offset + effective_limit]

    return {
        "data": {
            "items": [
                {
                    "slug": s.get("slug"),
                    "name": s.get("name"),
                    "category": s.get("category"),
                    "description": s.get("description"),
                }
                for s in paginated_items
            ],
            "total": len(items),
            "limit": effective_limit,
            "offset": offset,
        },
        "error": None,
    }


@router.get("/services/{slug}")
async def get_service(slug: str, raw_request: Request):
    """Fetch a service profile by slug, including latest score."""
    canonical_slug = public_service_slug(slug) or slug

    # Get service info
    services = _canonicalize_service_rows(
        await _cached_fetch(
            "services",
            f"services?slug=in.({_build_in_filter(set(public_service_slug_candidates(slug)))})"
            "&select=slug,name,category,description"
        )
    )
    service = next((row for row in services if row.get("slug") == canonical_slug), None)
    if service is None:
        return _not_found_response(
            raw_request,
            error="service_not_found",
            message=f"No service found with slug '{slug}'",
            resolution="Check available services at GET /v1/services or /v1/search?q=...",
        )

    # Get latest score
    score_query_slugs = _score_query_slugs([canonical_slug])
    scores = await _cached_fetch(
        "scores",
        f"scores?service_slug=in.({_build_in_filter(set(score_query_slugs))})"
        "&order=calculated_at.desc&limit=1"
    )
    score: dict[str, Any] = {}
    if scores:
        sc = scores[0]
        dimension_snapshot = _score_dimension_snapshot(sc)
        autonomy = dimension_snapshot.get("autonomy") if isinstance(dimension_snapshot, dict) else None
        autonomy_score = _coerce_float(sc.get("autonomy_score"))
        if autonomy_score is None and isinstance(autonomy, dict):
            autonomy_score = _coerce_float(autonomy.get("avg"))

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
            "autonomy_score": autonomy_score,
            "autonomy": autonomy,
            "an_score_version": "0.3",
            "dimension_snapshot": dimension_snapshot,
        }

    # Get alternatives (same category, different slug, ranked by score)
    alternatives: list[dict] = []
    if service.get("category"):
        # First get same-category services
        alt_services = _canonicalize_service_rows(
            await _cached_fetch(
                "services",
                f"services?category=eq.{quote(service['category'])}&select=slug,name"
            )
        )
        if alt_services:
            alt_names = {
                str(s.get("slug") or ""): str(s.get("name") or s.get("slug") or "")
                for s in alt_services
                if s.get("slug") and s.get("slug") != canonical_slug
            }
            alt_slugs = set(alt_names)
            if alt_slugs:
                alt_score_query_slugs = _score_query_slugs(sorted(alt_slugs))
                alt_scores = await _cached_fetch(
                    "scores",
                    f"scores?service_slug=in.({_build_in_filter(set(alt_score_query_slugs))})"
                    "&order=aggregate_recommendation_score.desc.nullslast"
                    f"&limit={max(5, len(alt_score_query_slugs))}"
                )
            else:
                alt_scores = []
            if alt_scores:
                seen_alternatives: set[str] = set()
                for asc in alt_scores:
                    raw_alt_slug = str(asc.get("service_slug") or "").strip()
                    alt_slug = public_service_slug(raw_alt_slug) or raw_alt_slug
                    if not alt_slug or alt_slug in seen_alternatives or alt_slug not in alt_names:
                        continue
                    seen_alternatives.add(alt_slug)
                    alternatives.append({
                        "slug": alt_slug,
                        "name": alt_names.get(alt_slug, alt_slug),
                        "an_score": asc.get("aggregate_recommendation_score"),
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


@router.get("/services/{slug}/score", response_model=None)
async def get_service_score(slug: str, raw_request: Request):
    """Get the latest AN score for a service (Supabase REST)."""
    canonical_slug = public_service_slug(slug) or slug
    service_rows = _canonicalize_service_rows(
        await _cached_fetch(
            "services",
            f"services?slug=in.({_build_in_filter(set(public_service_slug_candidates(slug)))})"
            "&select=slug,official_docs"
        )
    )
    service = next((row for row in service_rows if row.get("slug") == canonical_slug), None)
    if service is None:
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

    score_query_slugs = _score_query_slugs([canonical_slug])
    scores = await _cached_fetch(
        "scores",
        f"scores?service_slug=in.({_build_in_filter(set(score_query_slugs))})"
        "&order=calculated_at.desc&limit=1"
    )
    if not scores:
        return {
            "service_slug": canonical_slug,
            "an_score": None,
            "score": None,
            "execution_score": None,
            "access_readiness_score": None,
            "autonomy_score": None,
            "autonomy": None,
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
    dimension_snapshot = _score_dimension_snapshot(sc)
    autonomy = dimension_snapshot.get("autonomy") if isinstance(dimension_snapshot, dict) else None
    autonomy_score = _coerce_float(sc.get("autonomy_score"))
    if autonomy_score is None and isinstance(autonomy, dict):
        autonomy_score = _coerce_float(autonomy.get("avg"))

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
    failure_query_slugs = _score_query_slugs([canonical_slug])
    failures = await _cached_fetch(
        "failure_modes",
        f"failure_modes?service_slug=in.({_build_in_filter(set(failure_query_slugs))})"
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
        "service_slug": public_service_slug(sc.get("service_slug")) or canonical_slug,
        "an_score": sc.get("aggregate_recommendation_score"),
        "score": sc.get("aggregate_recommendation_score"),
        "execution_score": sc.get("execution_score"),
        "access_readiness_score": sc.get("access_readiness_score"),
        "autonomy_score": autonomy_score,
        "autonomy": autonomy,
        "an_score_version": "0.3",
        "confidence": sc.get("confidence", 0),
        "tier": sc.get("tier", "unknown"),
        "tier_label": sc.get("tier_label", "Unknown"),
        "explanation": explanation,
        "dimension_snapshot": dimension_snapshot,
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
    canonical_slug = public_service_slug(slug) or slug
    failure_query_slugs = _score_query_slugs([canonical_slug])
    failures = await _cached_fetch(
        "failure_modes",
        f"failure_modes?service_slug=in.({_build_in_filter(set(failure_query_slugs))})"
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
    canonical_slug = public_service_slug(slug) or slug
    score_query_slugs = _score_query_slugs([canonical_slug])
    scores = await _cached_fetch(
        "scores",
        f"scores?service_slug=in.({_build_in_filter(set(score_query_slugs))})"
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
    canonical_slug = public_service_slug(slug) or slug
    return {"data": {"slug": canonical_slug, "schema": None}, "error": None}


@router.post("/services/{slug}/report")
async def report_failure(slug: str) -> dict:
    """Submit a failure report for a service."""
    canonical_slug = public_service_slug(slug) or slug
    return {"data": {"slug": canonical_slug, "accepted": True}, "error": None}
