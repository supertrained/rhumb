"""Layer 1 — Raw Provider Access.

Provides direct, named-provider execution with no routing intelligence.
The agent picks the provider; Rhumb handles credentials, billing,
observability, and the execution receipt.

Endpoints:
- ``GET  /v2/providers``                        — list available providers
- ``GET  /v2/providers/{provider_id}``          — provider detail + capabilities
- ``POST /v2/providers/{provider_id}/execute``  — execute on a named provider

Pricing: ``provider_cost + max($0.0002, provider_cost × 0.08)``

This is the escape hatch / trust anchor.  Agents who need exact provider
control bypass Layer 2 routing entirely.  The same receipt chain, error
envelopes, budget enforcement, and policy controls apply.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Optional
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from routes import capability_execute as v1_execute
from routes._supabase import supabase_fetch
from routes.proxy import SERVICE_REGISTRY, normalize_slug
from services.budget_enforcer import BudgetStatus
from services.error_envelope import RhumbError
from services.provider_attribution import build_attribution_sync
from services.route_explanation import build_layer1_explanation, store_explanation
from services.service_slugs import (
    CANONICAL_TO_PROXY,
    canonicalize_service_slug,
    public_service_slug,
    public_service_slug_candidates,
)
from services.receipt_service import (
    ReceiptInput,
    get_receipt_service,
    hash_caller_ip,
    hash_request_payload,
    hash_response_payload,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_LAYER = 1
_COMPAT_VERSION = "2026-03-30"
_COMPAT_MODE = "v1-translate"

# Layer 1 markup: 8% + $0.0002 floor
_LAYER1_MARKUP_RATE = 0.08
_LAYER1_MARKUP_FLOOR = 0.0002

_FORWARD_HEADER_NAMES = [
    "X-Rhumb-Key",
    "X-Agent-Token",
    "X-Payment",
    "PAYMENT-SIGNATURE",
    "Authorization",
    "User-Agent",
]
_RESPONSE_HEADER_NAMES = [
    "X-Request-ID",
    "X-Payment-Response",
    "PAYMENT-RESPONSE",
    "X-Rhumb-Auth",
    "X-Rhumb-Wallet",
    "X-Rhumb-Rate-Remaining",
]

_V2_NAVIGATION_URL_KEYS = {
    "search_url",
    "resolve_url",
    "estimate_url",
    "credential_modes_url",
    "retry_url",
    "execute_url",
}


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class L1ProviderPolicy(BaseModel):
    """Per-call policy subset for Layer 1 (limited vs Layer 2)."""

    model_config = ConfigDict(extra="forbid")

    timeout_ms: int | None = Field(
        default=None,
        ge=1000,
        le=300_000,
        description="Provider-side timeout in milliseconds.",
    )
    max_cost_usd: float | None = Field(
        default=None,
        ge=0,
        description="Hard per-call ceiling enforced before execution.",
    )


class L1ExecuteRequest(BaseModel):
    """Layer 1 execute envelope — agent specifies the exact provider."""

    model_config = ConfigDict(extra="forbid")

    capability: str = Field(
        ...,
        description="Capability ID to execute (e.g. 'search.query').",
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-native parameters.",
    )
    credential_mode: str = Field(
        default="auto",
        description="Credential mode (auto, byok, rhumb_managed, agent_vault).",
    )
    policy: L1ProviderPolicy | None = Field(
        default=None,
        description="Optional per-call policy overrides.",
    )
    idempotency_key: str | None = Field(
        default=None,
        description="Optional per-call idempotency key.",
    )
    interface: str = Field(
        default="rest",
        description="Calling surface label for analytics.",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _provider_slug_candidates(provider_id: str) -> list[str]:
    return public_service_slug_candidates(provider_id)


def _compat_headers() -> dict[str, str]:
    return {
        "X-Rhumb-Version": _COMPAT_VERSION,
        "X-Rhumb-Compat": _COMPAT_MODE,
        "X-Rhumb-Layer": "1",
    }


def _forward_request_headers(raw_request: Request) -> dict[str, str]:
    headers: dict[str, str] = {}
    for name in _FORWARD_HEADER_NAMES:
        value = raw_request.headers.get(name)
        if value:
            headers[name] = value
    return headers


def _merge_response_headers(source: httpx.Response | None = None) -> dict[str, str]:
    headers = _compat_headers()
    if source is None:
        return headers
    for name in _RESPONSE_HEADER_NAMES:
        value = source.headers.get(name)
        if value:
            headers[name] = value
    return headers


async def _forward_internal(
    raw_request: Request,
    *,
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
) -> httpx.Response:
    headers = _forward_request_headers(raw_request)
    if extra_headers:
        headers.update(extra_headers)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=raw_request.app),
        base_url="http://rhumb-internal",
    ) as client:
        return await client.request(
            method,
            path,
            params=params,
            json=json_body,
            headers=headers,
        )


def _parse_endpoint_pattern(endpoint_pattern: str | None) -> tuple[str | None, str | None]:
    if not endpoint_pattern or " " not in endpoint_pattern.strip():
        return None, None
    method, path = endpoint_pattern.strip().split(" ", 1)
    return method.upper(), path.strip()


def _rewrite_v1_capabilities_url(url: str) -> str:
    if not url.startswith("/v1/capabilities"):
        return url
    return f"/v2{url[3:]}"


def _rewrite_endpoint_pattern(endpoint_pattern: str) -> str:
    method, path = _parse_endpoint_pattern(endpoint_pattern)
    if method is None or path is None:
        return endpoint_pattern
    rewritten_path = _rewrite_v1_capabilities_url(path)
    if rewritten_path == path:
        return endpoint_pattern
    return f"{method} {rewritten_path}"


def _rewrite_navigation_urls(payload: Any) -> Any:
    """Rewrite any v1 capability navigation URLs returned through the v2 Layer 1 surface."""
    if isinstance(payload, dict):
        rewritten: dict[str, Any] = {}
        for key, value in payload.items():
            if key in _V2_NAVIGATION_URL_KEYS and isinstance(value, str):
                rewritten[key] = _rewrite_v1_capabilities_url(value)
            elif key == "endpoint_pattern" and isinstance(value, str):
                rewritten[key] = _rewrite_endpoint_pattern(value)
            else:
                rewritten[key] = _rewrite_navigation_urls(value)
        return rewritten
    if isinstance(payload, list):
        return [_rewrite_navigation_urls(item) for item in payload]
    if isinstance(payload, str) and "/v1/capabilities" in payload:
        # Only rewrite the v1 capabilities namespace when it appears inside
        # human-readable error messages (e.g. resolution strings).
        return payload.replace("/v1/capabilities", "/v2/capabilities")
    return payload


def _layer1_cost(provider_cost_usd: float) -> dict[str, float]:
    """Calculate Layer 1 pricing: 8% markup with $0.0002 floor."""
    rhumb_fee = max(_LAYER1_MARKUP_FLOOR, provider_cost_usd * _LAYER1_MARKUP_RATE)
    total = provider_cost_usd + rhumb_fee
    return {
        "provider_cost_usd": round(provider_cost_usd, 6),
        "rhumb_fee_usd": round(rhumb_fee, 6),
        "total_usd": round(total, 6),
        "markup_rate": _LAYER1_MARKUP_RATE,
        "markup_floor_usd": _LAYER1_MARKUP_FLOOR,
    }


def _budget_summary(status: BudgetStatus | None) -> dict[str, Any] | None:
    if status is None or status.budget_usd is None:
        return None
    return {
        "budget_usd": status.budget_usd,
        "spent_usd": status.spent_usd,
        "remaining_usd": status.remaining_usd,
        "period": status.period,
        "hard_limit": status.hard_limit,
        "alert_threshold_pct": status.alert_threshold_pct,
        "alert_fired": status.alert_fired,
    }


def _build_in_filter(values: set[str]) -> str:
    return ",".join(f'"{value}"' for value in sorted(values))


def _public_provider_slug(provider_id: str | None) -> str:
    return public_service_slug(provider_id) or str(provider_id or "").strip().lower()


def _canonicalize_known_provider_aliases(
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


def _canonicalize_provider_text(
    text: Any,
    provider_id: str | None,
    *,
    preserve_human_shorthand: bool = False,
) -> str | None:
    if text is None:
        return None
    rendered = str(text)
    canonical = _public_provider_slug(provider_id)
    if not canonical:
        return rendered

    candidates = {
        str(candidate).strip()
        for candidate in public_service_slug_candidates(canonical)
        if str(candidate or "").strip()
    }
    alias_candidates = {
        candidate for candidate in candidates if candidate.lower() != canonical.lower()
    }
    if not alias_candidates:
        return rendered

    pattern = re.compile(
        rf"(?<![a-z0-9-])(?:{'|'.join(re.escape(candidate) for candidate in sorted(alias_candidates, key=len, reverse=True))})(?![a-z0-9-])",
        re.IGNORECASE,
    )

    def _replace(match: re.Match[str]) -> str:
        matched = match.group(0)
        lowered = matched.lower()
        if preserve_human_shorthand and lowered.isalpha() and matched == lowered.upper():
            return matched
        return canonical

    canonicalized = pattern.sub(_replace, rendered)
    return _canonicalize_known_provider_aliases(
        canonicalized,
        preserve_canonical=canonical if preserve_human_shorthand else None,
    )


def _canonicalize_provider_metadata_text(
    text: Any,
    response_provider_id: str | None,
    stored_provider_id: str | None,
) -> str | None:
    if text is None:
        return None

    canonical = _public_provider_slug(response_provider_id)
    if not canonical:
        return str(text)

    raw_stored_slug = str(stored_provider_id or "").strip().lower()
    return _canonicalize_provider_text(
        text,
        canonical,
        preserve_human_shorthand=raw_stored_slug == canonical.lower(),
    )


def _canonicalize_provider_value(value: Any) -> Any:
    if isinstance(value, str):
        public_slug = _public_provider_slug(value)
        return public_slug or value
    return value


_PROVIDER_VALUE_KEYS = {
    "provider",
    "provider_used",
    "provider_id",
    "provider_slug",
    "selected_provider",
    "requested_provider",
    "fallback_provider",
}


_PROVIDER_LIST_KEYS = {
    "available_providers",
    "candidate_providers",
    "fallback_providers",
    "supported_provider_slugs",
    "unavailable_provider_slugs",
    "not_execute_ready_provider_slugs",
    "policy_candidates",
}


def _collect_provider_contexts(value: Any, provider_ids: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _PROVIDER_VALUE_KEYS and isinstance(item, str) and item.strip():
                provider_ids.add(item.strip())
            elif key in _PROVIDER_LIST_KEYS and isinstance(item, list):
                for entry in item:
                    if isinstance(entry, str) and entry.strip():
                        provider_ids.add(entry.strip())
            _collect_provider_contexts(item, provider_ids)
        return

    if isinstance(value, list):
        for item in value:
            _collect_provider_contexts(item, provider_ids)


def _canonicalize_provider_text_from_contexts(text: Any, provider_ids: set[str]) -> str | None:
    if text is None:
        return None

    canonicalized = str(text)
    for provider_id in sorted(provider_ids, key=len, reverse=True):
        canonicalized = _canonicalize_provider_text(canonicalized, provider_id) or canonicalized
    return canonicalized


def _canonicalize_provider_payload_with_contexts(value: Any, *, provider_ids: set[str]) -> Any:
    if isinstance(value, dict):
        canonicalized: dict[str, Any] = {}
        for key, item in value.items():
            if key in _PROVIDER_VALUE_KEYS:
                canonicalized[key] = _canonicalize_provider_value(item)
            elif key in {"message", "detail", "error_message"}:
                canonicalized[key] = _canonicalize_provider_text_from_contexts(item, provider_ids)
            elif key in _PROVIDER_LIST_KEYS and isinstance(item, list):
                canonicalized[key] = [_canonicalize_provider_value(entry) for entry in item]
            else:
                canonicalized[key] = _canonicalize_provider_payload_with_contexts(item, provider_ids=provider_ids)
        return canonicalized
    if isinstance(value, list):
        return [_canonicalize_provider_payload_with_contexts(item, provider_ids=provider_ids) for item in value]
    return value


def _canonicalize_provider_payload(value: Any, *, provider_id: str | None) -> Any:
    provider_ids: set[str] = set()
    if provider_id:
        provider_ids.add(str(provider_id).strip())
    _collect_provider_contexts(value, provider_ids)
    return _canonicalize_provider_payload_with_contexts(value, provider_ids=provider_ids)


def _runtime_provider_slug(provider_id: str) -> str:
    public_slug = _public_provider_slug(provider_id)
    return normalize_slug(public_slug)


def _all_direct_provider_mappings() -> list[dict[str, Any]]:
    mappings: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for capability_id in sorted(v1_execute.DIRECT_EXECUTE_CAPABILITY_IDS):
        for mapping in v1_execute._direct_capability_service_mappings(capability_id):
            service_slug = str(mapping.get("service_slug") or "").strip()
            capability = str(mapping.get("capability_id") or capability_id).strip()
            if not service_slug or not capability:
                continue
            key = (canonicalize_service_slug(service_slug), capability)
            if key in seen:
                continue
            seen.add(key)
            normalized_mapping = dict(mapping)
            normalized_mapping["capability_id"] = capability
            mappings.append(normalized_mapping)
    return mappings


def _direct_provider_service_mappings(provider_id: str) -> list[dict[str, Any]]:
    return [
        mapping
        for mapping in _all_direct_provider_mappings()
        if v1_execute._service_slug_matches(mapping.get("service_slug"), provider_id)
    ]


async def _catalog_provider_services(provider_id: str) -> list[dict[str, Any]]:
    rows_by_key: set[tuple[str, str]] = set()
    merged_rows: list[dict[str, Any]] = []
    for candidate in _provider_slug_candidates(provider_id):
        rows = await supabase_fetch(
            f"capability_services?service_slug=eq.{quote(candidate)}"
            f"&select=capability_id,service_slug,credential_modes,auth_method,"
            f"endpoint_pattern,cost_per_call,cost_currency,free_tier_calls"
        ) or []
        for row in rows:
            capability = str(row.get("capability_id") or "").strip()
            service_slug = str(row.get("service_slug") or candidate).strip()
            if not capability or not service_slug:
                continue
            key = (capability, canonicalize_service_slug(service_slug))
            if key in rows_by_key:
                continue
            rows_by_key.add(key)
            merged_rows.append(row)
    return merged_rows


async def _resolve_provider_services(provider_id: str) -> list[dict]:
    """Fetch all capability mappings for a given provider slug."""
    direct_rows = _direct_provider_service_mappings(provider_id)
    catalog_rows = await _catalog_provider_services(provider_id)
    if not direct_rows:
        return catalog_rows

    merged_rows: list[dict[str, Any]] = []
    seen_capabilities: set[str] = set()
    for row in [*direct_rows, *catalog_rows]:
        capability = str(row.get("capability_id") or "").strip()
        if not capability or capability in seen_capabilities:
            continue
        seen_capabilities.add(capability)
        merged_rows.append(row)
    return merged_rows


async def _resolve_provider_score(provider_id: str) -> dict | None:
    score_slugs = {
        candidate
        for candidate in _provider_slug_candidates(provider_id)
        if candidate
    }
    if not score_slugs:
        return None

    rows = await supabase_fetch(
        f"scores?service_slug=in.({_build_in_filter(score_slugs)})"
        f"&select=service_slug,aggregate_recommendation_score,tier,tier_label,calculated_at"
        f"&order=calculated_at.desc"
    )
    if not rows:
        return None

    canonical_provider_slug = public_service_slug(provider_id) or str(provider_id).strip().lower()
    for row in rows:
        row_slug = str(row.get("service_slug") or "").strip()
        if row_slug and canonicalize_service_slug(row_slug) == canonical_provider_slug:
            normalized_row = dict(row)
            normalized_row["service_slug"] = canonical_provider_slug
            return normalized_row
    return None


def _merge_provider_detail(
    *,
    provider_id: str,
    service_row: dict[str, Any] | None,
    score_row: dict[str, Any] | None,
    direct_mappings: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    direct_mappings = direct_mappings or []
    direct_primary = direct_mappings[0] if direct_mappings else {}

    canonical_provider_slug = public_service_slug(provider_id) if provider_id else None
    runtime_slug = _runtime_provider_slug(canonical_provider_slug or provider_id)
    has_service_row = bool(service_row and service_row.get("slug"))
    has_direct_mapping = bool(direct_mappings)
    is_runtime_callable = runtime_slug in SERVICE_REGISTRY

    if not has_service_row and not has_direct_mapping and not is_runtime_callable:
        return None

    slug = canonical_provider_slug
    if not slug and service_row and service_row.get("slug"):
        slug = public_service_slug(str(service_row["slug"])) or str(service_row["slug"]).strip().lower()
    elif not slug and direct_primary.get("service_slug"):
        slug = public_service_slug(str(direct_primary["service_slug"])) or str(direct_primary["service_slug"]).strip().lower()

    if not slug:
        return None

    runtime_slug = _runtime_provider_slug(slug)
    runtime_meta = SERVICE_REGISTRY.get(runtime_slug, {})
    direct_name = direct_primary.get("service_name")
    direct_category = direct_primary.get("category")
    direct_tier_label = direct_primary.get("tier_label") or ("Direct" if direct_mappings else None)
    direct_description = None
    if direct_name:
        direct_description = f"Direct {direct_name} capability execution."

    return {
        "slug": slug,
        "runtime_slug": runtime_slug,
        "name": (service_row or {}).get("name") or direct_name or slug,
        "description": (service_row or {}).get("description") or direct_description,
        "category": (service_row or {}).get("category") or direct_category,
        "official_docs": (service_row or {}).get("official_docs"),
        "api_domain": runtime_meta.get("domain"),
        "aggregate_recommendation_score": (score_row or {}).get("aggregate_recommendation_score"),
        "tier": (score_row or {}).get("tier"),
        "tier_label": (score_row or {}).get("tier_label") or direct_tier_label,
        "callable": runtime_slug in SERVICE_REGISTRY or bool(direct_mappings),
    }


def _canonicalize_service_rows(rows: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    """Normalize service rows onto canonical provider ids, preferring canonical rows.

    When both canonical/public and runtime-alias rows exist for the same provider,
    keep the canonical row as the base record but backfill any missing fields from
    the alias row so Layer 1 list responses do not drift based on row order.
    """

    if not rows:
        return {}

    canonical_rows: dict[str, dict[str, Any]] = {}
    for row in rows:
        raw_slug = str(row.get("slug") or "").strip().lower()
        canonical_slug = public_service_slug(raw_slug) or raw_slug
        if not canonical_slug:
            continue

        normalized_row = {
            **row,
            "slug": canonical_slug,
            "name": _canonicalize_provider_metadata_text(
                row.get("name"),
                canonical_slug,
                raw_slug,
            ),
            "description": _canonicalize_provider_metadata_text(
                row.get("description"),
                canonical_slug,
                raw_slug,
            ),
        }

        existing = canonical_rows.get(canonical_slug)
        if existing is None:
            canonical_rows[canonical_slug] = normalized_row
            continue

        existing_raw_slug = str(existing.get("_raw_slug") or canonical_slug).strip().lower()
        candidate_is_canonical = raw_slug == canonical_slug
        existing_is_canonical = existing_raw_slug == canonical_slug

        if candidate_is_canonical and not existing_is_canonical:
            preferred = normalized_row
            fallback = existing
        else:
            preferred = existing
            fallback = normalized_row

        merged = dict(preferred)
        for field in ("name", "description", "category", "official_docs"):
            if not merged.get(field) and fallback.get(field):
                merged[field] = fallback[field]

        merged["_raw_slug"] = canonical_slug if preferred is normalized_row else existing_raw_slug
        canonical_rows[canonical_slug] = merged

    for row in canonical_rows.values():
        row.pop("_raw_slug", None)

    return canonical_rows


async def _resolve_provider_detail(provider_id: str) -> dict | None:
    """Fetch the service detail for a provider slug."""
    service_rows: list[dict[str, Any]] = []
    for candidate in _provider_slug_candidates(provider_id):
        rows = await supabase_fetch(
            f"services?slug=eq.{quote(candidate)}"
            f"&select=slug,name,description,category,official_docs"
            f"&limit=1"
        )
        if rows:
            service_rows.extend(rows)

    canonical_provider_slug = public_service_slug(provider_id) or str(provider_id).strip().lower()
    service_row = _canonicalize_service_rows(service_rows).get(canonical_provider_slug)

    score_row = await _resolve_provider_score(provider_id)
    direct_mappings = _direct_provider_service_mappings(provider_id)
    return _merge_provider_detail(
        provider_id=provider_id,
        service_row=service_row,
        score_row=score_row,
        direct_mappings=direct_mappings,
    )


async def _resolve_agent_for_budget(raw_request: Request):
    """If the request is authenticated via X-Rhumb-Key, return the agent."""
    x_rhumb_key = raw_request.headers.get("X-Rhumb-Key")
    if not x_rhumb_key:
        return None
    agent = await v1_execute._get_identity_store().verify_api_key_with_agent(x_rhumb_key)
    return agent


async def _enforce_agent_budget(
    *,
    agent_id: str,
    estimated_cost: float | None,
) -> BudgetStatus:
    from services.budget_enforcer import BudgetEnforcer

    enforcer = BudgetEnforcer()
    status = await enforcer.get_budget(agent_id)
    if estimated_cost is None or float(estimated_cost) <= 0:
        return status
    if status.budget_usd is None or status.remaining_usd is None:
        return status
    if not status.hard_limit or status.remaining_usd >= float(estimated_cost):
        return status

    raise RhumbError(
        "BUDGET_EXCEEDED",
        message=(
            f"Estimated call cost ${float(estimated_cost):.4f} exceeds remaining "
            f"{status.period or 'agent'} budget ${float(status.remaining_usd):.4f}."
        ),
        detail="Increase the agent budget, wait for the next budget reset, or lower the expected call cost.",
        extra={"budget": _budget_summary(status)},
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/providers")
async def list_providers(
    capability: str | None = Query(default=None, description="Filter by capability ID"),
    category: str | None = Query(default=None, description="Filter by category"),
    status_filter: str | None = Query(
        default=None,
        alias="status",
        description="Filter by status (callable, scored, listed)",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """List available providers with optional filters.

    Layer 1 should expose the runtime-callable provider surface, not the
    full scored catalog. Provider metadata lives in ``services`` while AN
    score/tier lives in ``scores``.
    """
    direct_mappings = _all_direct_provider_mappings()
    direct_mappings_by_provider: dict[str, list[dict[str, Any]]] = {}
    for mapping in direct_mappings:
        service_slug = str(mapping.get("service_slug") or "").strip()
        if not service_slug:
            continue
        canonical_slug = canonicalize_service_slug(service_slug)
        direct_mappings_by_provider.setdefault(canonical_slug, []).append(mapping)

    callable_provider_slugs = {
        canonicalize_service_slug(slug)
        for slug in SERVICE_REGISTRY
    }
    callable_provider_slugs.update(direct_mappings_by_provider.keys())

    provider_slugs = set(callable_provider_slugs)
    if status_filter in {"listed", "scored"}:
        mapping_rows = await supabase_fetch("capability_services?select=service_slug") or []
        provider_slugs.update(
            canonicalize_service_slug(str(row["service_slug"]))
            for row in mapping_rows
            if row.get("service_slug")
        )

    if capability:
        direct_capability_rows = v1_execute._direct_capability_service_mappings(capability)
        if direct_capability_rows:
            capability_slugs = {
                canonicalize_service_slug(str(row["service_slug"]))
                for row in direct_capability_rows
                if row.get("service_slug")
            }
        else:
            capability_rows = await supabase_fetch(
                f"capability_services?capability_id=eq.{quote(capability)}&select=service_slug"
            ) or []
            capability_slugs = {
                canonicalize_service_slug(str(row["service_slug"]))
                for row in capability_rows
                if row.get("service_slug")
            }
        provider_slugs &= capability_slugs

    if not provider_slugs:
        return {
            "error": None,
            "data": {
                "providers": [],
                "total": 0,
                "limit": limit,
                "offset": offset,
                "_rhumb_v2": {
                    "api_version": "v2-alpha",
                    "layer": _LAYER,
                },
            },
        }

    provider_lookup_slugs = {
        candidate
        for provider_slug in provider_slugs
        for candidate in _provider_slug_candidates(provider_slug)
        if candidate
    }
    slug_filter = _build_in_filter(provider_lookup_slugs)
    service_rows = await supabase_fetch(
        f"services?slug=in.({slug_filter})&select=slug,name,description,category,official_docs"
    ) or []
    services_by_slug = _canonicalize_service_rows(service_rows)

    score_rows = await supabase_fetch(
        f"scores?service_slug=in.({slug_filter})"
        f"&select=service_slug,aggregate_recommendation_score,tier,tier_label,calculated_at"
        f"&order=calculated_at.desc"
    ) or []
    scores_by_slug: dict[str, dict[str, Any]] = {}
    for row in score_rows:
        row_slug = str(row.get("service_slug") or "").strip()
        if not row_slug:
            continue
        canonical_slug = canonicalize_service_slug(row_slug)
        if canonical_slug in provider_slugs and canonical_slug not in scores_by_slug:
            normalized_row = dict(row)
            normalized_row["service_slug"] = canonical_slug
            scores_by_slug[canonical_slug] = normalized_row

    providers = []
    for slug in provider_slugs:
        detail = _merge_provider_detail(
            provider_id=slug,
            service_row=services_by_slug.get(slug),
            score_row=scores_by_slug.get(slug),
            direct_mappings=direct_mappings_by_provider.get(slug),
        )
        if detail is None:
            continue
        if category and detail.get("category") != category:
            continue
        if status_filter == "callable" and not detail.get("callable"):
            continue
        if status_filter == "scored" and detail.get("aggregate_recommendation_score") is None:
            continue
        providers.append({
            "id": detail.get("slug", slug),
            "name": detail.get("name", slug),
            "description": detail.get("description"),
            "category": detail.get("category"),
            "an_score": detail.get("aggregate_recommendation_score"),
            "tier": detail.get("tier_label"),
            "callable": bool(detail.get("callable")),
        })

    providers.sort(
        key=lambda provider: (
            -(provider.get("an_score") if provider.get("an_score") is not None else -1.0),
            provider.get("name") or provider.get("id") or "",
        )
    )
    total = len(providers)
    page = providers[offset : offset + limit]

    return {
        "error": None,
        "data": {
            "providers": page,
            "total": total,
            "limit": limit,
            "offset": offset,
            "_rhumb_v2": {
                "api_version": "v2-alpha",
                "layer": _LAYER,
            },
        },
    }


@router.get("/providers/{provider_id}")
async def get_provider(provider_id: str) -> dict[str, Any]:
    """Get provider detail including available capabilities."""
    public_provider_id = _public_provider_slug(provider_id)
    detail = await _resolve_provider_detail(provider_id)
    if detail is None:
        raise RhumbError(
            "PROVIDER_UNAVAILABLE",
            message=f"Provider '{public_provider_id}' not found.",
            detail="Check the provider slug at GET /v2/providers.",
        )

    mappings = await _resolve_provider_services(provider_id)
    capabilities = [
        {
            "capability_id": m.get("capability_id"),
            "credential_modes": m.get("credential_modes"),
            "cost_per_call": m.get("cost_per_call"),
            "cost_currency": m.get("cost_currency"),
            "free_tier_calls": m.get("free_tier_calls"),
        }
        for m in mappings
    ]

    slug = detail.get("slug", public_provider_id)
    is_callable = bool(detail.get("callable"))

    return {
        "error": None,
        "data": {
            "id": slug,
            "name": detail.get("name", slug),
            "description": detail.get("description"),
            "category": detail.get("category"),
            "an_score": detail.get("aggregate_recommendation_score"),
            "tier": detail.get("tier_label"),
            "callable": is_callable,
            "capabilities": capabilities,
            "pricing": {
                "model": "passthrough_plus_markup",
                "markup_rate": _LAYER1_MARKUP_RATE,
                "markup_floor_usd": _LAYER1_MARKUP_FLOOR,
                "description": f"provider_cost + max(${_LAYER1_MARKUP_FLOOR}, provider_cost × {_LAYER1_MARKUP_RATE})",
            },
            "_rhumb_v2": {
                "api_version": "v2-alpha",
                "layer": _LAYER,
            },
        },
    }


@router.post("/providers/{provider_id}/execute")
async def execute_on_provider(
    provider_id: str,
    payload: L1ExecuteRequest,
    raw_request: Request,
    x_rhumb_idempotency_key: str | None = Header(None, alias="X-Rhumb-Idempotency-Key"),
) -> JSONResponse:
    """Execute a capability on a specific named provider (Layer 1).

    No routing intelligence — the agent picks the provider.  Rhumb handles
    credentials, billing, observability, receipts.
    """
    t_start = time.monotonic()

    # ── Validate the provider exists ──────────────────────────────────
    public_provider_id = _public_provider_slug(provider_id)
    detail = await _resolve_provider_detail(provider_id)
    if detail is None:
        raise RhumbError(
            "PROVIDER_UNAVAILABLE",
            message=f"Provider '{public_provider_id}' not found.",
            detail="Check the provider slug at GET /v2/providers.",
        )

    provider_public_slug = detail.get("slug", public_provider_id)
    provider_runtime_slug = detail.get("runtime_slug") or _runtime_provider_slug(provider_public_slug)

    # ── Validate the provider supports the requested capability ──────
    mappings = await _resolve_provider_services(provider_id)
    mapping = next(
        (m for m in mappings if m.get("capability_id") == payload.capability),
        None,
    )
    if mapping is None:
        raise RhumbError(
            "CAPABILITY_NOT_FOUND",
            message=f"Provider '{provider_public_slug}' does not support capability '{payload.capability}'.",
            detail=f"Check supported capabilities at GET /v2/providers/{provider_public_slug}.",
        )

    # ── Cost estimation via v1 compat ────────────────────────────────
    estimate_response = await _forward_internal(
        raw_request,
        method="GET",
        path=f"/v1/capabilities/{payload.capability}/execute/estimate",
        params={
            "credential_mode": payload.credential_mode,
            "provider": provider_runtime_slug,
        },
    )
    estimate_body = _canonicalize_provider_payload(
        estimate_response.json(),
        provider_id=provider_public_slug,
    )
    estimate_body = _rewrite_navigation_urls(estimate_body)
    if estimate_response.status_code != 200:
        return JSONResponse(
            status_code=estimate_response.status_code,
            content=estimate_body,
            headers=_merge_response_headers(estimate_response),
        )

    estimate_data = estimate_body.get("data") or {}
    estimated_provider_cost = float(estimate_data.get("cost_estimate_usd") or 0)
    endpoint_pattern = estimate_data.get("endpoint_pattern")
    method, path = _parse_endpoint_pattern(endpoint_pattern)

    # ── Layer 1 cost calculation ─────────────────────────────────────
    layer1_cost = _layer1_cost(estimated_provider_cost)

    # ── Per-call max_cost policy ─────────────────────────────────────
    if payload.policy and payload.policy.max_cost_usd is not None:
        if layer1_cost["total_usd"] > payload.policy.max_cost_usd:
            raise RhumbError(
                "BUDGET_EXCEEDED",
                message=(
                    f"Estimated total cost ${layer1_cost['total_usd']:.4f} exceeds "
                    f"policy ceiling ${payload.policy.max_cost_usd:.4f}."
                ),
                detail="Raise max_cost_usd or choose a cheaper capability.",
                extra={"cost": layer1_cost},
            )

    # ── Agent budget enforcement ─────────────────────────────────────
    budget_status: BudgetStatus | None = None
    agent = await _resolve_agent_for_budget(raw_request)
    has_inline_x402 = bool(
        raw_request.headers.get("X-Payment")
        or raw_request.headers.get("PAYMENT-SIGNATURE")
    )
    if agent is not None and not has_inline_x402:
        budget_status = await _enforce_agent_budget(
            agent_id=agent.agent_id,
            estimated_cost=layer1_cost["total_usd"],
        )

    # ── Execute via v1 compat layer ──────────────────────────────────
    v1_payload: dict[str, Any] = {
        "provider": provider_runtime_slug,
        "credential_mode": payload.credential_mode,
        "idempotency_key": payload.idempotency_key or x_rhumb_idempotency_key,
        "interface": f"{payload.interface}-v2-l1",
        "body": payload.parameters,
    }
    if method:
        v1_payload["method"] = method
    if path:
        v1_payload["path"] = path

    execute_response = await _forward_internal(
        raw_request,
        method="POST",
        path=f"/v1/capabilities/{payload.capability}/execute",
        json_body=v1_payload,
        extra_headers={"X-Rhumb-Skip-Receipt": "true"},
    )
    body = _canonicalize_provider_payload(
        execute_response.json(),
        provider_id=provider_public_slug,
    )
    body = _rewrite_navigation_urls(body)

    t_total_ms = int((time.monotonic() - t_start) * 1000)

    # ── Receipt creation ─────────────────────────────────────────────
    execution_data = body.get("data") if isinstance(body.get("data"), dict) else {}
    execution_id = execution_data.get("execution_id", "")
    is_success = execute_response.status_code == 200

    receipt_id: str | None = None
    try:
        receipt_input = ReceiptInput(
            execution_id=execution_id or f"v2-l1-{int(time.time())}",
            capability_id=payload.capability,
            status="success" if is_success else "failure",
            agent_id=execution_data.get("agent_id", agent.agent_id if agent else "unknown"),
            provider_id=provider_public_slug,
            credential_mode=payload.credential_mode,
            layer=_LAYER,
            org_id=execution_data.get("org_id", agent.organization_id if agent else None),
            caller_ip_hash=hash_caller_ip(raw_request.client.host if raw_request.client else None),
            provider_name=provider_public_slug,
            router_version=_COMPAT_VERSION,
            candidates_evaluated=1,
            winner_reason="agent_pinned_layer1",
            total_latency_ms=t_total_ms,
            rhumb_overhead_ms=t_total_ms - (execution_data.get("provider_latency_ms") or t_total_ms),
            provider_latency_ms=execution_data.get("provider_latency_ms"),
            provider_cost_usd=layer1_cost["provider_cost_usd"],
            rhumb_fee_usd=layer1_cost["rhumb_fee_usd"],
            total_cost_usd=layer1_cost["total_usd"],
            request_hash=hash_request_payload(payload.parameters),
            response_hash=hash_response_payload(execution_data.get("result")),
            interface=f"{payload.interface}-v2-l1",
            compat_mode=_COMPAT_MODE,
            idempotency_key=payload.idempotency_key or x_rhumb_idempotency_key,
            error_code=body.get("error", {}).get("code") if not is_success else None,
            error_message=body.get("error", {}).get("message") if not is_success else None,
        )
        receipt = await get_receipt_service().create_receipt(receipt_input)
        receipt_id = receipt.receipt_id
        logger.info(
            "l1_receipt_created receipt_id=%s provider=%s capability=%s status=%s",
            receipt_id, provider_public_slug, payload.capability, receipt_input.status,
        )
    except Exception:
        logger.exception("l1_receipt_creation_failed execution_id=%s", execution_id)

    # ── Provider attribution (WU-41.2) ────────────────────────────────
    provider_latency_ms = execution_data.get("provider_latency_ms")
    attribution = build_attribution_sync(
        provider_slug=provider_public_slug,
        provider_name=detail.get("name"),
        provider_category=detail.get("category"),
        provider_docs_url=detail.get("official_docs"),
        an_score=detail.get("aggregate_recommendation_score"),
        tier=detail.get("tier_label"),
        layer=_LAYER,
        receipt_id=receipt_id,
        cost_provider_usd=layer1_cost["provider_cost_usd"],
        cost_rhumb_fee_usd=layer1_cost["rhumb_fee_usd"],
        cost_total_usd=layer1_cost["total_usd"],
        latency_total_ms=float(t_total_ms),
        latency_provider_ms=float(provider_latency_ms) if provider_latency_ms else None,
        latency_overhead_ms=float(t_total_ms - (provider_latency_ms or t_total_ms)),
        credential_mode=payload.credential_mode,
    )

    # ── Route explanation (WU-41.3) — Layer 1 ─────────────────────────
    explanation_id: str | None = None
    try:
        l1_explanation = build_layer1_explanation(
            capability_id=payload.capability,
            provider_id=provider_public_slug,
        )
        explanation_id = l1_explanation.explanation_id
        store_explanation(l1_explanation)
    except Exception:
        logger.exception("l1_explanation_failed provider=%s", provider_public_slug)

    # ── Annotate response with Layer 1 metadata ──────────────────────
    if is_success and execution_data:
        if receipt_id:
            execution_data["receipt_id"] = receipt_id
        execution_data["_rhumb_v2"] = {
            "api_version": "v2-alpha",
            "compat_mode": _COMPAT_MODE,
            "layer": _LAYER,
            "receipt_id": receipt_id,
            "explanation_id": explanation_id,
            "provider": {
                "id": provider_public_slug,
                "display_name": detail.get("name", provider_public_slug),
                "capability_used": payload.capability,
                "an_score": detail.get("aggregate_recommendation_score"),
            },
            "cost": layer1_cost,
            "latency": {
                "total_ms": t_total_ms,
                "provider_ms": provider_latency_ms,
                "rhumb_overhead_ms": t_total_ms - (provider_latency_ms or t_total_ms),
            },
            "budget_applied": bool(budget_status and budget_status.budget_usd is not None),
            "budget_summary": _budget_summary(budget_status),
        }
        # Inject canonical _rhumb provider identity block
        execution_data["_rhumb"] = attribution.to_rhumb_block()

    # ── Billing event emission (WU-41.5) ──────────────────────────────
    try:
        from services.billing_events import BillingEventType, get_billing_event_stream
        _billing_org = agent.organization_id if agent else None
        if _billing_org and is_success:
            get_billing_event_stream().emit(
                BillingEventType.EXECUTION_CHARGED,
                org_id=_billing_org,
                amount_usd_cents=int(float(layer1_cost.get("total_usd", 0) if isinstance(layer1_cost, dict) else 0) * 100),
                receipt_id=receipt_id,
                execution_id=execution_id,
                capability_id=payload.capability,
                provider_slug=provider_public_slug,
                metadata={"layer": 1, "credential_mode": payload.credential_mode or "auto"},
            )
        elif _billing_org and not is_success:
            get_billing_event_stream().emit(
                BillingEventType.EXECUTION_FAILED_NO_CHARGE,
                org_id=_billing_org,
                amount_usd_cents=0,
                execution_id=execution_id,
                capability_id=payload.capability,
                provider_slug=provider_public_slug,
                metadata={"layer": 1, "error": str(body.get("error", ""))[:200]},
            )
    except Exception:
        logger.exception("l1_billing_event_emission_failed execution_id=%s", execution_id)

    merged_headers = _merge_response_headers(execute_response)
    merged_headers.update(attribution.to_response_headers())

    return JSONResponse(
        status_code=execute_response.status_code,
        content=body,
        headers=merged_headers,
    )
