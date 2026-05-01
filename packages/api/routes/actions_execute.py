"""GitHub Actions workflow-run read-first capability execution for AUD-18."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from routes._supabase import supabase_insert
from schemas.actions_capabilities import WorkflowRunGetRequest, WorkflowRunListRequest
from services.actions_connection_registry import ActionsRefError, resolve_actions_bundle
from services.actions_receipt_summary import summarize_actions_execution
from services.github_actions_read_executor import (
    GitHubActionsExecutorError,
    get_workflow_run,
    list_workflow_runs,
)
from services.receipt_service import (
    ReceiptInput,
    get_receipt_service,
    hash_caller_ip,
    hash_request_payload,
    hash_response_payload,
)

logger = logging.getLogger(__name__)

ACTIONS_CAPABILITY_IDS = frozenset({"workflow_run.list", "workflow_run.get"})


def is_actions_capability(capability_id: str) -> bool:
    return capability_id in ACTIONS_CAPABILITY_IDS


def _client_ip(raw_request: Request) -> str | None:
    forwarded_for = raw_request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    if raw_request.client:
        return raw_request.client.host
    return None


def _normalized_actions_credential_mode(value: Any) -> str:
    return str(value or "").strip().lower()


async def handle_actions_execute(
    *,
    capability_id: str,
    raw_request: Request,
    agent_id: str,
    org_id: str | None,
    execution_id: str,
    request_id: str,
) -> JSONResponse | dict:
    start = time.perf_counter()
    provider_used = "github"
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
            code="actions_request_invalid",
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
            code="actions_request_invalid",
            message="JSON body must be an object",
            status_code=400,
            started_at=start,
        )

    requested_mode = _normalized_actions_credential_mode(body.get("credential_mode", credential_mode))
    if requested_mode != "byok":
        return await _failure_response(
            raw_request=raw_request,
            agent_id=agent_id,
            org_id=org_id,
            request_id=request_id,
            execution_id=execution_id,
            capability_id=capability_id,
            provider_used=provider_used,
            credential_mode=requested_mode,
            request_payload=body,
            code="actions_credential_mode_invalid",
            message="GitHub Actions capabilities currently support credential_mode 'byok' only",
            status_code=400,
            started_at=start,
        )
    credential_mode = requested_mode
    request_body = dict(body)
    request_body.pop("credential_mode", None)

    try:
        if capability_id == "workflow_run.list":
            request = WorkflowRunListRequest.model_validate(request_body)
            bundle = resolve_actions_bundle(request.actions_ref)
            result = await list_workflow_runs(request, bundle=bundle, execution_id=execution_id)
        elif capability_id == "workflow_run.get":
            request = WorkflowRunGetRequest.model_validate(request_body)
            bundle = resolve_actions_bundle(request.actions_ref)
            result = await get_workflow_run(request, bundle=bundle, execution_id=execution_id)
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
                code="actions_capability_unknown",
                message=f"Unknown GitHub Actions capability: {capability_id}",
                status_code=400,
                started_at=start,
            )
    except ActionsRefError as exc:
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
            code="actions_ref_invalid",
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
            code="actions_request_validation_error",
            message=str(exc),
            status_code=422,
            started_at=start,
        )
    except GitHubActionsExecutorError as exc:
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
    summary = summarize_actions_execution(capability_id, response_dict)

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
        actions_ref=response_dict.get("actions_ref"),
        run_id=response_dict.get("run_id"),
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
        logger.warning("actions_receipt_creation_failed execution_id=%s error=%s", execution_id, exc)
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
        actions_ref=(request_payload or {}).get("actions_ref"),
        run_id=(request_payload or {}).get("run_id"),
    )
    return _error_response(
        request_id=request_id,
        execution_id=execution_id,
        capability_id=capability_id,
        actions_ref=(request_payload or {}).get("actions_ref"),
        run_id=(request_payload or {}).get("run_id"),
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
    actions_ref: str | None = None,
    run_id: int | None = None,
) -> None:
    path = f"/{capability_id}"
    if actions_ref:
        path += f"/{actions_ref}"
    if run_id:
        path += f"/{run_id}"

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
        logger.warning("actions_execution_record_failed execution_id=%s error=%s", execution_id, exc)


def _error_response(
    *,
    request_id: str,
    execution_id: str,
    capability_id: str,
    actions_ref: str | None,
    run_id: int | None,
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
    if actions_ref:
        content["actions_ref"] = actions_ref
    if run_id:
        content["run_id"] = run_id
    return JSONResponse(status_code=status_code, content=content)
