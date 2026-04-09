"""Support read-first capability execution for AUD-18."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from routes._supabase import supabase_insert
from schemas.support_capabilities import (
    ConversationGetRequest,
    ConversationListPartsRequest,
    ConversationListRequest,
    TicketGetRequest,
    TicketListCommentsRequest,
    TicketSearchRequest,
)
from services.receipt_service import (
    ReceiptInput,
    get_receipt_service,
    hash_caller_ip,
    hash_request_payload,
    hash_response_payload,
)
from services.support_connection_registry import (
    SupportRefError,
    resolve_intercom_support_bundle,
    resolve_zendesk_support_bundle,
)
from services.intercom_read_executor import (
    IntercomExecutorError,
    get_conversation,
    list_conversation_parts,
    list_conversations,
)
from services.support_receipt_summary import summarize_support_execution
from services.zendesk_read_executor import (
    ZendeskExecutorError,
    get_ticket,
    list_comments,
    search_tickets,
)

logger = logging.getLogger(__name__)

SUPPORT_CAPABILITY_IDS = frozenset({
    "ticket.search",
    "ticket.get",
    "ticket.list_comments",
    "conversation.list",
    "conversation.get",
    "conversation.list_parts",
})


def is_support_capability(capability_id: str) -> bool:
    return capability_id in SUPPORT_CAPABILITY_IDS


def _provider_for_capability(capability_id: str) -> str:
    if capability_id.startswith("conversation."):
        return "intercom"
    return "zendesk"


def _client_ip(raw_request: Request) -> str | None:
    forwarded_for = raw_request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    if raw_request.client:
        return raw_request.client.host
    return None


async def handle_support_execute(
    *,
    capability_id: str,
    raw_request: Request,
    agent_id: str,
    org_id: str | None,
    execution_id: str,
    request_id: str,
) -> JSONResponse | dict:
    start = time.perf_counter()
    provider_used = _provider_for_capability(capability_id)
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
            code="support_request_invalid",
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
            code="support_credential_mode_invalid",
            message="Support capabilities currently support credential_mode 'byok' only",
            status_code=400,
            started_at=start,
        )

    try:
        if capability_id == "ticket.search":
            request = TicketSearchRequest.model_validate(body)
            bundle = resolve_zendesk_support_bundle(request.support_ref)
            result = await search_tickets(request, bundle=bundle, execution_id=execution_id)
        elif capability_id == "ticket.get":
            request = TicketGetRequest.model_validate(body)
            bundle = resolve_zendesk_support_bundle(request.support_ref)
            result = await get_ticket(request, bundle=bundle, execution_id=execution_id)
        elif capability_id == "ticket.list_comments":
            request = TicketListCommentsRequest.model_validate(body)
            bundle = resolve_zendesk_support_bundle(request.support_ref)
            result = await list_comments(request, bundle=bundle, execution_id=execution_id)
        elif capability_id == "conversation.list":
            request = ConversationListRequest.model_validate(body)
            bundle = resolve_intercom_support_bundle(request.support_ref)
            result = await list_conversations(request, bundle=bundle, execution_id=execution_id)
        elif capability_id == "conversation.get":
            request = ConversationGetRequest.model_validate(body)
            bundle = resolve_intercom_support_bundle(request.support_ref)
            result = await get_conversation(request, bundle=bundle, execution_id=execution_id)
        elif capability_id == "conversation.list_parts":
            request = ConversationListPartsRequest.model_validate(body)
            bundle = resolve_intercom_support_bundle(request.support_ref)
            result = await list_conversation_parts(request, bundle=bundle, execution_id=execution_id)
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
                code="support_capability_unknown",
                message=f"Unknown support capability: {capability_id}",
                status_code=400,
                started_at=start,
            )
    except SupportRefError as exc:
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
            code="support_ref_invalid",
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
            code="support_request_validation_error",
            message=str(exc),
            status_code=422,
            started_at=start,
        )
    except (ZendeskExecutorError, IntercomExecutorError) as exc:
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
    summary = summarize_support_execution(capability_id, response_dict)

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
        support_ref=response_dict.get("support_ref"),
        ticket_id=response_dict.get("ticket_id"),
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
        logger.warning("support_receipt_creation_failed execution_id=%s error=%s", execution_id, exc)
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
        support_ref=(request_payload or {}).get("support_ref"),
        ticket_id=(request_payload or {}).get("ticket_id"),
    )
    return _error_response(
        request_id=request_id,
        execution_id=execution_id,
        capability_id=capability_id,
        support_ref=(request_payload or {}).get("support_ref"),
        ticket_id=(request_payload or {}).get("ticket_id"),
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
    support_ref: str | None = None,
    ticket_id: int | str | None = None,
) -> None:
    path = f"/{capability_id}"
    if support_ref:
        path += f"/{support_ref}"
    if ticket_id is not None:
        path += f"/{ticket_id}"

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
        logger.warning("support_execution_record_failed execution_id=%s error=%s", execution_id, exc)


def _error_response(
    *,
    request_id: str,
    execution_id: str,
    capability_id: str,
    support_ref: str | None,
    ticket_id: int | str | None,
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
    if support_ref:
        content["support_ref"] = support_ref
    if ticket_id is not None:
        content["ticket_id"] = ticket_id
    return JSONResponse(status_code=status_code, content=content)
