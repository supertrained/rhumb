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
