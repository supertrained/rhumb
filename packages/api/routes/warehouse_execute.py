"""BigQuery warehouse read-first capability execution for AUD-18."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from routes._supabase import supabase_insert
from schemas.warehouse_capabilities import (
    WarehouseQueryReadRequest,
    WarehouseSchemaDescribeRequest,
)
from services.bigquery_read_executor import (
    WarehouseExecutorError,
    describe_schema,
    execute_read_query,
)
from services.receipt_service import (
    ReceiptInput,
    get_receipt_service,
    hash_caller_ip,
    hash_request_payload,
    hash_response_payload,
)
from services.warehouse_connection_registry import WarehouseRefError, resolve_warehouse_bundle
from services.warehouse_receipt_summary import summarize_warehouse_execution

logger = logging.getLogger(__name__)

WAREHOUSE_CAPABILITY_IDS = frozenset({"warehouse.query.read", "warehouse.schema.describe"})


def is_warehouse_capability(capability_id: str) -> bool:
    return capability_id in WAREHOUSE_CAPABILITY_IDS


def _client_ip(raw_request: Request) -> str | None:
    forwarded_for = raw_request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    if raw_request.client:
        return raw_request.client.host
    return None


async def handle_warehouse_execute(
    *,
    capability_id: str,
    raw_request: Request,
    agent_id: str,
    org_id: str | None,
    execution_id: str,
    request_id: str,
) -> JSONResponse | dict:
    start = time.perf_counter()
    provider_used = "bigquery"
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
            code="warehouse_request_invalid",
            message="Invalid JSON body",
            status_code=400,
            started_at=start,
        )

    requested_mode = body.get("credential_mode", credential_mode)
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
            code="warehouse_credential_mode_invalid",
            message="Warehouse capabilities currently support credential_mode 'byok' only",
            status_code=400,
            started_at=start,
        )

    try:
        if capability_id == "warehouse.query.read":
            request = WarehouseQueryReadRequest.model_validate(body)
            bundle = resolve_warehouse_bundle(request.warehouse_ref)
            result = await execute_read_query(
                request,
                bundle=bundle,
                execution_id=execution_id,
            )
        elif capability_id == "warehouse.schema.describe":
            request = WarehouseSchemaDescribeRequest.model_validate(body)
            bundle = resolve_warehouse_bundle(request.warehouse_ref)
            result = await describe_schema(
                request,
                bundle=bundle,
                execution_id=execution_id,
            )
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
                code="warehouse_capability_unknown",
                message=f"Unknown warehouse capability: {capability_id}",
                status_code=400,
                started_at=start,
            )
    except WarehouseRefError as exc:
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
            code="warehouse_ref_invalid",
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
            code="warehouse_request_invalid",
            message=str(exc),
            status_code=400,
            started_at=start,
        )
    except WarehouseExecutorError as exc:
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
    response_dict = result.model_dump(mode="json", by_alias=True, exclude_none=True)
    summary = summarize_warehouse_execution(capability_id, response_dict)

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
    )

    return {"data": response_dict, "summary": summary, "error": None}


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
        logger.warning("warehouse_receipt_creation_failed execution_id=%s error=%s", execution_id, exc)
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
    receipt = await _emit_receipt(
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
    )
    return _error_response(
        request_id=request_id,
        execution_id=execution_id,
        capability_id=capability_id,
        warehouse_ref=(request_payload or {}).get("warehouse_ref"),
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
) -> None:
    try:
        await supabase_insert("capability_executions", {
            "id": execution_id,
            "agent_id": agent_id,
            "capability_id": capability_id,
            "provider_used": provider_used,
            "credential_mode": credential_mode,
            "method": "DIRECT",
            "path": f"/{capability_id}",
            "upstream_status": upstream_status,
            "success": success,
            "total_latency_ms": round(total_latency_ms, 1),
            "billing_status": "unbilled",
            "interface": "rest",
            "error_message": error_message,
        })
    except Exception as exc:
        logger.warning("warehouse_execution_record_failed execution_id=%s error=%s", execution_id, exc)


def _error_response(
    *,
    request_id: str,
    execution_id: str,
    capability_id: str,
    warehouse_ref: str | None = None,
    code: str,
    message: str,
    status_code: int,
) -> JSONResponse:
    content = {
        "error": code,
        "message": message,
        "capability_id": capability_id,
        "execution_id": execution_id,
        "request_id": request_id,
    }
    if warehouse_ref:
        content["warehouse_ref"] = warehouse_ref
    return JSONResponse(status_code=status_code, content=content)
