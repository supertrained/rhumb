"""Resolve v2 compatibility gateway.

Initial v2 surface for Layer 2 execution. This ships an honest, opt-in
compatibility namespace without breaking the existing `/v1/` contract.

Current scope:
- `/v2/health`
- `/v2/capabilities`
- `/v2/capabilities/{capability_id}/resolve`
- `/v2/capabilities/{capability_id}/credential-modes`
- `/v2/policy`
- `/v2/capabilities/{capability_id}/execute/estimate`
- `/v2/capabilities/{capability_id}/execute`

The execute path currently translates the new v2 request envelope into the
existing v1 capability execute contract, then returns the v1 execution payload
annotated with `_rhumb_v2` metadata. This is deliberately conservative: the
v2 path is real and testable today, while the deeper receipt/policy/routing
internals land in later R40 slices.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)
from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from routes import capabilities as v1_capabilities
from routes import capability_execute as v1_execute
from services.budget_enforcer import BudgetEnforcer, BudgetStatus
from services.error_envelope import RhumbError
from services.policy_engine import PolicyProviderDecision, get_policy_engine
from services.receipt_service import (
    ReceiptInput,
    get_receipt_service,
    hash_caller_ip,
    hash_request_payload,
    hash_response_payload,
)
from services.provider_attribution import build_attribution
from services.resolve_policy_store import StoredResolvePolicy, get_resolve_policy_store
from services.route_explanation import build_explanation, persist_explanation, store_explanation
from services.service_slugs import (
    CANONICAL_TO_PROXY,
    canonicalize_service_slug,
    public_service_slug_candidates,
)

router = APIRouter()

_COMPAT_VERSION = "2026-03-30"
_COMPAT_MODE = "v1-translate"
_SUPPORTED_POLICY_FIELDS = [
    "pin",
    "provider_preference",
    "provider_deny",
    "allow_only",
    "max_cost_usd",
]
_VALID_RESOLVE_CREDENTIAL_MODES = frozenset({"byok", "rhumb_managed", "agent_vault"})
_VALID_ESTIMATE_CREDENTIAL_MODES = frozenset({"auto", *_VALID_RESOLVE_CREDENTIAL_MODES})
_POLICY_LIST_FIELDS = [
    "provider_preference",
    "provider_deny",
    "allow_only",
]
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
_PUBLIC_PROVIDER_FIELD_KEYS = {
    "provider",
    "provider_used",
    "provider_id",
    "provider_slug",
    "preferred_provider",
    "selected_provider",
    "requested_provider",
    "fallback_provider",
    "service_slug",
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
_PUBLIC_PROVIDER_TEXT_KEYS = {
    "message",
    "detail",
    "error_message",
}
_PUBLIC_PROVIDER_ALIAS_TEXT_KEYS = {
    "setup_hint",
}

_v2_budget_enforcer = BudgetEnforcer()


class V2CapabilityPolicy(BaseModel):
    """Inline v2 per-call policy overrides for the supported compat subset."""

    model_config = ConfigDict(extra="forbid")

    pin: str | None = Field(
        default=None,
        description="Hard-pin execution to a specific provider.",
    )
    provider_preference: list[str] | None = Field(
        default=None,
        description="Ordered provider preference list. Set to [] to clear stored account preference for this call.",
    )
    provider_deny: list[str] | None = Field(
        default=None,
        description="Providers that must not be used for this execution.",
    )
    allow_only: list[str] | None = Field(
        default=None,
        description="If present, restrict execution to this provider subset. Set to [] to clear stored account restriction for this call.",
    )
    max_cost_usd: float | None = Field(
        default=None,
        ge=0,
        description="Hard per-call ceiling enforced before execution using the existing estimate path.",
    )


class V2StoredPolicy(BaseModel):
    """Persisted organization-level policy subset that v2 supports today."""

    model_config = ConfigDict(extra="forbid")

    pin: str | None = Field(
        default=None,
        description="Stored provider pin for this organization.",
    )
    provider_preference: list[str] = Field(
        default_factory=list,
        description="Stored ordered provider preferences for this organization.",
    )
    provider_deny: list[str] = Field(
        default_factory=list,
        description="Stored deny-list for this organization.",
    )
    allow_only: list[str] = Field(
        default_factory=list,
        description="Stored allow-list for this organization.",
    )
    max_cost_usd: float | None = Field(
        default=None,
        ge=0,
        description="Stored per-call max-cost ceiling for this organization.",
    )


class V2CapabilityExecuteRequest(BaseModel):
    """Layer 2 execute envelope for the initial v2 gateway slice."""

    model_config = ConfigDict(extra="forbid")

    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Normalized capability parameters.",
    )
    policy: V2CapabilityPolicy | None = Field(
        default=None,
        description="Optional per-call override subset supported by the compat layer.",
    )
    credential_mode: str = Field(
        default="auto",
        description="Credential mode (auto, byok, rhumb_managed, agent_vault; legacy byo accepted).",
    )
    idempotency_key: str | None = Field(
        default=None,
        description="Optional per-call idempotency key.",
    )
    interface: str = Field(
        default="rest",
        description="Calling surface label for analytics and compat reporting.",
    )


def _compat_headers() -> dict[str, str]:
    return {
        "X-Rhumb-Version": _COMPAT_VERSION,
        "X-Rhumb-Compat": _COMPAT_MODE,
    }


def _canonicalize_credential_mode(credential_mode: str | None) -> str:
    """Normalize legacy credential-mode aliases for the compat surface."""
    return v1_execute._canonicalize_credential_mode(credential_mode) or "auto"


def _validated_credential_mode_filter(credential_mode: str | None) -> str | None:
    if credential_mode is None:
        return None

    raw_value = str(credential_mode).strip()
    normalized = v1_execute._canonicalize_credential_mode(raw_value)
    if normalized in _VALID_RESOLVE_CREDENTIAL_MODES:
        return normalized

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'credential_mode' filter.",
        detail="Use one of: byok, rhumb_managed, agent_vault. Legacy 'byo' is accepted as 'byok'.",
    )


def _validated_estimate_credential_mode(credential_mode: str | None) -> str:
    if credential_mode is None:
        raw_value = "auto"
    else:
        raw_value = str(credential_mode).strip()

    if not raw_value:
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid 'credential_mode' parameter.",
            detail="Use one of: auto, byok, rhumb_managed, agent_vault. Legacy 'byo' is accepted as 'byok'.",
        )

    normalized = v1_execute._canonicalize_credential_mode(raw_value) or "auto"
    if normalized in _VALID_ESTIMATE_CREDENTIAL_MODES:
        return normalized

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'credential_mode' parameter.",
        detail="Use one of: auto, byok, rhumb_managed, agent_vault. Legacy 'byo' is accepted as 'byok'.",
    )


def _validated_estimate_provider_filter(provider: str | None) -> str | None:
    if provider is None:
        return None

    normalized = str(provider).strip()
    if normalized:
        return normalized

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'provider' filter.",
        detail="Provide a non-empty provider slug or omit the filter.",
    )


def _compat_meta() -> dict[str, Any]:
    return {
        "api_version": "v2-alpha",
        "compat_mode": _COMPAT_MODE,
        "layer": 2,
    }


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


def _annotate_v2_body(body: dict[str, Any]) -> dict[str, Any]:
    meta = _compat_meta()
    if isinstance(body.get("data"), dict):
        body["data"]["_rhumb_v2"] = meta
    else:
        body["_rhumb_v2"] = meta
    return body


def _extract_error_fields(body: Any) -> tuple[str | None, str | None]:
    """Tolerate both structured and x402-style string error payloads."""
    if not isinstance(body, dict):
        return None, None
    error = body.get("error")
    if isinstance(error, dict):
        return error.get("code"), error.get("message")
    if isinstance(error, str):
        message = body.get("detail")
        if not isinstance(message, str):
            message = body.get("resolution") if isinstance(body.get("resolution"), str) else None
        return error, message
    return None, None


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


def _compat_receipt_id(execution_id: str | None) -> str | None:
    if not execution_id:
        return None
    return f"rcpt_compat_{execution_id}"


def _preferred_provider(policy: V2CapabilityPolicy | None) -> str | None:
    if not policy:
        return None
    if policy.pin:
        return policy.pin.strip()
    if policy.provider_preference:
        return policy.provider_preference[0]
    return None


async def _resolve_policy_agent(raw_request: Request):
    x_rhumb_key = raw_request.headers.get("X-Rhumb-Key")
    if not x_rhumb_key:
        raise RhumbError(
            "CREDENTIAL_INVALID",
            message="Resolve v2 policy endpoints require a valid governed API key.",
            detail="Provide a valid X-Rhumb-Key header tied to an organization-backed agent.",
        )

    agent = await v1_execute._get_identity_store().verify_api_key_with_agent(x_rhumb_key)
    if agent is None:
        raise RhumbError(
            "CREDENTIAL_INVALID",
            message="Invalid or expired governed API key.",
            detail="Provide a valid X-Rhumb-Key header or use an x402 payment flow.",
        )
    if not agent.organization_id:
        raise RhumbError(
            "CREDENTIAL_INVALID",
            message="Governed API key is not attached to an organization.",
            detail="Rotate or recreate the key after the agent has been attached to an organization.",
        )
    return agent


async def _resolve_policy_agent_id(raw_request: Request) -> str:
    x_rhumb_key = raw_request.headers.get("X-Rhumb-Key")
    if not x_rhumb_key:
        return raw_request.headers.get("X-Rhumb-Agent-Id") or "x402_anonymous"

    agent = await v1_execute._get_identity_store().verify_api_key_with_agent(x_rhumb_key)
    if agent is None:
        raise RhumbError(
            "CREDENTIAL_INVALID",
            message="Invalid or expired governed API key.",
            detail="Provide a valid X-Rhumb-Key header or use an x402 payment flow.",
        )
    return agent.agent_id


def _effective_policy_active(policy: V2CapabilityPolicy | None) -> bool:
    if policy is None:
        return False
    policy_engine = get_policy_engine()
    return policy_engine.has_provider_controls(policy) or policy.max_cost_usd is not None


def _stored_policy_to_response(policy: StoredResolvePolicy | None) -> V2StoredPolicy:
    if policy is None:
        return V2StoredPolicy()
    return V2StoredPolicy(
        pin=policy.pin,
        provider_preference=list(policy.provider_preference or []),
        provider_deny=list(policy.provider_deny or []),
        allow_only=list(policy.allow_only or []),
        max_cost_usd=policy.max_cost_usd,
    )


def _stored_policy_to_inline(policy: StoredResolvePolicy | None) -> V2CapabilityPolicy | None:
    if policy is None:
        return None
    return V2CapabilityPolicy(
        pin=policy.pin,
        provider_preference=list(policy.provider_preference or []),
        provider_deny=list(policy.provider_deny or []),
        allow_only=list(policy.allow_only or []),
        max_cost_usd=policy.max_cost_usd,
    )


def _merge_effective_policy(
    account_policy: StoredResolvePolicy | None,
    inline_policy: V2CapabilityPolicy | None,
) -> tuple[V2CapabilityPolicy | None, dict[str, Any]]:
    account_inline = _stored_policy_to_inline(account_policy)
    values: dict[str, Any] = {}
    organization_fields: list[str] = []
    inline_fields: list[str] = []

    for field_name in _SUPPORTED_POLICY_FIELDS:
        inline_supplied = inline_policy is not None and field_name in inline_policy.model_fields_set
        if inline_supplied:
            value = getattr(inline_policy, field_name)
            inline_fields.append(field_name)
        elif account_inline is not None:
            value = getattr(account_inline, field_name)
            has_value = value is not None and (not isinstance(value, list) or bool(value))
            if has_value:
                organization_fields.append(field_name)
        else:
            value = None

        if field_name in _POLICY_LIST_FIELDS:
            if inline_supplied or (value is not None and value):
                values[field_name] = list(value or [])
            continue

        if value is not None:
            values[field_name] = value

    effective_policy = None
    if values or organization_fields or inline_fields:
        effective_policy = V2CapabilityPolicy(**values)

    return effective_policy, {
        "scope": "organization",
        "has_account_policy": _effective_policy_active(account_inline),
        "organization_fields": organization_fields,
        "inline_fields": inline_fields,
    }


def _policy_summary(policy: V2CapabilityPolicy | None) -> dict[str, Any] | None:
    if policy is None:
        return None
    return get_policy_engine().summarize_policy(policy)


def _has_inline_x402_payment(raw_request: Request) -> bool:
    return bool(
        raw_request.headers.get("X-Payment")
        or raw_request.headers.get("PAYMENT-SIGNATURE")
    )


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


def _public_provider_slug(slug: str | None) -> str | None:
    if slug is None:
        return None
    cleaned = str(slug).strip().lower()
    if not cleaned:
        return None
    return canonicalize_service_slug(cleaned)


def _public_provider_list(slugs: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for slug in slugs or []:
        public_slug = _public_provider_slug(slug)
        if not public_slug or public_slug in seen:
            continue
        normalized.append(public_slug)
        seen.add(public_slug)
    return normalized


def _public_policy_summary(summary: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(summary, dict):
        return summary

    normalized = dict(summary)
    if "pin" in normalized:
        normalized["pin"] = _public_provider_slug(normalized.get("pin"))
    for field in (
        "provider_preference",
        "provider_deny",
        "allow_only",
        "candidate_providers",
    ):
        if field in normalized:
            normalized[field] = _public_provider_list(normalized.get(field))
    return normalized


def _canonicalize_execute_body_provider_fields(
    body: Any,
    *,
    provider_slug: str | None,
) -> Any:
    provider_slugs: set[str] = set()
    if provider_slug:
        provider_slugs.add(str(provider_slug).strip())
    _collect_execute_body_provider_slugs(body, provider_slugs)
    return _canonicalize_execute_body_provider_payload(body, provider_slugs=provider_slugs)


def _collect_execute_body_provider_slugs(value: Any, provider_slugs: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _PUBLIC_PROVIDER_FIELD_KEYS:
                if isinstance(item, str) and item.strip():
                    provider_slugs.add(item.strip())
                continue
            if key in _PUBLIC_PROVIDER_LIST_KEYS and isinstance(item, list):
                for entry in item:
                    if isinstance(entry, str) and entry.strip():
                        provider_slugs.add(entry.strip())
                continue
            _collect_execute_body_provider_slugs(item, provider_slugs)
    elif isinstance(value, list):
        for item in value:
            _collect_execute_body_provider_slugs(item, provider_slugs)


def _canonicalize_execute_body_provider_value(value: Any) -> Any:
    if isinstance(value, str):
        return _public_provider_slug(value) or value
    return value


def _canonicalize_known_execute_body_provider_aliases(text: Any) -> str | None:
    if text is None:
        return None

    replacements: dict[str, str] = {}
    for canonical in CANONICAL_TO_PROXY:
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


def _canonicalize_execute_body_provider_text(
    text: Any,
    *,
    provider_slugs: set[str],
    alias_only: bool = False,
) -> str | None:
    if text is None:
        return None

    rendered = str(text)
    replacements: dict[str, str] = {}
    for provider_slug in provider_slugs:
        canonical = _public_provider_slug(provider_slug)
        if not canonical:
            continue
        if alias_only and str(provider_slug).strip().lower() == canonical.lower():
            continue
        for candidate in public_service_slug_candidates(canonical):
            cleaned = str(candidate or "").strip()
            if cleaned:
                replacements[cleaned.lower()] = canonical

    if not replacements:
        return rendered

    canonicalized = rendered
    for candidate in sorted(replacements, key=len, reverse=True):
        canonicalized = re.sub(
            rf"(?<![a-z0-9-]){re.escape(candidate)}(?![a-z0-9-])",
            replacements[candidate],
            canonicalized,
            flags=re.IGNORECASE,
        )
    return _canonicalize_known_execute_body_provider_aliases(canonicalized)


def _canonicalize_execute_body_provider_payload(
    value: Any,
    *,
    provider_slugs: set[str],
) -> Any:
    if isinstance(value, dict):
        canonicalized: dict[str, Any] = {}
        for key, item in value.items():
            if key in _PUBLIC_PROVIDER_FIELD_KEYS:
                canonicalized[key] = _canonicalize_execute_body_provider_value(item)
            elif key in _PUBLIC_PROVIDER_TEXT_KEYS:
                canonicalized[key] = _canonicalize_execute_body_provider_text(
                    item,
                    provider_slugs=provider_slugs,
                )
            elif key in _PUBLIC_PROVIDER_ALIAS_TEXT_KEYS:
                canonicalized[key] = _canonicalize_execute_body_provider_text(
                    item,
                    provider_slugs=provider_slugs,
                    alias_only=True,
                )
            elif key in _PUBLIC_PROVIDER_LIST_KEYS and isinstance(item, list):
                canonicalized[key] = [
                    _canonicalize_execute_body_provider_value(entry)
                    for entry in item
                ]
            else:
                canonicalized[key] = _canonicalize_execute_body_provider_payload(
                    item,
                    provider_slugs=provider_slugs,
                )
        return canonicalized
    if isinstance(value, list):
        return [
            _canonicalize_execute_body_provider_payload(
                item,
                provider_slugs=provider_slugs,
            )
            for item in value
        ]
    return value


async def _enforce_agent_budget(
    *,
    agent_id: str,
    estimated_cost: float | None,
) -> BudgetStatus:
    status = await _v2_budget_enforcer.get_budget(agent_id)
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


@dataclass
class PolicyEvaluationResult:
    """Result of evaluating provider policy, with mapping context for explanation."""

    decision: PolicyProviderDecision | None
    all_mappings: list[dict[str, Any]]
    eligible_mappings: list[dict[str, Any]]


async def _evaluate_provider_policy(
    capability_id: str,
    raw_request: Request,
    policy: V2CapabilityPolicy | None,
) -> PolicyEvaluationResult:
    all_mappings = await v1_execute._get_capability_services(capability_id)

    policy_engine = get_policy_engine()
    if not policy_engine.has_provider_controls(policy):
        return PolicyEvaluationResult(
            decision=None,
            all_mappings=all_mappings,
            eligible_mappings=all_mappings,
        )

    agent_id = await _resolve_policy_agent_id(raw_request)
    decision = await policy_engine.resolve_provider(
        mappings=all_mappings,
        agent_id=agent_id,
        policy=policy,
        auto_selector=v1_execute._auto_select_provider,
    )
    # Eligible = the candidates that survived policy filtering
    eligible_slugs = set(decision.candidate_providers) if decision else set()
    eligible_mappings = [
        m for m in all_mappings
        if m.get("service_slug") in eligible_slugs
    ] if eligible_slugs else all_mappings

    return PolicyEvaluationResult(
        decision=decision,
        all_mappings=all_mappings,
        eligible_mappings=eligible_mappings,
    )


@router.get("/health")
async def v2_health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": _COMPAT_VERSION,
        "compat_mode": _COMPAT_MODE,
        "layer": 2,
    }


@router.get("/capabilities")
async def list_capabilities_v2(
    domain: str | None = Query(default=None, description="Filter by domain"),
    search: str | None = Query(default=None, description="Search capabilities by text"),
    limit: int = Query(default=50),
    offset: int = Query(default=0),
) -> dict[str, Any]:
    body = await v1_capabilities.list_capabilities(
        domain=domain,
        search=search,
        limit=limit,
        offset=offset,
    )
    if isinstance(body, dict):
        body = _annotate_v2_body(body)
    return body


@router.get("/capabilities/{capability_id}/resolve")
async def resolve_capability_v2(
    capability_id: str,
    raw_request: Request,
    credential_mode: str | None = Query(
        default=None,
        description="Filter by credential mode (byok, rhumb_managed, agent_vault; legacy byo accepted).",
    ),
) -> JSONResponse:
    canonical_credential_mode = _validated_credential_mode_filter(credential_mode)
    resolve_response = await _forward_internal(
        raw_request,
        method="GET",
        path=f"/v1/capabilities/{capability_id}/resolve",
        params=(
            {"credential_mode": canonical_credential_mode}
            if canonical_credential_mode is not None
            else None
        ),
    )

    body = _rewrite_navigation_urls(resolve_response.json())
    body = _canonicalize_execute_body_provider_fields(body, provider_slug=None)
    if resolve_response.status_code == 200 and isinstance(body.get("data"), dict):
        body = _annotate_v2_body(body)

    return JSONResponse(
        status_code=resolve_response.status_code,
        content=body,
        headers=_merge_response_headers(resolve_response),
    )


@router.get("/capabilities/{capability_id}/credential-modes")
async def get_credential_modes_v2(
    capability_id: str,
    raw_request: Request,
) -> JSONResponse:
    modes_response = await _forward_internal(
        raw_request,
        method="GET",
        path=f"/v1/capabilities/{capability_id}/credential-modes",
    )

    body = _rewrite_navigation_urls(modes_response.json())
    body = _canonicalize_execute_body_provider_fields(body, provider_slug=None)
    if modes_response.status_code == 200 and isinstance(body.get("data"), dict):
        body = _annotate_v2_body(body)

    return JSONResponse(
        status_code=modes_response.status_code,
        content=body,
        headers=_merge_response_headers(modes_response),
    )


@router.get("/policy")
async def get_policy_v2(raw_request: Request) -> dict[str, Any]:
    agent = await _resolve_policy_agent(raw_request)
    stored_policy = await get_resolve_policy_store().get_policy(agent.organization_id)
    policy = _stored_policy_to_response(stored_policy)
    return {
        "error": None,
        "data": {
            "scope": "organization",
            "organization_id": agent.organization_id,
            "policy": policy.model_dump(),
            "has_policy": _effective_policy_active(_stored_policy_to_inline(stored_policy)),
            "updated_at": stored_policy.updated_at if stored_policy else None,
            "_rhumb_v2": {
                "api_version": "v2-alpha",
                "compat_mode": _COMPAT_MODE,
                "layer": 2,
                "supported_policy_fields": _SUPPORTED_POLICY_FIELDS,
            },
        },
    }


@router.put("/policy")
async def put_policy_v2(
    payload: V2StoredPolicy,
    raw_request: Request,
) -> dict[str, Any]:
    agent = await _resolve_policy_agent(raw_request)
    stored_policy = await get_resolve_policy_store().put_policy(
        agent.organization_id,
        pin=payload.pin,
        provider_preference=payload.provider_preference,
        provider_deny=payload.provider_deny,
        allow_only=payload.allow_only,
        max_cost_usd=payload.max_cost_usd,
    )
    if stored_policy is None:
        raise RhumbError(
            "SERVICE_UNAVAILABLE",
            message="Unable to persist Resolve v2 policy at the moment.",
            detail="Retry shortly. If the problem persists, check Supabase availability.",
        )

    response_policy = _stored_policy_to_response(stored_policy)
    return {
        "error": None,
        "data": {
            "scope": "organization",
            "organization_id": agent.organization_id,
            "policy": response_policy.model_dump(),
            "has_policy": _effective_policy_active(_stored_policy_to_inline(stored_policy)),
            "updated_at": stored_policy.updated_at,
            "_rhumb_v2": {
                "api_version": "v2-alpha",
                "compat_mode": _COMPAT_MODE,
                "layer": 2,
                "supported_policy_fields": _SUPPORTED_POLICY_FIELDS,
            },
        },
    }


@router.get("/capabilities/{capability_id}/execute/estimate")
async def estimate_capability_v2(
    capability_id: str,
    raw_request: Request,
    credential_mode: str = Query(
        "auto",
        description="Credential mode (auto, byok, rhumb_managed, agent_vault; legacy byo accepted).",
    ),
    provider: str | None = Query(default=None),
) -> JSONResponse:
    canonical_credential_mode = _validated_estimate_credential_mode(credential_mode)
    canonical_provider = _validated_estimate_provider_filter(provider)
    estimate_response = await _forward_internal(
        raw_request,
        method="GET",
        path=f"/v1/capabilities/{capability_id}/execute/estimate",
        params={
            "credential_mode": canonical_credential_mode,
            **({"provider": canonical_provider} if canonical_provider else {}),
        },
    )

    body = _rewrite_navigation_urls(estimate_response.json())
    body = _canonicalize_execute_body_provider_fields(
        body,
        provider_slug=canonical_provider,
    )
    if estimate_response.status_code == 200 and isinstance(body.get("data"), dict):
        if body["data"].get("credential_mode") is not None:
            body["data"]["credential_mode"] = _canonicalize_credential_mode(
                body["data"].get("credential_mode")
            )
        body = _annotate_v2_body(body)

    return JSONResponse(
        status_code=estimate_response.status_code,
        content=body,
        headers=_merge_response_headers(estimate_response),
    )


@router.post("/capabilities/{capability_id}/execute")
async def execute_capability_v2(
    capability_id: str,
    payload: V2CapabilityExecuteRequest,
    raw_request: Request,
    x_rhumb_idempotency_key: str | None = Header(None, alias="X-Rhumb-Idempotency-Key"),
) -> JSONResponse:
    canonical_credential_mode = _canonicalize_credential_mode(payload.credential_mode)
    agent = None
    account_policy = None
    if raw_request.headers.get("X-Rhumb-Key"):
        agent = await _resolve_policy_agent(raw_request)
        account_policy = await get_resolve_policy_store().get_policy(agent.organization_id)

    effective_policy, policy_source = _merge_effective_policy(account_policy, payload.policy)
    try:
        policy_eval = await _evaluate_provider_policy(capability_id, raw_request, effective_policy)
    except RhumbError as exc:
        extra = dict(exc.extra or {})
        if "policy" in extra:
            extra["policy"] = _public_policy_summary(extra.get("policy"))
        if "selected_provider" in extra:
            extra["selected_provider"] = _public_provider_slug(extra.get("selected_provider")) or extra.get("selected_provider")
        raise RhumbError(
            exc.code,
            message=exc.message,
            detail=exc.detail,
            receipt_id=exc.receipt_id,
            provider=exc.provider,
            retry_after_ms=exc.retry_after_ms,
            extra=extra,
        ) from exc
    provider_decision = policy_eval.decision
    preferred_provider = (
        provider_decision.selected_provider
        if provider_decision and provider_decision.selected_provider
        else _preferred_provider(effective_policy)
    )

    estimate_response = await _forward_internal(
        raw_request,
        method="GET",
        path=f"/v1/capabilities/{capability_id}/execute/estimate",
        params={
            "credential_mode": canonical_credential_mode,
            **({"provider": preferred_provider} if preferred_provider else {}),
        },
    )

    estimate_body = _rewrite_navigation_urls(estimate_response.json())
    estimate_body = _canonicalize_execute_body_provider_fields(
        estimate_body,
        provider_slug=preferred_provider,
    )
    if estimate_response.status_code != 200:
        return JSONResponse(
            status_code=estimate_response.status_code,
            content=estimate_body,
            headers=_merge_response_headers(estimate_response),
        )

    estimate_data = estimate_body.get("data") or {}
    selected_provider = estimate_data.get("provider")
    selected_provider_public = _public_provider_slug(selected_provider) or selected_provider
    policy_candidates_public = _public_provider_list(
        provider_decision.candidate_providers if provider_decision else []
    )
    endpoint_pattern = estimate_data.get("endpoint_pattern")
    estimated_cost = estimate_data.get("cost_estimate_usd")
    method, path = _parse_endpoint_pattern(endpoint_pattern)

    if (
        provider_decision
        and policy_candidates_public
        and selected_provider_public not in policy_candidates_public
    ):
        raise RhumbError(
            "NO_PROVIDER_AVAILABLE",
            message="Estimated provider does not satisfy the execution policy.",
            detail="Retry with an explicit preferred provider or relax the provider filters.",
            extra={
                "policy": _public_policy_summary(provider_decision.policy_summary),
                "selected_provider": selected_provider_public,
            },
        )

    if effective_policy and effective_policy.max_cost_usd is not None and estimated_cost is not None:
        if float(estimated_cost) > effective_policy.max_cost_usd:
            raise RhumbError(
                "BUDGET_EXCEEDED",
                message=(
                    f"Estimated call cost ${float(estimated_cost):.4f} exceeds policy ceiling "
                    f"${effective_policy.max_cost_usd:.4f}."
                ),
                detail="Raise max_cost_usd, choose a cheaper provider, or retry without a hard ceiling.",
            )

    budget_status: BudgetStatus | None = None
    if agent is not None and not _has_inline_x402_payment(raw_request):
        budget_status = await _enforce_agent_budget(
            agent_id=agent.agent_id,
            estimated_cost=float(estimated_cost) if estimated_cost is not None else None,
        )

    v1_payload: dict[str, Any] = {
        "provider": selected_provider_public or selected_provider,
        "credential_mode": canonical_credential_mode,
        "idempotency_key": payload.idempotency_key or x_rhumb_idempotency_key,
        "interface": f"{payload.interface}-v2",
        "body": payload.parameters,
    }
    if method:
        v1_payload["method"] = method
    if path:
        v1_payload["path"] = path

    execute_response = await _forward_internal(
        raw_request,
        method="POST",
        path=f"/v1/capabilities/{capability_id}/execute",
        json_body=v1_payload,
        extra_headers={"X-Rhumb-Skip-Receipt": "true"},
    )
    body = _rewrite_navigation_urls(execute_response.json())
    body = _canonicalize_execute_body_provider_fields(
        body,
        provider_slug=selected_provider_public or selected_provider,
    )

    # ── Receipt creation ─────────────────────────────────────────────
    execution_data = body.get("data") if isinstance(body.get("data"), dict) else {}
    effective_credential_mode = canonical_credential_mode
    if execution_data.get("credential_mode") is not None:
        effective_credential_mode = _canonicalize_credential_mode(
            execution_data.get("credential_mode")
        )
        execution_data["credential_mode"] = effective_credential_mode
    provider_used_public = (
        _public_provider_slug(execution_data.get("provider_used"))
        or execution_data.get("provider_used")
    )
    if provider_used_public:
        body = _canonicalize_execute_body_provider_fields(
            body,
            provider_slug=provider_used_public,
        )
        execution_data = body.get("data") if isinstance(body.get("data"), dict) else {}
        if execution_data.get("credential_mode") is not None:
            execution_data["credential_mode"] = effective_credential_mode
    execution_id = execution_data.get("execution_id", "")
    is_success = execute_response.status_code == 200

    receipt_id: str | None = None
    provider_public_slug = provider_used_public or selected_provider_public or "unknown"
    try:
        error_code, error_message = _extract_error_fields(body)
        receipt_input = ReceiptInput(
            execution_id=execution_id or f"v2-compat-{int(time.time())}",
            capability_id=capability_id,
            status="success" if is_success else "failure",
            agent_id=execution_data.get("agent_id", "unknown"),
            provider_id=provider_public_slug,
            credential_mode=effective_credential_mode,
            layer=2,
            org_id=execution_data.get("org_id"),
            caller_ip_hash=hash_caller_ip(raw_request.client.host if raw_request.client else None),
            provider_name=provider_public_slug,
            router_version=_COMPAT_VERSION,
            candidates_evaluated=(
                len(provider_decision.candidate_providers)
                if provider_decision and provider_decision.candidate_providers
                else None
            ),
            winner_reason=(
                provider_decision.selected_reason if provider_decision else None
            ),
            total_latency_ms=execution_data.get("latency_ms"),
            rhumb_overhead_ms=execution_data.get("overhead_ms"),
            provider_latency_ms=execution_data.get("provider_latency_ms"),
            provider_cost_usd=float(estimated_cost) if estimated_cost else None,
            request_hash=hash_request_payload(payload.parameters),
            response_hash=hash_response_payload(execution_data.get("result")),
            interface=f"{payload.interface}-v2",
            compat_mode=_COMPAT_MODE,
            idempotency_key=payload.idempotency_key or x_rhumb_idempotency_key,
            error_code=error_code if not is_success else None,
            error_message=error_message if not is_success else None,
        )
        receipt = await get_receipt_service().create_receipt(receipt_input)
        receipt_id = receipt.receipt_id
        logger.info(
            "v2_receipt_created receipt_id=%s execution_id=%s provider=%s status=%s",
            receipt_id, execution_id, provider_public_slug, receipt_input.status,
        )
    except Exception:
        # Receipt creation must never block execution delivery.
        # Log and continue — the execution result is still valid.
        logger.exception("v2_receipt_creation_failed execution_id=%s", execution_id)

    # ── Route explanation (WU-41.3) ─────────────────────────────────
    explanation_id: str | None = None
    try:
        # Gather scores for explanation via read-only score cache (WU-41.4)
        from services.score_cache import get_score_cache as _get_sc
        _slugs = [m.get("service_slug", "") for m in policy_eval.all_mappings if m.get("service_slug")]
        _scores_by_slug: dict[str, float] = _get_sc().scores_by_slug(_slugs) if _slugs else {}

        _circuit_states: dict[str, str] = {}
        from routes.proxy import get_breaker_registry as _get_br
        _br = _get_br()
        for m in policy_eval.all_mappings:
            slug = m.get("service_slug", "")
            if slug:
                agent_for_br = agent.agent_id if agent else "anonymous"
                breaker = _br.get(slug, agent_for_br)
                _circuit_states[slug] = breaker.state.value if hasattr(breaker.state, 'value') else str(breaker.state)

        explanation = build_explanation(
            capability_id=capability_id,
            mappings=policy_eval.all_mappings,
            scores_by_slug=_scores_by_slug,
            circuit_states=_circuit_states,
            selected_provider=selected_provider_public or selected_provider,
            policy_pin=effective_policy.pin if effective_policy else None,
            policy_deny=list(effective_policy.provider_deny) if effective_policy and effective_policy.provider_deny else None,
            policy_allow_only=list(effective_policy.allow_only) if effective_policy and effective_policy.allow_only else None,
            max_cost_usd=effective_policy.max_cost_usd if effective_policy else None,
            layer=2,
        )
        explanation_id = explanation.explanation_id
        store_explanation(explanation)
        await persist_explanation(explanation, receipt_id=receipt_id)
    except Exception:
        logger.exception("v2_route_explanation_failed execution_id=%s", execution_id)

    # ── Provider attribution (WU-41.2) ─────────────────────────────
    attribution_headers: dict[str, str] = {}
    try:
        attribution = await build_attribution(
            provider_slug=provider_public_slug,
            layer=2,
            receipt_id=receipt_id,
            cost_provider_usd=float(estimated_cost) if estimated_cost else None,
            credential_mode=effective_credential_mode,
        )
        attribution_headers = attribution.to_response_headers()
    except Exception:
        logger.exception("v2_attribution_failed execution_id=%s", execution_id)
        attribution = None

    # ── Annotate response ─────────────────────────────────────────────
    if is_success and execution_data:
        policy_summary = _public_policy_summary(
            provider_decision.policy_summary
            if provider_decision is not None
            else _policy_summary(effective_policy)
        )
        v2_meta: dict[str, Any] = {
            **_compat_meta(),
            "receipt_id": receipt_id or _compat_receipt_id(execution_id),
            "explanation_id": explanation_id,
            "selected_provider": selected_provider_public,
            "policy_applied": _effective_policy_active(effective_policy),
            "policy_selected_reason": provider_decision.selected_reason if provider_decision else None,
            "policy_candidates": policy_candidates_public if provider_decision else None,
            "policy_summary": policy_summary,
            "policy_source": policy_source,
            "budget_applied": bool(budget_status and budget_status.budget_usd is not None),
            "budget_summary": _budget_summary(budget_status),
            "estimated_cost_usd": estimated_cost,
            "translated_from": {
                "parameters": True,
                "policy_provider_preference": bool(payload.policy and payload.policy.provider_preference),
                "policy_pin": bool(payload.policy and payload.policy.pin),
                "policy_provider_deny": bool(payload.policy and payload.policy.provider_deny),
                "policy_allow_only": bool(payload.policy and payload.policy.allow_only),
                "idempotency_header_used": bool(x_rhumb_idempotency_key and not payload.idempotency_key),
            },
        }
        if receipt_id:
            execution_data["receipt_id"] = receipt_id
        execution_data["_rhumb_v2"] = v2_meta

        # Inject canonical _rhumb provider identity block
        if attribution is not None:
            execution_data["_rhumb"] = attribution.to_rhumb_block()

    # ── Billing event emission (WU-41.5) ──────────────────────────────
    try:
        from services.billing_events import BillingEventType, get_billing_event_stream
        _billing_org = agent.organization_id if agent else None
        if _billing_org and is_success:
            get_billing_event_stream().emit(
                BillingEventType.EXECUTION_CHARGED,
                org_id=_billing_org,
                amount_usd_cents=int(float(estimated_cost or 0) * 100),
                receipt_id=receipt_id,
                execution_id=execution_id,
                capability_id=capability_id,
                provider_slug=provider_public_slug,
                metadata={"layer": 2, "credential_mode": effective_credential_mode},
            )
        elif _billing_org and not is_success:
            get_billing_event_stream().emit(
                BillingEventType.EXECUTION_FAILED_NO_CHARGE,
                org_id=_billing_org,
                amount_usd_cents=0,
                execution_id=execution_id,
                capability_id=capability_id,
                provider_slug=provider_public_slug,
                metadata={"layer": 2, "error": str(body.get("error", ""))[:200]},
            )
    except Exception:
        logger.exception("v2_billing_event_emission_failed execution_id=%s", execution_id)

    merged_headers = _merge_response_headers(execute_response)
    merged_headers.update(attribution_headers)

    return JSONResponse(
        status_code=execute_response.status_code,
        content=body,
        headers=merged_headers,
    )
