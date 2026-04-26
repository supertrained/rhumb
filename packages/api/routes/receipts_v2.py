"""Resolve v2 Receipt endpoints.

GET /v2/receipts/{receipt_id}                — Get a single execution receipt
GET /v2/receipts/{receipt_id}/explanation     — Get routing explanation for receipt
GET /v2/receipts                             — Query receipts with filters
GET /v2/receipts/chain/verify                — Verify chain integrity
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


def _validated_int_range(value: int, *, field_name: str, minimum: int, maximum: int) -> int:
    if minimum <= value <= maximum:
        return value

    raise RhumbError(
        "INVALID_PARAMETERS",
        message=f"Invalid '{field_name}' filter.",
        detail=f"Provide an integer between {minimum} and {maximum}.",
    )


def _validated_non_negative_int(value: int, *, field_name: str) -> int:
    if value >= 0:
        return value

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


@router.get("/receipts/{receipt_id}")
async def get_receipt(receipt_id: str) -> dict[str, Any]:
    """Fetch a single execution receipt by ID."""
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


@router.get("/receipts")
async def query_receipts(
    agent_id: Optional[str] = Query(default=None, description="Filter by agent ID"),
    org_id: Optional[str] = Query(default=None, description="Filter by organization ID"),
    capability_id: Optional[str] = Query(default=None, description="Filter by capability ID"),
    provider_id: Optional[str] = Query(default=None, description="Filter by provider ID"),
    status: Optional[str] = Query(default=None, description="Filter by status (success, failure, timeout, rejected)"),
    limit: int = Query(default=50, description="Max results"),
    offset: int = Query(default=0, description="Pagination offset"),
) -> dict[str, Any]:
    """Query execution receipts with optional filters."""
    agent_id = _validated_optional_filter(agent_id, field_name="agent_id")
    org_id = _validated_optional_filter(org_id, field_name="org_id")
    capability_id = _validated_optional_filter(capability_id, field_name="capability_id")
    provider_id = _validated_optional_filter(provider_id, field_name="provider_id")
    status = _validated_receipt_status(status)
    limit = _validated_int_range(limit, field_name="limit", minimum=1, maximum=200)
    offset = _validated_non_negative_int(offset, field_name="offset")
    service = get_receipt_service()
    receipts = await service.query_receipts(
        agent_id=agent_id,
        org_id=org_id,
        capability_id=capability_id,
        provider_id=provider_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return {
        "data": {
            "receipts": receipts,
            "count": len(receipts),
            "limit": limit,
            "offset": offset,
        },
        "error": None,
    }


@router.get("/receipts/chain/verify")
async def verify_chain(
    start_sequence: Optional[int] = Query(default=None, description="Start chain sequence (inclusive)"),
    end_sequence: Optional[int] = Query(default=None, description="End chain sequence (inclusive)"),
    limit: int = Query(default=100, description="Max receipts to check"),
) -> dict[str, Any]:
    """Verify the integrity of the receipt chain.

    Checks that each receipt's previous_receipt_hash matches the
    preceding receipt's receipt_hash. Returns verification results
    including any broken chain links detected.
    """
    _validate_chain_range(start_sequence, end_sequence)
    limit = _validated_int_range(limit, field_name="limit", minimum=1, maximum=1000)
    service = get_receipt_service()
    result = await service.verify_chain(
        start_sequence=start_sequence,
        end_sequence=end_sequence,
        limit=limit,
    )
    return {"data": result, "error": None}
