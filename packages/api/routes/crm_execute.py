"""CRM read-first capability execution for AUD-18."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from routes._supabase import supabase_insert
from schemas.crm_capabilities import (
    CrmObjectDescribeRequest,
    CrmRecordGetRequest,
    CrmRecordSearchRequest,
)
from services.crm_connection_registry import (
    CrmBundle,
    CrmRefError,
    HubSpotCrmBundle,
    SalesforceCrmBundle,
    resolve_crm_bundle,
)
from services.crm_receipt_summary import summarize_crm_execution
from services.hubspot_crm_read_executor import (
    HubSpotCrmExecutorError,
    describe_object as describe_hubspot_object,
    get_record as get_hubspot_record,
    search_records as search_hubspot_records,
)
from services.salesforce_crm_read_executor import (
    SalesforceCrmExecutorError,
    describe_object as describe_salesforce_object,
    get_record as get_salesforce_record,
    search_records as search_salesforce_records,
)
from services.receipt_service import (
    ReceiptInput,
    get_receipt_service,
    hash_caller_ip,
    hash_request_payload,
    hash_response_payload,
)

logger = logging.getLogger(__name__)

CRM_CAPABILITY_IDS = frozenset({
    "crm.object.describe",
    "crm.record.search",
    "crm.record.get",
})


def is_crm_capability(capability_id: str) -> bool:
    return capability_id in CRM_CAPABILITY_IDS


def _client_ip(raw_request: Request) -> str | None:
    forwarded_for = raw_request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    if raw_request.client:
        return raw_request.client.host
    return None


def _normalized_crm_credential_mode(value: Any) -> str:
    return str(value or "").strip().lower()


async def handle_crm_execute(
    *,
    capability_id: str,
    raw_request: Request,
    agent_id: str,
    org_id: str | None,
    execution_id: str,
    request_id: str,
) -> JSONResponse | dict:
    start = time.perf_counter()
    provider_used = "unknown"
    credential_mode = "byok"

    try:
        body = await raw_request.json()
    except Exception:
        return await _failure_response(
            raw_request=raw_request,
            agent_id=agent_id,
            org_id=org_id,
            request_id=request_id,
            execution_id=execution_id,
            capability_id=capability_id,
            provider_used=provider_used,
            credential_mode=credential_mode,
            code="crm_request_invalid",
            message="Invalid JSON body",
            status_code=400,
            started_at=start,
        )
    if not isinstance(body, dict):
        return await _failure_response(
            raw_request=raw_request,
            agent_id=agent_id,
            org_id=org_id,
            request_id=request_id,
            execution_id=execution_id,
            capability_id=capability_id,
            provider_used=provider_used,
            credential_mode=credential_mode,
            code="crm_request_invalid",
            message="Request body must be a JSON object",
            status_code=400,
            started_at=start,
        )

    requested_mode = _normalized_crm_credential_mode(body.get("credential_mode", credential_mode))
    if requested_mode != "byok":
        return await _failure_response(
            raw_request=raw_request,
            agent_id=agent_id,
            org_id=org_id,
            request_id=request_id,
            execution_id=execution_id,
            capability_id=capability_id,
            provider_used=provider_used,
            credential_mode=str(requested_mode),
            request_payload=body,
            code="crm_credential_mode_invalid",
            message="CRM capabilities currently support credential_mode 'byok' only",
            status_code=400,
            started_at=start,
        )
    credential_mode = requested_mode
    request_body = dict(body)
    request_body.pop("credential_mode", None)

    try:
        if capability_id == "crm.object.describe":
            request = CrmObjectDescribeRequest.model_validate(request_body)
            bundle = resolve_crm_bundle(request.crm_ref)
            provider_used = bundle.provider
            result = await _execute_describe(request=request, bundle=bundle, execution_id=execution_id)
        elif capability_id == "crm.record.search":
            request = CrmRecordSearchRequest.model_validate(request_body)
            bundle = resolve_crm_bundle(request.crm_ref)
            provider_used = bundle.provider
            result = await _execute_search(request=request, bundle=bundle, execution_id=execution_id)
        elif capability_id == "crm.record.get":
            request = CrmRecordGetRequest.model_validate(request_body)
            bundle = resolve_crm_bundle(request.crm_ref)
            provider_used = bundle.provider
            result = await _execute_get(request=request, bundle=bundle, execution_id=execution_id)
        else:
            return await _failure_response(
                raw_request=raw_request,
                agent_id=agent_id,
                org_id=org_id,
                request_id=request_id,
                execution_id=execution_id,
                capability_id=capability_id,
                provider_used=provider_used,
                credential_mode=credential_mode,
                request_payload=body,
                code="crm_capability_unknown",
                message=f"Unknown CRM capability: {capability_id}",
                status_code=400,
                started_at=start,
            )
    except CrmRefError as exc:
        return await _failure_response(
            raw_request=raw_request,
            agent_id=agent_id,
            org_id=org_id,
            request_id=request_id,
            execution_id=execution_id,
            capability_id=capability_id,
            provider_used=provider_used,
            credential_mode=credential_mode,
            request_payload=body,
            code="crm_ref_invalid",
            message=str(exc),
            status_code=400,
            started_at=start,
        )
    except ValidationError as exc:
        return await _failure_response(
            raw_request=raw_request,
            agent_id=agent_id,
            org_id=org_id,
            request_id=request_id,
            execution_id=execution_id,
            capability_id=capability_id,
            provider_used=provider_used,
            credential_mode=credential_mode,
            request_payload=body,
            code="crm_request_invalid",
            message=str(exc),
            status_code=400,
            started_at=start,
        )
    except (HubSpotCrmExecutorError, SalesforceCrmExecutorError) as exc:
        return await _failure_response(
            raw_request=raw_request,
            agent_id=agent_id,
            org_id=org_id,
            request_id=request_id,
            execution_id=execution_id,
            capability_id=capability_id,
            provider_used=provider_used,
            credential_mode=credential_mode,
            request_payload=body,
            code=exc.code,
            message=exc.message,
            status_code=exc.status_code,
            started_at=start,
        )

    total_ms = round((time.perf_counter() - start) * 1000, 1)
    response_dict = result.model_dump(mode="json", by_alias=True)
    summary = summarize_crm_execution(capability_id, response_dict)

    receipt = await _emit_receipt(
        execution_id=execution_id,
        capability_id=capability_id,
        status="success",
        agent_id=agent_id,
        org_id=org_id,
        credential_mode=credential_mode,
        provider_used=provider_used,
        raw_request=raw_request,
        total_latency_ms=total_ms,
        request_payload=body,
        response_payload=response_dict,
    )

    response_dict["receipt_id"] = receipt.receipt_id if receipt else "unavailable"
    response_dict["execution_id"] = execution_id

    await _record_execution(
        execution_id=execution_id,
        agent_id=agent_id,
        capability_id=capability_id,
        credential_mode=credential_mode,
        provider_used=provider_used,
        upstream_status=200,
        success=True,
        total_latency_ms=total_ms,
        crm_ref=response_dict.get("crm_ref"),
        object_type=response_dict.get("object_type"),
        record_id=response_dict.get("record_id"),
    )

    return {"data": response_dict, "summary": summary, "error": None}


async def _execute_describe(
    *,
    request: CrmObjectDescribeRequest,
    bundle: CrmBundle,
    execution_id: str,
):
    if isinstance(bundle, HubSpotCrmBundle):
        return await describe_hubspot_object(request, bundle=bundle, execution_id=execution_id)
    if isinstance(bundle, SalesforceCrmBundle):
        return await describe_salesforce_object(request, bundle=bundle, execution_id=execution_id)
    raise RuntimeError(f"Unsupported CRM bundle provider '{bundle.provider}'")


async def _execute_search(
    *,
    request: CrmRecordSearchRequest,
    bundle: CrmBundle,
    execution_id: str,
):
    if isinstance(bundle, HubSpotCrmBundle):
        return await search_hubspot_records(request, bundle=bundle, execution_id=execution_id)
    if isinstance(bundle, SalesforceCrmBundle):
        return await search_salesforce_records(request, bundle=bundle, execution_id=execution_id)
    raise RuntimeError(f"Unsupported CRM bundle provider '{bundle.provider}'")


async def _execute_get(
    *,
    request: CrmRecordGetRequest,
    bundle: CrmBundle,
    execution_id: str,
):
    if isinstance(bundle, HubSpotCrmBundle):
        return await get_hubspot_record(request, bundle=bundle, execution_id=execution_id)
    if isinstance(bundle, SalesforceCrmBundle):
        return await get_salesforce_record(request, bundle=bundle, execution_id=execution_id)
    raise RuntimeError(f"Unsupported CRM bundle provider '{bundle.provider}'")


async def _emit_receipt(
    *,
    execution_id: str,
    capability_id: str,
    status: str,
    agent_id: str,
    org_id: str | None,
    credential_mode: str,
    provider_used: str,
    raw_request: Request,
    total_latency_ms: float,
    request_payload: dict | None = None,
    response_payload: dict | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
):
    try:
        return await get_receipt_service().create_receipt(ReceiptInput(
            execution_id=execution_id,
            capability_id=capability_id,
            status=status,
            agent_id=agent_id,
            provider_id=provider_used,
            credential_mode=credential_mode,
            layer=2,
            org_id=org_id,
            caller_ip_hash=hash_caller_ip(_client_ip(raw_request)),
            total_latency_ms=total_latency_ms,
            request_hash=hash_request_payload(request_payload),
            response_hash=hash_response_payload(response_payload),
            interface="rest",
            error_code=error_code,
            error_message=error_message,
        ))
    except Exception as exc:
        logger.warning("crm_receipt_creation_failed execution_id=%s error=%s", execution_id, exc)
        return None


async def _failure_response(
    *,
    raw_request: Request,
    agent_id: str,
    org_id: str | None,
    request_id: str,
    execution_id: str,
    capability_id: str,
    provider_used: str,
    credential_mode: str,
    code: str,
    message: str,
    status_code: int,
    started_at: float,
    request_payload: dict | None = None,
) -> JSONResponse:
    total_ms = round((time.perf_counter() - started_at) * 1000, 1)
    await _emit_receipt(
        execution_id=execution_id,
        capability_id=capability_id,
        status="failure",
        agent_id=agent_id,
        org_id=org_id,
        credential_mode=credential_mode,
        provider_used=provider_used,
        raw_request=raw_request,
        total_latency_ms=total_ms,
        request_payload=request_payload,
        error_code=code,
        error_message=message,
    )
    await _record_execution(
        execution_id=execution_id,
        agent_id=agent_id,
        capability_id=capability_id,
        credential_mode=credential_mode,
        provider_used=provider_used,
        upstream_status=status_code,
        success=False,
        total_latency_ms=total_ms,
        error_message=message,
        crm_ref=(request_payload or {}).get("crm_ref"),
        object_type=(request_payload or {}).get("object_type"),
        record_id=(request_payload or {}).get("record_id"),
    )
    return _error_response(
        request_id=request_id,
        execution_id=execution_id,
        capability_id=capability_id,
        crm_ref=(request_payload or {}).get("crm_ref"),
        object_type=(request_payload or {}).get("object_type"),
        record_id=(request_payload or {}).get("record_id"),
        code=code,
        message=message,
        status_code=status_code,
    )


async def _record_execution(
    *,
    execution_id: str,
    agent_id: str,
    capability_id: str,
    credential_mode: str,
    provider_used: str,
    upstream_status: int,
    success: bool,
    total_latency_ms: float,
    error_message: str | None = None,
    crm_ref: str | None = None,
    object_type: str | None = None,
    record_id: str | None = None,
) -> None:
    path = f"/{capability_id}"
    if crm_ref:
        path += f"/{crm_ref}"
    if object_type:
        path += f"/{object_type}"
    if record_id:
        path += f"/{record_id}"

    try:
        await supabase_insert("capability_executions", {
            "id": execution_id,
            "agent_id": agent_id,
            "capability_id": capability_id,
            "provider_used": provider_used,
            "credential_mode": credential_mode,
            "method": "DIRECT",
            "path": path,
            "upstream_status": upstream_status,
            "success": success,
            "total_latency_ms": round(total_latency_ms, 1),
            "billing_status": "unbilled",
            "interface": "rest",
            "error_message": error_message,
        })
    except Exception as exc:
        logger.warning("crm_execution_record_failed execution_id=%s error=%s", execution_id, exc)


def _error_response(
    *,
    request_id: str,
    execution_id: str,
    capability_id: str,
    crm_ref: str | None,
    object_type: str | None,
    record_id: str | None,
    code: str,
    message: str,
    status_code: int,
) -> JSONResponse:
    content: dict[str, Any] = {
        "error": code,
        "message": message,
        "capability_id": capability_id,
        "execution_id": execution_id,
        "request_id": request_id,
    }
    if crm_ref:
        content["crm_ref"] = crm_ref
    if object_type:
        content["object_type"] = object_type
    if record_id:
        content["record_id"] = record_id
    return JSONResponse(status_code=status_code, content=content)
