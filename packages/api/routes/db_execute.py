"""DB-read capability execution — AUD-18 Wave 1.

Direct PostgreSQL read path for db.query.read, db.schema.describe,
and db.row.get capabilities.  Unlike the proxy-based execute surface,
these connect to the agent's own database (resolved via connection_ref
→ env-var DSN) and run read-only operations directly.

Hard constraints:
  - Read-only: the SQL classifier blocks all mutating statements.
  - Bounded: row limits, timeouts, and result size caps are enforced.
  - Receipted: every execution produces a chain-hashed receipt.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from routes._supabase import supabase_insert
from schemas.db_capabilities import (
    DbQueryReadRequest,
    DbRowGetRequest,
    DbSchemaDescribeRequest,
)
from services.db_connection_registry import (
    AgentVaultDsnError,
    ConnectionRefError,
    detect_postgres_provider,
    resolve_agent_vault_dsn,
    resolve_dsn,
    validate_connection_ref,
)
from services.db_receipt_summary import summarize_db_execution
from services.postgres_read_executor import (
    DbExecutorError,
    describe_schema,
    execute_read_query,
    get_rows,
)
from services.receipt_service import (
    ReceiptInput,
    get_receipt_service,
    hash_caller_ip,
    hash_request_payload,
    hash_response_payload,
)

logger = logging.getLogger(__name__)

DB_CAPABILITY_IDS = frozenset({"db.query.read", "db.schema.describe", "db.row.get"})


def is_db_capability(capability_id: str) -> bool:
    """Return True if capability_id is a DB-read capability."""
    return capability_id in DB_CAPABILITY_IDS


def _client_ip(raw_request: Request) -> str | None:
    forwarded_for = raw_request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    if raw_request.client:
        return raw_request.client.host
    return None


async def handle_db_execute(
    *,
    capability_id: str,
    raw_request: Request,
    agent_id: str,
    org_id: str | None,
    execution_id: str,
    request_id: str,
) -> JSONResponse | dict:
    """Execute a DB-read capability and return the response.

    Called from the main execute_capability route when the capability_id
    is one of the three DB-read capabilities.
    """
    start = time.perf_counter()
    provider_used = "postgresql"
    credential_mode = "byok"

    # Parse the request body
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
            credential_mode=credential_mode,
            provider_used=provider_used,
            code="db_request_invalid",
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
            credential_mode=credential_mode,
            provider_used=provider_used,
            code="db_request_invalid",
            message="JSON body must be an object",
            status_code=400,
            started_at=start,
        )

    raw_credential_mode = body.get("credential_mode", credential_mode)
    if isinstance(raw_credential_mode, str):
        credential_mode = raw_credential_mode.strip().lower()
    else:
        credential_mode = str(raw_credential_mode)
    if credential_mode not in {"byok", "agent_vault"}:
        return await _failure_response(
            raw_request=raw_request,
            agent_id=agent_id,
            org_id=org_id,
            request_id=request_id,
            execution_id=execution_id,
            capability_id=capability_id,
            credential_mode=credential_mode,
            provider_used=provider_used,
            request_payload=body,
            code="db_credential_mode_invalid",
            message="DB capabilities support credential_mode 'byok' or 'agent_vault' only",
            status_code=400,
            started_at=start,
        )

    dsn_override: str | None = None
    if credential_mode == "agent_vault":
        raw_agent_token = raw_request.headers.get("x-agent-token")
        agent_token = raw_agent_token.strip() if raw_agent_token else ""
        if not agent_token:
            return await _failure_response(
                raw_request=raw_request,
                agent_id=agent_id,
                org_id=org_id,
                request_id=request_id,
                execution_id=execution_id,
                capability_id=capability_id,
                credential_mode=credential_mode,
                provider_used=provider_used,
                request_payload=body,
                code="db_agent_token_required",
                message="X-Agent-Token header required for agent_vault credential mode",
                status_code=400,
                started_at=start,
            )
        try:
            dsn_override = resolve_agent_vault_dsn(
                agent_token,
                expected_connection_ref=body.get("connection_ref"),
                expected_agent_id=agent_id,
                expected_org_id=org_id,
            )
        except AgentVaultDsnError as exc:
            return await _failure_response(
                raw_request=raw_request,
                agent_id=agent_id,
                org_id=org_id,
                request_id=request_id,
                execution_id=execution_id,
                capability_id=capability_id,
                credential_mode=credential_mode,
                provider_used=provider_used,
                request_payload=body,
                code="db_agent_token_invalid",
                message=str(exc),
                status_code=400,
                started_at=start,
            )

    try:
        if capability_id == "db.query.read":
            request, dsn, provider_used = _prepare_query_read(body, credential_mode, dsn_override)
            result = await execute_read_query(
                request,
                credential_mode=credential_mode,
                provider_used=provider_used,
                dsn=dsn,
                execution_id=execution_id,
            )
        elif capability_id == "db.schema.describe":
            request, dsn, provider_used = _prepare_schema_describe(body, credential_mode, dsn_override)
            result = await describe_schema(
                request,
                credential_mode=credential_mode,
                provider_used=provider_used,
                dsn=dsn,
                execution_id=execution_id,
            )
        elif capability_id == "db.row.get":
            request, dsn, provider_used = _prepare_row_get(body, credential_mode, dsn_override)
            result = await get_rows(
                request,
                credential_mode=credential_mode,
                provider_used=provider_used,
                dsn=dsn,
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
                credential_mode=credential_mode,
                provider_used=provider_used,
                request_payload=body,
                code="db_capability_unknown",
                message=f"Unknown DB capability: {capability_id}",
                status_code=400,
                started_at=start,
            )
    except ConnectionRefError as exc:
        return await _failure_response(
            raw_request=raw_request,
            agent_id=agent_id,
            org_id=org_id,
            request_id=request_id,
            execution_id=execution_id,
            capability_id=capability_id,
            credential_mode=credential_mode,
            provider_used=provider_used,
            request_payload=body,
            code="db_connection_ref_invalid",
            message=str(exc),
            status_code=400,
            started_at=start,
        )
    except DbExecutorError as exc:
        return await _failure_response(
            raw_request=raw_request,
            agent_id=agent_id,
            org_id=org_id,
            request_id=request_id,
            execution_id=execution_id,
            capability_id=capability_id,
            credential_mode=credential_mode,
            provider_used=provider_used,
            request_payload=body,
            code=exc.code,
            message=exc.message,
            status_code=422,
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
            credential_mode=credential_mode,
            provider_used=provider_used,
            request_payload=body,
            code="db_request_validation_error",
            message=str(exc),
            status_code=422,
            started_at=start,
        )

    total_ms = round((time.perf_counter() - start) * 1000, 1)
    response_dict = result.model_dump(mode="json", by_alias=True)

    # Build human-readable summary
    summary = summarize_db_execution(capability_id, response_dict)

    # Emit receipt
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
        provider_latency_ms=response_dict.get("duration_ms"),
        request_payload=body,
        response_payload=response_dict,
    )

    response_dict["receipt_id"] = receipt.receipt_id if receipt else "unavailable"
    response_dict["execution_id"] = execution_id

    logger.info(
        "db_execute_success capability_id=%s execution_id=%s agent_id=%s summary=%s",
        capability_id,
        execution_id,
        agent_id,
        summary,
    )

    await _record_execution(
        execution_id=execution_id,
        agent_id=agent_id,
        capability_id=capability_id,
        credential_mode=credential_mode,
        provider_used=provider_used,
        upstream_status=200,
        success=True,
        total_latency_ms=total_ms,
        receipt_id=receipt.receipt_id if receipt else None,
    )

    return {
        "data": response_dict,
        "summary": summary,
        "error": None,
    }


# ── Internal helpers ──────────────────────────────────────────────


def _prepare_query_read(
    body: dict[str, Any],
    credential_mode: str,
    dsn_override: str | None,
) -> tuple[DbQueryReadRequest, str, str]:
    request = DbQueryReadRequest.model_validate(body)
    dsn, provider_used = _resolve_request_dsn(request.connection_ref, credential_mode, dsn_override)
    return request, dsn, provider_used


def _prepare_schema_describe(
    body: dict[str, Any],
    credential_mode: str,
    dsn_override: str | None,
) -> tuple[DbSchemaDescribeRequest, str, str]:
    request = DbSchemaDescribeRequest.model_validate(body)
    dsn, provider_used = _resolve_request_dsn(request.connection_ref, credential_mode, dsn_override)
    return request, dsn, provider_used


def _prepare_row_get(
    body: dict[str, Any],
    credential_mode: str,
    dsn_override: str | None,
) -> tuple[DbRowGetRequest, str, str]:
    request = DbRowGetRequest.model_validate(body)
    dsn, provider_used = _resolve_request_dsn(request.connection_ref, credential_mode, dsn_override)
    return request, dsn, provider_used


def _resolve_request_dsn(
    connection_ref: str,
    credential_mode: str,
    dsn_override: str | None,
) -> tuple[str, str]:
    if credential_mode == "agent_vault":
        # Keep connection_ref constraints consistent even though the DSN is
        # supplied by the agent.
        validate_connection_ref(connection_ref)
        assert dsn_override is not None
        dsn = dsn_override
    else:
        dsn = resolve_dsn(connection_ref)
    return dsn, detect_postgres_provider(dsn)


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
    provider_latency_ms: float | None = None,
    request_payload: dict | None = None,
    response_payload: dict | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
):
    """Emit a chain-hashed receipt for a DB execution. Best-effort."""
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
            provider_latency_ms=provider_latency_ms,
            rhumb_overhead_ms=(
                round(total_latency_ms - provider_latency_ms, 1)
                if provider_latency_ms is not None
                else None
            ),
            request_hash=hash_request_payload(request_payload),
            response_hash=hash_response_payload(response_payload),
            interface="rest",
            error_code=error_code,
            error_message=error_message,
        ))
    except Exception as exc:
        logger.warning(
            "db_receipt_creation_failed execution_id=%s error=%s",
            execution_id,
            exc,
        )
        return None


async def _failure_response(
    *,
    raw_request: Request,
    agent_id: str,
    org_id: str | None,
    request_id: str,
    execution_id: str,
    capability_id: str,
    credential_mode: str,
    provider_used: str,
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
        receipt_id=receipt.receipt_id if receipt else None,
        error_message=message,
    )
    return _error_response(
        request_id=request_id,
        execution_id=execution_id,
        capability_id=capability_id,
        connection_ref=(request_payload or {}).get("connection_ref"),
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
    receipt_id: str | None = None,
    error_message: str | None = None,
) -> None:
    """Best-effort recording of the execution to capability_executions."""
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
        logger.warning(
            "db_execution_record_failed execution_id=%s error=%s",
            execution_id,
            exc,
        )


def _error_response(
    *,
    request_id: str,
    execution_id: str,
    capability_id: str,
    connection_ref: str | None = None,
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
    if connection_ref:
        content["connection_ref"] = connection_ref
    return JSONResponse(status_code=status_code, content=content)
