"""Resolve v2 Receipt endpoints.

GET /v2/receipts/{receipt_id}                — Get a single execution receipt
GET /v2/receipts/{receipt_id}/explanation     — Get routing explanation for receipt
GET /v2/receipts                             — Query receipts with filters
GET /v2/receipts/chain/verify                — Verify chain integrity
POST /v2/receipts/{receipt_id}/verify         — Verify one receipt
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Query

from services.error_envelope import RhumbError
from services.receipt_service import get_receipt_service
from services.route_explanation import (
    get_explanation,
    get_persisted_explanation,
    get_persisted_explanation_by_receipt,
)

router = APIRouter()

_VALID_RECEIPT_STATUSES = frozenset({"success", "failure", "timeout", "rejected"})


def _compact_receipt_from_row(receipt: dict[str, Any]) -> dict[str, Any]:
    """Build PP-6 compact receipt facts from the full stored receipt row."""

    status = str(receipt.get("status") or "unknown")
    retryable = bool(receipt.get("retryable"))
    return {
        "mode": "compact",
        "status": status,
        "typed_error": receipt.get("error_code"),
        "stop_condition": receipt.get("stop_condition"),
        "retryable": retryable,
        "receipt_id": receipt.get("receipt_id"),
        "route_explanation_id": receipt.get("route_explanation_id")
        or receipt.get("explanation_id"),
        "route": {
            "capability_id": receipt.get("capability_id"),
            "service_id": receipt.get("service_id"),
            "provider_id": receipt.get("provider_id"),
            "route_id": receipt.get("route_id"),
            "substrate": receipt.get("substrate"),
            "provenance_origin": receipt.get("provenance_origin"),
            "source_risk": receipt.get("source_risk"),
            "manifest_digest": receipt.get("manifest_digest"),
            "evidence_packet_digest": receipt.get("evidence_packet_digest"),
        },
        "route_plan": {
            "route_plan_id_hash": receipt.get("route_plan_id_hash"),
        },
        "budget": {
            "provider_cost_usd": receipt.get("provider_cost_usd"),
            "total_cost_usd": receipt.get("total_cost_usd"),
            "credits_deducted": receipt.get("credits_deducted"),
        },
        "next_recommended_action": receipt.get("next_recommended_action")
        or (
            "fetch_or_verify_receipt" if status == "success" else "inspect_error_and_resolve_again"
        ),
    }


def _verify_single_receipt(receipt: dict[str, Any], explanation_available: bool) -> dict[str, Any]:
    """Return PP-6 single-receipt verifier output.

    This verifies what the stored row can prove locally: issuer/shape,
    chain-material presence, request/output hash presence, route-plan binding
    by token hash, redaction posture, receipt status, and explanation lookup.
    It intentionally does not claim provider-side truth beyond returned payload
    hashing or global chain inclusion outside this receipt row.
    """

    receipt_hash = receipt.get("receipt_hash")
    chain_sequence = receipt.get("chain_sequence")
    request_hash = receipt.get("request_hash")
    response_hash = receipt.get("response_hash")
    route_plan_hash = receipt.get("route_plan_id_hash")
    status = receipt.get("status")
    status_ok = status in _VALID_RECEIPT_STATUSES
    checks = {
        "issuer_format_valid": bool(str(receipt.get("receipt_id") or "").startswith("rcpt_")),
        "receipt_hash_present": bool(receipt_hash),
        "chain_material_present": bool(receipt_hash and chain_sequence is not None),
        "request_hash_present": bool(request_hash),
        "response_hash_present": bool(response_hash),
        "route_plan_hash_present": bool(route_plan_hash),
        "route_facts_present": bool(receipt.get("route_id") and receipt.get("manifest_digest")),
        "redaction_compact_mode": True,
        "status_known": status_ok,
        "explanation_available": explanation_available,
    }
    return {
        "receipt_id": receipt.get("receipt_id"),
        "verifier_status": "verified" if all(checks.values()) else "partial",
        "checks": checks,
        "issuer": {
            "format_valid": checks["issuer_format_valid"],
            "signature_result": "not_signed_in_compact_mode",
        },
        "chain": {
            "inclusion_status": (
                "material_present" if checks["chain_material_present"] else "missing_chain_material"
            ),
            "chain_sequence": chain_sequence,
            "receipt_hash": receipt_hash,
            "previous_receipt_hash": receipt.get("previous_receipt_hash"),
        },
        "hashes": {
            "input_hash_status": "present" if request_hash else "missing",
            "output_hash_status": "present" if response_hash else "missing",
            "request_hash": request_hash,
            "response_hash": response_hash,
        },
        "redaction": {
            "status": "compact_hashes_only",
            "raw_payload_returned": False,
        },
        "receipt_status": status,
        "explanation_available": explanation_available,
        "compact_receipt": _compact_receipt_from_row(receipt),
        "what_is_proven": [
            "receipt row exists and carries chain material",
            "stored input/output hashes are present when corresponding checks pass",
            "route facts and route-plan token hash are present when corresponding checks pass",
        ],
        "what_is_not_proven": [
            "provider-side content truth beyond returned payload hashing",
            "global chain continuity; use GET /v2/receipts/chain/verify for range checks",
            "raw payload recovery from compact receipt metadata",
        ],
    }


def _validated_receipt_id(receipt_id: str) -> str:
    normalized = str(receipt_id or "").strip()
    if normalized:
        return normalized

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'receipt_id' path parameter.",
        detail="Provide a non-empty receipt_id from an execution response.",
    )


def _validated_optional_filter(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    if normalized:
        return normalized

    raise RhumbError(
        "INVALID_PARAMETERS",
        message=f"Invalid '{field_name}' filter.",
        detail=f"Provide a non-empty '{field_name}' value or omit the filter.",
    )


def _validated_receipt_status(status: str | None) -> str | None:
    if status is None:
        return None

    normalized = status.strip().lower()
    if normalized in _VALID_RECEIPT_STATUSES:
        return normalized

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'status' filter.",
        detail="Use one of: success, failure, timeout, rejected.",
    )


def _parsed_int_filter(value: str | int | None, *, field_name: str) -> int:
    raw = "" if value is None else str(value).strip()
    if not raw:
        raise RhumbError(
            "INVALID_PARAMETERS",
            message=f"Invalid '{field_name}' filter.",
            detail="Provide an integer value or omit the filter.",
        )
    if raw.lower() in {"true", "false"}:
        raise RhumbError(
            "INVALID_PARAMETERS",
            message=f"Invalid '{field_name}' filter.",
            detail="Provide an integer value or omit the filter.",
        )

    try:
        parsed = int(raw)
    except ValueError as exc:
        raise RhumbError(
            "INVALID_PARAMETERS",
            message=f"Invalid '{field_name}' filter.",
            detail="Provide an integer value or omit the filter.",
        ) from exc

    return parsed


def _validated_int_range(
    value: str | int | None, *, field_name: str, minimum: int, maximum: int
) -> int:
    parsed = _parsed_int_filter(value, field_name=field_name)
    if minimum <= parsed <= maximum:
        return parsed

    raise RhumbError(
        "INVALID_PARAMETERS",
        message=f"Invalid '{field_name}' filter.",
        detail=f"Provide an integer between {minimum} and {maximum}.",
    )


def _validated_non_negative_int(value: str | int | None, *, field_name: str) -> int:
    parsed = _parsed_int_filter(value, field_name=field_name)
    if parsed >= 0:
        return parsed

    raise RhumbError(
        "INVALID_PARAMETERS",
        message=f"Invalid '{field_name}' filter.",
        detail="Provide an integer greater than or equal to 0.",
    )


def _validate_chain_range(start_sequence: int | None, end_sequence: int | None) -> None:
    if start_sequence is not None and start_sequence < 1:
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid 'start_sequence' filter.",
            detail="Use a positive chain sequence number.",
        )
    if end_sequence is not None and end_sequence < 1:
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid 'end_sequence' filter.",
            detail="Use a positive chain sequence number.",
        )
    if start_sequence is not None and end_sequence is not None and start_sequence > end_sequence:
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid receipt chain range.",
            detail="'start_sequence' must be less than or equal to 'end_sequence'.",
        )


def _validated_optional_positive_int(value: str | int | None, *, field_name: str) -> int | None:
    if value is None:
        return None

    parsed = _parsed_int_filter(value, field_name=field_name)
    if parsed >= 1:
        return parsed

    raise RhumbError(
        "INVALID_PARAMETERS",
        message=f"Invalid '{field_name}' filter.",
        detail="Use a positive chain sequence number.",
    )


@router.get("/receipts/{receipt_id}")
async def get_receipt(receipt_id: str) -> dict[str, Any]:
    """Fetch a single execution receipt by ID."""
    receipt_id = _validated_receipt_id(receipt_id)
    service = get_receipt_service()
    receipt = await service.get_receipt(receipt_id)
    if receipt is None:
        raise RhumbError(
            "RECEIPT_NOT_FOUND",
            message=f"No receipt found with id '{receipt_id}'",
            detail="Check the receipt_id from an execution response, or query receipts at GET /v2/receipts",
        )
    return {"data": receipt, "error": None}


@router.get("/receipts/{receipt_id}/explanation")
async def get_receipt_explanation(receipt_id: str) -> dict[str, Any]:
    """Get the routing explanation for a Layer 2 execution receipt.

    Layer 1 receipts do not have explanations — the agent chose the provider.
    """
    receipt_id = _validated_receipt_id(receipt_id)
    # Verify the receipt exists first
    service = get_receipt_service()
    receipt = await service.get_receipt(receipt_id)
    if receipt is None:
        raise RhumbError(
            "RECEIPT_NOT_FOUND",
            message=f"No receipt found with id '{receipt_id}'",
            detail="Check the receipt_id from an execution response.",
        )

    # Check if this is a Layer 1 receipt (no explanation for L1)
    if receipt.get("layer") == 1:
        return {
            "data": {
                "receipt_id": receipt_id,
                "layer": 1,
                "explanation": None,
                "message": "Layer 1 executions do not produce routing explanations. The agent explicitly chose the provider.",
            },
            "error": None,
        }

    # Preferred lookup order:
    #   1. in-memory cache by explanation_id (hot same-process path)
    #   2. persisted explanation by explanation_id (if receipt carries it later)
    #   3. persisted explanation by receipt_id (durable cross-process path)
    explanation = None
    exp_id_from_receipt = receipt.get("explanation_id")
    if exp_id_from_receipt:
        explanation = get_explanation(exp_id_from_receipt)
        if explanation is None:
            explanation = await get_persisted_explanation(str(exp_id_from_receipt))

    if explanation is None:
        explanation = await get_persisted_explanation_by_receipt(receipt_id)

    if explanation is None:
        return {
            "data": {
                "receipt_id": receipt_id,
                "layer": receipt.get("layer", 2),
                "explanation": None,
                "message": "No routing explanation is available for this receipt. The execution may predate the explanation engine.",
            },
            "error": None,
        }

    return {"data": explanation.to_dict(), "error": None}


@router.post("/receipts/{receipt_id}/verify")
async def verify_receipt(receipt_id: str) -> dict[str, Any]:
    """Verify one receipt and return compact/full-verifier status fields."""

    receipt_id = _validated_receipt_id(receipt_id)
    service = get_receipt_service()
    receipt = await service.get_receipt(receipt_id)
    if receipt is None:
        raise RhumbError(
            "RECEIPT_NOT_FOUND",
            message=f"No receipt found with id '{receipt_id}'",
            detail="Check the receipt_id from an execution response, or query receipts at GET /v2/receipts",
        )

    explanation_available = False
    exp_id_from_receipt = receipt.get("route_explanation_id") or receipt.get("explanation_id")
    if exp_id_from_receipt:
        explanation_available = get_explanation(str(exp_id_from_receipt)) is not None
        if not explanation_available:
            explanation_available = (
                await get_persisted_explanation(str(exp_id_from_receipt)) is not None
            )
    if not explanation_available:
        explanation_available = await get_persisted_explanation_by_receipt(receipt_id) is not None

    return {"data": _verify_single_receipt(receipt, explanation_available), "error": None}


@router.get("/receipts")
async def query_receipts(
    agent_id: Optional[str] = Query(default=None, description="Filter by agent ID"),
    org_id: Optional[str] = Query(default=None, description="Filter by organization ID"),
    capability_id: Optional[str] = Query(default=None, description="Filter by capability ID"),
    provider_id: Optional[str] = Query(default=None, description="Filter by provider ID"),
    status: Optional[str] = Query(
        default=None, description="Filter by status (success, failure, timeout, rejected)"
    ),
    limit: str = Query(default="50", description="Max results"),
    offset: str = Query(default="0", description="Pagination offset"),
) -> dict[str, Any]:
    """Query execution receipts with optional filters."""
    agent_id = _validated_optional_filter(agent_id, field_name="agent_id")
    org_id = _validated_optional_filter(org_id, field_name="org_id")
    capability_id = _validated_optional_filter(capability_id, field_name="capability_id")
    provider_id = _validated_optional_filter(provider_id, field_name="provider_id")
    status = _validated_receipt_status(status)
    limit_value = _validated_int_range(limit, field_name="limit", minimum=1, maximum=200)
    offset_value = _validated_non_negative_int(offset, field_name="offset")
    service = get_receipt_service()
    receipts = await service.query_receipts(
        agent_id=agent_id,
        org_id=org_id,
        capability_id=capability_id,
        provider_id=provider_id,
        status=status,
        limit=limit_value,
        offset=offset_value,
    )
    return {
        "data": {
            "receipts": receipts,
            "count": len(receipts),
            "limit": limit_value,
            "offset": offset_value,
        },
        "error": None,
    }


@router.get("/receipts/chain/verify")
async def verify_chain(
    start_sequence: Optional[str] = Query(
        default=None, description="Start chain sequence (inclusive)"
    ),
    end_sequence: Optional[str] = Query(default=None, description="End chain sequence (inclusive)"),
    limit: str = Query(default="100", description="Max receipts to check"),
) -> dict[str, Any]:
    """Verify the integrity of the receipt chain.

    Checks that each receipt's previous_receipt_hash matches the
    preceding receipt's receipt_hash. Returns verification results
    including any broken chain links detected.
    """
    start_sequence_value = _validated_optional_positive_int(
        start_sequence, field_name="start_sequence"
    )
    end_sequence_value = _validated_optional_positive_int(end_sequence, field_name="end_sequence")
    _validate_chain_range(start_sequence_value, end_sequence_value)
    limit_value = _validated_int_range(limit, field_name="limit", minimum=1, maximum=1000)
    service = get_receipt_service()
    result = await service.verify_chain(
        start_sequence=start_sequence_value,
        end_sequence=end_sequence_value,
        limit=limit_value,
    )
    return {"data": result, "error": None}
