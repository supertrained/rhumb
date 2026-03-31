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
        description="Credential mode (auto, byo, rhumb_managed, agent_vault).",
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
) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=raw_request.app),
        base_url="http://rhumb-internal",
    ) as client:
        return await client.request(
            method,
            path,
            params=params,
            json=json_body,
            headers=_forward_request_headers(raw_request),
        )


def _parse_endpoint_pattern(endpoint_pattern: str | None) -> tuple[str | None, str | None]:
    if not endpoint_pattern or " " not in endpoint_pattern.strip():
        return None, None
    method, path = endpoint_pattern.strip().split(" ", 1)
    return method.upper(), path.strip()


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


async def _resolve_provider_services(provider_id: str) -> list[dict]:
    """Fetch all capability mappings for a given provider slug."""
    normalized = normalize_slug(provider_id)
    rows = await supabase_fetch(
        f"capability_services?service_slug=eq.{quote(normalized)}"
        f"&select=capability_id,service_slug,credential_modes,auth_method,"
        f"endpoint_pattern,cost_per_call,cost_currency,free_tier_calls"
    )
    return rows or []


async def _resolve_provider_detail(provider_id: str) -> dict | None:
    """Fetch the service detail for a provider slug."""
    normalized = normalize_slug(provider_id)
    rows = await supabase_fetch(
        f"services?slug=eq.{quote(normalized)}"
        f"&select=slug,name,description,category,api_domain,"
        f"aggregate_recommendation_score,tier_label"
        f"&limit=1"
    )
    if rows:
        return rows[0]
    return None


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

    Providers with at least one capability_services mapping and an active
    credential are considered 'callable'.
    """
    # Build the base query
    query = "services?select=slug,name,description,category,api_domain,aggregate_recommendation_score,tier_label"

    filters: list[str] = []
    if category:
        filters.append(f"category=eq.{quote(category)}")

    query += f"&order=aggregate_recommendation_score.desc.nullslast"
    query += f"&limit={limit}&offset={offset}"
    for f in filters:
        query += f"&{f}"

    services = await supabase_fetch(query) or []

    # If capability filter, narrow to providers that have that mapping
    if capability:
        mappings = await supabase_fetch(
            f"capability_services?capability_id=eq.{quote(capability)}"
            f"&select=service_slug"
        )
        if mappings:
            valid_slugs = {m["service_slug"] for m in mappings}
            services = [s for s in services if s.get("slug") in valid_slugs]
        else:
            services = []

    providers = []
    for svc in services:
        slug = svc.get("slug", "")
        is_callable = slug in SERVICE_REGISTRY or bool(svc.get("api_domain"))
        providers.append({
            "id": slug,
            "name": svc.get("name", slug),
            "description": svc.get("description"),
            "category": svc.get("category"),
            "an_score": svc.get("aggregate_recommendation_score"),
            "tier": svc.get("tier_label"),
            "callable": is_callable,
        })

    return {
        "error": None,
        "data": {
            "providers": providers,
            "total": len(providers),
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
    detail = await _resolve_provider_detail(provider_id)
    if detail is None:
        raise RhumbError(
            "PROVIDER_UNAVAILABLE",
            message=f"Provider '{provider_id}' not found.",
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

    slug = detail.get("slug", provider_id)
    is_callable = slug in SERVICE_REGISTRY or bool(detail.get("api_domain"))

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
    detail = await _resolve_provider_detail(provider_id)
    if detail is None:
        raise RhumbError(
            "PROVIDER_UNAVAILABLE",
            message=f"Provider '{provider_id}' not found.",
            detail="Check the provider slug at GET /v2/providers.",
        )

    provider_slug = detail.get("slug", provider_id)

    # ── Validate the provider supports the requested capability ──────
    mappings = await _resolve_provider_services(provider_id)
    mapping = next(
        (m for m in mappings if m.get("capability_id") == payload.capability),
        None,
    )
    if mapping is None:
        raise RhumbError(
            "CAPABILITY_NOT_FOUND",
            message=f"Provider '{provider_id}' does not support capability '{payload.capability}'.",
            detail=f"Check supported capabilities at GET /v2/providers/{provider_id}.",
        )

    # ── Cost estimation via v1 compat ────────────────────────────────
    estimate_response = await _forward_internal(
        raw_request,
        method="GET",
        path=f"/v1/capabilities/{payload.capability}/execute/estimate",
        params={
            "credential_mode": payload.credential_mode,
            "provider": provider_slug,
        },
    )
    estimate_body = estimate_response.json()
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
        "provider": provider_slug,
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
    )
    body = execute_response.json()

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
            provider_id=provider_slug,
            credential_mode=payload.credential_mode,
            layer=_LAYER,
            org_id=execution_data.get("org_id", agent.organization_id if agent else None),
            caller_ip_hash=hash_caller_ip(raw_request.client.host if raw_request.client else None),
            provider_name=provider_slug,
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
            receipt_id, provider_slug, payload.capability, receipt_input.status,
        )
    except Exception:
        logger.exception("l1_receipt_creation_failed execution_id=%s", execution_id)

    # ── Annotate response with Layer 1 metadata ──────────────────────
    if is_success and execution_data:
        execution_data["_rhumb_v2"] = {
            "api_version": "v2-alpha",
            "compat_mode": _COMPAT_MODE,
            "layer": _LAYER,
            "receipt_id": receipt_id,
            "provider": {
                "id": provider_slug,
                "display_name": detail.get("name", provider_slug),
                "capability_used": payload.capability,
                "an_score": detail.get("aggregate_recommendation_score"),
            },
            "cost": layer1_cost,
            "latency": {
                "total_ms": t_total_ms,
                "provider_ms": execution_data.get("provider_latency_ms"),
                "rhumb_overhead_ms": t_total_ms - (execution_data.get("provider_latency_ms") or t_total_ms),
            },
            "budget_applied": bool(budget_status and budget_status.budget_usd is not None),
            "budget_summary": _budget_summary(budget_status),
        }

    return JSONResponse(
        status_code=execute_response.status_code,
        content=body,
        headers={
            **_merge_response_headers(execute_response),
            "X-Rhumb-Provider": provider_slug,
        },
    )
