"""Provider Attribution Service.

Implements WU-41.2: every execution response includes a canonical `_rhumb`
provider identity block.  The block is structurally identical across all
execution paths (v1, v2 Layer 2, v2 Layer 1) so agents can always extract
the same provider metadata regardless of which layer handled the call.

**Guarantee** (from Resolve Product Spec §2.2):
> At every layer, in every response, the provider that executed the work is
> explicitly identified.  Abstraction does not mean erasure.

Response headers (set by callers after building attribution):
- ``X-Rhumb-Provider``        — canonical provider slug
- ``X-Rhumb-Provider-Region`` — region hint when known
- ``X-Rhumb-Receipt-Id``      — receipt ID for the execution
- ``X-Rhumb-Layer``           — layer that handled the call (1 or 2)
- ``X-Rhumb-Cost-Usd``        — total billed cost

Response body ``_rhumb`` block: provider identity, docs URL, cost, latency,
and layer info.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import quote

from routes._supabase import supabase_fetch
from services.service_slugs import (
    canonicalize_service_slug,
    public_service_slug,
    public_service_slug_candidates,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cache for provider detail lookups (avoid repeated DB queries)
# ---------------------------------------------------------------------------

_provider_cache: dict[str, dict[str, Any] | None] = {}


def _canonical_provider_slug(provider_slug: str) -> str:
    cleaned = str(provider_slug or "unknown").strip().lower()
    return canonicalize_service_slug(cleaned) or "unknown"


async def _fetch_provider_detail(provider_slug: str) -> dict[str, Any] | None:
    """Fetch service row for attribution, with in-memory cache."""
    canonical_slug = _canonical_provider_slug(provider_slug)
    if canonical_slug in _provider_cache:
        return _provider_cache[canonical_slug]

    result: dict[str, Any] | None = None
    for candidate in public_service_slug_candidates(canonical_slug):
        rows = await supabase_fetch(
            f"services?slug=eq.{quote(candidate)}"
            f"&select=slug,name,description,category,api_domain,"
            f"aggregate_recommendation_score,tier_label,official_docs"
            f"&limit=1"
        )
        if rows:
            result = dict(rows[0])
            normalized_slug = public_service_slug(result.get("slug"))
            if normalized_slug:
                result["slug"] = normalized_slug
            break

    # Cache (bounded: evict if > 200 entries)
    if len(_provider_cache) > 200:
        _provider_cache.clear()
    _provider_cache[canonical_slug] = result
    return result


def clear_provider_cache() -> None:
    """Clear the in-memory provider detail cache (for tests)."""
    _provider_cache.clear()


# ---------------------------------------------------------------------------
# Attribution data structure
# ---------------------------------------------------------------------------

@dataclass
class ProviderAttribution:
    """Canonical provider attribution block for any execution response."""

    provider_id: str
    provider_name: str | None = None
    provider_category: str | None = None
    provider_docs_url: str | None = None
    an_score: float | None = None
    tier: str | None = None

    layer: int = 2
    receipt_id: str | None = None

    cost_provider_usd: float | None = None
    cost_rhumb_fee_usd: float | None = None
    cost_total_usd: float | None = None

    latency_total_ms: float | None = None
    latency_provider_ms: float | None = None
    latency_overhead_ms: float | None = None

    credential_mode: str | None = None
    region: str | None = None

    def to_rhumb_block(self) -> dict[str, Any]:
        """Build the canonical ``_rhumb`` response body block."""
        block: dict[str, Any] = {
            "provider": {
                "id": self.provider_id,
                "name": self.provider_name or self.provider_id,
                "category": self.provider_category,
                "docs_url": self.provider_docs_url,
                "an_score": self.an_score,
                "tier": self.tier,
            },
            "layer": self.layer,
            "receipt_id": self.receipt_id,
        }

        # Cost
        if self.cost_total_usd is not None:
            block["cost"] = {
                "provider_usd": self.cost_provider_usd,
                "rhumb_fee_usd": self.cost_rhumb_fee_usd,
                "total_usd": self.cost_total_usd,
            }

        # Latency
        if self.latency_total_ms is not None:
            block["latency"] = {
                "total_ms": self.latency_total_ms,
                "provider_ms": self.latency_provider_ms,
                "overhead_ms": self.latency_overhead_ms,
            }

        # Credential mode
        if self.credential_mode:
            block["credential_mode"] = self.credential_mode

        # Region
        if self.region:
            block["region"] = self.region

        return block

    def to_response_headers(self) -> dict[str, str]:
        """Build attribution response headers per spec §2.2."""
        headers: dict[str, str] = {
            "X-Rhumb-Provider": self.provider_id,
        }
        if self.region:
            headers["X-Rhumb-Provider-Region"] = self.region
        if self.receipt_id:
            headers["X-Rhumb-Receipt-Id"] = self.receipt_id
        headers["X-Rhumb-Layer"] = str(self.layer)
        if self.cost_total_usd is not None:
            headers["X-Rhumb-Cost-Usd"] = f"{self.cost_total_usd:.6f}"
        return headers

    def to_error_context(self) -> dict[str, Any]:
        """Build attribution context for error envelopes."""
        return {
            "provider_id": self.provider_id,
            "provider_name": self.provider_name or self.provider_id,
            "layer": self.layer,
            "receipt_id": self.receipt_id,
        }


# ---------------------------------------------------------------------------
# Builder functions
# ---------------------------------------------------------------------------

async def build_attribution(
    *,
    provider_slug: str,
    layer: int = 2,
    receipt_id: str | None = None,
    cost_provider_usd: float | None = None,
    cost_rhumb_fee_usd: float | None = None,
    cost_total_usd: float | None = None,
    latency_total_ms: float | None = None,
    latency_provider_ms: float | None = None,
    latency_overhead_ms: float | None = None,
    credential_mode: str | None = None,
    region: str | None = None,
) -> ProviderAttribution:
    """Build a full attribution object by fetching provider details."""
    canonical_slug = _canonical_provider_slug(provider_slug)
    detail = await _fetch_provider_detail(canonical_slug)

    return ProviderAttribution(
        provider_id=str(detail.get("slug") or canonical_slug) if detail else canonical_slug,
        provider_name=detail.get("name") if detail else None,
        provider_category=detail.get("category") if detail else None,
        provider_docs_url=detail.get("official_docs") if detail else None,
        an_score=detail.get("aggregate_recommendation_score") if detail else None,
        tier=detail.get("tier_label") if detail else None,
        layer=layer,
        receipt_id=receipt_id,
        cost_provider_usd=cost_provider_usd,
        cost_rhumb_fee_usd=cost_rhumb_fee_usd,
        cost_total_usd=cost_total_usd,
        latency_total_ms=latency_total_ms,
        latency_provider_ms=latency_provider_ms,
        latency_overhead_ms=latency_overhead_ms,
        credential_mode=credential_mode,
        region=region,
    )


def build_attribution_sync(
    *,
    provider_slug: str,
    provider_name: str | None = None,
    provider_category: str | None = None,
    provider_docs_url: str | None = None,
    an_score: float | None = None,
    tier: str | None = None,
    layer: int = 2,
    receipt_id: str | None = None,
    cost_provider_usd: float | None = None,
    cost_rhumb_fee_usd: float | None = None,
    cost_total_usd: float | None = None,
    latency_total_ms: float | None = None,
    latency_provider_ms: float | None = None,
    latency_overhead_ms: float | None = None,
    credential_mode: str | None = None,
    region: str | None = None,
) -> ProviderAttribution:
    """Build an attribution object from pre-fetched data (no DB lookup)."""
    canonical_slug = _canonical_provider_slug(provider_slug)
    return ProviderAttribution(
        provider_id=canonical_slug,
        provider_name=provider_name,
        provider_category=provider_category,
        provider_docs_url=provider_docs_url,
        an_score=an_score,
        tier=tier,
        layer=layer,
        receipt_id=receipt_id,
        cost_provider_usd=cost_provider_usd,
        cost_rhumb_fee_usd=cost_rhumb_fee_usd,
        cost_total_usd=cost_total_usd,
        latency_total_ms=latency_total_ms,
        latency_provider_ms=latency_provider_ms,
        latency_overhead_ms=latency_overhead_ms,
        credential_mode=credential_mode,
        region=region,
    )
