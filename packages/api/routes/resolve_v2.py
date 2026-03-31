"""Resolve v2 compatibility gateway.

Initial v2 surface for Layer 2 execution. This ships an honest, opt-in
compatibility namespace without breaking the existing `/v1/` contract.

Current scope:
- `/v2/health`
- `/v2/capabilities`
- `/v2/capabilities/{capability_id}/execute/estimate`
- `/v2/capabilities/{capability_id}/execute`

The execute path currently translates the new v2 request envelope into the
existing v1 capability execute contract, then returns the v1 execution payload
annotated with `_rhumb_v2` metadata. This is deliberately conservative: the
v2 path is real and testable today, while the deeper receipt/policy/routing
internals land in later R40 slices.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from routes import capabilities as v1_capabilities

router = APIRouter()

_COMPAT_VERSION = "2026-03-30"
_COMPAT_MODE = "v1-translate"
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


class V2CapabilityPolicy(BaseModel):
    """Subset of the v2 policy envelope supported by the compatibility slice."""

    model_config = ConfigDict(extra="forbid")

    provider_preference: list[str] = Field(
        default_factory=list,
        description="Ordered provider preference list. Initial compat slice honors only the first entry.",
    )
    max_cost_usd: float | None = Field(
        default=None,
        ge=0,
        description="Hard per-call ceiling enforced before execution using the existing estimate path.",
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
        description="Optional execution policy subset supported by the compat layer.",
    )
    credential_mode: str = Field(
        default="auto",
        description="Credential mode (auto, byo, rhumb_managed, agent_vault).",
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


def _compat_receipt_id(execution_id: str | None) -> str | None:
    if not execution_id:
        return None
    return f"rcpt_compat_{execution_id}"


def _preferred_provider(policy: V2CapabilityPolicy | None) -> str | None:
    if not policy or not policy.provider_preference:
        return None
    return policy.provider_preference[0]


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
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    body = await v1_capabilities.list_capabilities(
        domain=domain,
        search=search,
        limit=limit,
        offset=offset,
    )
    if isinstance(body, dict):
        meta = {
            "api_version": "v2-alpha",
            "compat_mode": _COMPAT_MODE,
            "layer": 2,
        }
        if isinstance(body.get("data"), dict):
            body["data"]["_rhumb_v2"] = meta
        else:
            body["_rhumb_v2"] = meta
    return body


@router.get("/capabilities/{capability_id}/execute/estimate")
async def estimate_capability_v2(
    capability_id: str,
    raw_request: Request,
    credential_mode: str = Query("auto"),
    provider: str | None = Query(default=None),
) -> JSONResponse:
    estimate_response = await _forward_internal(
        raw_request,
        method="GET",
        path=f"/v1/capabilities/{capability_id}/execute/estimate",
        params={
            "credential_mode": credential_mode,
            **({"provider": provider} if provider else {}),
        },
    )

    body = estimate_response.json()
    if estimate_response.status_code == 200 and isinstance(body.get("data"), dict):
        body["data"]["_rhumb_v2"] = {
            "api_version": "v2-alpha",
            "compat_mode": _COMPAT_MODE,
            "layer": 2,
        }

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
    preferred_provider = _preferred_provider(payload.policy)

    estimate_response = await _forward_internal(
        raw_request,
        method="GET",
        path=f"/v1/capabilities/{capability_id}/execute/estimate",
        params={
            "credential_mode": payload.credential_mode,
            **({"provider": preferred_provider} if preferred_provider else {}),
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
    selected_provider = estimate_data.get("provider")
    endpoint_pattern = estimate_data.get("endpoint_pattern")
    estimated_cost = estimate_data.get("cost_estimate_usd")
    method, path = _parse_endpoint_pattern(endpoint_pattern)

    if payload.policy and payload.policy.max_cost_usd is not None and estimated_cost is not None:
        if float(estimated_cost) > payload.policy.max_cost_usd:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": (
                        f"Estimated call cost ${float(estimated_cost):.4f} exceeds policy ceiling "
                        f"${payload.policy.max_cost_usd:.4f}."
                    ),
                    "resolution": "Raise max_cost_usd, choose a cheaper provider, or retry without a hard ceiling.",
                },
            )

    v1_payload: dict[str, Any] = {
        "provider": selected_provider,
        "credential_mode": payload.credential_mode,
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
    )
    body = execute_response.json()

    if execute_response.status_code == 200 and isinstance(body.get("data"), dict):
        execution_data = body["data"]
        execution_data["_rhumb_v2"] = {
            "api_version": "v2-alpha",
            "compat_mode": _COMPAT_MODE,
            "layer": 2,
            "receipt_id": _compat_receipt_id(execution_data.get("execution_id")),
            "selected_provider": selected_provider,
            "policy_applied": bool(payload.policy),
            "policy_mode": "provider_preference+max_cost_usd",
            "estimated_cost_usd": estimated_cost,
            "translated_from": {
                "parameters": True,
                "policy_provider_preference": bool(preferred_provider),
                "idempotency_header_used": bool(x_rhumb_idempotency_key and not payload.idempotency_key),
            },
        }

    return JSONResponse(
        status_code=execute_response.status_code,
        content=body,
        headers=_merge_response_headers(execute_response),
    )
