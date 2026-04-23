"""Capability execution route — execute capabilities through the proxy layer.

Agents call POST /v1/capabilities/{id}/execute with a provider-native payload.
The route resolves the provider, injects auth, proxies the request, and logs
the execution to capability_executions.

Supports two authentication paths:
  1. **Registered agent** — ``X-Rhumb-Key`` header (existing API-key flow).
  2. **x402 anonymous** — ``X-Payment`` header with on-chain USDC payment.
     No API key or signup required; identity is derived from wallet address.
     Rate-limited per wallet to prevent abuse.

Routed execute capabilities can use either path. Direct AUD-18 system-of-record
execute rails currently require ``X-Rhumb-Key`` and return auth-only recovery
guidance instead of x402 payment discovery.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
import uuid
from typing import Any, Optional
from urllib.parse import quote, urlencode

import httpx
from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from routes._supabase import (
    SupabaseWriteUnavailable,
    supabase_fetch,
    supabase_insert,
    supabase_insert_required,
    supabase_patch,
    supabase_patch_required,
)
from routes.proxy import (
    SERVICE_REGISTRY,
    get_breaker_registry,
    get_pool_manager,
    normalize_slug,
)
from schemas.agent_identity import AgentIdentityStore, get_agent_identity_store
from schemas.db_capabilities import (
    DbAgentVaultTokenizeRequest,
    DbAgentVaultTokenizeResponse,
)
from services.audit_trail import AuditEventType, get_audit_trail
from services.auto_reload import check_and_trigger_auto_reload
from services.billing_events import BillingEventType, get_billing_event_stream
from services.budget_enforcer import BudgetEnforcer
from services.credit_deduction import CreditDeductionService
from services.payment_health import check_billing_health
from services.payment_metrics import log_payment_event
from services.payment_requests import PaymentRequestService
from services.durable_idempotency import DurableIdempotencyStore, IdempotencyUnavailable
from services.durable_rate_limit import DurableRateLimiter
from services.durable_replay_guard import DurableReplayGuard, ReplayGuardUnavailable
from services.kill_switches import init_kill_switch_registry
from services.x402 import PaymentRequiredException, build_x402_response
from services.x402_middleware import decode_x_payment_header, inspect_x_payment_header
from services.x402_settlement import (
    X402FacilitatorNotConfigured,
    X402SettlementFailed,
    X402SettlementService,
    X402VerificationFailed,
)
from services.usdc_verifier import verify_usdc_payment
from services.proxy_auth import AuthInjector, AuthInjectionRequest, get_auth_injector
from services.proxy_credentials import get_credential_store
from services.routing_engine import RoutingEngine
from services.receipt_service import (
    ReceiptInput,
    get_receipt_service,
    hash_caller_ip,
    hash_request_payload,
    hash_response_payload,
)
from services.provider_attribution import build_attribution
from services.service_slugs import (
    canonicalize_service_slug,
    normalize_proxy_slug,
    public_service_slug,
    public_service_slug_candidates,
)
from services.db_connection_registry import AgentVaultDsnError, issue_agent_vault_dsn_token

_budget_enforcer = BudgetEnforcer()
_credit_deduction = CreditDeductionService()
_payment_requests = PaymentRequestService()
_x402_settlement = X402SettlementService()
_routing_engine = RoutingEngine()
_identity_store: Optional[AgentIdentityStore] = None
_durable_replay_guard: DurableReplayGuard | None = None
_durable_rate_limiter: DurableRateLimiter | None = None
_durable_idempotency_store: DurableIdempotencyStore | None = None


def _get_identity_store() -> AgentIdentityStore:
    """Lazy-init identity store (matches proxy.py pattern)."""
    global _identity_store
    if _identity_store is None:
        _identity_store = get_agent_identity_store()
    return _identity_store


async def _get_replay_guard() -> DurableReplayGuard:
    global _durable_replay_guard
    if _durable_replay_guard is None:
        from db.client import get_supabase_client

        supabase = await get_supabase_client()
        _durable_replay_guard = DurableReplayGuard(supabase)
    return _durable_replay_guard


async def _get_rate_limiter() -> DurableRateLimiter:
    global _durable_rate_limiter
    if _durable_rate_limiter is None:
        from db.client import get_supabase_client

        try:
            supabase = await get_supabase_client()
        except Exception:
            logger.warning(
                "durable_rate_limiter_init_failed falling back to local emergency limiter",
                exc_info=True,
            )

            class _UnavailableSupabaseClient:
                def rpc(self, *_args, **_kwargs):
                    raise RuntimeError("supabase_unavailable")

                def table(self, *_args, **_kwargs):
                    raise RuntimeError("supabase_unavailable")

            supabase = _UnavailableSupabaseClient()

        _durable_rate_limiter = DurableRateLimiter(supabase)
    return _durable_rate_limiter


async def _get_idempotency_store() -> DurableIdempotencyStore:
    global _durable_idempotency_store
    if _durable_idempotency_store is None:
        from db.client import get_supabase_client

        supabase = await get_supabase_client()
        _durable_idempotency_store = DurableIdempotencyStore(supabase)
    return _durable_idempotency_store

logger = logging.getLogger(__name__)


CRM_CAPABILITY_IDS = frozenset({"crm.object.describe", "crm.record.search", "crm.record.get"})
ACTIONS_CAPABILITY_IDS = frozenset({"workflow_run.list", "workflow_run.get"})
DB_CAPABILITY_IDS = frozenset({"db.query.read", "db.schema.describe", "db.row.get"})
WAREHOUSE_CAPABILITY_IDS = frozenset({"warehouse.query.read", "warehouse.schema.describe"})
DEPLOYMENT_CAPABILITY_IDS = frozenset({"deployment.list", "deployment.get"})
STORAGE_CAPABILITY_IDS = frozenset({"object.list", "object.head", "object.get"})
SUPPORT_CAPABILITY_IDS = frozenset(
    {
        "ticket.search",
        "ticket.get",
        "ticket.list_comments",
        "conversation.list",
        "conversation.get",
        "conversation.list_parts",
    }
)
DIRECT_EXECUTE_CAPABILITY_IDS = frozenset(
    CRM_CAPABILITY_IDS
    | ACTIONS_CAPABILITY_IDS
    | DB_CAPABILITY_IDS
    | WAREHOUSE_CAPABILITY_IDS
    | DEPLOYMENT_CAPABILITY_IDS
    | STORAGE_CAPABILITY_IDS
    | SUPPORT_CAPABILITY_IDS
)
_VALID_EXECUTE_CREDENTIAL_MODES = frozenset({"auto", "byok", "rhumb_managed", "agent_vault"})


def _direct_execute_auth_detail(capability_id: str) -> str | None:
    if capability_id in CRM_CAPABILITY_IDS:
        return "X-Rhumb-Key header required for CRM capability execution"
    if capability_id in ACTIONS_CAPABILITY_IDS:
        return "X-Rhumb-Key header required for GitHub Actions capability execution"
    if capability_id in DB_CAPABILITY_IDS:
        return "X-Rhumb-Key header required for database capability execution"
    if capability_id in WAREHOUSE_CAPABILITY_IDS:
        return "X-Rhumb-Key header required for warehouse capability execution"
    if capability_id in DEPLOYMENT_CAPABILITY_IDS:
        return "X-Rhumb-Key header required for deployment capability execution"
    if capability_id in STORAGE_CAPABILITY_IDS:
        return "X-Rhumb-Key header required for storage capability execution"
    if capability_id in SUPPORT_CAPABILITY_IDS:
        return "X-Rhumb-Key header required for support capability execution"
    return None


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


async def _capability_not_found_response(raw_request: Request, capability_id: str) -> JSONResponse:
    """Reuse the capability-registry 404 envelope so execute surfaces share suggestions/search links."""
    from routes.capabilities import _capability_not_found

    return await _capability_not_found(raw_request, capability_id)


def _capability_resolve_url(capability_id: str, *, credential_mode: str | None = None) -> str:
    """Build a resolve URL that helps callers inspect provider options for a capability."""
    url = f"/v1/capabilities/{quote(capability_id, safe='')}/resolve"
    normalized_mode = _canonicalize_credential_mode(credential_mode)
    if normalized_mode:
        url += f"?credential_mode={quote(normalized_mode, safe='')}"
    return url


def _capability_estimate_url(
    capability_id: str,
    *,
    provider: str | None = None,
    credential_mode: str | None = None,
) -> str:
    """Build an estimate URL that helps callers inspect cost for a concrete option."""
    url = f"/v1/capabilities/{quote(capability_id, safe='')}/execute/estimate"
    params: list[tuple[str, str]] = []
    if provider:
        params.append(("provider", provider))
    normalized_mode = _canonicalize_credential_mode(credential_mode)
    if normalized_mode:
        params.append(("credential_mode", normalized_mode))
    if params:
        url += f"?{urlencode(params)}"
    return url


def _capability_credential_modes_url(capability_id: str) -> str:
    """Build a credential-modes URL for a capability."""
    return f"/v1/capabilities/{quote(capability_id, safe='')}/credential-modes"


def _provider_option_summaries(mappings: list[dict]) -> list[dict[str, Any]]:
    """Return stable provider summaries for recovery/error responses."""
    options: list[dict[str, Any]] = []
    seen: set[str] = set()
    for mapping in mappings:
        provider = str(mapping.get("service_slug") or "").strip()
        public_provider = _public_provider_slug(provider) or provider
        if not public_provider or public_provider in seen:
            continue
        modes = _parse_credential_modes(mapping.get("credential_modes") or ["byok"]) or ["byok"]
        options.append(
            {
                "provider": public_provider,
                "credential_modes": modes,
            }
        )
        seen.add(public_provider)
    return options


def _matching_provider_mapping(mappings: list[dict], provider: str | None) -> dict | None:
    """Return the mapping row for a requested provider slug, if present."""
    if not provider:
        return None
    return next(
        (
            mapping
            for mapping in mappings
            if _service_slug_matches(mapping.get("service_slug"), provider)
        ),
        None,
    )


def _execute_auth_handoff(
    capability_id: str,
    *,
    supported_paths: tuple[str, ...] = ("governed_api_key", "wallet_prefund", "x402_per_call"),
    reason: str = "auth_or_payment_required",
) -> dict[str, Any]:
    """Return machine-readable next-step guidance when execute is blocked on auth/payment."""
    execute_url = f"/v1/capabilities/{quote(capability_id, safe='')}/execute"
    path_options: dict[str, dict[str, Any]] = {
        "governed_api_key": {
            "kind": "governed_api_key",
            "recommended": True,
            "setup_url": "/auth/login",
            "retry_header": "X-Rhumb-Key",
            "summary": "Default for most buyers and most repeat agent traffic.",
            "requires_human_setup": True,
            "automatic_after_setup": True,
        },
        "wallet_prefund": {
            "kind": "wallet_prefund",
            "recommended": False,
            "setup_url": "/payments/agent",
            "retry_header": "X-Rhumb-Key",
            "summary": "Best when wallet identity matters and the same wallet will call repeatedly.",
            "requires_human_setup": True,
            "automatic_after_setup": True,
        },
        "x402_per_call": {
            "kind": "x402_per_call",
            "recommended": False,
            "setup_url": "/payments/agent",
            "retry_header": "X-Payment",
            "summary": "Use when request-level payment authorization is the point and the runtime can pay from a wallet.",
            "requires_human_setup": True,
            "automatic_after_setup": True,
            "requires_wallet_support": True,
        },
    }
    paths = [path_options[kind] for kind in supported_paths if kind in path_options]
    recommended_path = next(
        (
            path.get("kind")
            for path in paths
            if path.get("recommended") is True and isinstance(path.get("kind"), str)
        ),
        paths[0]["kind"] if paths else None,
    )
    return {
        "reason": reason,
        "recommended_path": recommended_path,
        "retry_url": execute_url,
        "docs_url": "/docs#resolve-mental-model",
        "paths": paths,
    }


def _direct_execute_auth_required_response(
    raw_request: Request,
    *,
    capability_id: str,
    detail: str,
) -> JSONResponse:
    """Return a structured auth handoff for direct execute rails that require API keys."""
    request_id = getattr(raw_request.state, "request_id", None) or str(uuid.uuid4())
    execute_url = f"/v1/capabilities/{quote(capability_id, safe='')}/execute"
    return JSONResponse(
        status_code=401,
        content={
            "error": "authentication_required",
            "message": detail,
            "resolution": (
                "Create or use a funded governed API key at /auth/login, then retry "
                "this execute call with X-Rhumb-Key. Use resolve first if you need "
                "to inspect the current preferred rail."
            ),
            "request_id": request_id,
            "execute_url": execute_url,
            "resolve_url": _capability_resolve_url(capability_id),
            "credential_modes_url": _capability_credential_modes_url(capability_id),
            "auth_handoff": _execute_auth_handoff(
                capability_id,
                supported_paths=("governed_api_key",),
                reason="auth_required",
            ),
        },
    )


def _direct_execute_get_not_supported_response(
    raw_request: Request,
    *,
    capability_id: str,
) -> JSONResponse:
    """Direct execute rails use POST after auth, not GET x402 discovery."""
    request_id = getattr(raw_request.state, "request_id", None) or str(uuid.uuid4())
    execute_url = f"/v1/capabilities/{quote(capability_id, safe='')}/execute"
    return JSONResponse(
        status_code=405,
        headers={"Allow": "POST"},
        content={
            "error": "method_not_allowed",
            "message": "Direct capability execute discovery is POST-only after API-key auth.",
            "resolution": (
                "Retry with POST and X-Rhumb-Key. Use resolve or credential-modes if you need "
                "setup guidance before executing."
            ),
            "request_id": request_id,
            "execute_url": execute_url,
            "resolve_url": _capability_resolve_url(capability_id),
            "credential_modes_url": _capability_credential_modes_url(capability_id),
            "auth_handoff": _execute_auth_handoff(
                capability_id,
                supported_paths=("governed_api_key",),
                reason="post_required",
            ),
        },
    )


def _invalid_governed_api_key_response(
    raw_request: Request,
    *,
    capability_id: str,
) -> JSONResponse:
    """Return a structured 401 that preserves the legacy FastAPI `detail` field.

    Some clients key off the default `{detail: ...}` shape. We keep that key
    while also returning the richer auth-handoff envelope used elsewhere.
    """
    request_id = getattr(raw_request.state, "request_id", None) or str(uuid.uuid4())
    execute_url = f"/v1/capabilities/{quote(capability_id, safe='')}/execute"
    detail = "Invalid or expired governed API key"
    return JSONResponse(
        status_code=401,
        content={
            "detail": detail,
            "error": "invalid_api_key",
            "message": detail,
            "resolution": "Create or use a funded governed API key at /auth/login, then retry.",
            "request_id": request_id,
            "execute_url": execute_url,
            "resolve_url": _capability_resolve_url(capability_id),
            "credential_modes_url": _capability_credential_modes_url(capability_id),
            "auth_handoff": _execute_auth_handoff(
                capability_id,
                supported_paths=("governed_api_key",),
                reason="invalid_api_key",
            ),
        },
    )


def _direct_execute_estimate_readiness(capability_id: str) -> dict[str, Any] | None:
    """Return auth guidance when estimate is anonymous but execute still needs an API key."""
    detail = _direct_execute_auth_detail(capability_id)
    if detail is None:
        return None
    execute_url = f"/v1/capabilities/{quote(capability_id, safe='')}/execute"
    return {
        "status": "auth_required",
        "message": detail,
        "resolution": (
            "Create or use a funded governed API key at /auth/login, then retry "
            "this execute call with X-Rhumb-Key. Use resolve first if you need "
            "to inspect the current preferred rail."
        ),
        "execute_url": execute_url,
        "resolve_url": _capability_resolve_url(capability_id),
        "credential_modes_url": _capability_credential_modes_url(capability_id),
        "auth_handoff": _execute_auth_handoff(
            capability_id,
            supported_paths=("governed_api_key",),
            reason="auth_required",
        ),
    }


def _execute_recovery_hints(
    *,
    capability_id: str,
    mappings: list[dict],
    credential_mode: str | None = None,
    requested_provider: str | None = None,
    selected_mapping: dict | None = None,
) -> dict[str, Any]:
    """Return stable resolve/estimate/provider hints for execute-time recovery."""
    effective_provider_raw = requested_provider or (
        str(selected_mapping.get("service_slug") or "").strip()
        if isinstance(selected_mapping, dict)
        else None
    )
    effective_provider = (
        (_public_provider_slug(effective_provider_raw) or effective_provider_raw)
        if effective_provider_raw
        else None
    )
    effective_mode = credential_mode if credential_mode and credential_mode != "auto" else None
    requested_mapping = _matching_provider_mapping(mappings, effective_provider_raw or effective_provider)
    target_mapping = requested_mapping or selected_mapping

    hints: dict[str, Any] = {
        "resolve_url": _capability_resolve_url(capability_id, credential_mode=effective_mode),
        "estimate_url": _capability_estimate_url(
            capability_id,
            provider=effective_provider,
            credential_mode=effective_mode,
        ),
        "available_providers": _provider_option_summaries(mappings),
        "auth_handoff": _execute_auth_handoff(capability_id),
    }
    if effective_mode:
        hints["credential_mode"] = effective_mode
    if effective_provider:
        hints["requested_provider"] = effective_provider

    requested_modes = _parse_credential_modes(
        target_mapping.get("credential_modes") if isinstance(target_mapping, dict) else []
    )
    if requested_modes:
        hints["requested_provider_credential_modes"] = requested_modes

    return hints


def _managed_provider_unavailable_response(
    raw_request: Request,
    *,
    capability_id: str,
    mappings: list[dict],
    requested_provider: str | None,
    available_managed_mappings: list[dict] | None = None,
) -> JSONResponse:
    """Return a structured 503 with managed-provider alternatives when available."""
    request_id = getattr(raw_request.state, "request_id", None) or f"req_{uuid.uuid4().hex[:12]}"
    requested_mapping = _matching_provider_mapping(mappings, requested_provider)
    available_providers = _provider_option_summaries(available_managed_mappings or [])

    if requested_provider:
        public_requested_provider = _public_provider_label(requested_provider)
        requested_slug = _public_provider_slug(requested_provider) or requested_provider
        content: dict[str, Any] = {
            "error": "provider_not_available",
            "message": (
                f"Provider '{public_requested_provider}' is not available for capability "
                f"'{capability_id}' with credential_mode 'rhumb_managed'"
            ),
            "resolution": (
                "Retry without provider to auto-select a managed provider, choose one "
                "of the available managed providers, or switch to credential_mode: byok "
                "if you want to use your own API key."
            ),
            "credential_mode": "rhumb_managed",
            "requested_provider": requested_slug,
            "available_providers": available_providers,
            "resolve_url": _capability_resolve_url(capability_id, credential_mode="rhumb_managed"),
            "request_id": request_id,
        }
        requested_modes = _parse_credential_modes(
            requested_mapping.get("credential_modes") if requested_mapping else []
        )
        if requested_modes:
            content["requested_provider_credential_modes"] = requested_modes
        return JSONResponse(status_code=503, content=content)

    return JSONResponse(
        status_code=503,
        content={
            "error": "managed_provider_unavailable",
            "message": f"No managed providers available for capability '{capability_id}'",
            "resolution": (
                "Retry with credential_mode: byok using your own API key, or inspect the "
                "resolve surface for currently supported providers."
            ),
            "credential_mode": "rhumb_managed",
            "available_providers": available_providers,
            "resolve_url": _capability_resolve_url(capability_id, credential_mode="rhumb_managed"),
            "request_id": request_id,
        },
    )


def _billing_unavailable_response(
    raw_request: Request,
    *,
    detail: str | None = None,
) -> JSONResponse:
    request_id = getattr(raw_request.state, "request_id", None) or str(uuid.uuid4())
    content: dict[str, Any] = {
        "error": "billing_unavailable",
        "message": "Billing system temporarily unavailable. Execution blocked for safety.",
        "resolution": "Retry in 30 seconds. If persistent, check https://rhumb.dev/status",
        "request_id": request_id,
    }
    if detail:
        content["detail"] = detail
    return JSONResponse(status_code=503, content=content)


def _emit_execution_billing_event(
    *,
    success: bool,
    org_id: str | None,
    execution_id: str,
    capability_id: str,
    provider_slug: str | None,
    credential_mode: str,
    amount_usd_cents: int | None,
    receipt_id: str | None = None,
    interface: str | None = None,
    billing_status: str | None = None,
    error_message: str | None = None,
) -> None:
    """Best-effort durable billing event emission for live execution outcomes."""
    if not org_id:
        return

    metadata: dict[str, Any] = {
        "layer": 2,
        "credential_mode": credential_mode,
    }
    if interface:
        metadata["interface"] = interface
    if billing_status:
        metadata["billing_status"] = billing_status
    if error_message:
        metadata["error"] = str(error_message)[:200]

    try:
        get_billing_event_stream().emit(
            BillingEventType.EXECUTION_CHARGED if success else BillingEventType.EXECUTION_FAILED_NO_CHARGE,
            org_id=org_id,
            amount_usd_cents=max(int(amount_usd_cents or 0), 0) if success else 0,
            receipt_id=receipt_id,
            execution_id=execution_id,
            capability_id=capability_id,
            provider_slug=provider_slug,
            metadata=metadata,
        )
    except Exception:
        logger.exception(
            "execution_billing_event_emission_failed execution_id=%s provider=%s",
            execution_id,
            provider_slug,
        )


def _record_execution_audit_outcome(
    *,
    success: bool,
    org_id: str | None,
    agent_id: str | None,
    execution_id: str,
    capability_id: str,
    provider_slug: str | None,
    credential_mode: str,
    interface: str,
    upstream_status: int | None,
    receipt_id: str | None = None,
    billing_status: str | None = None,
    latency_ms: float | None = None,
    error_message: str | None = None,
) -> None:
    """Best-effort durable audit recording for live execution outcomes."""
    detail: dict[str, Any] = {
        "capability_id": capability_id,
        "credential_mode": credential_mode,
        "interface": interface,
    }
    if upstream_status is not None:
        detail["upstream_status"] = upstream_status
    if billing_status is not None:
        detail["billing_status"] = billing_status
    if latency_ms is not None:
        detail["latency_ms"] = round(latency_ms, 1)
    if error_message:
        detail["error"] = str(error_message)[:300]

    try:
        get_audit_trail().record(
            AuditEventType.EXECUTION_COMPLETED if success else AuditEventType.EXECUTION_FAILED,
            "capability.execute",
            org_id=org_id,
            agent_id=agent_id,
            principal=agent_id,
            resource_type="capability_execution",
            resource_id=execution_id,
            detail=detail,
            receipt_id=receipt_id,
            execution_id=execution_id,
            provider_slug=provider_slug,
        )
    except Exception:
        logger.exception(
            "execution_audit_record_failed execution_id=%s provider=%s",
            execution_id,
            provider_slug,
        )


async def _create_payment_request_safe(
    *,
    org_id: str | None,
    capability_id: str,
    amount_usd_cents: int,
    execution_id: str | None = None,
) -> dict | None:
    """Best-effort payment request creation for x402 discovery / settlement tracking."""
    if amount_usd_cents <= 0:
        return None
    try:
        return await _payment_requests.create_payment_request(
            org_id=org_id,
            capability_id=capability_id,
            amount_usd_cents=amount_usd_cents,
            execution_id=execution_id,
        )
    except ValueError as exc:
        logger.info(
            "x402_payment_request_skipped capability_id=%s execution_id=%s reason=%s",
            capability_id,
            execution_id,
            exc,
        )
    except Exception as exc:
        logger.warning(
            "x402_payment_request_failed capability_id=%s execution_id=%s error=%s",
            capability_id,
            execution_id,
            exc,
        )
    return None


def _normalize_x402_payment_header(
    x_payment: str | None,
    payment_signature: str | None,
) -> str | None:
    """Bridge PAYMENT-SIGNATURE into the existing X-Payment flow when needed."""
    if payment_signature and (not x_payment or x_payment == "required"):
        logger.info("x402_payment_signature_bridged")
        return payment_signature
    return x_payment


def _extract_standard_x402_authorization(payment_data: dict[str, Any] | None) -> dict[str, Any] | None:
    payload = payment_data.get("payload") if isinstance(payment_data, dict) else None
    if not isinstance(payload, dict):
        return None
    authorization = payload.get("authorization")
    return authorization if isinstance(authorization, dict) else None


def _extract_standard_x402_payment_request_id(payment_data: dict[str, Any] | None) -> str | None:
    if not isinstance(payment_data, dict):
        return None
    accepted = payment_data.get("accepted")
    accepted_extra = accepted.get("extra") if isinstance(accepted, dict) else None
    for candidate in (
        payment_data.get("paymentRequestId"),
        payment_data.get("payment_request_id"),
        accepted_extra.get("paymentRequestId") if isinstance(accepted_extra, dict) else None,
        accepted_extra.get("payment_request_id") if isinstance(accepted_extra, dict) else None,
    ):
        if candidate:
            return str(candidate)
    return None


def _build_standard_x402_payment_requirements(
    *,
    capability_id: str,
    cost_usd_cents: int,
    payment_request: dict | None,
) -> dict[str, Any]:
    api_base = os.environ.get("API_BASE_URL", "https://api.rhumb.dev")
    response = build_x402_response(
        capability_id=capability_id,
        cost_usd_cents=cost_usd_cents,
        resource_url=f"{api_base}/v1/capabilities/{capability_id}/execute",
        payment_request=payment_request,
    )
    exact_option = next(
        (option for option in response.get("accepts", []) if option.get("scheme") == "exact"),
        None,
    )
    if exact_option is not None:
        return exact_option
    if payment_request:
        return {
            "scheme": "exact",
            "network": payment_request.get("network"),
            "maxAmountRequired": payment_request.get("amount_usdc_atomic"),
            "amount": payment_request.get("amount_usdc_atomic"),
            "resource": f"{api_base}/v1/capabilities/{capability_id}/execute",
            "description": f"Rhumb capability execution: {capability_id}",
            "mimeType": "application/json",
            "payTo": payment_request.get("pay_to_address"),
            "maxTimeoutSeconds": 300,
            "asset": payment_request.get("asset_address"),
            "extra": {
                "name": "USD Coin",
                "version": "2",
                "paymentRequestId": payment_request.get("id"),
            },
        }
    raise ValueError("No x402 exact payment option available for this capability")


def _build_standard_x402_payment_response_header(settle_response: dict[str, Any]) -> str:
    return base64.b64encode(
        json.dumps(settle_response, separators=(",", ":")).encode("utf-8")
    ).decode("utf-8")


def _build_x402_compatibility_error_response(
    raw_request: Request,
    *,
    payment_trace: dict[str, Any],
) -> JSONResponse:
    """Return a structured error for detected-but-unsupported x402 proof formats."""
    request_id = _request_id(raw_request)
    network = payment_trace.get("declared_network")
    resolution = (
        "Retry with an X-Payment proof containing tx_hash, network, and wallet_address, "
        "or use a funded governed API key via /auth/login. If you need wallet setup guidance, "
        "use /payments/agent. Rhumb does not currently support settling standard x402 "
        "authorization payloads on Base mainnet, and the public x402 facilitator is not "
        "integrated here."
    )
    if network in ("base-sepolia", "evm:84532"):
        resolution = (
            "Retry with an X-Payment proof containing tx_hash, network, and wallet_address, "
            "or use a funded governed API key via /auth/login. If you need wallet setup guidance, "
            "use /payments/agent. Rhumb does not currently settle standard x402 authorization "
            "payloads in this execute path."
        )

    return JSONResponse(
        status_code=422,
        content={
            "error": "x402_proof_format_unsupported",
            "message": (
                "Detected a standard x402 authorization payload, but this execute endpoint "
                "currently verifies direct USDC transfer receipts by tx_hash."
            ),
            "resolution": resolution,
            "request_id": request_id,
            "compatibility": {
                "detected_format": payment_trace.get("proof_format"),
                "supported_formats": ["legacy_tx_hash"],
                "network": network,
                "scheme": payment_trace.get("declared_scheme"),
                "payer": payment_trace.get("declared_from"),
                "pay_to": payment_trace.get("declared_to"),
                "standard_authorization_supported": False,
            },
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
        "provider": _public_provider_slug(provider) or provider,
        "agent_id": agent_id,
        "org_id": org_id,
        "execution_id": execution_id,
        "x_payment_present": bool(x_payment and x_payment != "required"),
        "x_payment_parse_mode": trace.get("parse_mode", "missing"),
        "x_payment_top_level_keys": trace.get("top_level_keys", []),
        "x_payment_proof_format": trace.get("proof_format", "unknown"),
        "x_payment_network": trace.get("declared_network"),
        "x_payment_scheme": trace.get("declared_scheme"),
        "branch_outcome": outcome,
        "response_status": response_status,
        "payment_headers_set": payment_headers_set,
    }
    if extra:
        payload.update(extra)

    payload = {k: v for k, v in payload.items() if v is not None}
    logger.info(
        "x402_interop_trace %s",
        json.dumps(payload, sort_keys=True, default=str),
        extra={"x402_interop": payload},
    )


# ---------------------------------------------------------------------------
# x402 anonymous wallet rate limiter (durable, cross-worker)
# ---------------------------------------------------------------------------

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
# Per-agent execution rate limiter (durable, cross-worker)
# Prevents abuse of managed credentials and general execution flooding.
# ---------------------------------------------------------------------------

_AGENT_EXEC_RATE_LIMIT = 30   # requests per minute per agent (all modes)
_AGENT_EXEC_RATE_WINDOW = 60  # seconds

_MANAGED_DAILY_LIMIT = 200    # managed executions per day per agent
_MANAGED_DAILY_WINDOW = 86400  # 24 hours


async def _check_rate_limit(
    namespace: str,
    subject: str,
    limit: int,
    window_seconds: int,
) -> tuple[bool, int]:
    limiter = await _get_rate_limiter()
    normalized = subject.lower().strip()
    key = f"{namespace}:{normalized}"
    return await limiter.check_and_increment(key, limit, window_seconds)


async def check_agent_exec_rate_limit(agent_id: str) -> tuple[bool, int]:
    """Check per-agent per-minute execution rate limit. Returns (allowed, remaining)."""
    return await _check_rate_limit(
        "agent_exec",
        agent_id,
        _AGENT_EXEC_RATE_LIMIT,
        _AGENT_EXEC_RATE_WINDOW,
    )


async def check_managed_daily_limit(agent_id: str) -> tuple[bool, int]:
    """Check per-agent daily managed execution cap. Returns (allowed, remaining)."""
    return await _check_rate_limit(
        "managed_daily",
        agent_id,
        _MANAGED_DAILY_LIMIT,
        _MANAGED_DAILY_WINDOW,
    )


async def check_wallet_rate_limit(wallet_address: str) -> tuple[bool, int]:
    """Check per-wallet rate limit. Returns (allowed, remaining_requests)."""
    return await _check_rate_limit(
        "wallet",
        wallet_address,
        _WALLET_RATE_LIMIT,
        _WALLET_RATE_WINDOW,
    )


async def _build_execute_discovery_response(capability_id: str) -> JSONResponse:
    """Return x402 payment requirements for the execute surface without executing.

    Some x402 clients probe the resource URL with GET before issuing the real
    POST request. Treat GET /execute as a side-effect-free discovery surface so
    those clients can learn the payment requirements without triggering a 405.
    """
    cap_services_for_402 = await _get_capability_services(capability_id)
    recovery_hints = _execute_recovery_hints(
        capability_id=capability_id,
        mappings=cap_services_for_402,
    )
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
                "resolution": (
                    "Default next step: create or use a funded governed API key at /auth/login and retry with X-Rhumb-Key. "
                    "If you need a wallet-first path, use /payments/agent for wallet-prefund or x402 per-call. "
                    "Inspect the estimate and resolve surfaces before retrying if you only need discovery."
                ),
                "balanceRequired": None,
                "balanceRequiredUsd": None,
                **recovery_hints,
            },
            headers={"X-Payment": "required"},
        )

    billed_cost_usd = cost_for_402 * 1.15
    billed_cents_for_402 = max(int(round(billed_cost_usd * 100)), 1)
    payment_request = await _create_payment_request_safe(
        org_id=None,
        capability_id=capability_id,
        amount_usd_cents=billed_cents_for_402,
    )
    body_402 = build_x402_response(
        capability_id=capability_id,
        cost_usd_cents=billed_cents_for_402,
        resource_url=f"{api_base}/v1/capabilities/{capability_id}/execute",
        payment_request=payment_request,
        resolution=(
            "Default next step: create or use a funded governed API key at /auth/login and retry with X-Rhumb-Key. "
            "If you need a wallet-first path, use /payments/agent for wallet-prefund or x402 per-call. "
            "Inspect the resolve and estimate surfaces before retrying if you only need discovery."
        ),
        supplemental_fields=recovery_hints,
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
    method: Optional[str] = Field(None, description="HTTP method (GET, POST, etc.) — required for byok/agent_vault, optional for rhumb_managed")
    path: Optional[str] = Field(None, description="Provider API path (e.g. /v3/mail/send) — required for byok/agent_vault, optional for rhumb_managed")
    body: Optional[dict] = Field(None, description="Request body (provider-native)")
    params: Optional[dict] = Field(None, description="Query parameters")
    credential_mode: str = Field(
        "auto",
        description=(
            "Credential mode (auto, byok, rhumb_managed, agent_vault). "
            "'auto' uses rhumb_managed when available, falls back to byok."
        ),
    )
    idempotency_key: Optional[str] = Field(None, description="Idempotency key to prevent duplicate execution")
    interface: str = Field("rest", description="Client interface (rest, mcp, cli, sdk)")


@router.post("/db/agent-vault/tokenize")
async def tokenize_db_agent_vault(
    request: DbAgentVaultTokenizeRequest,
    x_rhumb_key: str | None = Header(default=None, alias="X-Rhumb-Key"),
) -> dict:
    """Exchange a raw PostgreSQL DSN for a short-lived opaque DB vault token.

    This is a bridge away from repeatedly sending the raw DSN in X-Agent-Token.
    The issued token is encrypted, bound to the authenticated agent, and scoped
    to the provided connection_ref.
    """
    if not x_rhumb_key:
        raise HTTPException(status_code=401, detail="X-Rhumb-Key header required")

    agent = await _get_identity_store().verify_api_key_with_agent(x_rhumb_key)
    if agent is None:
        raise HTTPException(status_code=401, detail="Invalid X-Rhumb-Key")

    try:
        issued_at = int(time.time())
        token = issue_agent_vault_dsn_token(
            request.dsn,
            connection_ref=request.connection_ref,
            agent_id=agent.agent_id,
            org_id=agent.organization_id,
            issued_at=issued_at,
            ttl_seconds=request.ttl_seconds,
        )
    except AgentVaultDsnError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    response = DbAgentVaultTokenizeResponse(
        token=token,
        token_format="rhdbv1",
        connection_ref=request.connection_ref,
        ttl_seconds=request.ttl_seconds,
        expires_at=issued_at + request.ttl_seconds,
    )
    return {
        "data": response.model_dump(mode="json"),
        "error": None,
    }


async def _parse_execute_request(raw_request: Request) -> CapabilityExecuteRequest:
    """Parse execute payloads even when clients omit Content-Type.

    Some x402 buyers POST raw JSON bodies without setting
    ``Content-Type: application/json`` during discovery/retry. FastAPI's
    normal body parsing rejects those requests before the route can return a
    402 discovery envelope or process the paid retry. Parse the raw body
    ourselves so valid JSON still reaches the execute logic.

    Also support two legacy/client-friendly shapes that already appear in the
    wild:
    1. envelope fields like ``provider`` / ``credential_mode`` passed via the
       query string (mirroring ``/execute/estimate`` usage)
    2. provider-native JSON bodies posted directly without wrapping them under
       a top-level ``body`` key
    """
    envelope_fields = {
        "provider",
        "method",
        "path",
        "body",
        "params",
        "credential_mode",
        "idempotency_key",
        "interface",
    }

    query_overrides = {
        field: value
        for field in envelope_fields
        if field not in {"body", "params"}
        for value in [raw_request.query_params.get(field)]
        if value is not None and value != ""
    }

    raw_body = await raw_request.body()
    if not raw_body or not raw_body.strip():
        try:
            request = CapabilityExecuteRequest.model_validate(query_overrides)
            request.credential_mode = _canonicalize_credential_mode(request.credential_mode) or "auto"
            return request
        except ValidationError as exc:
            raise RequestValidationError(exc.errors()) from exc

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise RequestValidationError(
            [
                {
                    "type": "value_error.jsondecode",
                    "loc": ("body",),
                    "msg": f"JSON decode error: {exc.msg}",
                    "input": raw_body.decode("utf-8", errors="replace"),
                    "ctx": {"error": exc.msg},
                }
            ]
        ) from exc

    if isinstance(payload, dict):
        if payload and not any(field in payload for field in envelope_fields):
            payload = {"body": payload}
        for key, value in query_overrides.items():
            payload.setdefault(key, value)

    try:
        request = CapabilityExecuteRequest.model_validate(payload)
        request.credential_mode = _canonicalize_credential_mode(request.credential_mode) or "auto"
        return request
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


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


def _public_provider_slug(provider_slug: str | None) -> str | None:
    return public_service_slug(provider_slug) or provider_slug


def _public_provider_label(provider_slug: str | None) -> str:
    return str(_public_provider_slug(provider_slug) or provider_slug or "unknown")


def _canonicalize_public_provider_message(
    message: str | None,
    provider_slug: str | None,
) -> str | None:
    """Rewrite exact quoted provider mentions onto canonical public slugs."""
    if message is None:
        return None

    public_provider = _public_provider_slug(provider_slug)
    if not public_provider:
        return message

    rewritten = str(message)
    for candidate in public_service_slug_candidates(provider_slug):
        if candidate and candidate != public_provider:
            rewritten = rewritten.replace(f"'{candidate}'", f"'{public_provider}'")
    return rewritten


_PUBLIC_PROVIDER_VALUE_KEYS = {
    "provider",
    "provider_used",
    "provider_id",
    "provider_slug",
    "selected_provider",
    "requested_provider",
    "fallback_provider",
}
_PUBLIC_PROVIDER_LIST_KEYS = {
    "available_providers",
    "candidate_providers",
    "fallback_providers",
    "supported_provider_slugs",
    "unavailable_provider_slugs",
    "not_execute_ready_provider_slugs",
    "policy_candidates",
}
_PUBLIC_PROVIDER_TEXT_KEYS = {"message", "detail", "error_message"}


def _collect_public_provider_contexts(value: Any, provider_slugs: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _PUBLIC_PROVIDER_VALUE_KEYS and isinstance(item, str):
                cleaned = item.strip()
                if cleaned:
                    provider_slugs.add(cleaned)
            elif key in _PUBLIC_PROVIDER_LIST_KEYS and isinstance(item, list):
                for entry in item:
                    if isinstance(entry, str):
                        cleaned = entry.strip()
                        if cleaned:
                            provider_slugs.add(cleaned)
                    else:
                        _collect_public_provider_contexts(entry, provider_slugs)
            else:
                _collect_public_provider_contexts(item, provider_slugs)
        return
    if isinstance(value, list):
        for item in value:
            _collect_public_provider_contexts(item, provider_slugs)


def _canonicalize_public_provider_text(
    text: Any,
    provider_slugs: set[str],
) -> str | None:
    if text is None:
        return None

    rendered = str(text)
    replacements: dict[str, str] = {}
    for provider_slug in provider_slugs:
        canonical = _public_provider_slug(provider_slug)
        if not canonical:
            continue
        for candidate in public_service_slug_candidates(canonical):
            cleaned = str(candidate or "").strip()
            if not cleaned or cleaned.lower() == canonical.lower():
                continue
            replacements[cleaned.lower()] = canonical

    if not replacements:
        return rendered

    pattern = re.compile(
        rf"(?<![a-z0-9-])(?:{'|'.join(re.escape(candidate) for candidate in sorted(replacements, key=len, reverse=True))})(?![a-z0-9-])",
        re.IGNORECASE,
    )
    return pattern.sub(lambda match: replacements[match.group(0).lower()], rendered)


def _canonicalize_public_provider_value(value: Any) -> Any:
    if isinstance(value, str):
        return _public_provider_slug(value) or value
    return value


def _canonicalize_public_provider_payload(value: Any, *, provider_slug: str | None) -> Any:
    provider_slugs: set[str] = set()
    if provider_slug:
        provider_slugs.add(str(provider_slug).strip())
    _collect_public_provider_contexts(value, provider_slugs)
    return _canonicalize_public_provider_payload_with_contexts(value, provider_slugs=provider_slugs)


def _canonicalize_public_provider_payload_with_contexts(
    value: Any,
    *,
    provider_slugs: set[str],
) -> Any:
    if isinstance(value, dict):
        canonicalized: dict[str, Any] = {}
        for key, item in value.items():
            if key in _PUBLIC_PROVIDER_VALUE_KEYS:
                canonicalized[key] = _canonicalize_public_provider_value(item)
            elif key in _PUBLIC_PROVIDER_TEXT_KEYS:
                canonicalized[key] = _canonicalize_public_provider_text(item, provider_slugs)
            elif key in _PUBLIC_PROVIDER_LIST_KEYS and isinstance(item, list):
                canonicalized[key] = [_canonicalize_public_provider_value(entry) for entry in item]
            else:
                canonicalized[key] = _canonicalize_public_provider_payload_with_contexts(
                    item,
                    provider_slugs=provider_slugs,
                )
        return canonicalized
    if isinstance(value, list):
        return [
            _canonicalize_public_provider_payload_with_contexts(item, provider_slugs=provider_slugs)
            for item in value
        ]
    return value


def _extract_public_error_message(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("error_message", "detail", "message", "error"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        nested_result = value.get("result")
        if nested_result is not None:
            nested_message = _extract_public_error_message(nested_result)
            if nested_message:
                return nested_message
        for nested in value.values():
            nested_message = _extract_public_error_message(nested)
            if nested_message:
                return nested_message
        return None
    if isinstance(value, list):
        for item in value:
            nested_message = _extract_public_error_message(item)
            if nested_message:
                return nested_message
    return None


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


def _direct_capability_stub(capability_id: str) -> Optional[dict[str, str]]:
    """Return a minimal direct-capability row when the DB catalog does not carry one."""
    descriptions = {
        "crm.object.describe": "Describe CRM objects through a direct read-only execution rail.",
        "crm.record.search": "Search CRM records through a direct read-only execution rail.",
        "crm.record.get": "Fetch a CRM record through a direct read-only execution rail.",
        "workflow_run.list": "List workflow runs through a direct read-only GitHub Actions rail.",
        "workflow_run.get": "Fetch a workflow run through a direct read-only GitHub Actions rail.",
        "db.query.read": "Execute a bounded read-only SQL query through a direct PostgreSQL rail.",
        "db.schema.describe": "Inspect database schema metadata through a direct PostgreSQL rail.",
        "db.row.get": "Fetch a single database row through a direct PostgreSQL rail.",
        "warehouse.query.read": "Execute a bounded read-only warehouse query through a direct BigQuery rail.",
        "warehouse.schema.describe": "Inspect warehouse schema metadata through a direct BigQuery rail.",
        "deployment.list": "List deployments through a direct read-only Vercel rail.",
        "deployment.get": "Fetch a deployment through a direct read-only Vercel rail.",
        "object.list": "List storage objects through a direct read-only AWS S3 rail.",
        "object.head": "Fetch storage object metadata through a direct read-only AWS S3 rail.",
        "object.get": "Fetch a bounded storage object through a direct read-only AWS S3 rail.",
        "ticket.search": "Search tickets through a direct read-only Zendesk rail.",
        "ticket.get": "Fetch a ticket through a direct read-only Zendesk rail.",
        "ticket.list_comments": "List ticket comments through a direct read-only Zendesk rail.",
        "conversation.list": "List conversations through a direct read-only Intercom rail.",
        "conversation.get": "Fetch a conversation through a direct read-only Intercom rail.",
        "conversation.list_parts": "List conversation parts through a direct read-only Intercom rail.",
    }
    if capability_id not in DIRECT_EXECUTE_CAPABILITY_IDS:
        return None
    domain, _, action = capability_id.partition(".")
    return {
        "id": capability_id,
        "domain": domain,
        "action": action or capability_id,
        "description": descriptions.get(capability_id, "Direct read-only execution rail."),
    }


def _direct_capability_service_mappings(capability_id: str) -> list[dict[str, Any]]:
    """Mirror the direct-capability provider rows from the capability registry route."""
    from routes import capabilities as capability_routes

    if capability_id in CRM_CAPABILITY_IDS:
        return list(capability_routes._crm_direct_provider_details(capability_id))
    if capability_id in ACTIONS_CAPABILITY_IDS:
        return [capability_routes._actions_direct_provider_details(capability_id)]
    if capability_id in DB_CAPABILITY_IDS:
        return [capability_routes._db_direct_provider_details(capability_id)]
    if capability_id in WAREHOUSE_CAPABILITY_IDS:
        return [capability_routes._warehouse_direct_provider_details(capability_id)]
    if capability_id in DEPLOYMENT_CAPABILITY_IDS:
        return [capability_routes._deployment_direct_provider_details(capability_id)]
    if capability_id in STORAGE_CAPABILITY_IDS:
        return [capability_routes._object_storage_direct_provider_details(capability_id)]
    if capability_id in SUPPORT_CAPABILITY_IDS:
        return [capability_routes._support_direct_provider_details(capability_id)]
    return []


async def _resolve_capability(capability_id: str) -> Optional[dict]:
    """Fetch a capability row by ID. Returns None if not found."""
    caps = await supabase_fetch(
        f"capabilities?id=eq.{quote(capability_id)}"
        f"&select=id,domain,action,description&limit=1"
    )
    if caps:
        return caps[0]
    return _direct_capability_stub(capability_id)


async def _get_capability_services(capability_id: str) -> list[dict]:
    """Fetch capability mappings, keeping direct rails on synthetic provider truth."""
    direct_mappings = _direct_capability_service_mappings(capability_id)
    if direct_mappings:
        return direct_mappings

    mappings = await supabase_fetch(
        f"capability_services?capability_id=eq.{quote(capability_id)}"
        f"&select=service_slug,credential_modes,auth_method,endpoint_pattern,"
        f"cost_per_call,cost_currency,free_tier_calls"
    )
    if mappings:
        return mappings
    return []


async def _get_service_domain(service_slug: str) -> Optional[str]:
    """Resolve a service's api_domain from the services table."""
    for candidate in public_service_slug_candidates(service_slug):
        rows = await supabase_fetch(
            f"services?slug=eq.{quote(candidate)}&select=slug,api_domain&limit=1"
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

    breaker_reg = get_breaker_registry()
    if len(mappings) == 1:
        only_mapping = mappings[0]
        only_slug = normalize_proxy_slug(only_mapping["service_slug"])
        breaker = breaker_reg.get(only_slug, agent_id)
        if breaker.allow_request():
            return only_mapping
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
        public_requested_provider = _public_provider_label(requested_provider)
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
                detail=f"Provider '{public_requested_provider}' not available for capability '{capability_id}'",
            )
        breaker = get_breaker_registry().get(normalize_proxy_slug(chosen["service_slug"]), agent_id)
        if not breaker.allow_request():
            raise HTTPException(
                status_code=503,
                detail=f"Provider '{public_requested_provider}' circuit is open — try later",
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


def _canonicalize_credential_mode(credential_mode: str | None) -> str | None:
    """Normalize legacy credential-mode aliases to the public vocabulary."""
    normalized = str(credential_mode or "").strip().lower()
    if not normalized:
        return None
    if normalized == "byo":
        return "byok"
    return normalized


def _parse_credential_modes(raw_modes: Any) -> list[str]:
    """Normalize credential_modes from Supabase into a list of strings."""
    if isinstance(raw_modes, str):
        return [
            normalized
            for mode in raw_modes.split(",")
            for normalized in [_canonicalize_credential_mode(mode)]
            if normalized
        ]
    if isinstance(raw_modes, (list, tuple, set)):
        parsed_modes: list[str] = []
        for mode in raw_modes:
            normalized = _canonicalize_credential_mode(str(mode))
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
    normalized_mode = _canonicalize_credential_mode(credential_mode) or "auto"
    if normalized_mode != "auto":
        return normalized_mode, None

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

    resolved_mode = "rhumb_managed" if managed_mapping is not None else "byok"
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
    public_provider = _public_provider_label(service_slug)
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
        detail=f"No API domain configured for provider '{public_provider}'",
    )


def _inject_auth_request_parts(
    service_slug: str,
    auth_method: Optional[str],
    headers: dict[str, str],
    body: dict | None,
    params: dict | None,
) -> tuple[dict[str, str], dict | None, dict | None]:
    """Inject provider auth into request headers, params, or body.

    For supported proxy-managed services, delegate to :class:`AuthInjector`.
    For dynamic services, fall back to a simple header-based injection.
    """
    public_provider = _public_provider_label(service_slug)

    # Supported proxy services — use the full AuthInjector
    if service_slug in AuthInjector.AUTH_PATTERNS:
        method_enum = AuthInjector.default_method_for(service_slug)
        if method_enum is None:
            raise HTTPException(status_code=500, detail=f"No auth method for provider '{public_provider}'")
        injector = get_auth_injector()
        try:
            injected = injector.inject_request_parts(
                AuthInjectionRequest(
                    service=service_slug,
                    agent_id="capability_execute",
                    auth_method=method_enum,
                    existing_headers=headers,
                    existing_body=body,
                    existing_params=params or {},
                )
            )
            return injected.headers, injected.body, injected.params
        except (ValueError, RuntimeError) as e:
            logger.warning(
                "capability_execute auth injection unavailable provider=%s runtime_provider=%s error=%s",
                public_provider,
                service_slug,
                e,
            )
            raise HTTPException(
                status_code=503,
                detail=f"Credential unavailable for provider '{public_provider}'",
            )

    # Dynamic services — simple credential lookup
    if not auth_method:
        raise HTTPException(
            status_code=500,
            detail=f"No auth_method defined for provider '{public_provider}'",
        )

    store = get_credential_store()
    credential = store.get_credential(service_slug, auth_method)
    if credential is None:
        raise HTTPException(
            status_code=503,
            detail=f"No credential found for {public_provider}/{auth_method}",
        )

    headers = headers.copy()
    if auth_method == "basic_auth":
        encoded = base64.b64encode(credential.encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"
    else:
        # bearer_token, api_key — both use Bearer
        headers["Authorization"] = f"Bearer {credential}"

    return headers, body, params


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

@router.get("/capabilities/{capability_id}/execute")
async def discover_execute_capability(
    capability_id: str,
    raw_request: Request,
    x_rhumb_key: Optional[str] = Header(None, alias="X-Rhumb-Key"),
    x_payment: Optional[str] = Header(None, alias="X-Payment"),
    payment_signature: Optional[str] = Header(None, alias="PAYMENT-SIGNATURE"),
) -> JSONResponse:
    """Return x402 payment requirements for execute without executing anything.

    Also captures all incoming headers for x402 interop diagnostics
    when buyers retry with GET + payment proof (as awal does).

    Direct AUD-18 execute rails do not use GET x402 discovery. They require
    X-Rhumb-Key for execution and keep GET limited to auth/setup guidance.
    """
    x_payment = _normalize_x402_payment_header(x_payment, payment_signature)

    direct_auth_detail = _direct_execute_auth_detail(capability_id)
    if direct_auth_detail is not None:
        if not x_rhumb_key:
            return _direct_execute_auth_required_response(
                raw_request,
                capability_id=capability_id,
                detail=direct_auth_detail,
            )
        agent = await _get_identity_store().verify_api_key_with_agent(x_rhumb_key)
        if agent is None:
            return _invalid_governed_api_key_response(raw_request, capability_id=capability_id)
        return _direct_execute_get_not_supported_response(
            raw_request,
            capability_id=capability_id,
        )

    capability = await _resolve_capability(capability_id)
    if capability is None:
        return await _capability_not_found_response(raw_request, capability_id)

    payment_trace = (
        inspect_x_payment_header(x_payment)
        if x_payment and x_payment != "required"
        else inspect_x_payment_header(None)
    )
    if payment_trace.get("proof_format") == "standard_authorization_payload":
        if not _x402_settlement.is_configured():
            response = _build_x402_compatibility_error_response(
                raw_request,
                payment_trace=payment_trace,
            )
            _log_x402_interop_trace(
                raw_request,
                capability_id=capability_id,
                x_payment=x_payment,
                payment_trace=payment_trace,
                outcome="standard_authorization_unsupported",
                response_status=response.status_code,
                payment_headers_set=False,
            )
            return response

    return await _build_execute_discovery_response(capability_id)


_INTERNAL_SKIP_RECEIPT_HEADER = "X-Rhumb-Skip-Receipt"


def _should_skip_receipt(raw_request: Request) -> bool:
    value = raw_request.headers.get(_INTERNAL_SKIP_RECEIPT_HEADER, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


@router.post("/capabilities/{capability_id}/execute")
async def execute_capability(
    capability_id: str,
    raw_request: Request,
    x_rhumb_key: Optional[str] = Header(None, alias="X-Rhumb-Key"),
    x_agent_token: Optional[str] = Header(None, alias="X-Agent-Token"),
    x_payment: Optional[str] = Header(None, alias="X-Payment"),
    payment_signature: Optional[str] = Header(None, alias="PAYMENT-SIGNATURE"),
) -> dict:
    """Execute a capability through the proxy layer.

    Resolves provider, injects auth, proxies the request upstream,
    logs the execution, and returns the upstream response.

    Supports x402 inline payment via the ``X-Payment`` header or
    the standard x402 v2 ``PAYMENT-SIGNATURE`` header.
    """
    x_payment = _normalize_x402_payment_header(x_payment, payment_signature)
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

    # ── AUD-18: direct capability early dispatch ───────────────────
    # These capabilities bypass the proxy layer entirely.
    direct_auth_detail = _direct_execute_auth_detail(capability_id)
    if capability_id in DIRECT_EXECUTE_CAPABILITY_IDS:
        execution_id = f"exec_{uuid.uuid4().hex}"
        request_id = getattr(raw_request.state, "request_id", None) or str(uuid.uuid4())
        if not x_rhumb_key:
            return _direct_execute_auth_required_response(
                raw_request,
                capability_id=capability_id,
                detail=direct_auth_detail or "X-Rhumb-Key header required for direct capability execution",
            )
        agent = await _get_identity_store().verify_api_key_with_agent(x_rhumb_key)
        if agent is None:
            return _invalid_governed_api_key_response(raw_request, capability_id=capability_id)
        if capability_id in CRM_CAPABILITY_IDS:
            from routes.crm_execute import handle_crm_execute

            return await handle_crm_execute(
                capability_id=capability_id,
                raw_request=raw_request,
                agent_id=agent.agent_id,
                org_id=agent.organization_id,
                execution_id=execution_id,
                request_id=request_id,
            )
        if capability_id in ACTIONS_CAPABILITY_IDS:
            from routes.actions_execute import handle_actions_execute

            return await handle_actions_execute(
                capability_id=capability_id,
                raw_request=raw_request,
                agent_id=agent.agent_id,
                org_id=agent.organization_id,
                execution_id=execution_id,
                request_id=request_id,
            )
        if capability_id in DB_CAPABILITY_IDS:
            from routes.db_execute import handle_db_execute

            return await handle_db_execute(
                capability_id=capability_id,
                raw_request=raw_request,
                agent_id=agent.agent_id,
                org_id=agent.organization_id,
                execution_id=execution_id,
                request_id=request_id,
            )
        if capability_id in WAREHOUSE_CAPABILITY_IDS:
            from routes.warehouse_execute import handle_warehouse_execute

            return await handle_warehouse_execute(
                capability_id=capability_id,
                raw_request=raw_request,
                agent_id=agent.agent_id,
                org_id=agent.organization_id,
                execution_id=execution_id,
                request_id=request_id,
            )
        if capability_id in DEPLOYMENT_CAPABILITY_IDS:
            from routes.deployment_execute import handle_deployment_execute

            return await handle_deployment_execute(
                capability_id=capability_id,
                raw_request=raw_request,
                agent_id=agent.agent_id,
                org_id=agent.organization_id,
                execution_id=execution_id,
                request_id=request_id,
            )
        if capability_id in STORAGE_CAPABILITY_IDS:
            from routes.storage_execute import handle_storage_execute

            return await handle_storage_execute(
                capability_id=capability_id,
                raw_request=raw_request,
                agent_id=agent.agent_id,
                org_id=agent.organization_id,
                execution_id=execution_id,
                request_id=request_id,
            )
        from routes.support_execute import handle_support_execute

        return await handle_support_execute(
            capability_id=capability_id,
            raw_request=raw_request,
            agent_id=agent.agent_id,
            org_id=agent.organization_id,
            execution_id=execution_id,
            request_id=request_id,
        )

    capability = await _resolve_capability(capability_id)
    if capability is None:
        return await _capability_not_found_response(raw_request, capability_id)

    request = await _parse_execute_request(raw_request)

    # ── Authentication: API key OR x402 payment ────────────────────
    is_x402_anonymous = False
    x402_wallet_address: Optional[str] = None
    x402_rate_remaining: Optional[int] = None
    payment_trace = (
        inspect_x_payment_header(x_payment)
        if x_payment and x_payment != "required"
        else inspect_x_payment_header(None)
    )

    if x_rhumb_key:
        # Path 1: Registered agent with API key (existing flow)
        agent = await _get_identity_store().verify_api_key_with_agent(x_rhumb_key)
        if agent is None:
            return _invalid_governed_api_key_response(raw_request, capability_id=capability_id)
        agent_id = agent.agent_id
        org_id = agent.organization_id
    elif x_payment and x_payment != "required":
        # Path 2: x402 anonymous — payment header present, no API key.
        payment_data = payment_trace.get("payment_data")
        if payment_trace.get("proof_format") == "standard_authorization_payload":
            if not _x402_settlement.is_configured():
                response = _build_x402_compatibility_error_response(
                    raw_request,
                    payment_trace=payment_trace,
                )
                _log_x402_interop_trace(
                    raw_request,
                    capability_id=capability_id,
                    x_payment=x_payment,
                    payment_trace=payment_trace,
                    outcome="standard_authorization_unconfigured",
                    response_status=response.status_code,
                    provider=request.provider,
                    payment_headers_set=False,
                )
                return response

            authorization = _extract_standard_x402_authorization(payment_data)
            payer_wallet = authorization.get("from") if authorization else None
            if not payer_wallet:
                response = await _build_execute_discovery_response(capability_id)
                _log_x402_interop_trace(
                    raw_request,
                    capability_id=capability_id,
                    x_payment=x_payment,
                    payment_trace=payment_trace,
                    outcome="payer_wallet_missing",
                    response_status=response.status_code,
                    provider=request.provider,
                    payment_headers_set="X-Payment" in response.headers,
                )
                return response

            is_x402_anonymous = True
            x402_wallet_address = payer_wallet
            agent_id = f"x402_wallet_{payer_wallet.lower()}"
            org_id = "x402_anonymous"

            allowed, remaining = await check_wallet_rate_limit(payer_wallet)
            x402_rate_remaining = remaining
            if not allowed:
                _log_x402_interop_trace(
                    raw_request,
                    capability_id=capability_id,
                    x_payment=x_payment,
                    payment_trace=payment_trace,
                    outcome="rate_limited",
                    response_status=429,
                    provider=request.provider,
                    payment_headers_set=False,
                    extra={"wallet": payer_wallet},
                )
                raise HTTPException(
                    status_code=429,
                    detail="Wallet rate limit exceeded. Retry in one minute.",
                )
        # SECURITY: We only set is_x402_anonymous AFTER validating that the
        # header contains a decodable legacy tx_hash proof. Garbage headers
        # must not grant anonymous execution.
        elif not payment_data or not payment_data.get("tx_hash"):
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

        else:
            # Replay prevention: reject reused tx_hash. Financial replay
            # protection must fail closed rather than degrading to
            # per-process memory during control-plane outage.
            tx_hash = payment_data["tx_hash"]
            try:
                is_replay = await (await _get_replay_guard()).check_and_claim(
                    tx_hash,
                    allow_fallback=False,
                )
            except ReplayGuardUnavailable as exc:
                _log_x402_interop_trace(
                    raw_request,
                    capability_id=capability_id,
                    x_payment=x_payment,
                    payment_trace=payment_trace,
                    outcome="payment_protection_unavailable",
                    response_status=503,
                    provider=request.provider,
                    payment_headers_set=False,
                    extra={"tx_hash": tx_hash},
                )
                raise HTTPException(
                    status_code=503,
                    detail="Payment protection temporarily unavailable. Retry shortly.",
                ) from exc

            if is_replay:
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
                allowed, remaining = await check_wallet_rate_limit(x402_wallet_address)
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
    exec_allowed, exec_remaining = await check_agent_exec_rate_limit(agent_id)
    if not exec_allowed:
        raise HTTPException(
            status_code=429,
            detail="Execution rate limit exceeded (30/min). Slow down.",
            headers={"Retry-After": "60"},
        )

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
                "message": "Managed credential execution is temporarily suspended. Use your own API key (credential_mode: byok) to continue.",
                "resolution": "Check https://rhumb.dev/status for updates or switch to byok credentials",
                "request_id": f"req_{uuid.uuid4().hex[:12]}",
            },
        )

    # Stricter daily cap for managed credentials (Rhumb's own keys)
    if request.credential_mode == "rhumb_managed":
        managed_allowed, managed_remaining = await check_managed_daily_limit(agent_id)
        if not managed_allowed:
            raise HTTPException(
                status_code=429,
                detail="Daily managed execution limit exceeded (200/day). "
                       "Consider using byok credentials for higher volume.",
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
                detail="method and path are required for byok credential mode",
            )

    selected_mapping: dict | None = None
    if request.credential_mode == "byok":
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
        if selected_mapping is None:
            fallback_managed_mapping = None
            if request.provider:
                fallback_managed_mapping = await _resolve_managed_provider_mapping(
                    capability_id=capability_id,
                    mappings=cap_services,
                    requested_provider=None,
                )
            return _managed_provider_unavailable_response(
                raw_request,
                capability_id=capability_id,
                mappings=cap_services,
                requested_provider=request.provider,
                available_managed_mappings=[fallback_managed_mapping] if fallback_managed_mapping else [],
            )

    # 0. Pre-execution budget/credit reservation estimate
    cost_estimate = _extract_cost_usd(selected_mapping)
    upstream_cost_cents, billed_cost_cents, margin_cents = _calculate_billing_amounts(cost_estimate)

    kill_switch_registry = await init_kill_switch_registry()
    kill_switch_provider = (
        selected_mapping.get("service_slug")
        if isinstance(selected_mapping, dict)
        else request.provider
    )
    operation_class = "financial" if (
        request.credential_mode == "rhumb_managed"
        or billed_cost_cents > 0
        or bool(x_payment and x_payment != "required")
    ) else "non_financial"
    blocked, kill_reason = kill_switch_registry.is_blocked(
        agent_id=agent_id,
        provider_slug=kill_switch_provider,
        operation_class=operation_class,
        require_authoritative=True,
    )
    if blocked:
        logger.warning(
            "execution_blocked_by_kill_switch agent_id=%s capability_id=%s provider=%s operation_class=%s reason=%s",
            agent_id,
            capability_id,
            kill_switch_provider,
            operation_class,
            kill_reason,
        )
        return JSONResponse(
            status_code=503,
            content={
                "error": "kill_switch_active",
                "message": "Execution is temporarily blocked by a kill switch or control-plane safety gate.",
                "resolution": "Retry later or contact Rhumb support if the block appears unexpected.",
                "detail": kill_reason,
                "request_id": getattr(raw_request.state, "request_id", None) or f"req_{uuid.uuid4().hex[:12]}",
            },
        )

    execution_id = f"exec_{uuid.uuid4().hex}"
    idempotency_store: DurableIdempotencyStore | None = None
    idempotency_claimed = False

    async def _release_idempotency_claim() -> None:
        nonlocal idempotency_claimed
        if request.idempotency_key and idempotency_claimed and idempotency_store is not None:
            await idempotency_store.release(request.idempotency_key)
            idempotency_claimed = False

    async def _store_idempotent_result(status: str, result_hash: str) -> None:
        if request.idempotency_key and idempotency_store is not None:
            await idempotency_store.store(
                request.idempotency_key,
                execution_id,
                capability_id,
                status,
                result_hash,
            )

    def _payment_recording_unavailable(exc: SupabaseWriteUnavailable) -> HTTPException:
        return HTTPException(
            status_code=503,
            detail=(
                "Payment may have been accepted, but durable recording is unavailable. "
                "Do not retry blindly; verify settlement first."
            ),
        )

    def _execution_recording_unavailable(exc: SupabaseWriteUnavailable) -> HTTPException:
        return HTTPException(
            status_code=503,
            detail=(
                "Execution may have completed, but durable recording failed. "
                "Do not retry blindly; verify side effects before retrying."
            ),
        )

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
            return _billing_unavailable_response(
                raw_request,
                detail=None if billing_reason in {"timeout", "connection_error"} else billing_reason,
            )

    # ── x402 inline payment handling ─────────────────────────────────
    # If the client sends an X-Payment header with a USDC tx_hash, we:
    #   1. Verify the tx hasn't been used before (replay protection)
    #   2. Verify the on-chain USDC transfer matches expected amount/recipient
    #   3. Durably record the receipt in usdc_receipts
    #   4. Durably record the payment on the org ledger for registered agents
    #   5. Treat verified on-chain payment as authorization and skip Supabase
    #      billing reservations entirely
    x402_receipt: dict | None = None
    standard_x402_payment_response_header: str | None = None
    if x_payment and x_payment != "required":
        payment_data = payment_trace.get("payment_data") or decode_x_payment_header(x_payment)
        if payment_trace.get("proof_format") == "standard_authorization_payload":
            payment_request_id = _extract_standard_x402_payment_request_id(payment_data)
            pending_payment_request: dict | None = None
            if payment_request_id:
                pending_payment_request = await _payment_requests.get_pending_request(payment_request_id)
                if not pending_payment_request:
                    raise HTTPException(
                        status_code=402,
                        detail="Payment settlement failed: payment request not found or expired",
                    )
                if pending_payment_request.get("capability_id") != capability_id:
                    raise HTTPException(
                        status_code=402,
                        detail="Payment settlement failed: payment request capability mismatch",
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
                )
                raise HTTPException(
                    status_code=402,
                    detail="Payment settlement failed: cost data unavailable for selected provider",
                )

            try:
                payment_requirements = _build_standard_x402_payment_requirements(
                    capability_id=capability_id,
                    cost_usd_cents=billed_cost_cents,
                    payment_request=pending_payment_request,
                )
            except ValueError as exc:
                raise HTTPException(status_code=402, detail=f"Payment settlement failed: {exc}") from exc

            authorization = _extract_standard_x402_authorization(payment_data)
            try:
                settlement = await _x402_settlement.verify_and_settle(
                    payment_data,
                    payment_requirements,
                )
            except X402FacilitatorNotConfigured:
                response = _build_x402_compatibility_error_response(
                    raw_request,
                    payment_trace=payment_trace,
                )
                _log_x402_interop_trace(
                    raw_request,
                    capability_id=capability_id,
                    x_payment=x_payment,
                    payment_trace=payment_trace,
                    outcome="standard_authorization_unconfigured",
                    response_status=response.status_code,
                    provider=request.provider,
                    payment_headers_set=False,
                    execution_id=execution_id,
                    agent_id=agent_id,
                    org_id=org_id,
                )
                return response
            except X402VerificationFailed as exc:
                log_payment_event(
                    "x402_payment_failed",
                    org_id=org_id,
                    capability_id=capability_id,
                    execution_id=execution_id,
                    network=payment_requirements.get("network"),
                    success=False,
                    error=str(exc),
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
                    extra={"verify_error": str(exc)},
                )
                raise HTTPException(
                    status_code=402,
                    detail=f"Payment verification failed: {exc}",
                ) from exc
            except X402SettlementFailed as exc:
                log_payment_event(
                    "x402_payment_failed",
                    org_id=org_id,
                    capability_id=capability_id,
                    execution_id=execution_id,
                    network=payment_requirements.get("network"),
                    success=False,
                    error=str(exc),
                )
                _log_x402_interop_trace(
                    raw_request,
                    capability_id=capability_id,
                    x_payment=x_payment,
                    payment_trace=payment_trace,
                    outcome="settle_failed",
                    response_status=402,
                    provider=request.provider,
                    payment_headers_set=False,
                    execution_id=execution_id,
                    agent_id=agent_id,
                    org_id=org_id,
                    extra={"settle_error": str(exc)},
                )
                raise HTTPException(
                    status_code=402,
                    detail=f"Payment settlement failed: {exc}",
                ) from exc

            tx_hash = settlement["transaction"]
            network = settlement.get("network") or payment_requirements.get("network")
            payer = settlement.get("payer") or (authorization or {}).get("from") or x402_wallet_address or ""
            pay_to = payment_requirements.get("payTo")
            amount_atomic = payment_requirements.get("amount") or payment_requirements.get("maxAmountRequired") or "0"

            try:
                await supabase_insert_required("usdc_receipts", {
                    "payment_request_id": payment_request_id,
                    "tx_hash": tx_hash,
                    "from_address": payer,
                    "to_address": pay_to,
                    "amount_usdc_atomic": amount_atomic,
                    "amount_usd_cents": billed_cost_cents,
                    "network": network,
                    "block_number": None,
                    "org_id": org_id,
                    "execution_id": execution_id,
                    "status": "confirmed",
                })

                if payment_request_id:
                    await _payment_requests.mark_verified(payment_request_id, tx_hash)

                if not is_x402_anonymous:
                    current_credits = await supabase_fetch(
                        f"org_credits?org_id=eq.{quote(org_id)}&select=balance_usd_cents&limit=1"
                    )
                    current_balance = int(current_credits[0].get("balance_usd_cents", 0)) if current_credits else 0
                    new_balance = current_balance + billed_cost_cents

                    await supabase_insert_required("credit_ledger", {
                        "org_id": org_id,
                        "amount_usd_cents": billed_cost_cents,
                        "balance_after_usd_cents": new_balance,
                        "event_type": "x402_payment",
                        "capability_execution_id": execution_id,
                        "description": f"x402 authorization settlement tx:{tx_hash[:16]}…",
                    })

                    if current_credits:
                        await supabase_patch_required(
                            f"org_credits?org_id=eq.{quote(org_id)}",
                            {"balance_usd_cents": new_balance},
                        )
            except SupabaseWriteUnavailable as exc:
                raise _payment_recording_unavailable(exc) from exc

            standard_x402_payment_response_header = settlement["payment_response_header"]
            log_payment_event(
                "x402_payment_verified",
                org_id=org_id,
                capability_id=capability_id,
                execution_id=execution_id,
                tx_hash=tx_hash,
                network=network,
                amount_usd_cents=billed_cost_cents,
            )
            x402_receipt = {
                "tx_hash": tx_hash,
                "from_address": payer,
                "to_address": pay_to,
                "amount_atomic": amount_atomic,
                "network": network,
                "payment_request_id": payment_request_id,
            }
        elif payment_data and payment_data.get("tx_hash"):
            tx_hash = payment_data["tx_hash"]
            payment_request_id = (
                payment_data.get("payment_request_id")
                or payment_data.get("paymentRequestId")
            )
            pending_payment_request: dict | None = None
            if payment_request_id:
                pending_payment_request = await _payment_requests.get_pending_request(payment_request_id)
                if not pending_payment_request:
                    raise HTTPException(
                        status_code=402,
                        detail="Payment verification failed: payment request not found or expired",
                    )
                if pending_payment_request.get("capability_id") != capability_id:
                    raise HTTPException(
                        status_code=402,
                        detail="Payment verification failed: payment request capability mismatch",
                    )

            network = (
                payment_data.get("network")
                or (pending_payment_request or {}).get("network")
                or "evm:84532"
            )
            declared_wallet = payment_data.get("wallet_address") or payment_data.get("from")

            # Verify on-chain
            wallet = (
                (pending_payment_request or {}).get("pay_to_address")
                or os.environ.get("RHUMB_USDC_WALLET_ADDRESS", "")
            )
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

            expected_atomic = (
                (pending_payment_request or {}).get("amount_usdc_atomic")
                or (str(billed_cost_cents * 10000) if billed_cost_cents > 0 else "0")
            )
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

            try:
                is_replay = await (await _get_replay_guard()).check_and_claim(
                    tx_hash,
                    allow_fallback=False,
                )
            except ReplayGuardUnavailable as exc:
                _log_x402_interop_trace(
                    raw_request,
                    capability_id=capability_id,
                    x_payment=x_payment,
                    payment_trace=payment_trace,
                    outcome="payment_protection_unavailable",
                    response_status=503,
                    provider=request.provider,
                    payment_headers_set=False,
                    execution_id=execution_id,
                    agent_id=agent_id,
                    org_id=org_id,
                    extra={"tx_hash": tx_hash, "network": network},
                )
                raise HTTPException(
                    status_code=503,
                    detail="Payment protection temporarily unavailable. Retry shortly.",
                ) from exc

            if is_replay:
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

            try:
                # Record receipt in usdc_receipts (durable replay claim already held)
                await supabase_insert_required("usdc_receipts", {
                    "payment_request_id": payment_request_id,
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

                if payment_request_id:
                    await _payment_requests.mark_verified(payment_request_id, tx_hash)

                if not is_x402_anonymous:
                    current_credits = await supabase_fetch(
                        f"org_credits?org_id=eq.{quote(org_id)}&select=balance_usd_cents&limit=1"
                    )
                    current_balance = int(current_credits[0].get("balance_usd_cents", 0)) if current_credits else 0
                    new_balance = current_balance + billed_cost_cents

                    await supabase_insert_required("credit_ledger", {
                        "org_id": org_id,
                        "amount_usd_cents": billed_cost_cents,
                        "balance_after_usd_cents": new_balance,
                        "event_type": "x402_payment",
                        "capability_execution_id": execution_id,
                        "description": f"x402 USDC payment tx:{tx_hash[:16]}…",
                    })

                    if current_credits:
                        await supabase_patch_required(
                            f"org_credits?org_id=eq.{quote(org_id)}",
                            {"balance_usd_cents": new_balance},
                        )
            except SupabaseWriteUnavailable as exc:
                raise _payment_recording_unavailable(exc) from exc

            log_payment_event(
                "x402_payment_verified",
                org_id=org_id,
                capability_id=capability_id,
                execution_id=execution_id,
                tx_hash=tx_hash,
                network=network,
                amount_usd_cents=billed_cost_cents,
            )
            x402_receipt = {
                **verification,
                "payment_request_id": payment_request_id,
            }

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

    provider_hint = _public_provider_slug(
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

    if request.idempotency_key:
        try:
            idempotency_store = await _get_idempotency_store()
            existing_claim = await idempotency_store.claim(
                request.idempotency_key,
                execution_id,
                capability_id,
                org_id=org_id,
                agent_id=agent_id,
                allow_fallback=False,
            )
        except IdempotencyUnavailable as exc:
            raise HTTPException(
                status_code=503,
                detail="Idempotency protection temporarily unavailable. Retry shortly.",
            ) from exc

        if existing_claim is not None:
            return {
                "data": {
                    "capability_id": capability_id,
                    "execution_id": existing_claim.execution_id,
                    "deduplicated": True,
                },
                "error": None,
            }
        idempotency_claimed = True

    try:
        await supabase_insert_required("capability_executions", {
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
    except SupabaseWriteUnavailable as exc:
        await _release_idempotency_claim()
        raise HTTPException(
            status_code=503,
            detail="Execution control plane temporarily unavailable. Retry shortly.",
        ) from exc

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
            payment_request = await _create_payment_request_safe(
                org_id=org_id,
                capability_id=capability_id,
                amount_usd_cents=billed_cost_cents,
                execution_id=execution_id,
            )
            await _release_idempotency_claim()
            raise PaymentRequiredException(
                capability_id=capability_id,
                cost_usd_cents=billed_cost_cents,
                resource_url=f"{api_base}/v1/capabilities/{capability_id}/execute",
                detail=budget_result.reason or "Agent budget exceeded",
                payment_request=payment_request,
                resolution=(
                    "Default next step: use a funded governed API key at /auth/login and retry with X-Rhumb-Key. "
                    "If you need a wallet-first path, use /payments/agent for wallet-prefund or x402 per-call. "
                    "Inspect the resolve and estimate surfaces before retrying if you only need discovery."
                ),
                supplemental_fields=_execute_recovery_hints(
                    capability_id=capability_id,
                    mappings=cap_services,
                    credential_mode=request.credential_mode,
                    requested_provider=request.provider,
                    selected_mapping=selected_mapping,
                ),
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
                await _release_idempotency_claim()
                return _billing_unavailable_response(raw_request)
            if not credit_result.allowed:
                if cost_estimate > 0:
                    await _budget_enforcer.release(agent_id, cost_estimate)
                payment_request = await _create_payment_request_safe(
                    org_id=org_id,
                    capability_id=capability_id,
                    amount_usd_cents=billed_cost_cents,
                    execution_id=execution_id,
                )
                await _release_idempotency_claim()
                raise PaymentRequiredException(
                    capability_id=capability_id,
                    cost_usd_cents=billed_cost_cents,
                    resource_url=f"{api_base}/v1/capabilities/{capability_id}/execute",
                    detail=credit_result.reason or "Insufficient org credits",
                    payment_request=payment_request,
                    resolution=(
                        "Default next step: use a funded governed API key at /auth/login and retry with X-Rhumb-Key. "
                        "If you need a wallet-first path, use /payments/agent for wallet-prefund or x402 per-call. "
                        "Inspect the resolve and estimate surfaces before retrying if you only need discovery."
                    ),
                    supplemental_fields=_execute_recovery_hints(
                        capability_id=capability_id,
                        mappings=cap_services,
                        credential_mode=request.credential_mode,
                        requested_provider=request.provider,
                        selected_mapping=selected_mapping,
                    ),
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
        from services.upstream_budget import claim_provider_budget

        # Claim upstream provider budget before burning our managed API credits.
        # This is durable and shared across workers so budget exhaustion survives
        # restarts and coordinated load.
        provider_slug = (
            selected_mapping.get("service_slug")
            if isinstance(selected_mapping, dict)
            else request.provider
        )
        if provider_slug:
            budget_ok, budget_reason = await claim_provider_budget(provider_slug)
            if not budget_ok:
                await _release_reservations()
                budget_reason_text = str(budget_reason or "")
                authority_unavailable = (
                    "authority" in budget_reason_text.lower()
                    and "unavailable" in budget_reason_text.lower()
                )
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": (
                            "managed_budget_authority_unavailable"
                            if authority_unavailable
                            else "provider_budget_exhausted"
                        ),
                        "message": _canonicalize_public_provider_message(
                            budget_reason,
                            provider_slug,
                        ),
                        "resolution": (
                            "Retry after the managed budget authority is restored, or use credential_mode: byok with your own API key if you need an immediate bypass"
                            if authority_unavailable
                            else "Switch to credential_mode: byok with your own API key, or try again after budget reset"
                        ),
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
        except SupabaseWriteUnavailable as exc:
            await _release_reservations()
            raise _execution_recording_unavailable(exc) from exc
        except Exception:
            await _release_reservations()
            raise

        if budget_remaining is not None:
            result["budget_remaining_usd"] = round(budget_remaining - cost_estimate, 4) if cost_estimate else budget_remaining
        if credit_remaining_cents is not None:
            result["org_credits_remaining_cents"] = credit_remaining_cents

        managed_success = result.get("upstream_status", 200) < 400
        managed_provider = _public_provider_slug(
            result.get("provider_used") or request.provider or "unknown"
        ) or "unknown"
        result = _canonicalize_public_provider_payload(result, provider_slug=managed_provider)
        result["provider_used"] = managed_provider
        upstream_response = result.get("upstream_response")
        error_message = _extract_public_error_message(upstream_response) if not managed_success else None
        managed_billing_status = (
            "billed"
            if managed_success and billed_cost_cents > 0
            else ("refunded" if not managed_success else "unbilled")
        )

        update_payload: dict[str, Any] = {"billing_status": managed_billing_status}
        if error_message:
            update_payload["error_message"] = error_message

        try:
            await supabase_patch_required(
                f"capability_executions?id=eq.{quote(execution_id)}",
                update_payload,
            )
        except SupabaseWriteUnavailable as exc:
            raise _execution_recording_unavailable(exc) from exc

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

        # ── Emit execution receipt (managed) ──
        if not _should_skip_receipt(raw_request):
            try:
                managed_receipt = await get_receipt_service().create_receipt(ReceiptInput(
                    execution_id=execution_id,
                    capability_id=capability_id,
                    status="success" if managed_success else "failure",
                    agent_id=agent_id,
                    provider_id=managed_provider,
                    credential_mode="rhumb_managed",
                    org_id=org_id,
                    caller_ip_hash=hash_caller_ip(_client_ip(raw_request)),
                    total_latency_ms=result.get("total_latency_ms") or result.get("latency_ms"),
                    provider_latency_ms=result.get("upstream_latency_ms"),
                    rhumb_overhead_ms=(
                        (result.get("total_latency_ms") or 0) - (result.get("upstream_latency_ms") or 0)
                        if result.get("total_latency_ms") and result.get("upstream_latency_ms")
                        else None
                    ),
                    provider_cost_usd=cost_estimate if upstream_cost_cents > 0 else None,
                    rhumb_fee_usd=round(margin_cents / 100, 6) if margin_cents > 0 else None,
                    total_cost_usd=round(billed_cost_cents / 100, 6) if billed_cost_cents > 0 else None,
                    credits_deducted=round(billed_cost_cents / 100, 6) if billed_cost_cents > 0 else None,
                    request_hash=hash_request_payload(request.body),
                    response_hash=hash_response_payload(upstream_response),
                    x402_tx_hash=x402_receipt.get("tx_hash") if x402_receipt else None,
                    x402_network=x402_receipt.get("network") if x402_receipt else None,
                    x402_payer=x402_receipt.get("from_address") if x402_receipt else None,
                    interface=request.interface,
                    idempotency_key=request.idempotency_key,
                    error_code=str(result.get("upstream_status")) if not managed_success else None,
                    error_message=error_message if not managed_success else None,
                ))
                result["receipt_id"] = managed_receipt.receipt_id
            except Exception as receipt_err:
                logger.warning("receipt_creation_failed execution_id=%s error=%s", execution_id, receipt_err)

        _emit_execution_billing_event(
            success=managed_success,
            org_id=org_id,
            execution_id=execution_id,
            capability_id=capability_id,
            provider_slug=managed_provider,
            credential_mode="rhumb_managed",
            amount_usd_cents=billed_cost_cents,
            receipt_id=result.get("receipt_id"),
            interface=request.interface,
            billing_status=managed_billing_status,
            error_message=error_message if not managed_success else None,
        )
        _record_execution_audit_outcome(
            success=managed_success,
            org_id=org_id,
            agent_id=agent_id,
            execution_id=execution_id,
            capability_id=capability_id,
            provider_slug=managed_provider,
            credential_mode="rhumb_managed",
            interface=request.interface,
            upstream_status=result.get("upstream_status"),
            receipt_id=result.get("receipt_id"),
            billing_status=managed_billing_status,
            latency_ms=result.get("total_latency_ms") or result.get("latency_ms"),
            error_message=error_message if not managed_success else None,
        )

        await _store_idempotent_result(
            "completed" if managed_success else "failed",
            hash_response_payload(result.get("upstream_response")),
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
                detail=f"No API domain for provider '{_public_provider_label(request.provider)}'",
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

            public_provider_used = (
                _public_provider_slug(request.provider) or request.provider or "unknown"
            )
            update_payload = {
                "provider_used": public_provider_used,
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

            vault_response = {
                "capability_id": capability_id,
                "provider_used": public_provider_used,
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
            vault_response = _canonicalize_public_provider_payload(
                vault_response,
                provider_slug=public_provider_used,
            )
            upstream_response = vault_response.get("upstream_response")
            error_message = _extract_public_error_message(upstream_response) if not success else None
            if error_message:
                update_payload["error_message"] = error_message

            try:
                await supabase_patch_required(
                    f"capability_executions?id=eq.{quote(execution_id)}",
                    update_payload,
                )
            except SupabaseWriteUnavailable as exc:
                raise _execution_recording_unavailable(exc) from exc

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

            # ── Emit execution receipt (agent_vault) ──
            if not _should_skip_receipt(raw_request):
                try:
                    vault_receipt_obj = await get_receipt_service().create_receipt(ReceiptInput(
                        execution_id=execution_id,
                        capability_id=capability_id,
                        status="success" if success else "failure",
                        agent_id=agent_id,
                        provider_id=public_provider_used,
                        credential_mode="agent_vault",
                        org_id=org_id,
                        caller_ip_hash=hash_caller_ip(_client_ip(raw_request)),
                        total_latency_ms=round(total_latency_ms, 1),
                        provider_latency_ms=round(upstream_latency_ms, 1),
                        rhumb_overhead_ms=round(total_latency_ms - upstream_latency_ms, 1),
                        provider_cost_usd=cost_estimate if upstream_cost_cents and upstream_cost_cents > 0 else None,
                        rhumb_fee_usd=round(margin_cents / 100, 6) if margin_cents and margin_cents > 0 else None,
                        total_cost_usd=round(billed_cost_cents / 100, 6) if billed_cost_cents > 0 else None,
                        credits_deducted=round(billed_cost_cents / 100, 6) if billed_cost_cents > 0 else None,
                        request_hash=hash_request_payload(request.body),
                        response_hash=hash_response_payload(upstream_response),
                        x402_tx_hash=x402_receipt.get("tx_hash") if x402_receipt else None,
                        x402_network=x402_receipt.get("network") if x402_receipt else None,
                        x402_payer=x402_receipt.get("from_address") if x402_receipt else None,
                        interface=request.interface,
                        idempotency_key=request.idempotency_key,
                        error_code=str(upstream_status) if not success else None,
                        error_message=error_message if not success else None,
                    ))
                    vault_response["receipt_id"] = vault_receipt_obj.receipt_id
                except Exception as receipt_err:
                    logger.warning("receipt_creation_failed execution_id=%s error=%s", execution_id, receipt_err)

            _emit_execution_billing_event(
                success=success,
                org_id=org_id,
                execution_id=execution_id,
                capability_id=capability_id,
                provider_slug=public_provider_used,
                credential_mode="agent_vault",
                amount_usd_cents=billed_cost_cents,
                receipt_id=vault_response.get("receipt_id"),
                interface=request.interface,
                billing_status=billing_status,
                error_message=error_message if not success else None,
            )
            _record_execution_audit_outcome(
                success=success,
                org_id=org_id,
                agent_id=agent_id,
                execution_id=execution_id,
                capability_id=capability_id,
                provider_slug=public_provider_used,
                credential_mode="agent_vault",
                interface=request.interface,
                upstream_status=upstream_status,
                receipt_id=vault_response.get("receipt_id"),
                billing_status=billing_status,
                latency_ms=total_latency_ms,
                error_message=error_message if not success else None,
            )

            await _store_idempotent_result(
                "completed" if success else "failed",
                hash_response_payload(upstream_response),
            )
            return {"data": vault_response, "error": None}

        except httpx.HTTPError as e:
            public_requested_provider = _public_provider_label(request.provider)
            logger.warning(
                "agent_vault upstream request failed provider=%s public_provider=%s agent_id=%s error=%s",
                request.provider,
                public_requested_provider,
                agent_id,
                e,
            )
            await _release_reservations()
            raise HTTPException(
                status_code=502,
                detail=f"Upstream request failed for provider '{public_requested_provider}'",
            ) from e

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
    headers, auth_body, auth_params = _inject_auth_request_parts(
        proxy_slug,
        auth_method,
        headers,
        request.body,
        request.params,
    )

    request_start = time.perf_counter()
    upstream_status: Optional[int] = None
    upstream_response: Any = None
    upstream_latency_ms = 0.0
    success = False
    error_message: Optional[str] = None

    public_requested_provider = _public_provider_label(request.provider or provider_slug)
    use_pool = proxy_slug in SERVICE_REGISTRY
    final_body, final_params = _prepare_upstream_payload(
        request.method,
        auth_body,
        auth_params,
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
        logger.warning(
            "capability_execute upstream request failed provider=%s public_provider=%s proxy_slug=%s agent_id=%s error=%s",
            provider_slug,
            public_requested_provider,
            proxy_slug,
            agent_id,
            e,
        )
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
            detail=f"Upstream request failed for provider '{public_requested_provider}'",
        ) from e

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

    public_provider_used = _public_provider_slug(provider_slug)
    update_payload = {
        "provider_used": public_provider_used,
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
        "fallback_provider": _public_provider_slug(fallback_provider),
        "idempotency_key": request.idempotency_key,
        "error_message": error_message,
        "interface": request.interface,
    }

    response_data = {
        "capability_id": capability_id,
        "provider_used": public_provider_used,
        "credential_mode": request.credential_mode,
        "upstream_status": upstream_status,
        "upstream_response": upstream_response,
        "cost_estimate_usd": cost_per_call,
        "latency_ms": round(total_latency_ms, 1),
        "fallback_attempted": fallback_attempted,
        "fallback_provider": _public_provider_slug(fallback_provider),
        "execution_id": execution_id,
    }
    if budget_remaining is not None:
        response_data["budget_remaining_usd"] = round(budget_remaining, 4)
    if credit_remaining_cents is not None:
        response_data["org_credits_remaining_cents"] = credit_remaining_cents
    response_data = _canonicalize_public_provider_payload(
        response_data,
        provider_slug=public_provider_used,
    )
    upstream_response = response_data.get("upstream_response")
    if not success and error_message is None:
        error_message = _extract_public_error_message(upstream_response)
        if error_message:
            update_payload["error_message"] = error_message

    try:
        await supabase_patch_required(
            f"capability_executions?id=eq.{quote(execution_id)}",
            update_payload,
        )
    except SupabaseWriteUnavailable as exc:
        raise _execution_recording_unavailable(exc) from exc

    # ── Build response headers ──────────────────────────────────────
    response_headers: dict[str, str] = {}

    # x402 anonymous identity headers
    if is_x402_anonymous:
        response_headers["X-Rhumb-Auth"] = "x402-anonymous"
        if x402_wallet_address:
            response_headers["X-Rhumb-Wallet"] = x402_wallet_address
        if x402_rate_remaining is not None:
            response_headers["X-Rhumb-Rate-Remaining"] = str(x402_rate_remaining)

    # x402: attach receipt info and payment response headers
    if x402_receipt:
        response_data["x402_receipt"] = {
            "tx_hash": x402_receipt["tx_hash"],
            "verified": True,
        }
        payment_response = {
            "verified": True,
            "tx_hash": x402_receipt["tx_hash"],
        }
        if x402_receipt.get("payment_request_id"):
            response_data["x402_receipt"]["payment_request_id"] = x402_receipt["payment_request_id"]
            payment_response["paymentRequestId"] = x402_receipt["payment_request_id"]
        if x402_receipt.get("network"):
            response_data["x402_receipt"]["network"] = x402_receipt["network"]
            payment_response["network"] = x402_receipt["network"]
        if standard_x402_payment_response_header:
            response_headers["PAYMENT-RESPONSE"] = standard_x402_payment_response_header
            response_headers["X-Payment-Response"] = standard_x402_payment_response_header
        else:
            response_headers["X-Payment-Response"] = json.dumps(payment_response)

    # ── Emit execution receipt (BYO) ──
    if not _should_skip_receipt(raw_request):
        try:
            byo_receipt_obj = await get_receipt_service().create_receipt(ReceiptInput(
                execution_id=execution_id,
                capability_id=capability_id,
                status="success" if success else "failure",
                agent_id=agent_id,
                provider_id=public_provider_used,
                credential_mode=request.credential_mode,
                org_id=org_id,
                caller_ip_hash=hash_caller_ip(_client_ip(raw_request)),
                total_latency_ms=round(total_latency_ms, 1),
                provider_latency_ms=round(upstream_latency_ms, 1),
                rhumb_overhead_ms=round(total_latency_ms - upstream_latency_ms, 1),
                provider_cost_usd=cost_per_call,
                rhumb_fee_usd=round(actual_margin_cents / 100, 6) if actual_margin_cents and actual_margin_cents > 0 else None,
                total_cost_usd=round(actual_billed_cents / 100, 6) if actual_billed_cents and actual_billed_cents > 0 else None,
                credits_deducted=round(actual_billed_cents / 100, 6) if actual_billed_cents and actual_billed_cents > 0 else None,
                request_hash=hash_request_payload(request.body),
                response_hash=hash_response_payload(upstream_response),
                x402_tx_hash=x402_receipt.get("tx_hash") if x402_receipt else None,
                x402_network=x402_receipt.get("network") if x402_receipt else None,
                x402_payer=x402_receipt.get("from_address") if x402_receipt else None,
                interface=request.interface,
                idempotency_key=request.idempotency_key,
                error_code=str(upstream_status) if not success else None,
                error_message=error_message,
            ))
            response_data["receipt_id"] = byo_receipt_obj.receipt_id
        except Exception as receipt_err:
            logger.warning("receipt_creation_failed execution_id=%s error=%s", execution_id, receipt_err)

    _emit_execution_billing_event(
        success=success,
        org_id=org_id,
        execution_id=execution_id,
        capability_id=capability_id,
        provider_slug=public_provider_used,
        credential_mode=request.credential_mode,
        amount_usd_cents=actual_billed_cents,
        receipt_id=response_data.get("receipt_id"),
        interface=request.interface,
        billing_status=billing_status,
        error_message=error_message if not success else None,
    )
    _record_execution_audit_outcome(
        success=success,
        org_id=org_id,
        agent_id=agent_id,
        execution_id=execution_id,
        capability_id=capability_id,
        provider_slug=public_provider_used,
        credential_mode=request.credential_mode,
        interface=request.interface,
        upstream_status=upstream_status,
        receipt_id=response_data.get("receipt_id"),
        billing_status=billing_status,
        latency_ms=total_latency_ms,
        error_message=error_message if not success else None,
    )

    # ── Provider attribution (WU-41.2) ──────────────────────────────
    try:
        attribution = await build_attribution(
            provider_slug=public_provider_used,
            layer=2,
            receipt_id=response_data.get("receipt_id"),
            cost_provider_usd=cost_per_call,
            cost_rhumb_fee_usd=(
                round(actual_margin_cents / 100, 6)
                if actual_margin_cents and actual_margin_cents > 0 else None
            ),
            cost_total_usd=(
                round(actual_billed_cents / 100, 6)
                if actual_billed_cents and actual_billed_cents > 0 else None
            ),
            latency_total_ms=round(total_latency_ms, 1),
            latency_provider_ms=round(upstream_latency_ms, 1),
            latency_overhead_ms=round(total_latency_ms - upstream_latency_ms, 1),
            credential_mode=request.credential_mode,
        )
        response_data["_rhumb"] = attribution.to_rhumb_block()
        response_headers.update(attribution.to_response_headers())
    except Exception:
        logger.exception("v1_attribution_failed execution_id=%s provider=%s", execution_id, provider_slug)

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
    await _store_idempotent_result(
        "completed",
        hash_response_payload(response_data.get("upstream_response")),
    )
    return {"data": response_data, "error": None}


@router.get("/capabilities/{capability_id}/execute/estimate")
async def estimate_capability(
    capability_id: str,
    raw_request: Request,
    provider: Optional[str] = Query(None, description="Provider slug"),
    credential_mode: str = Query(
        "auto",
        description=(
            "Credential mode (auto, byok, rhumb_managed, agent_vault). "
            "'auto' uses rhumb_managed when available, falls back to byok."
        ),
    ),
    x_rhumb_key: Optional[str] = Header(None, alias="X-Rhumb-Key"),
) -> Any:
    """Dry-run cost estimate — returns provider selection, cost, and circuit state without executing.

    API key is optional. Without an API key the response still includes
    provider, cost, and circuit state but omits budget-specific fields.
    This lets x402 agents discover pricing before paying.
    """
    normalized_credential_mode = _canonicalize_credential_mode(credential_mode)
    if (
        normalized_credential_mode is None
        and str(credential_mode or "").strip()
    ) or normalized_credential_mode not in _VALID_EXECUTE_CREDENTIAL_MODES:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid 'credential_mode' parameter. Use one of: auto, byok, rhumb_managed, agent_vault. "
                "Legacy 'byo' is accepted as 'byok'."
            ),
        )
    credential_mode = normalized_credential_mode or "auto"

    # Authenticate if API key provided; otherwise allow anonymous estimate
    agent_id: Optional[str] = None
    is_anonymous_estimate = False

    if x_rhumb_key:
        agent = await _get_identity_store().verify_api_key_with_agent(x_rhumb_key)
        if agent is None:
            return _invalid_governed_api_key_response(raw_request, capability_id=capability_id)
        agent_id = agent.agent_id
    else:
        is_anonymous_estimate = True
        agent_id = "x402_anonymous"

    cap = await _resolve_capability(capability_id)
    if cap is None:
        return await _capability_not_found_response(raw_request, capability_id)

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
    if credential_mode == "rhumb_managed":
        chosen = managed_mapping or await _resolve_managed_provider_mapping(
            capability_id=capability_id,
            mappings=mappings,
            requested_provider=provider,
        )
        if chosen is None:
            fallback_managed_mapping = None
            if provider:
                fallback_managed_mapping = await _resolve_managed_provider_mapping(
                    capability_id=capability_id,
                    mappings=mappings,
                    requested_provider=None,
                )
            return _managed_provider_unavailable_response(
                raw_request,
                capability_id=capability_id,
                mappings=mappings,
                requested_provider=provider,
                available_managed_mappings=[fallback_managed_mapping] if fallback_managed_mapping else [],
            )
    elif provider:
        public_provider = _public_provider_label(provider)
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
                detail=f"Provider '{public_provider}' not available for capability '{capability_id}'",
            )
    elif capability_id in DIRECT_EXECUTE_CAPABILITY_IDS:
        chosen = mappings[0]
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
        "provider": _public_provider_slug(provider_slug),
        "credential_mode": credential_mode,
        "cost_estimate_usd": cost_per_call,
        "circuit_state": circuit_state,
        "endpoint_pattern": chosen.get("endpoint_pattern"),
    }

    if is_anonymous_estimate and capability_id in DIRECT_EXECUTE_CAPABILITY_IDS:
        execute_readiness = _direct_execute_estimate_readiness(capability_id)
        if execute_readiness is not None:
            estimate_data["execute_readiness"] = execute_readiness

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
