"""Resolve v2 Receipt endpoints.

GET /v2/receipts/{receipt_id}                — Get a single execution receipt
GET /v2/receipts/{receipt_id}/explanation     — Get routing explanation for receipt
GET /v2/receipts                             — Query receipts with filters
GET /v2/receipts/chain/verify                — Verify chain integrity
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from services.error_envelope import RhumbError
from services.receipt_service import get_receipt_service
from services.route_explanation import (
    get_explanation,
    get_persisted_explanation,
    get_persisted_explanation_by_receipt,
)

router = APIRouter()


@router.get("/receipts/{receipt_id}")
async def get_receipt(receipt_id: str) -> dict[str, Any]:
    """Fetch a single execution receipt by ID."""
    service = get_receipt_service()
    receipt = await service.get_receipt(receipt_id)
    if receipt is None:
        raise RhumbError(
            "CAPABILITY_NOT_FOUND",
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
            "CAPABILITY_NOT_FOUND",
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
    limit: int = Query(default=50, ge=1, le=200, description="Max results"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
) -> dict[str, Any]:
    """Query execution receipts with optional filters."""
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
    limit: int = Query(default=100, ge=1, le=1000, description="Max receipts to check"),
) -> dict[str, Any]:
    """Verify the integrity of the receipt chain.

    Checks that each receipt's previous_receipt_hash matches the
    preceding receipt's receipt_hash. Returns verification results
    including any broken chain links detected.
    """
    service = get_receipt_service()
    result = await service.verify_chain(
        start_sequence=start_sequence,
        end_sequence=end_sequence,
        limit=limit,
    )
    return {"data": result, "error": None}
