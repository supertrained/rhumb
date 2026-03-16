"""Capability registry routes — maps agent capabilities to services.

Agents think in capabilities ("send an email"), not services ("call SendGrid").
This module provides discovery, resolution, and bundle endpoints.
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Query

from routes._supabase import supabase_fetch

router = APIRouter()


@router.get("/capabilities")
async def list_capabilities(
    domain: str | None = Query(default=None, description="Filter by domain (e.g. 'email', 'payment')"),
    search: str | None = Query(default=None, description="Search capabilities by text"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """List capabilities with optional domain filter and text search.

    Returns capabilities enriched with provider count and top provider info.
    """
    # Build PostgREST query
    path = "capabilities?select=id,domain,action,description,input_hint,outcome&order=domain.asc,action.asc"
    if domain:
        path += f"&domain=eq.{quote(domain)}"
    if search:
        encoded = quote(f"*{search}*")
        path += (
            f"&or=(id.ilike.{encoded},"
            f"description.ilike.{encoded},"
            f"domain.ilike.{encoded},"
            f"action.ilike.{encoded})"
        )

    capabilities = await supabase_fetch(path)
    if capabilities is None:
        return {"data": {"items": [], "total": 0, "limit": limit, "offset": offset}, "error": "Unable to load capabilities."}

    total = len(capabilities)
    page = capabilities[offset : offset + limit]

    if not page:
        return {"data": {"items": [], "total": total, "limit": limit, "offset": offset}, "error": None}

    # Get provider counts and top providers for this page
    cap_ids = [c["id"] for c in page]
    cap_filter = ",".join(f'"{cid}"' for cid in cap_ids)

    mappings = await supabase_fetch(
        f"capability_services?capability_id=in.({cap_filter})"
        f"&select=capability_id,service_slug"
    )

    # Get scores for provider ranking
    if mappings:
        service_slugs = list({m["service_slug"] for m in mappings})
        slug_filter = ",".join(f'"{s}"' for s in service_slugs)
        scores = await supabase_fetch(
            f"scores?service_slug=in.({slug_filter})"
            f"&select=service_slug,aggregate_recommendation_score,tier_label"
            f"&order=aggregate_recommendation_score.desc.nullslast"
        )
    else:
        scores = []

    # Index scores by slug (best per slug)
    scores_by_slug: dict[str, dict] = {}
    if scores:
        for sc in scores:
            slug = sc.get("service_slug")
            if slug and slug not in scores_by_slug:
                scores_by_slug[slug] = sc

    # Build provider stats per capability
    providers_by_cap: dict[str, list[str]] = {}
    if mappings:
        for m in mappings:
            cid = m["capability_id"]
            providers_by_cap.setdefault(cid, []).append(m["service_slug"])

    items = []
    for cap in page:
        cid = cap["id"]
        provider_slugs = providers_by_cap.get(cid, [])
        provider_count = len(provider_slugs)

        # Find top provider by AN score
        top_provider = None
        if provider_slugs:
            best_slug = None
            best_score = -1.0
            for slug in provider_slugs:
                sc = scores_by_slug.get(slug, {})
                agg = sc.get("aggregate_recommendation_score")
                if agg is not None and agg > best_score:
                    best_score = agg
                    best_slug = slug
            if best_slug:
                sc = scores_by_slug.get(best_slug, {})
                top_provider = {
                    "slug": best_slug,
                    "an_score": sc.get("aggregate_recommendation_score"),
                    "tier_label": sc.get("tier_label"),
                }

        items.append({
            "id": cid,
            "domain": cap.get("domain"),
            "action": cap.get("action"),
            "description": cap.get("description"),
            "input_hint": cap.get("input_hint"),
            "outcome": cap.get("outcome"),
            "provider_count": provider_count,
            "top_provider": top_provider,
        })

    return {
        "data": {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        },
        "error": None,
    }


@router.get("/capabilities/domains")
async def list_domains() -> dict:
    """List all capability domains with counts.

    Useful for building domain navigation / filtering UIs.
    """
    capabilities = await supabase_fetch(
        "capabilities?select=domain&order=domain.asc"
    )
    if capabilities is None:
        return {"data": {"domains": []}, "error": "Unable to load domains."}

    # Count capabilities per domain
    domain_counts: dict[str, int] = {}
    for cap in capabilities:
        d = cap.get("domain", "unknown")
        domain_counts[d] = domain_counts.get(d, 0) + 1

    domains = [
        {"domain": d, "capability_count": c}
        for d, c in sorted(domain_counts.items())
    ]

    return {"data": {"domains": domains}, "error": None}


@router.get("/capabilities/bundles")
async def list_bundles(
    search: str | None = Query(default=None, description="Search bundles by text"),
) -> dict:
    """List capability bundles (compound capabilities).

    Bundles represent pre-packaged capability chains that deliver more
    value together than individually (e.g., enrich + verify + validate).
    """
    path = (
        "capability_bundles?select=id,name,description,example,value_proposition"
        "&order=name.asc"
    )
    if search:
        encoded = quote(f"*{search}*")
        path += (
            f"&or=(id.ilike.{encoded},"
            f"name.ilike.{encoded},"
            f"description.ilike.{encoded})"
        )

    bundles = await supabase_fetch(path)
    if bundles is None:
        return {"data": {"bundles": []}, "error": "Unable to load bundles."}

    if not bundles:
        return {"data": {"bundles": []}, "error": None}

    # Get bundle-capability mappings
    bundle_ids = [b["id"] for b in bundles]
    bid_filter = ",".join(f'"{bid}"' for bid in bundle_ids)
    mappings = await supabase_fetch(
        f"bundle_capabilities?bundle_id=in.({bid_filter})"
        f"&select=bundle_id,capability_id,sequence_order"
        f"&order=sequence_order.asc"
    )

    caps_by_bundle: dict[str, list[str]] = {}
    if mappings:
        for m in mappings:
            bid = m["bundle_id"]
            caps_by_bundle.setdefault(bid, []).append(m["capability_id"])

    items = []
    for bundle in bundles:
        bid = bundle["id"]
        items.append({
            "id": bid,
            "name": bundle.get("name"),
            "description": bundle.get("description"),
            "example": bundle.get("example"),
            "value_proposition": bundle.get("value_proposition"),
            "capabilities": caps_by_bundle.get(bid, []),
        })

    return {"data": {"bundles": items}, "error": None}


@router.get("/capabilities/{capability_id}")
async def get_capability(capability_id: str) -> dict:
    """Get a single capability with full provider details."""
    caps = await supabase_fetch(
        f"capabilities?id=eq.{quote(capability_id)}"
        f"&select=id,domain,action,description,input_hint,outcome&limit=1"
    )
    if not caps:
        return {"data": None, "error": f"Capability '{capability_id}' not found."}

    cap = caps[0]

    # Get all service mappings for this capability
    mappings = await supabase_fetch(
        f"capability_services?capability_id=eq.{quote(capability_id)}"
        f"&select=service_slug,credential_modes,auth_method,endpoint_pattern,"
        f"cost_per_call,cost_currency,free_tier_calls,notes,is_primary"
    )

    providers = []
    if mappings:
        # Get scores + service names for all mapped services
        slugs = [m["service_slug"] for m in mappings]
        slug_filter = ",".join(f'"{s}"' for s in slugs)

        scores = await supabase_fetch(
            f"scores?service_slug=in.({slug_filter})"
            f"&select=service_slug,aggregate_recommendation_score,tier,tier_label"
            f"&order=aggregate_recommendation_score.desc.nullslast"
        )
        services = await supabase_fetch(
            f"services?slug=in.({slug_filter})&select=slug,name,category"
        )

        scores_by_slug: dict[str, dict] = {}
        if scores:
            for sc in scores:
                slug = sc.get("service_slug")
                if slug and slug not in scores_by_slug:
                    scores_by_slug[slug] = sc

        names_by_slug: dict[str, str] = {}
        cats_by_slug: dict[str, str] = {}
        if services:
            for svc in services:
                names_by_slug[svc["slug"]] = svc.get("name", svc["slug"])
                cats_by_slug[svc["slug"]] = svc.get("category", "")

        for m in mappings:
            slug = m["service_slug"]
            sc = scores_by_slug.get(slug, {})
            providers.append({
                "service_slug": slug,
                "service_name": names_by_slug.get(slug, slug),
                "category": cats_by_slug.get(slug, ""),
                "an_score": sc.get("aggregate_recommendation_score"),
                "tier": sc.get("tier"),
                "tier_label": sc.get("tier_label"),
                "auth_method": m.get("auth_method"),
                "endpoint_pattern": m.get("endpoint_pattern"),
                "credential_modes": m.get("credential_modes", ["byo"]),
                "cost_per_call": float(m["cost_per_call"]) if m.get("cost_per_call") is not None else None,
                "cost_currency": m.get("cost_currency", "USD"),
                "free_tier_calls": m.get("free_tier_calls"),
                "notes": m.get("notes"),
                "is_primary": m.get("is_primary", True),
            })

        # Sort providers by AN score descending (nulls last)
        providers.sort(key=lambda p: -(p.get("an_score") or 0))

    return {
        "data": {
            **cap,
            "providers": providers,
            "provider_count": len(providers),
        },
        "error": None,
    }


@router.get("/capabilities/{capability_id}/resolve")
async def resolve_capability(
    capability_id: str,
    credential_mode: str | None = Query(default=None, description="Filter by credential mode (byo, rhumb_managed, agent_vault)"),
) -> dict:
    """Resolve a capability to ranked providers with health-aware recommendations.

    This is the core agent-facing endpoint: "I need email.send — what should I use?"
    Returns providers ranked by AN score with cost, health, and recommendation data.
    """
    # Verify capability exists
    caps = await supabase_fetch(
        f"capabilities?id=eq.{quote(capability_id)}"
        f"&select=id,domain,action,description&limit=1"
    )
    if not caps:
        return {"data": None, "error": f"Capability '{capability_id}' not found."}

    # Get service mappings
    mapping_path = (
        f"capability_services?capability_id=eq.{quote(capability_id)}"
        f"&select=service_slug,credential_modes,auth_method,endpoint_pattern,"
        f"cost_per_call,cost_currency,free_tier_calls,notes"
    )
    if credential_mode:
        # Filter by credential mode using array contains
        mapping_path += f"&credential_modes=cs.{{{quote(credential_mode)}}}"

    mappings = await supabase_fetch(mapping_path)
    if not mappings:
        return {
            "data": {
                "capability": capability_id,
                "providers": [],
                "fallback_chain": [],
            },
            "error": None,
        }

    # Get scores for all mapped services
    slugs = [m["service_slug"] for m in mappings]
    slug_filter = ",".join(f'"{s}"' for s in slugs)

    scores = await supabase_fetch(
        f"scores?service_slug=in.({slug_filter})"
        f"&select=service_slug,aggregate_recommendation_score,execution_score,"
        f"access_readiness_score,tier,tier_label,confidence"
        f"&order=aggregate_recommendation_score.desc.nullslast"
    )

    services = await supabase_fetch(
        f"services?slug=in.({slug_filter})&select=slug,name"
    )

    scores_by_slug: dict[str, dict] = {}
    if scores:
        for sc in scores:
            slug = sc.get("service_slug")
            if slug and slug not in scores_by_slug:
                scores_by_slug[slug] = sc

    names_by_slug: dict[str, str] = {}
    if services:
        for svc in services:
            names_by_slug[svc["slug"]] = svc.get("name", svc["slug"])

    # Build ranked provider list with recommendations
    providers = []
    for m in mappings:
        slug = m["service_slug"]
        sc = scores_by_slug.get(slug, {})
        an_score = sc.get("aggregate_recommendation_score")
        tier = sc.get("tier")

        # Determine recommendation
        recommendation = "available"
        reason = ""
        if an_score is not None and an_score >= 7.5:
            recommendation = "preferred"
            reason = f"High AN score ({an_score:.1f})"
        elif an_score is not None and an_score >= 6.0:
            recommendation = "available"
            reason = f"Solid AN score ({an_score:.1f})"
        elif an_score is not None:
            recommendation = "caution"
            reason = f"Lower AN score ({an_score:.1f}) — check failure modes"
        else:
            recommendation = "unscored"
            reason = "No AN score available yet"

        # Enhance reason with cost info
        cost = m.get("cost_per_call")
        free_tier = m.get("free_tier_calls")
        if free_tier and cost is None:
            reason += f", {free_tier:,} free calls/month"
        elif cost is not None:
            reason += f", ${cost}/call"
            if free_tier:
                reason += f" ({free_tier:,} free)"

        providers.append({
            "service_slug": slug,
            "service_name": names_by_slug.get(slug, slug),
            "an_score": an_score,
            "execution_score": sc.get("execution_score"),
            "access_readiness_score": sc.get("access_readiness_score"),
            "tier": tier,
            "tier_label": sc.get("tier_label"),
            "confidence": sc.get("confidence"),
            "cost_per_call": float(cost) if cost is not None else None,
            "cost_currency": m.get("cost_currency", "USD"),
            "free_tier_calls": free_tier,
            "credential_modes": m.get("credential_modes", ["byo"]),
            "auth_method": m.get("auth_method"),
            "endpoint_pattern": m.get("endpoint_pattern"),
            "recommendation": recommendation,
            "recommendation_reason": reason,
        })

    # Sort: preferred first, then by AN score descending
    rank_order = {"preferred": 0, "available": 1, "caution": 2, "unscored": 3}
    providers.sort(key=lambda p: (
        rank_order.get(p["recommendation"], 4),
        -(p.get("an_score") or 0),
    ))

    # Build fallback chain (top 3 preferred/available providers)
    fallback_chain = [
        p["service_slug"]
        for p in providers
        if p["recommendation"] in ("preferred", "available")
    ][:3]

    # Check for relevant bundles
    bundle_rows = await supabase_fetch(
        f"bundle_capabilities?capability_id=eq.{quote(capability_id)}"
        f"&select=bundle_id"
    )
    bundle_ids = list({r["bundle_id"] for r in bundle_rows}) if bundle_rows else []

    return {
        "data": {
            "capability": capability_id,
            "providers": providers,
            "fallback_chain": fallback_chain,
            "related_bundles": bundle_ids,
        },
        "error": None,
    }
