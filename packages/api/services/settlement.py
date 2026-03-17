"""Daily USDC settlement pipeline.

Phase 1: semi-manual — batches receipts and creates records.
Pedro manually initiates Coinbase conversion.
Phase 2 will automate the Coinbase conversion via API.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from routes._supabase import (
    supabase_fetch,
    supabase_insert_returning,
    supabase_patch,
)
from services.payment_metrics import log_payment_event

logger = logging.getLogger(__name__)


async def create_daily_settlement_batch(batch_date: str | None = None) -> dict | None:
    """Create a settlement batch for a given date (default: yesterday).

    Collects all unsettled USDC receipts confirmed on that date,
    sums the total USDC, and creates a batch record.

    Returns the batch dict, or None if no receipts to settle.
    Idempotent: skips if a batch already exists for the date.
    """
    if batch_date is None:
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        batch_date = yesterday.strftime("%Y-%m-%d")

    # ── Idempotency check ────────────────────────────────────────────────
    existing = await supabase_fetch(
        f"settlement_batches?batch_date=eq.{batch_date}&select=id&limit=1"
    )
    if existing:
        logger.info("Settlement batch already exists for %s, skipping", batch_date)
        return None

    # ── Collect unsettled receipts for the date ──────────────────────────
    receipts = await supabase_fetch(
        f"usdc_receipts?settled=eq.false"
        f"&confirmed_at=gte.{batch_date}T00:00:00Z"
        f"&confirmed_at=lt.{batch_date}T23:59:59.999Z"
        f"&select=id,amount_usdc_atomic"
    )

    if not receipts:
        logger.info("No unsettled receipts for %s", batch_date)
        return None

    # ── Sum total USDC (atomic units stored as TEXT → int sum → back to TEXT)
    total_usdc = sum(int(r["amount_usdc_atomic"]) for r in receipts)
    receipt_ids = [r["id"] for r in receipts]

    # ── Create batch record ──────────────────────────────────────────────
    batch = await supabase_insert_returning(
        "settlement_batches",
        {
            "batch_date": batch_date,
            "total_usdc_atomic": str(total_usdc),
            "status": "pending",
        },
    )

    if batch is None:
        logger.error("Failed to create settlement batch for %s", batch_date)
        return None

    batch_id = batch["id"]

    # ── Link receipts to batch + mark as settled ─────────────────────────
    now_iso = datetime.now(timezone.utc).isoformat()

    for rid in receipt_ids:
        await supabase_patch(
            f"usdc_receipts?id=eq.{rid}",
            {
                "settled": True,
                "settled_at": now_iso,
                "settlement_batch_id": batch_id,
            },
        )

    logger.info(
        "Settlement batch %s created for %s: %s receipts, %s USDC atomic",
        batch_id,
        batch_date,
        len(receipt_ids),
        total_usdc,
    )
    log_payment_event(
        "settlement_batch_started",
        batch_count=len(receipt_ids),
    )

    return {
        "batch_id": batch_id,
        "batch_date": batch_date,
        "total_usdc_atomic": str(total_usdc),
        "receipt_count": len(receipt_ids),
    }


async def get_pending_batches() -> list[dict]:
    """Get all pending settlement batches (not yet converted to USD)."""
    return (
        await supabase_fetch(
            "settlement_batches?status=eq.pending&order=batch_date.desc&select=*"
        )
        or []
    )


async def mark_batch_converted(
    batch_id: str,
    total_usd_cents: int,
    coinbase_conversion_id: str | None = None,
) -> bool:
    """Mark a batch as converted (manual step in Phase 1).

    Updates the batch status to 'converted', records the USD total and
    optional Coinbase conversion ID.

    Returns True if the batch was found and updated, False otherwise.
    """
    payload: dict = {
        "status": "converted",
        "total_usd_cents": total_usd_cents,
    }
    if coinbase_conversion_id is not None:
        payload["coinbase_conversion_id"] = coinbase_conversion_id

    result = await supabase_patch(
        f"settlement_batches?id=eq.{batch_id}",
        payload,
    )

    if result is None or (isinstance(result, list) and len(result) == 0):
        logger.warning("Settlement batch %s not found for conversion", batch_id)
        return False

    logger.info(
        "Settlement batch %s marked converted: %d USD cents",
        batch_id,
        total_usd_cents,
    )
    log_payment_event(
        "settlement_converted",
        amount_usd_cents=total_usd_cents,
    )
    return True
