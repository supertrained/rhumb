"""Capability execution route — execute capabilities through the proxy layer.

Agents call POST /v1/capabilities/{id}/execute with a provider-native payload.
The route resolves the provider, injects auth, proxies the request, and logs
the execution to capability_executions.
"""

from __future__ import annotations

import base64
import logging
import time
import uuid
from typing import Any, Optional
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from routes._supabase import supabase_fetch, supabase_insert
from routes.proxy import (
    SERVICE_REGISTRY,
    get_breaker_registry,
    get_pool_manager,
)
from services.budget_enforcer import BudgetEnforcer
from services.proxy_auth import AuthInjector, AuthInjectionRequest, get_auth_injector
from services.proxy_credentials import get_credential_store

_budget_enforcer = BudgetEnforcer()

logger = logging.getLogger(__name__)

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
    credential_mode: str = Field("byo", description="Credential mode (byo, rhumb_managed, agent_vault)")
    idempotency_key: Optional[str] = Field(None, description="Idempotency key to prevent duplicate execution")
    interface: str = Field("rest", description="Client interface (rest, mcp, cli, sdk)")


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
    """Pick the best provider from mappings using AN score + circuit health.

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

    # Score each mapping: AN score, penalise open circuits
    ranked: list[tuple[float, dict]] = []
    for m in mappings:
        slug = m["service_slug"]
        an_score = scores_by_slug.get(slug, 0.0)
        breaker = breaker_reg.get(slug, agent_id)
        if not breaker.allow_request():
            continue  # circuit open — skip
        ranked.append((an_score, m))

    if not ranked:
        return None

    ranked.sort(key=lambda t: -t[0])
    return ranked[0][1]


def _resolve_base_url(service_slug: str, api_domain: Optional[str]) -> str:
    """Build base URL: prefer hardcoded SERVICE_REGISTRY, then dynamic domain."""
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

@router.post("/capabilities/{capability_id}/execute")
async def execute_capability(
    capability_id: str,
    request: CapabilityExecuteRequest,
    x_rhumb_key: Optional[str] = Header(None, alias="X-Rhumb-Key"),
    x_agent_token: Optional[str] = Header(None, alias="X-Agent-Token"),
) -> dict:
    """Execute a capability through the proxy layer.

    Resolves provider, injects auth, proxies the request upstream,
    logs the execution, and returns the upstream response.
    """
    if not x_rhumb_key:
        raise HTTPException(status_code=401, detail="X-Rhumb-Key header required")

    agent_id = x_rhumb_key  # simplified — real auth resolves agent identity

    # 0. Pre-execution budget check
    # Estimate cost from capability_services for budget enforcement
    cost_estimate = 0.0
    cap_services = await _get_capability_services(capability_id)
    if cap_services:
        # Use the cheapest mapped cost as the budget reservation
        costs = [float(m["cost_per_call"]) for m in cap_services if m.get("cost_per_call") is not None]
        cost_estimate = min(costs) if costs else 0.0

    budget_result = await _budget_enforcer.check_and_decrement(agent_id, cost_estimate)
    if not budget_result.allowed:
        raise HTTPException(status_code=402, detail=budget_result.reason)

    budget_remaining = budget_result.remaining_usd

    # 1. Verify capability exists
    cap = await _resolve_capability(capability_id)
    if cap is None:
        # Release budget reservation since we're not executing
        if cost_estimate > 0:
            await _budget_enforcer.release(agent_id, cost_estimate)
        raise HTTPException(status_code=404, detail=f"Capability '{capability_id}' not found")

    # ── Mode 2: Rhumb-managed execution ──────────────────────────────
    if request.credential_mode == "rhumb_managed":
        from services.rhumb_managed import get_managed_executor
        executor = get_managed_executor()
        try:
            result = await executor.execute(
                capability_id=capability_id,
                agent_id=agent_id,
                body=request.body,
                params=request.params,
                service_slug=request.provider,
                interface=request.interface,
            )
        except Exception:
            # Release budget on failure
            if cost_estimate > 0:
                await _budget_enforcer.release(agent_id, cost_estimate)
            raise
        if budget_remaining is not None:
            result["budget_remaining_usd"] = round(budget_remaining - cost_estimate, 4) if cost_estimate else budget_remaining
        return {"data": result, "error": None}

    # ── Mode 3: Agent Vault (per-request token) ────────────────────
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

        # Validate token format
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
                raise HTTPException(status_code=400, detail=f"Invalid token: {error_msg}")

        # Resolve API domain
        api_domain = await _get_service_domain(request.provider)
        if not api_domain:
            raise HTTPException(
                status_code=500,
                detail=f"No API domain for provider '{request.provider}'",
            )
        base_url = api_domain if api_domain.startswith("http") else f"https://{api_domain}"

        # Build headers with agent's token (NEVER logged or persisted)
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

        # Execute
        execution_id = f"exec_{uuid.uuid4().hex}"
        request_start = time.perf_counter()
        path = request.path if request.path.startswith("/") else f"/{request.path}"

        try:
            async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
                upstream_start = time.perf_counter()
                resp = await client.request(
                    method=request.method,
                    url=path,
                    headers=vault_headers,
                    json=request.body,
                    params=request.params,
                )
                upstream_latency_ms = (time.perf_counter() - upstream_start) * 1000

            upstream_status = resp.status_code
            try:
                upstream_response = resp.json()
            except Exception:
                upstream_response = resp.text

            total_latency_ms = (time.perf_counter() - request_start) * 1000

            # Log execution (token is NEVER included)
            await supabase_insert("capability_executions", {
                "id": execution_id,
                "agent_id": agent_id,
                "capability_id": capability_id,
                "provider_used": request.provider,
                "credential_mode": "agent_vault",
                "method": request.method,
                "path": request.path,
                "upstream_status": upstream_status,
                "success": upstream_status < 500,
                "cost_estimate_usd": None,
                "total_latency_ms": round(total_latency_ms, 1),
                "upstream_latency_ms": round(upstream_latency_ms, 1),
                "fallback_attempted": False,
                "fallback_provider": None,
                "idempotency_key": request.idempotency_key,
                "error_message": None,
                "interface": request.interface,
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

            return {"data": vault_response, "error": None}

        except httpx.HTTPError as e:
            # Release budget on upstream failure
            if cost_estimate > 0:
                await _budget_enforcer.release(agent_id, cost_estimate)
            raise HTTPException(
                status_code=502,
                detail=f"Upstream request failed: {e}",
            )

    # ── Mode 1 (BYO) continues below ────────────────────────────────
    # Validate required fields for BYO mode
    if not request.method or not request.path:
        raise HTTPException(
            status_code=400,
            detail="method and path are required for byo credential mode",
        )

    # 2. Idempotency check
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

    # 3. Get capability service mappings
    mappings = await _get_capability_services(capability_id)
    if not mappings:
        raise HTTPException(
            status_code=503,
            detail=f"No providers configured for capability '{capability_id}'",
        )

    # 4. Resolve provider
    chosen: Optional[dict] = None
    fallback_attempted = False
    fallback_provider: Optional[str] = None

    if request.provider:
        # Explicit provider
        chosen = next((m for m in mappings if m["service_slug"] == request.provider), None)
        if chosen is None:
            raise HTTPException(
                status_code=503,
                detail=f"Provider '{request.provider}' not available for capability '{capability_id}'",
            )
        # Check circuit health
        breaker = get_breaker_registry().get(request.provider, agent_id)
        if not breaker.allow_request():
            raise HTTPException(
                status_code=503,
                detail=f"Provider '{request.provider}' circuit is open — try later",
            )
    else:
        # Auto-select best provider
        chosen = await _auto_select_provider(mappings, agent_id)
        if chosen is None:
            raise HTTPException(
                status_code=503,
                detail=f"No healthy providers available for capability '{capability_id}'",
            )

    provider_slug = chosen["service_slug"]
    auth_method = chosen.get("auth_method")
    cost_per_call = float(chosen["cost_per_call"]) if chosen.get("cost_per_call") is not None else None

    # 5. Resolve base URL
    api_domain = await _get_service_domain(provider_slug)
    base_url = _resolve_base_url(provider_slug, api_domain)

    # 6. Build request
    path = request.path if request.path.startswith("/") else f"/{request.path}"
    headers: dict[str, str] = {}
    headers = _inject_auth_headers(provider_slug, auth_method, headers)

    # 7. Execute upstream request
    execution_id = f"exec_{uuid.uuid4().hex}"
    request_start = time.perf_counter()
    upstream_status: Optional[int] = None
    upstream_response: Any = None
    upstream_latency_ms = 0.0
    success = False
    error_message: Optional[str] = None

    use_pool = provider_slug in SERVICE_REGISTRY

    try:
        if use_pool:
            pool = get_pool_manager()
            client = await pool.acquire(provider_slug, agent_id, base_url=base_url)
            try:
                upstream_start = time.perf_counter()
                resp = await client.request(
                    method=request.method,
                    url=path,
                    headers=headers,
                    json=request.body,
                    params=request.params,
                )
                upstream_latency_ms = (time.perf_counter() - upstream_start) * 1000
            finally:
                await pool.release(provider_slug, agent_id)
        else:
            async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
                upstream_start = time.perf_counter()
                resp = await client.request(
                    method=request.method,
                    url=path,
                    headers=headers,
                    json=request.body,
                    params=request.params,
                )
                upstream_latency_ms = (time.perf_counter() - upstream_start) * 1000

        upstream_status = resp.status_code
        try:
            upstream_response = resp.json()
        except Exception:
            upstream_response = resp.text

        success = upstream_status < 500

        # Record circuit breaker outcome
        breaker = get_breaker_registry().get(provider_slug, agent_id)
        if success:
            breaker.record_success(latency_ms=upstream_latency_ms)
        else:
            breaker.record_failure(status_code=upstream_status)

    except httpx.HTTPError as e:
        error_message = str(e)
        breaker = get_breaker_registry().get(provider_slug, agent_id)
        breaker.record_failure()

        # Release budget reservation on failure
        if cost_estimate > 0:
            await _budget_enforcer.release(agent_id, cost_estimate)

        # Attempt fallback if auto-selected
        if not request.provider and len(mappings) > 1:
            remaining = [m for m in mappings if m["service_slug"] != provider_slug]
            fallback = await _auto_select_provider(remaining, agent_id)
            if fallback:
                fallback_attempted = True
                fallback_provider = fallback["service_slug"]
                # NOTE: fallback execution is logged but not attempted in this slice
                # to keep complexity bounded. Future: recursive execute.

        raise HTTPException(
            status_code=502,
            detail=f"Upstream request failed: {error_message}",
        )

    total_latency_ms = (time.perf_counter() - request_start) * 1000

    # 8. Log execution
    await supabase_insert("capability_executions", {
        "id": execution_id,
        "agent_id": agent_id,
        "capability_id": capability_id,
        "provider_used": provider_slug,
        "credential_mode": request.credential_mode,
        "method": request.method,
        "path": request.path,
        "upstream_status": upstream_status,
        "success": success,
        "cost_estimate_usd": cost_per_call,
        "total_latency_ms": round(total_latency_ms, 1),
        "upstream_latency_ms": round(upstream_latency_ms, 1),
        "fallback_attempted": fallback_attempted,
        "fallback_provider": fallback_provider,
        "idempotency_key": request.idempotency_key,
        "error_message": error_message,
        "interface": request.interface,
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

    return {"data": response_data, "error": None}


@router.get("/capabilities/{capability_id}/execute/estimate")
async def estimate_capability(
    capability_id: str,
    provider: Optional[str] = Query(None, description="Provider slug"),
    credential_mode: str = Query("byo", description="Credential mode"),
    x_rhumb_key: Optional[str] = Header(None, alias="X-Rhumb-Key"),
) -> dict:
    """Dry-run cost estimate — returns provider selection, cost, and circuit state without executing."""
    if not x_rhumb_key:
        raise HTTPException(status_code=401, detail="X-Rhumb-Key header required")

    agent_id = x_rhumb_key

    cap = await _resolve_capability(capability_id)
    if cap is None:
        raise HTTPException(status_code=404, detail=f"Capability '{capability_id}' not found")

    mappings = await _get_capability_services(capability_id)
    if not mappings:
        raise HTTPException(
            status_code=503,
            detail=f"No providers configured for capability '{capability_id}'",
        )

    chosen: Optional[dict] = None
    if provider:
        chosen = next((m for m in mappings if m["service_slug"] == provider), None)
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
    cost_per_call = float(chosen["cost_per_call"]) if chosen.get("cost_per_call") is not None else None

    breaker = get_breaker_registry().get(provider_slug, agent_id)
    circuit_state = breaker.state.value

    # Include budget status in estimate
    budget_status = await _budget_enforcer.get_budget(agent_id)
    estimate_data: dict[str, Any] = {
        "capability_id": capability_id,
        "provider": provider_slug,
        "credential_mode": credential_mode,
        "cost_estimate_usd": cost_per_call,
        "circuit_state": circuit_state,
        "endpoint_pattern": chosen.get("endpoint_pattern"),
    }
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
