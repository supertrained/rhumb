"""Capability execution route — execute capabilities through the proxy layer.

Agents call POST /v1/capabilities/{id}/execute with a provider-native payload.
The route resolves the provider, injects auth, proxies the request, and logs
the execution to capability_executions.

Supports two authentication paths:
  1. **Registered agent** — ``X-Rhumb-Key`` header (existing API-key flow).
  2. **x402 anonymous** — ``X-Payment`` header with on-chain USDC payment.
     No API key or signup required; identity is derived from wallet address.
     Rate-limited per wallet to prevent abuse.

If neither header is present, the endpoint returns HTTP 402 with x402 payment
instructions so agents can discover how to pay.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
import uuid
from collections import defaultdict
from typing import Any, Optional
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from routes._supabase import supabase_fetch, supabase_insert, supabase_patch
from routes.proxy import (
    SERVICE_REGISTRY,
    get_breaker_registry,
    get_pool_manager,
    normalize_slug,
)
from schemas.agent_identity import AgentIdentityStore, get_agent_identity_store
from services.auto_reload import check_and_trigger_auto_reload
from services.budget_enforcer import BudgetEnforcer
from services.credit_deduction import CreditDeductionService
from services.payment_health import check_billing_health
from services.payment_metrics import log_payment_event
from services.x402 import PaymentRequiredException, build_x402_response
from services.x402_middleware import decode_x_payment_header, inspect_x_payment_header
from services.usdc_verifier import verify_usdc_payment
from services.proxy_auth import AuthInjector, AuthInjectionRequest, get_auth_injector
from services.proxy_credentials import get_credential_store
from services.routing_engine import RoutingEngine
from services.service_slugs import canonicalize_service_slug, normalize_proxy_slug

_budget_enforcer = BudgetEnforcer()
_credit_deduction = CreditDeductionService()
_routing_engine = RoutingEngine()
_identity_store: Optional[AgentIdentityStore] = None


def _get_identity_store() -> AgentIdentityStore:
    """Lazy-init identity store (matches proxy.py pattern)."""
    global _identity_store
    if _identity_store is None:
        _identity_store = get_agent_identity_store()
    return _identity_store

logger = logging.getLogger(__name__)


def _not_found_response(
    raw_request: Request,
    *,
    error: str,
    message: str,
    resolution: str,
) -> JSONResponse:
    """Return a standardized route-level 404 envelope."""
    request_id = getattr(raw_request.state, "request_id", None) or str(uuid.uuid4())
    return JSONResponse(
        status_code=404,
        content={
            "error": error,
            "message": message,
            "resolution": resolution,
            "request_id": request_id,
        },
    )


def _billing_unavailable_response(raw_request: Request) -> JSONResponse:
    request_id = getattr(raw_request.state, "request_id", None) or str(uuid.uuid4())
    return JSONResponse(
        status_code=503,
        content={
            "error": "billing_unavailable",
            "message": "Billing system temporarily unavailable. Execution blocked for safety.",
            "resolution": "Retry in 30 seconds. If persistent, check https://rhumb.dev/status",
            "request_id": request_id,
        },
    )


def _request_id(raw_request: Request) -> str:
    return getattr(raw_request.state, "request_id", None) or str(uuid.uuid4())


def _client_ip(raw_request: Request) -> str | None:
    forwarded_for = raw_request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    if raw_request.client:
        return raw_request.client.host
    return None


def _log_x402_interop_trace(
    raw_request: Request,
    *,
    capability_id: str,
    x_payment: str | None,
    payment_trace: dict[str, Any] | None,
    outcome: str,
    response_status: int,
    provider: str | None = None,
    payment_headers_set: bool = False,
    execution_id: str | None = None,
    agent_id: str | None = None,
    org_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    trace = payment_trace or {"parse_mode": "missing", "top_level_keys": []}
    payload = {
        "event": "x402_interop_trace",
        "request_id": _request_id(raw_request),
        "method": raw_request.method,
        "path": raw_request.url.path,
        "client_ip": _client_ip(raw_request),
        "user_agent": raw_request.headers.get("user-agent"),
        "content_type": raw_request.headers.get("content-type"),
        "capability_id": capability_id,
        "provider": provider,
        "agent_id": agent_id,
        "org_id": org_id,
        "execution_id": execution_id,
        "x_payment_present": bool(x_payment and x_payment != "required"),
        "x_payment_parse_mode": trace.get("parse_mode", "missing"),
        "x_payment_top_level_keys": trace.get("top_level_keys", []),
        "branch_outcome": outcome,
        "response_status": response_status,
        "payment_headers_set": payment_headers_set,
    }
    if extra:
        payload.update(extra)

    payload = {k: v for k, v in payload.items() if v is not None}
    logger.info("x402_interop_trace", extra={"x402_interop": payload})


# ---------------------------------------------------------------------------
# x402 anonymous wallet rate limiter (in-memory, per-process)
# ---------------------------------------------------------------------------

_wallet_requests: dict[str, list[float]] = defaultdict(list)
_WALLET_RATE_LIMIT = 60   # requests per minute per wallet
_WALLET_RATE_WINDOW = 60  # seconds

# ---------------------------------------------------------------------------
# x402 transaction replay prevention (in-memory, per-process)
# Prevents the same on-chain tx_hash from being used for multiple executions.
# ---------------------------------------------------------------------------

_used_tx_hashes: dict[str, float] = {}  # tx_hash -> first_seen_timestamp
_TX_HASH_TTL = 86400  # Keep hashes for 24h before allowing cleanup
_TX_HASH_CLEANUP_INTERVAL = 3600  # Prune expired entries every hour
_tx_hash_last_cleanup: float = 0.0


def check_tx_hash_replay(tx_hash: str) -> bool:
    """Check if a tx_hash has already been used. Returns True if it's a replay (rejected)."""
    global _tx_hash_last_cleanup
    now = time.time()
    key = tx_hash.lower().strip()

    # Periodic cleanup of expired entries
    if now - _tx_hash_last_cleanup > _TX_HASH_CLEANUP_INTERVAL:
        expired = [h for h, ts in _used_tx_hashes.items() if now - ts > _TX_HASH_TTL]
        for h in expired:
            del _used_tx_hashes[h]
        _tx_hash_last_cleanup = now

    if key in _used_tx_hashes:
        return True  # Replay detected

    _used_tx_hashes[key] = now
    return False  # First use, allowed

# ---------------------------------------------------------------------------
# Per-agent execution rate limiter (in-memory, per-process)
# Prevents abuse of managed credentials and general execution flooding.
# ---------------------------------------------------------------------------

_agent_exec_requests: dict[str, list[float]] = defaultdict(list)
_AGENT_EXEC_RATE_LIMIT = 30   # requests per minute per agent (all modes)
_AGENT_EXEC_RATE_WINDOW = 60  # seconds

_agent_managed_daily: dict[str, list[float]] = defaultdict(list)
_MANAGED_DAILY_LIMIT = 200    # managed executions per day per agent
_MANAGED_DAILY_WINDOW = 86400  # 24 hours


def check_agent_exec_rate_limit(agent_id: str) -> tuple[bool, int]:
    """Check per-agent per-minute execution rate limit. Returns (allowed, remaining)."""
    now = time.time()
    key = agent_id.lower()
    _agent_exec_requests[key] = [t for t in _agent_exec_requests[key] if now - t < _AGENT_EXEC_RATE_WINDOW]
    remaining = _AGENT_EXEC_RATE_LIMIT - len(_agent_exec_requests[key])
    if remaining <= 0:
        return False, 0
    _agent_exec_requests[key].append(now)
    return True, remaining - 1


def check_managed_daily_limit(agent_id: str) -> tuple[bool, int]:
    """Check per-agent daily managed execution cap. Returns (allowed, remaining)."""
    now = time.time()
    key = agent_id.lower()
    _agent_managed_daily[key] = [t for t in _agent_managed_daily[key] if now - t < _MANAGED_DAILY_WINDOW]
    remaining = _MANAGED_DAILY_LIMIT - len(_agent_managed_daily[key])
    if remaining <= 0:
        return False, 0
    _agent_managed_daily[key].append(now)
    return True, remaining - 1


def check_wallet_rate_limit(wallet_address: str) -> tuple[bool, int]:
    """Check per-wallet rate limit. Returns (allowed, remaining_requests)."""
    now = time.time()
    key = wallet_address.lower()
    _wallet_requests[key] = [t for t in _wallet_requests[key] if now - t < _WALLET_RATE_WINDOW]
    remaining = _WALLET_RATE_LIMIT - len(_wallet_requests[key])
    if remaining <= 0:
        return False, 0
    _wallet_requests[key].append(now)
    return True, remaining - 1


async def _build_execute_discovery_response(capability_id: str) -> JSONResponse:
    """Return x402 payment requirements for the execute surface without executing.

    Some x402 clients probe the resource URL with GET before issuing the real
    POST request. Treat GET /execute as a side-effect-free discovery surface so
    those clients can learn the payment requirements without triggering a 405.
    """
    cap_services_for_402 = await _get_capability_services(capability_id)
    cost_for_402 = 0.0
    if cap_services_for_402:
        costs = [
            float(m["cost_per_call"])
            for m in cap_services_for_402
            if m.get("cost_per_call") is not None
        ]
        cost_for_402 = min(costs) if costs else 0.0

    api_base = os.environ.get("API_BASE_URL", "https://api.rhumb.dev")
    if cost_for_402 <= 0:
        return JSONResponse(
            status_code=402,
            content={
                "x402Version": 1,
                "accepts": [],
                "error": "Cost data unavailable for this capability. Use the estimate endpoint first: "
                         f"GET {api_base}/v1/capabilities/{capability_id}/execute/estimate",
                "balanceRequired": None,
                "balanceRequiredUsd": None,
            },
            headers={"X-Payment": "required"},
        )

    billed_cost_usd = cost_for_402 * 1.15
    billed_cents_for_402 = max(int(round(billed_cost_usd * 100)), 1)
    body_402 = build_x402_response(
        capability_id=capability_id,
        cost_usd_cents=billed_cents_for_402,
        resource_url=f"{api_base}/v1/capabilities/{capability_id}/execute",
    )
    return JSONResponse(
        status_code=402,
        content=body_402,
        headers={"X-Payment": "required"},
    )


router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class CapabilityExecuteRequest(BaseModel):
    """Payload for POST /v1/capabilities/{capability_id}/execute."""

    provider: Optional[str] = Field(None, description="Provider slug (omit for auto-select)")
    method: Optional[str] = Field(None, description="HTTP method (GET, POST, etc.) — required for byo/agent_vault, optional for rhumb_managed")
    path: Optional[str] = Field(None, description="Provider API path (e.g. /v3/mail/send) — required for byo/agent_vault, optional for rhumb_managed")
    body: Optional[dict] = Field(None, description="Request body (provider-native)")
    params: Optional[dict] = Field(None, description="Query parameters")
    credential_mode: str = Field(
        "auto",
        description=(
            "Credential mode (auto, byo, rhumb_managed, agent_vault). "
            "'auto' uses rhumb_managed when available, falls back to byo."
        ),
    )
    idempotency_key: Optional[str] = Field(None, description="Idempotency key to prevent duplicate execution")
    interface: str = Field("rest", description="Client interface (rest, mcp, cli, sdk)")


# ---------------------------------------------------------------------------
# Upstream payload helpers
# ---------------------------------------------------------------------------

def _service_slug_matches(candidate_slug: str | None, requested_slug: str | None) -> bool:
    """Return True when canonical/proxy aliases refer to the same service."""
    if not candidate_slug or not requested_slug:
        return False
    return (
        candidate_slug == requested_slug
        or normalize_proxy_slug(candidate_slug) == normalize_proxy_slug(requested_slug)
        or canonicalize_service_slug(candidate_slug) == canonicalize_service_slug(requested_slug)
    )


def _prepare_upstream_payload(
    method: str | None,
    body: dict | None,
    params: dict | None,
) -> tuple[dict | None, dict | None]:
    """Normalize request payloads before upstream execution.

    GET/HEAD/DELETE requests should not send JSON bodies to providers that
    expect query-string inputs (for example PDL enrich). Promote body fields
    into params unless the param key is already set explicitly.
    """
    effective_params = dict(params) if params else {}
    if method and method.upper() in ("GET", "HEAD", "DELETE"):
        if body:
            for key, value in body.items():
                effective_params.setdefault(key, value)
        return None, effective_params or None
    return body, effective_params or None


# ---------------------------------------------------------------------------
# Provider resolution helpers
# ---------------------------------------------------------------------------

async def _resolve_capability(capability_id: str) -> Optional[dict]:
    """Fetch a capability row by ID. Returns None if not found."""
    caps = await supabase_fetch(
        f"capabilities?id=eq.{quote(capability_id)}"
        f"&select=id,domain,action,description&limit=1"
    )
    if not caps:
        return None
    return caps[0]


async def _get_capability_services(capability_id: str) -> list[dict]:
    """Fetch all capability_services mappings for a capability."""
    mappings = await supabase_fetch(
        f"capability_services?capability_id=eq.{quote(capability_id)}"
        f"&select=service_slug,credential_modes,auth_method,endpoint_pattern,"
        f"cost_per_call,cost_currency,free_tier_calls"
    )
    return mappings or []


async def _get_service_domain(service_slug: str) -> Optional[str]:
    """Resolve a service's api_domain from the services table."""
    rows = await supabase_fetch(
        f"services?slug=eq.{quote(service_slug)}&select=slug,api_domain&limit=1"
    )
    if rows and rows[0].get("api_domain"):
        return rows[0]["api_domain"]
    return None


async def _auto_select_provider(
    mappings: list[dict],
    agent_id: str,
) -> Optional[dict]:
    """Pick the best provider from mappings using RoutingEngine.

    Uses the agent's routing strategy (cheapest/fastest/highest_quality/balanced)
    with quality floor and cost ceiling filters.
    Returns the chosen mapping dict, or None if none available.
    """
    if not mappings:
        return None

    slugs = [m["service_slug"] for m in mappings]
    slug_filter = ",".join(f'"{s}"' for s in slugs)

    scores = await supabase_fetch(
        f"scores?service_slug=in.({slug_filter})"
        f"&select=service_slug,aggregate_recommendation_score"
        f"&order=aggregate_recommendation_score.desc.nullslast"
    )

    scores_by_slug: dict[str, float] = {}
    if scores:
        for sc in scores:
            slug = sc.get("service_slug")
            agg = sc.get("aggregate_recommendation_score")
            if slug and agg is not None and slug not in scores_by_slug:
                scores_by_slug[slug] = float(agg)

    breaker_reg = get_breaker_registry()
    circuit_states: dict[str, str] = {}
    for m in mappings:
        slug = m["service_slug"]
        breaker = breaker_reg.get(slug, agent_id)
        circuit_states[slug] = breaker.state.value if hasattr(breaker.state, 'value') else str(breaker.state)

    # Use agent's routing strategy
    strategy = await _routing_engine.get_strategy(agent_id)
    routed = _routing_engine.select_provider(
        mappings=mappings,
        scores_by_slug=scores_by_slug,
        circuit_states=circuit_states,
        strategy=strategy,
    )

    if routed is None:
        return None

    # Return the mapping dict for the selected provider
    return next((m for m in mappings if m["service_slug"] == routed.service_slug), None)


def _extract_cost_usd(mapping: dict | None) -> float:
    """Convert a capability_services mapping cost to float USD."""
    if mapping is None or mapping.get("cost_per_call") is None:
        return 0.0
    return float(mapping["cost_per_call"])


def _calculate_billing_amounts(cost_usd: float) -> tuple[int, int, int]:
    """Return upstream, billed, and margin cents for a USD cost."""
    upstream_cost_cents = int(round(cost_usd * 100)) if cost_usd > 0 else 0
    billed_cost_cents = int(round(upstream_cost_cents * 1.2)) if upstream_cost_cents > 0 else 0
    margin_cents = billed_cost_cents - upstream_cost_cents
    return upstream_cost_cents, billed_cost_cents, margin_cents


async def _select_provider_mapping(
    mappings: list[dict],
    requested_provider: Optional[str],
    agent_id: str,
    capability_id: str,
) -> dict:
    """Resolve the actual provider mapping for a BYO execution."""
    if not mappings:
        raise HTTPException(
            status_code=503,
            detail=f"No providers configured for capability '{capability_id}'",
        )

    if requested_provider:
        chosen = next(
            (
                m for m in mappings
                if _service_slug_matches(m.get("service_slug"), requested_provider)
            ),
            None,
        )
        if chosen is None:
            raise HTTPException(
                status_code=503,
                detail=f"Provider '{requested_provider}' not available for capability '{capability_id}'",
            )
        breaker = get_breaker_registry().get(normalize_proxy_slug(chosen["service_slug"]), agent_id)
        if not breaker.allow_request():
            raise HTTPException(
                status_code=503,
                detail=f"Provider '{requested_provider}' circuit is open — try later",
            )
        return chosen

    chosen = await _auto_select_provider(mappings, agent_id)
    if chosen is None:
        raise HTTPException(
            status_code=503,
            detail=f"No healthy providers available for capability '{capability_id}'",
        )
    return chosen


async def _resolve_managed_provider_mapping(
    capability_id: str,
    mappings: list[dict],
    requested_provider: Optional[str],
) -> dict | None:
    """Resolve the managed provider mapping used for a rhumb_managed execution."""
    from services.rhumb_managed import get_managed_executor

    executor = get_managed_executor()
    managed_config = await executor.get_managed_config(
        capability_id,
        requested_provider,
    )
    if managed_config is None:
        return None

    managed_slug = managed_config["service_slug"]
    return next(
        (
            m for m in mappings
            if _service_slug_matches(m.get("service_slug"), managed_slug)
        ),
        None,
    )


def _parse_credential_modes(raw_modes: Any) -> list[str]:
    """Normalize credential_modes from Supabase into a list of strings."""
    if isinstance(raw_modes, str):
        return [mode.strip() for mode in raw_modes.split(",") if mode.strip()]
    if isinstance(raw_modes, (list, tuple, set)):
        parsed_modes: list[str] = []
        for mode in raw_modes:
            normalized = str(mode).strip()
            if normalized:
                parsed_modes.append(normalized)
        return parsed_modes
    return []


async def _resolve_auto_credential_mode(
    capability_id: str,
    credential_mode: str,
    mappings: list[dict],
    requested_provider: Optional[str],
) -> tuple[str, dict | None]:
    """Resolve auto mode to rhumb_managed when an active managed config exists."""
    if credential_mode != "auto":
        return credential_mode, None

    candidate_mappings = [
        mapping
        for mapping in mappings
        if requested_provider is None
        or _service_slug_matches(mapping.get("service_slug"), requested_provider)
    ]
    managed_advertised = any(
        "rhumb_managed" in _parse_credential_modes(mapping.get("credential_modes", []))
        for mapping in candidate_mappings
    )

    managed_mapping: dict | None = None
    if managed_advertised:
        managed_mapping = await _resolve_managed_provider_mapping(
            capability_id=capability_id,
            mappings=mappings,
            requested_provider=requested_provider,
        )

    resolved_mode = "rhumb_managed" if managed_mapping is not None else "byo"
    logger.info(
        "credential_mode auto-resolved to %s for capability %s",
        resolved_mode,
        capability_id,
    )
    return resolved_mode, managed_mapping


def _resolve_base_url(
    service_slug: str,
    api_domain: Optional[str],
    request_path: Optional[str] = None,
) -> str:
    """Build base URL: prefer hardcoded SERVICE_REGISTRY, then dynamic domain.

    Some providers multiplex products across multiple API domains. Twilio is the
    current concrete case:
    - core messaging/voice/account APIs live on ``api.twilio.com``
    - Lookup v2 lives on ``lookups.twilio.com``
    - Verify v2 lives on ``verify.twilio.com``

    Resolve execution receives an explicit provider-native path, so route to the
    correct product domain when the request path makes that intent unambiguous.
    """
    normalized_path = request_path or ""
    if normalized_path and not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"

    if service_slug == "twilio":
        if normalized_path.startswith("/v2/PhoneNumbers"):
            return "https://lookups.twilio.com"
        if normalized_path.startswith("/v2/Services"):
            return "https://verify.twilio.com"

    reg = SERVICE_REGISTRY.get(service_slug)
    if reg:
        return f"https://{reg['domain']}"
    if api_domain:
        domain = api_domain
        if not domain.startswith("http"):
            domain = f"https://{domain}"
        return domain
    raise HTTPException(
        status_code=500,
        detail=f"No API domain configured for service '{service_slug}'",
    )


def _inject_auth_headers(
    service_slug: str,
    auth_method: Optional[str],
    headers: dict[str, str],
) -> dict[str, str]:
    """Inject Authorization header for a service.

    For the 5 hardcoded services, delegates to AuthInjector.
    For dynamic services, builds a simple auth header from CredentialStore.
    """
    # Hardcoded services — use the full AuthInjector
    if service_slug in AuthInjector.AUTH_PATTERNS:
        method_enum = AuthInjector.default_method_for(service_slug)
        if method_enum is None:
            raise HTTPException(status_code=500, detail=f"No auth method for '{service_slug}'")
        injector = get_auth_injector()
        try:
            return injector.inject(
                AuthInjectionRequest(
                    service=service_slug,
                    agent_id="capability_execute",
                    auth_method=method_enum,
                    existing_headers=headers,
                )
            )
        except (ValueError, RuntimeError) as e:
            raise HTTPException(status_code=503, detail=f"Credential unavailable: {e}")

    # Dynamic services — simple credential lookup
    if not auth_method:
        raise HTTPException(
            status_code=500,
            detail=f"No auth_method defined for service '{service_slug}'",
        )

    store = get_credential_store()
    credential = store.get_credential(service_slug, auth_method)
    if credential is None:
        raise HTTPException(
            status_code=503,
            detail=f"No credential found for {service_slug}/{auth_method}",
        )

    headers = headers.copy()
    if auth_method == "basic_auth":
        encoded = base64.b64encode(credential.encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"
    else:
        # bearer_token, api_key — both use Bearer
        headers["Authorization"] = f"Bearer {credential}"

    return headers


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

@router.get("/capabilities/{capability_id}/execute")
async def discover_execute_capability(
    capability_id: str,
    raw_request: Request,
) -> JSONResponse:
    """Return x402 payment requirements for execute without executing anything."""
    capability = await _resolve_capability(capability_id)
    if capability is None:
        return _not_found_response(
            raw_request,
            error="capability_not_found",
            message=f"No capability found with id '{capability_id}'",
            resolution=(
                "Browse capabilities at GET /v1/capabilities or use "
                "discover_capabilities MCP tool"
            ),
        )

    return await _build_execute_discovery_response(capability_id)


@router.post("/capabilities/{capability_id}/execute")
async def execute_capability(
    capability_id: str,
    request: CapabilityExecuteRequest,
    raw_request: Request,
    x_rhumb_key: Optional[str] = Header(None, alias="X-Rhumb-Key"),
    x_agent_token: Optional[str] = Header(None, alias="X-Agent-Token"),
    x_payment: Optional[str] = Header(None, alias="X-Payment"),
) -> dict:
    """Execute a capability through the proxy layer.

    Resolves provider, injects auth, proxies the request upstream,
    logs the execution, and returns the upstream response.

    Supports x402 inline payment via the ``X-Payment`` header.
    """
    # ── Kill Switch: full execution shutdown ───────────────────────
    if os.environ.get("MANAGED_EXECUTION_ENABLED", "").lower() == "false":
        logger.warning("Kill switch active: MANAGED_EXECUTION_ENABLED=false — rejecting execution")
        return JSONResponse(
            status_code=503,
            content={
                "error": "managed_execution_disabled",
                "message": "Capability execution is temporarily disabled for maintenance",
                "resolution": "Check https://rhumb.dev/status for updates",
                "request_id": f"req_{uuid.uuid4().hex[:12]}",
            },
        )

    capability = await _resolve_capability(capability_id)
    if capability is None:
        return _not_found_response(
            raw_request,
            error="capability_not_found",
            message=f"No capability found with id '{capability_id}'",
            resolution=(
                "Browse capabilities at GET /v1/capabilities or use "
                "discover_capabilities MCP tool"
            ),
        )

    # ── Authentication: API key OR x402 payment ────────────────────
    is_x402_anonymous = False
    x402_wallet_address: Optional[str] = None
    x402_rate_remaining: Optional[int] = None
    payment_trace = inspect_x_payment_header(x_payment) if x_payment and x_payment != "required" else {
        "payment_data": None,
        "parse_mode": "missing",
        "top_level_keys": [],
    }

    if x_rhumb_key:
        # Path 1: Registered agent with API key (existing flow)
        agent = await _get_identity_store().verify_api_key_with_agent(x_rhumb_key)
        if agent is None:
            raise HTTPException(status_code=401, detail="Invalid or expired Rhumb API key")
        agent_id = agent.agent_id
        org_id = agent.organization_id
    elif x_payment and x_payment != "required":
        # Path 2: x402 anonymous — payment header present, no API key.
        # SECURITY: We only set is_x402_anonymous AFTER validating the header
        # contains a decodeable payment payload with a tx_hash.  A garbage
        # header (e.g. "fake", "bypass") must NOT grant anonymous execution.
        payment_data = payment_trace.get("payment_data")
        if not payment_data or not payment_data.get("tx_hash"):
            # Header present but invalid/missing tx_hash → treat as
            # unauthenticated. Return the same discovery envelope clients see
            # on a GET probe or unauthenticated POST.
            response = await _build_execute_discovery_response(capability_id)
            _log_x402_interop_trace(
                raw_request,
                capability_id=capability_id,
                x_payment=x_payment,
                payment_trace=payment_trace,
                outcome="missing_tx_hash" if payment_data else "invalid",
                response_status=response.status_code,
                provider=request.provider,
                payment_headers_set="X-Payment" in response.headers,
            )
            return response

        # Replay prevention: reject reused tx_hash
        tx_hash = payment_data["tx_hash"]
        if check_tx_hash_replay(tx_hash):
            _log_x402_interop_trace(
                raw_request,
                capability_id=capability_id,
                x_payment=x_payment,
                payment_trace=payment_trace,
                outcome="replay",
                response_status=409,
                provider=request.provider,
                payment_headers_set=False,
                extra={"tx_hash": tx_hash},
            )
            raise HTTPException(
                status_code=409,
                detail="Transaction hash has already been used. Each payment can only be applied once.",
            )

        # Valid payment payload — proceed with x402 anonymous flow
        is_x402_anonymous = True
        x402_wallet_address = (
            payment_data.get("wallet_address")
            or payment_data.get("from")
        )
        # Derive deterministic identity from wallet (or use generic fallback)
        if x402_wallet_address:
            agent_id = f"x402_wallet_{x402_wallet_address.lower()}"
        else:
            agent_id = "x402_anonymous"
        org_id = "x402_anonymous"

        # Rate-limit per wallet to prevent abuse
        if x402_wallet_address:
            allowed, remaining = check_wallet_rate_limit(x402_wallet_address)
            x402_rate_remaining = remaining
            if not allowed:
                _log_x402_interop_trace(
                    raw_request,
                    capability_id=capability_id,
                    x_payment=x_payment,
                    payment_trace=payment_trace,
                    outcome="wallet_rate_limited",
                    response_status=429,
                    provider=request.provider,
                    payment_headers_set=False,
                    agent_id=agent_id,
                    org_id=org_id,
                    extra={"wallet_address": x402_wallet_address},
                )
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded for this wallet",
                    headers={"Retry-After": str(_WALLET_RATE_WINDOW)},
                )
    else:
        # Path 3: No auth at all — return x402 payment instructions
        response = await _build_execute_discovery_response(capability_id)
        _log_x402_interop_trace(
            raw_request,
            capability_id=capability_id,
            x_payment=x_payment,
            payment_trace=payment_trace,
            outcome="payment_required",
            response_status=response.status_code,
            provider=request.provider,
            payment_headers_set="X-Payment" in response.headers,
        )
        return response

    # ── Per-agent execution rate limiting ────────────────────────────
    # Applies to all execution modes to prevent flooding.
    exec_allowed, exec_remaining = check_agent_exec_rate_limit(agent_id)
    if not exec_allowed:
        raise HTTPException(
            status_code=429,
            detail="Execution rate limit exceeded (30/min). Slow down.",
            headers={"Retry-After": "60"},
        )

    # Idempotency before reservations.
    if request.idempotency_key:
        existing = await supabase_fetch(
            f"capability_executions?idempotency_key=eq.{quote(request.idempotency_key)}"
            f"&select=id,upstream_status,cost_estimate_usd&limit=1"
        )
        if existing:
            return {
                "data": {
                    "capability_id": capability_id,
                    "execution_id": existing[0]["id"],
                    "deduplicated": True,
                },
                "error": None,
            }

    cap_services = await _get_capability_services(capability_id)
    request.credential_mode, managed_mapping = await _resolve_auto_credential_mode(
        capability_id=capability_id,
        credential_mode=request.credential_mode,
        mappings=cap_services,
        requested_provider=request.provider,
    )

    # ── Kill Switch: managed-only shutdown ──────────────────────
    # Blocks Mode 2 (Rhumb's credentials) while allowing BYOK and x402.
    # Use when our upstream API budgets are being consumed too fast.
    if request.credential_mode == "rhumb_managed" and os.environ.get("MANAGED_ONLY_KILL", "").lower() == "true":
        logger.warning("Managed-only kill switch active — rejecting rhumb_managed execution for %s", agent_id)
        return JSONResponse(
            status_code=503,
            content={
                "error": "managed_execution_suspended",
                "message": "Managed credential execution is temporarily suspended. Use your own API key (credential_mode: byo) to continue.",
                "resolution": "Check https://rhumb.dev/status for updates or switch to BYO credentials",
                "request_id": f"req_{uuid.uuid4().hex[:12]}",
            },
        )

    # Stricter daily cap for managed credentials (Rhumb's own keys)
    if request.credential_mode == "rhumb_managed":
        managed_allowed, managed_remaining = check_managed_daily_limit(agent_id)
        if not managed_allowed:
            raise HTTPException(
                status_code=429,
                detail="Daily managed execution limit exceeded (200/day). "
                       "Consider using BYO credentials for higher volume.",
                headers={"Retry-After": "3600"},
            )

    # Validate required fields before reserving any budget/credits.
    if request.credential_mode == "agent_vault":
        if not x_agent_token:
            raise HTTPException(
                status_code=400,
                detail="X-Agent-Token header required for agent_vault credential mode. "
                       "Get a token via GET /v1/services/{slug}/ceremony",
            )
        if not request.method or not request.path:
            raise HTTPException(
                status_code=400,
                detail="method and path are required for agent_vault credential mode",
            )
        if not request.provider:
            raise HTTPException(
                status_code=400,
                detail="provider is required for agent_vault credential mode",
            )
    elif request.credential_mode != "rhumb_managed":
        if not request.method or not request.path:
            raise HTTPException(
                status_code=400,
                detail="method and path are required for byo credential mode",
            )

    selected_mapping: dict | None = None
    if request.credential_mode == "byo":
        selected_mapping = await _select_provider_mapping(
            mappings=cap_services,
            requested_provider=request.provider,
            agent_id=agent_id,
            capability_id=capability_id,
        )
    elif request.credential_mode == "agent_vault":
        selected_mapping = next(
            (
                m for m in cap_services
                if _service_slug_matches(m.get("service_slug"), request.provider)
            ),
            None,
        )
    elif request.credential_mode == "rhumb_managed":
        selected_mapping = managed_mapping or await _resolve_managed_provider_mapping(
            capability_id=capability_id,
            mappings=cap_services,
            requested_provider=request.provider,
        )

    # 0. Pre-execution budget/credit reservation estimate
    cost_estimate = _extract_cost_usd(selected_mapping)
    upstream_cost_cents, billed_cost_cents, margin_cents = _calculate_billing_amounts(cost_estimate)

    execution_id = f"exec_{uuid.uuid4().hex}"
    has_inline_x402_payment = bool(x_payment and x_payment != "required")

    # Free calls do not depend on org-credit balance. Billable non-x402 calls must
    # verify billing availability before any execution work starts.
    if billed_cost_cents > 0 and not has_inline_x402_payment:
        billing_healthy, billing_reason = await check_billing_health()
        if not billing_healthy:
            request_id = getattr(raw_request.state, "request_id", None) or "unknown"
            logger.error(
                "Blocking billable execution due to billing health failure "
                "request_id=%s agent_id=%s org_id=%s capability_id=%s reason=%s",
                request_id,
                agent_id,
                org_id,
                capability_id,
                billing_reason,
            )
            return _billing_unavailable_response(raw_request)

    # ── x402 inline payment handling ─────────────────────────────────
    # If the client sends an X-Payment header with a USDC tx_hash, we:
    #   1. Verify the tx hasn't been used before (replay protection)
    #   2. Verify the on-chain USDC transfer matches expected amount/recipient
    #   3. Record the receipt in usdc_receipts
    #   4. Best-effort record the payment on the org ledger for registered agents
    #   5. Treat verified on-chain payment as authorization and skip Supabase
    #      billing reservations entirely
    x402_receipt: dict | None = None
    if x_payment and x_payment != "required":
        payment_data = payment_trace.get("payment_data") or decode_x_payment_header(x_payment)
        if payment_data and payment_data.get("tx_hash"):
            tx_hash = payment_data["tx_hash"]
            network = payment_data.get("network", "evm:84532")
            declared_wallet = payment_data.get("wallet_address") or payment_data.get("from")

            # Replay protection: check if tx_hash is already recorded
            existing_receipt = await supabase_fetch(
                f"usdc_receipts?tx_hash=eq.{quote(tx_hash)}&select=id&limit=1"
            )
            if existing_receipt:
                _log_x402_interop_trace(
                    raw_request,
                    capability_id=capability_id,
                    x_payment=x_payment,
                    payment_trace=payment_trace,
                    outcome="replay",
                    response_status=402,
                    provider=request.provider,
                    payment_headers_set=False,
                    execution_id=execution_id,
                    agent_id=agent_id,
                    org_id=org_id,
                    extra={"tx_hash": tx_hash},
                )
                raise HTTPException(
                    status_code=402,
                    detail="Transaction already used",
                )

            # Verify on-chain
            wallet = os.environ.get("RHUMB_USDC_WALLET_ADDRESS", "")
            if not wallet:
                _log_x402_interop_trace(
                    raw_request,
                    capability_id=capability_id,
                    x_payment=x_payment,
                    payment_trace=payment_trace,
                    outcome="wallet_not_configured",
                    response_status=402,
                    provider=request.provider,
                    payment_headers_set=False,
                    execution_id=execution_id,
                    agent_id=agent_id,
                    org_id=org_id,
                    extra={"tx_hash": tx_hash, "network": network},
                )
                raise HTTPException(
                    status_code=402,
                    detail="Payment verification failed: wallet not configured",
                )
            if not declared_wallet:
                _log_x402_interop_trace(
                    raw_request,
                    capability_id=capability_id,
                    x_payment=x_payment,
                    payment_trace=payment_trace,
                    outcome="payer_wallet_missing",
                    response_status=402,
                    provider=request.provider,
                    payment_headers_set=False,
                    execution_id=execution_id,
                    agent_id=agent_id,
                    org_id=org_id,
                    extra={"tx_hash": tx_hash, "network": network},
                )
                raise HTTPException(
                    status_code=402,
                    detail="Payment verification failed: payer wallet not declared",
                )
            if selected_mapping is None or selected_mapping.get("cost_per_call") is None:
                _log_x402_interop_trace(
                    raw_request,
                    capability_id=capability_id,
                    x_payment=x_payment,
                    payment_trace=payment_trace,
                    outcome="cost_unavailable",
                    response_status=402,
                    provider=request.provider,
                    payment_headers_set=False,
                    execution_id=execution_id,
                    agent_id=agent_id,
                    org_id=org_id,
                    extra={"tx_hash": tx_hash, "network": network},
                )
                raise HTTPException(
                    status_code=402,
                    detail="Payment verification failed: cost data unavailable for selected provider",
                )

            expected_atomic = str(billed_cost_cents * 10000) if billed_cost_cents > 0 else "0"
            verification = await verify_usdc_payment(
                tx_hash=tx_hash,
                expected_to=wallet,
                expected_amount_atomic=expected_atomic,
                expected_from=declared_wallet,
                network=network,
            )

            if not verification.get("valid"):
                log_payment_event(
                    "x402_payment_failed",
                    org_id=org_id,
                    capability_id=capability_id,
                    execution_id=execution_id,
                    tx_hash=tx_hash,
                    network=network,
                    success=False,
                    error=verification.get("error", "unknown"),
                )
                _log_x402_interop_trace(
                    raw_request,
                    capability_id=capability_id,
                    x_payment=x_payment,
                    payment_trace=payment_trace,
                    outcome="verify_failed",
                    response_status=402,
                    provider=request.provider,
                    payment_headers_set=False,
                    execution_id=execution_id,
                    agent_id=agent_id,
                    org_id=org_id,
                    extra={
                        "tx_hash": tx_hash,
                        "network": network,
                        "verify_error": verification.get("error", "unknown"),
                    },
                )
                raise HTTPException(
                    status_code=402,
                    detail=f"Payment verification failed: {verification.get('error', 'unknown')}",
                )

            expected_atomic_int = billed_cost_cents * 10000
            paid_atomic = int(verification.get("amount_atomic", "0"))
            if expected_atomic_int > 0 and paid_atomic > ((expected_atomic_int * 120) // 100):
                logger.warning(
                    "Suspicious x402 overpayment detected tx_hash=%s org_id=%s capability_id=%s "
                    "paid_atomic=%s expected_atomic=%s provider=%s",
                    tx_hash,
                    org_id,
                    capability_id,
                    paid_atomic,
                    expected_atomic_int,
                    selected_mapping["service_slug"],
                )

            # Record receipt in usdc_receipts (replay protection via UNIQUE constraint)
            await supabase_insert("usdc_receipts", {
                "tx_hash": tx_hash,
                "from_address": verification.get("from_address", ""),
                "to_address": verification.get("to_address", wallet),
                "amount_usdc_atomic": verification.get("amount_atomic", expected_atomic),
                "amount_usd_cents": billed_cost_cents,
                "network": network,
                "block_number": verification.get("block_number"),
                "org_id": org_id,
                "execution_id": execution_id,
                "status": "confirmed",
            })

            # For registered agents, record the payment on the org ledger when
            # billing storage is available. Execution authorization comes from
            # the verified on-chain payment itself.
            if not is_x402_anonymous:
                current_credits = await supabase_fetch(
                    f"org_credits?org_id=eq.{quote(org_id)}&select=balance_usd_cents&limit=1"
                )
                current_balance = int(current_credits[0].get("balance_usd_cents", 0)) if current_credits else 0
                new_balance = current_balance + billed_cost_cents

                await supabase_insert("credit_ledger", {
                    "org_id": org_id,
                    "amount_usd_cents": billed_cost_cents,
                    "balance_after_usd_cents": new_balance,
                    "event_type": "x402_payment",
                    "capability_execution_id": execution_id,
                    "description": f"x402 USDC payment tx:{tx_hash[:16]}…",
                })

                if current_credits:
                    await supabase_patch(
                        f"org_credits?org_id=eq.{quote(org_id)}",
                        {"balance_usd_cents": new_balance},
                    )

            log_payment_event(
                "x402_payment_verified",
                org_id=org_id,
                capability_id=capability_id,
                execution_id=execution_id,
                tx_hash=tx_hash,
                network=network,
                amount_usd_cents=billed_cost_cents,
            )
            x402_receipt = verification

    # ── Budget & credit reservation (registered agents only) ──────
    # x402 anonymous agents pay per-call on-chain; no budget/credit system.
    # Registered agents with verified x402 payments are also exempt from the
    # Supabase billing gate because the payment proof is on-chain.
    budget_remaining: float | None = None
    credit_reserved = False
    credit_remaining_cents: int | None = None
    on_chain_payment_authorized = x402_receipt is not None
    api_base = os.environ.get(
        "API_BASE_URL", "https://api.rhumb.dev"
    )

    provider_hint = (
        request.provider
        or (selected_mapping.get("service_slug") if selected_mapping else None)
        or "pending"
    )
    inferred_method = request.method
    inferred_path = request.path
    endpoint_pattern = selected_mapping.get("endpoint_pattern") if selected_mapping else None
    if endpoint_pattern and (not inferred_method or not inferred_path):
        endpoint_parts = endpoint_pattern.split(" ", 1)
        if len(endpoint_parts) == 2:
            inferred_method = inferred_method or endpoint_parts[0]
            inferred_path = inferred_path or endpoint_parts[1]

    await supabase_insert("capability_executions", {
        "id": execution_id,
        "agent_id": agent_id,
        "capability_id": capability_id,
        "provider_used": provider_hint,
        "credential_mode": request.credential_mode,
        "method": inferred_method or "PENDING",
        "path": inferred_path or "/pending",
        "upstream_status": None,
        "success": False,
        "cost_estimate_usd": cost_estimate,
        "cost_usd_cents": billed_cost_cents if billed_cost_cents > 0 else None,
        "upstream_cost_cents": upstream_cost_cents if upstream_cost_cents > 0 else None,
        "margin_cents": margin_cents if billed_cost_cents > 0 else None,
        "billing_status": "pending" if billed_cost_cents > 0 else "unbilled",
        "total_latency_ms": None,
        "upstream_latency_ms": None,
        "fallback_attempted": False,
        "fallback_provider": None,
        "idempotency_key": request.idempotency_key,
        "error_message": None,
        "interface": request.interface,
    })

    if not is_x402_anonymous and not on_chain_payment_authorized:
        budget_result = await _budget_enforcer.check_and_decrement(agent_id, cost_estimate)
        if not budget_result.allowed:
            log_payment_event(
                "x402_payment_required",
                org_id=org_id,
                capability_id=capability_id,
                execution_id=execution_id,
                amount_usd_cents=billed_cost_cents,
            )
            raise PaymentRequiredException(
                capability_id=capability_id,
                cost_usd_cents=billed_cost_cents,
                resource_url=f"{api_base}/v1/capabilities/{capability_id}/execute",
                detail=budget_result.reason or "Agent budget exceeded",
            )

        budget_remaining = budget_result.remaining_usd

        # Step 2: org credit deduction (only when estimated cost > 0)
        if billed_cost_cents > 0:
            credit_result = await _credit_deduction.deduct(
                org_id,
                billed_cost_cents,
                execution_id=execution_id,
                agent_id=agent_id,
                fallback_cost_usd=cost_estimate,
                skip_budget_fallback=True,
            )
            if credit_result.billing_unavailable:
                if cost_estimate > 0:
                    await _budget_enforcer.release(agent_id, cost_estimate)
                request_id = getattr(raw_request.state, "request_id", None) or "unknown"
                logger.error(
                    "Blocking execution after billing RPC failure "
                    "request_id=%s agent_id=%s org_id=%s capability_id=%s execution_id=%s",
                    request_id,
                    agent_id,
                    org_id,
                    capability_id,
                    execution_id,
                )
                return _billing_unavailable_response(raw_request)
            if not credit_result.allowed:
                if cost_estimate > 0:
                    await _budget_enforcer.release(agent_id, cost_estimate)
                raise PaymentRequiredException(
                    capability_id=capability_id,
                    cost_usd_cents=billed_cost_cents,
                    resource_url=f"{api_base}/v1/capabilities/{capability_id}/execute",
                    detail=credit_result.reason or "Insufficient org credits",
                )
            credit_reserved = billed_cost_cents > 0
            credit_remaining_cents = credit_result.remaining_cents

            # Fire-and-forget auto-reload check when balance is known
            if credit_remaining_cents is not None:
                try:
                    reload_result = await check_and_trigger_auto_reload(
                        org_id, credit_remaining_cents
                    )
                    if reload_result:
                        logger.info("Auto-reload result for %s: %s", org_id, reload_result)
                except Exception as e:
                    logger.warning("Auto-reload check error (non-blocking): %s", e)

    async def _release_reservations() -> None:
        if is_x402_anonymous:
            return  # No reservations to release for anonymous agents
        if cost_estimate > 0:
            await _budget_enforcer.release(agent_id, cost_estimate)
        if credit_reserved and billed_cost_cents > 0:
            await _credit_deduction.release(
                org_id,
                billed_cost_cents,
                execution_id=execution_id,
                agent_id=agent_id,
                fallback_cost_usd=cost_estimate,
                skip_budget_fallback=True,
            )

    # ── Mode 2: Rhumb-managed execution ──────────────────────────────
    if request.credential_mode == "rhumb_managed":
        from services.rhumb_managed import get_managed_executor
        from services.upstream_budget import check_provider_budget, record_provider_usage

        # Check upstream provider budget before burning our API credits
        provider_slug = request.provider
        if provider_slug:
            budget_ok, budget_reason = check_provider_budget(provider_slug)
            if not budget_ok:
                await _release_reservations()
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": "provider_budget_exhausted",
                        "message": budget_reason,
                        "resolution": "Switch to credential_mode: byo with your own API key, or try again after budget reset",
                        "request_id": f"req_{uuid.uuid4().hex[:12]}",
                    },
                )

        executor = get_managed_executor()
        try:
            result = await executor.execute(
                capability_id=capability_id,
                agent_id=agent_id,
                body=request.body,
                params=request.params,
                service_slug=request.provider,
                interface=request.interface,
                execution_id=execution_id,
            )
        except Exception:
            await _release_reservations()
            raise

        # Record successful execution against upstream budget
        if provider_slug:
            record_provider_usage(provider_slug)

        await supabase_patch(
            f"capability_executions?id=eq.{quote(execution_id)}",
            {
                "billing_status": "billed" if billed_cost_cents > 0 else "unbilled",
            },
        )

        if budget_remaining is not None:
            result["budget_remaining_usd"] = round(budget_remaining - cost_estimate, 4) if cost_estimate else budget_remaining
        if credit_remaining_cents is not None:
            result["org_credits_remaining_cents"] = credit_remaining_cents
        if x_payment and x_payment != "required":
            _log_x402_interop_trace(
                raw_request,
                capability_id=capability_id,
                x_payment=x_payment,
                payment_trace=payment_trace,
                outcome="verified" if x402_receipt else "executed",
                response_status=200,
                provider=request.provider,
                payment_headers_set=False,
                execution_id=execution_id,
                agent_id=agent_id,
                org_id=org_id,
            )
        return {"data": result, "error": None}

    # ── Mode 3: Agent Vault (per-request token) ────────────────────
    if request.credential_mode == "agent_vault":
        from services.agent_vault import get_vault_validator
        validator = get_vault_validator()
        ceremony = await validator.get_ceremony(request.provider)

        if ceremony:
            is_valid, error_msg = validator.validate_format(
                x_agent_token,
                token_prefix=ceremony.get("token_prefix"),
                token_pattern=ceremony.get("token_pattern"),
            )
            if not is_valid:
                await _release_reservations()
                raise HTTPException(status_code=400, detail=f"Invalid token: {error_msg}")

        api_domain = await _get_service_domain(request.provider)
        if not api_domain:
            await _release_reservations()
            raise HTTPException(
                status_code=500,
                detail=f"No API domain for provider '{request.provider}'",
            )
        base_url = api_domain if api_domain.startswith("http") else f"https://{api_domain}"

        vault_headers: dict[str, str] = {}
        auth_type = ceremony.get("auth_type", "api_key") if ceremony else "api_key"

        if auth_type == "basic_auth":
            encoded = base64.b64encode(x_agent_token.encode()).decode()
            vault_headers["Authorization"] = f"Basic {encoded}"
        elif request.provider == "anthropic":
            vault_headers["x-api-key"] = x_agent_token
            vault_headers["anthropic-version"] = "2023-06-01"
        else:
            vault_headers["Authorization"] = f"Bearer {x_agent_token}"

        request_start = time.perf_counter()
        path = request.path if request.path.startswith("/") else f"/{request.path}"
        final_body, final_params = _prepare_upstream_payload(
            request.method,
            request.body,
            request.params,
        )

        try:
            async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
                upstream_start = time.perf_counter()
                resp = await client.request(
                    method=request.method,
                    url=path,
                    headers=vault_headers,
                    json=final_body,
                    params=final_params,
                )
                upstream_latency_ms = (time.perf_counter() - upstream_start) * 1000

            upstream_status = resp.status_code
            try:
                upstream_response = resp.json()
            except Exception:
                upstream_response = resp.text

            total_latency_ms = (time.perf_counter() - request_start) * 1000
            success = 200 <= upstream_status < 400
            billing_status = "billed"
            if not success:
                await _release_reservations()
                billing_status = "refunded"

            update_payload = {
                "provider_used": request.provider,
                "credential_mode": "agent_vault",
                "method": request.method,
                "path": request.path,
                "upstream_status": upstream_status,
                "success": success,
                "cost_estimate_usd": None,
                "cost_usd_cents": billed_cost_cents if billed_cost_cents > 0 else None,
                "upstream_cost_cents": upstream_cost_cents if upstream_cost_cents > 0 else None,
                "margin_cents": margin_cents if billed_cost_cents > 0 else None,
                "billing_status": billing_status,
                "total_latency_ms": round(total_latency_ms, 1),
                "upstream_latency_ms": round(upstream_latency_ms, 1),
                "fallback_attempted": False,
                "fallback_provider": None,
                "idempotency_key": request.idempotency_key,
                "error_message": None,
                "interface": request.interface,
            }
            updated = await supabase_patch(
                f"capability_executions?id=eq.{quote(execution_id)}",
                update_payload,
            )
            if not updated:
                await supabase_insert("capability_executions", {
                    "id": execution_id,
                    "agent_id": agent_id,
                    "capability_id": capability_id,
                    **update_payload,
                })

            vault_response = {
                "capability_id": capability_id,
                "provider_used": request.provider,
                "credential_mode": "agent_vault",
                "upstream_status": upstream_status,
                "upstream_response": upstream_response,
                "latency_ms": round(total_latency_ms, 1),
                "execution_id": execution_id,
            }
            if budget_remaining is not None:
                vault_response["budget_remaining_usd"] = round(budget_remaining, 4)
            if credit_remaining_cents is not None:
                vault_response["org_credits_remaining_cents"] = credit_remaining_cents

            if x_payment and x_payment != "required":
                _log_x402_interop_trace(
                    raw_request,
                    capability_id=capability_id,
                    x_payment=x_payment,
                    payment_trace=payment_trace,
                    outcome="verified" if x402_receipt else "executed",
                    response_status=200,
                    provider=request.provider,
                    payment_headers_set=False,
                    execution_id=execution_id,
                    agent_id=agent_id,
                    org_id=org_id,
                )
            return {"data": vault_response, "error": None}

        except httpx.HTTPError as e:
            await _release_reservations()
            raise HTTPException(
                status_code=502,
                detail=f"Upstream request failed: {e}",
            )

    # ── Mode 1 (BYO) continues below ────────────────────────────────
    mappings = cap_services
    if not mappings or selected_mapping is None:
        await _release_reservations()
        raise HTTPException(
            status_code=503,
            detail=f"No providers configured for capability '{capability_id}'",
        )

    chosen = selected_mapping
    fallback_attempted = False
    fallback_provider: Optional[str] = None

    provider_slug = chosen["service_slug"]
    # Normalize slug for proxy-layer lookups (SERVICE_REGISTRY, AuthInjector, CredentialStore)
    proxy_slug = normalize_slug(provider_slug)
    auth_method = chosen.get("auth_method")
    cost_per_call = float(chosen["cost_per_call"]) if chosen.get("cost_per_call") is not None else None

    path = request.path if request.path.startswith("/") else f"/{request.path}"

    api_domain = await _get_service_domain(provider_slug)
    base_url = _resolve_base_url(proxy_slug, api_domain, path)
    headers: dict[str, str] = {}
    headers = _inject_auth_headers(proxy_slug, auth_method, headers)

    request_start = time.perf_counter()
    upstream_status: Optional[int] = None
    upstream_response: Any = None
    upstream_latency_ms = 0.0
    success = False
    error_message: Optional[str] = None

    use_pool = proxy_slug in SERVICE_REGISTRY
    final_body, final_params = _prepare_upstream_payload(
        request.method,
        request.body,
        request.params,
    )

    try:
        if use_pool:
            pool = get_pool_manager()
            client = await pool.acquire(proxy_slug, agent_id, base_url=base_url)
            try:
                upstream_start = time.perf_counter()
                resp = await client.request(
                    method=request.method,
                    url=path,
                    headers=headers,
                    json=final_body,
                    params=final_params,
                )
                upstream_latency_ms = (time.perf_counter() - upstream_start) * 1000
            finally:
                await pool.release(proxy_slug, agent_id)
        else:
            async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
                upstream_start = time.perf_counter()
                resp = await client.request(
                    method=request.method,
                    url=path,
                    headers=headers,
                    json=final_body,
                    params=final_params,
                )
                upstream_latency_ms = (time.perf_counter() - upstream_start) * 1000

        upstream_status = resp.status_code
        try:
            upstream_response = resp.json()
        except Exception:
            upstream_response = resp.text

        success = 200 <= upstream_status < 400

        breaker = get_breaker_registry().get(proxy_slug, agent_id)
        if success:
            breaker.record_success(latency_ms=upstream_latency_ms)
        else:
            breaker.record_failure(status_code=upstream_status)

    except httpx.HTTPError as e:
        error_message = str(e)
        breaker = get_breaker_registry().get(proxy_slug, agent_id)
        breaker.record_failure()

        await _release_reservations()

        if not request.provider and len(mappings) > 1:
            remaining = [m for m in mappings if m["service_slug"] != provider_slug]
            fallback = await _auto_select_provider(remaining, agent_id)
            if fallback:
                fallback_attempted = True
                fallback_provider = fallback["service_slug"]

        raise HTTPException(
            status_code=502,
            detail=f"Upstream request failed: {error_message}",
        )

    total_latency_ms = (time.perf_counter() - request_start) * 1000

    # If upstream returned a server failure, refund reservations.
    billing_status = "billed"
    if not success:
        await _release_reservations()
        billing_status = "refunded"

    actual_upstream_cents = int(round(cost_per_call * 100)) if cost_per_call is not None else None
    actual_billed_cents = (
        int(round(actual_upstream_cents * 1.2)) if actual_upstream_cents is not None else None
    )
    actual_margin_cents = (
        (actual_billed_cents - actual_upstream_cents)
        if actual_billed_cents is not None and actual_upstream_cents is not None
        else None
    )

    update_payload = {
        "provider_used": provider_slug,
        "credential_mode": request.credential_mode,
        "method": request.method,
        "path": request.path,
        "upstream_status": upstream_status,
        "success": success,
        "cost_estimate_usd": cost_per_call,
        "cost_usd_cents": actual_billed_cents,
        "upstream_cost_cents": actual_upstream_cents,
        "margin_cents": actual_margin_cents,
        "billing_status": billing_status,
        "total_latency_ms": round(total_latency_ms, 1),
        "upstream_latency_ms": round(upstream_latency_ms, 1),
        "fallback_attempted": fallback_attempted,
        "fallback_provider": fallback_provider,
        "idempotency_key": request.idempotency_key,
        "error_message": error_message,
        "interface": request.interface,
    }
    updated = await supabase_patch(
        f"capability_executions?id=eq.{quote(execution_id)}",
        update_payload,
    )
    if not updated:
        await supabase_insert("capability_executions", {
            "id": execution_id,
            "agent_id": agent_id,
            "capability_id": capability_id,
            **update_payload,
        })

    response_data = {
        "capability_id": capability_id,
        "provider_used": provider_slug,
        "credential_mode": request.credential_mode,
        "upstream_status": upstream_status,
        "upstream_response": upstream_response,
        "cost_estimate_usd": cost_per_call,
        "latency_ms": round(total_latency_ms, 1),
        "fallback_attempted": fallback_attempted,
        "fallback_provider": fallback_provider,
        "execution_id": execution_id,
    }
    if budget_remaining is not None:
        response_data["budget_remaining_usd"] = round(budget_remaining, 4)
    if credit_remaining_cents is not None:
        response_data["org_credits_remaining_cents"] = credit_remaining_cents

    # ── Build response headers ──────────────────────────────────────
    response_headers: dict[str, str] = {}

    # x402 anonymous identity headers
    if is_x402_anonymous:
        response_headers["X-Rhumb-Auth"] = "x402-anonymous"
        if x402_wallet_address:
            response_headers["X-Rhumb-Wallet"] = x402_wallet_address
        if x402_rate_remaining is not None:
            response_headers["X-Rhumb-Rate-Remaining"] = str(x402_rate_remaining)

    # x402: attach receipt info and X-Payment-Response header
    if x402_receipt:
        response_data["x402_receipt"] = {
            "tx_hash": x402_receipt["tx_hash"],
            "verified": True,
        }
        response_headers["X-Payment-Response"] = json.dumps({
            "verified": True,
            "tx_hash": x402_receipt["tx_hash"],
        })

    if response_headers:
        response = JSONResponse(
            content={"data": response_data, "error": None},
            headers=response_headers,
        )
        if x_payment and x_payment != "required":
            _log_x402_interop_trace(
                raw_request,
                capability_id=capability_id,
                x_payment=x_payment,
                payment_trace=payment_trace,
                outcome="verified" if x402_receipt else "executed",
                response_status=response.status_code,
                provider=request.provider or provider_slug,
                payment_headers_set=bool(response_headers),
                execution_id=execution_id,
                agent_id=agent_id,
                org_id=org_id,
            )
        return response

    if x_payment and x_payment != "required":
        _log_x402_interop_trace(
            raw_request,
            capability_id=capability_id,
            x_payment=x_payment,
            payment_trace=payment_trace,
            outcome="verified" if x402_receipt else "executed",
            response_status=200,
            provider=request.provider or provider_slug,
            payment_headers_set=False,
            execution_id=execution_id,
            agent_id=agent_id,
            org_id=org_id,
        )
    return {"data": response_data, "error": None}


@router.get("/capabilities/{capability_id}/execute/estimate")
async def estimate_capability(
    capability_id: str,
    provider: Optional[str] = Query(None, description="Provider slug"),
    credential_mode: str = Query(
        "auto",
        description=(
            "Credential mode (auto, byo, rhumb_managed, agent_vault). "
            "'auto' uses rhumb_managed when available, falls back to byo."
        ),
    ),
    x_rhumb_key: Optional[str] = Header(None, alias="X-Rhumb-Key"),
) -> dict:
    """Dry-run cost estimate — returns provider selection, cost, and circuit state without executing.

    API key is optional. Without an API key the response still includes
    provider, cost, and circuit state but omits budget-specific fields.
    This lets x402 agents discover pricing before paying.
    """
    # Authenticate if API key provided; otherwise allow anonymous estimate
    agent_id: Optional[str] = None
    is_anonymous_estimate = False

    if x_rhumb_key:
        agent = await _get_identity_store().verify_api_key_with_agent(x_rhumb_key)
        if agent is None:
            raise HTTPException(status_code=401, detail="Invalid or expired Rhumb API key")
        agent_id = agent.agent_id
    else:
        is_anonymous_estimate = True
        agent_id = "x402_anonymous"

    cap = await _resolve_capability(capability_id)
    if cap is None:
        raise HTTPException(status_code=404, detail=f"Capability '{capability_id}' not found")

    mappings = await _get_capability_services(capability_id)
    if not mappings:
        raise HTTPException(
            status_code=503,
            detail=f"No providers configured for capability '{capability_id}'",
        )

    requested_credential_mode = credential_mode
    credential_mode, managed_mapping = await _resolve_auto_credential_mode(
        capability_id=capability_id,
        credential_mode=credential_mode,
        mappings=mappings,
        requested_provider=provider,
    )

    chosen: Optional[dict] = None
    if requested_credential_mode == "auto" and credential_mode == "rhumb_managed":
        chosen = managed_mapping
    elif provider:
        chosen = next(
            (
                m for m in mappings
                if _service_slug_matches(m.get("service_slug"), provider)
            ),
            None,
        )
        if chosen is None:
            raise HTTPException(
                status_code=503,
                detail=f"Provider '{provider}' not available for capability '{capability_id}'",
            )
    else:
        chosen = await _auto_select_provider(mappings, agent_id)
        if chosen is None:
            raise HTTPException(
                status_code=503,
                detail=f"No healthy providers available for capability '{capability_id}'",
            )

    provider_slug = chosen["service_slug"]
    proxy_slug = normalize_slug(provider_slug)
    cost_per_call = float(chosen["cost_per_call"]) if chosen.get("cost_per_call") is not None else None

    breaker = get_breaker_registry().get(proxy_slug, agent_id)
    circuit_state = breaker.state.value

    estimate_data: dict[str, Any] = {
        "capability_id": capability_id,
        "provider": provider_slug,
        "credential_mode": credential_mode,
        "cost_estimate_usd": cost_per_call,
        "circuit_state": circuit_state,
        "endpoint_pattern": chosen.get("endpoint_pattern"),
    }

    # Include budget status only for authenticated agents
    if not is_anonymous_estimate:
        budget_status = await _budget_enforcer.get_budget(agent_id)
        if budget_status.budget_usd is not None:
            estimate_data["budget_remaining_usd"] = budget_status.remaining_usd
            estimate_data["budget_period"] = budget_status.period
            can_afford = (
                cost_per_call is None
                or budget_status.remaining_usd is None
                or budget_status.remaining_usd >= cost_per_call
                or not budget_status.hard_limit
            )
            estimate_data["can_afford"] = can_afford

    return {"data": estimate_data, "error": None}
