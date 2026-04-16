"""Service slug alias helpers shared across proxy and public read surfaces.

Canonical/public service slugs live in Supabase tables like ``services`` and
``capability_services``. Some execution-layer systems still use shorter proxy
names (for example ``pdl``). These helpers keep public responses and review
surfaces anchored to canonical slugs while still allowing proxy internals to
resolve the short runtime names they need.
"""

from __future__ import annotations

CANONICAL_TO_PROXY: dict[str, str] = {
    "people-data-labs": "pdl",
    "brave-search-api": "brave-search",
}

PROXY_TO_CANONICAL: dict[str, str] = {
    proxy_slug: canonical_slug for canonical_slug, proxy_slug in CANONICAL_TO_PROXY.items()
}


def normalize_proxy_slug(slug: str) -> str:
    """Resolve a canonical/public slug to its proxy-layer equivalent."""
    return CANONICAL_TO_PROXY.get(slug, slug)


def canonicalize_service_slug(slug: str) -> str:
    """Resolve a proxy-layer alias back to its canonical/public slug."""
    return PROXY_TO_CANONICAL.get(slug, slug)


def public_service_slug(slug: str | None) -> str | None:
    """Normalize an optional slug for public/API-facing surfaces."""
    if slug is None:
        return None
    cleaned = str(slug).strip().lower()
    if not cleaned:
        return None
    return canonicalize_service_slug(cleaned)


def public_service_slug_candidates(slug: str | None) -> list[str]:
    """Return public and runtime candidates for alias-backed lookups."""
    raw = str(slug or "").strip().lower() or None
    public = public_service_slug(raw)

    candidates: list[str] = []
    for candidate in (
        public,
        raw,
        normalize_proxy_slug(public) if public else None,
    ):
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    return candidates
