"""Admin routes for durable chain-integrity operations."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from routes.admin_auth import require_admin_key
from services.audit_trail import AuditTrail, get_audit_trail
from services.billing_events import BillingEventStream, get_billing_event_stream
from services.chain_checkpoints import (
    checkpoint_audit_head,
    checkpoint_billing_head,
    checkpoint_execution_receipts_head,
    checkpoint_score_audit_head,
)
from services.durable_event_persistence import DurableEventOutbox, get_event_outbox
from services.error_envelope import RhumbError

router = APIRouter(prefix="/v1/admin/trust", tags=["admin-trust"])

VALID_CHECKPOINT_STREAMS = {
    "audit_events",
    "billing_events",
    "score_audit_chain",
    "execution_receipts",
}


def _validated_checkpoint_body(body: Any) -> dict[str, Any]:
    if body is None:
        return {}
    if isinstance(body, dict):
        return body

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid checkpoint payload",
        detail="Provide a JSON object payload or omit the body.",
    )


def _validated_checkpoint_reason(reason: Any) -> str:
    if reason is None:
        return "manual_head_snapshot"
    if not isinstance(reason, str):
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid checkpoint reason",
            detail="Provide a non-empty checkpoint reason string or omit the field.",
        )

    normalized = reason.strip()
    if normalized and len(normalized) <= 120:
        return normalized

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid checkpoint reason",
        detail="Provide a non-empty checkpoint reason up to 120 characters, or omit the field.",
    )


def _validated_checkpoint_metadata(metadata: Any) -> dict[str, Any]:
    if metadata is None:
        return {}
    if isinstance(metadata, dict):
        return metadata

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid checkpoint metadata",
        detail="Provide metadata as a JSON object or omit the field.",
    )


def _validated_checkpoint_flush(flush: Any) -> bool:
    if flush is None:
        return True
    if isinstance(flush, bool):
        return flush
    if isinstance(flush, str):
        normalized = flush.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid checkpoint flush flag",
        detail="Provide flush as a boolean value or omit the field.",
    )


_test_outbox: DurableEventOutbox | Any | None = None
_test_audit_trail: AuditTrail | None = None
_test_billing_stream: BillingEventStream | None = None
_test_score_audit_row: dict[str, Any] | None = None
_test_score_audit_verified_row: dict[str, Any] | None = None
_test_score_audit_count: int | None = None
_test_score_audit_verified_count: int | None = None
_test_execution_receipt_row: dict[str, Any] | None = None
_test_execution_receipt_count: int | None = None


def set_test_chain_integrity_stores(
    *,
    outbox: DurableEventOutbox | Any | None = None,
    audit_trail: AuditTrail | None = None,
    billing_stream: BillingEventStream | None = None,
    score_audit_row: dict[str, Any] | None = None,
    score_audit_verified_row: dict[str, Any] | None = None,
    score_audit_count: int | None = None,
    score_audit_verified_count: int | None = None,
    execution_receipt_row: dict[str, Any] | None = None,
    execution_receipt_count: int | None = None,
) -> None:
    """Inject test doubles for route-level chain-integrity tests."""
    global _test_outbox, _test_audit_trail, _test_billing_stream
    global _test_score_audit_row, _test_score_audit_verified_row
    global _test_score_audit_count, _test_score_audit_verified_count
    global _test_execution_receipt_row, _test_execution_receipt_count
    _test_outbox = outbox
    _test_audit_trail = audit_trail
    _test_billing_stream = billing_stream
    _test_score_audit_row = score_audit_row
    _test_score_audit_verified_row = score_audit_verified_row
    _test_score_audit_count = score_audit_count
    _test_score_audit_verified_count = score_audit_verified_count
    _test_execution_receipt_row = execution_receipt_row
    _test_execution_receipt_count = execution_receipt_count


@router.post("/chain-checkpoints/{stream_name}", dependencies=[Depends(require_admin_key)])
async def create_chain_checkpoint(
    stream_name: str,
    body: Any = Body(default=None),
) -> dict[str, Any]:
    """Persist a signed checkpoint for the current chain head."""
    checkpoint_body = _validated_checkpoint_body(body)
    normalized_stream = stream_name.strip().lower()
    if normalized_stream not in VALID_CHECKPOINT_STREAMS:
        valid_streams = ", ".join(sorted(VALID_CHECKPOINT_STREAMS))
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid checkpoint stream",
            detail=f"Use one of: {valid_streams}.",
        )

    reason = _validated_checkpoint_reason(checkpoint_body.get("reason"))
    metadata = _validated_checkpoint_metadata(checkpoint_body.get("metadata"))
    flush = _validated_checkpoint_flush(checkpoint_body.get("flush"))

    outbox = _test_outbox if _test_outbox is not None else get_event_outbox()
    if outbox is None:
        raise HTTPException(status_code=503, detail="Durable checkpoint outbox is unavailable.")

    try:
        if normalized_stream == "audit_events":
            payload = await checkpoint_audit_head(
                reason=reason,
                metadata=metadata,
                outbox=outbox,
                audit_trail=_test_audit_trail or get_audit_trail(),
                flush=flush,
            )
        elif normalized_stream == "billing_events":
            payload = await checkpoint_billing_head(
                reason=reason,
                metadata=metadata,
                outbox=outbox,
                billing_stream=_test_billing_stream or get_billing_event_stream(),
                flush=flush,
            )
        elif normalized_stream == "score_audit_chain":
            payload = await checkpoint_score_audit_head(
                reason=reason,
                metadata=metadata,
                outbox=outbox,
                latest_row=_test_score_audit_row,
                latest_verified_row=_test_score_audit_verified_row,
                row_count=_test_score_audit_count,
                verified_row_count=_test_score_audit_verified_count,
                flush=flush,
            )
        else:
            payload = await checkpoint_execution_receipts_head(
                reason=reason,
                metadata=metadata,
                outbox=outbox,
                latest_row=_test_execution_receipt_row,
                row_count=_test_execution_receipt_count,
                flush=flush,
            )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if payload is None:
        return {
            "status": "skipped",
            "stream_name": normalized_stream,
            "reason": reason,
            "detail": "Stream is empty; no checkpoint created.",
        }

    return {
        "status": "created",
        "stream_name": normalized_stream,
        "checkpoint": payload,
    }
