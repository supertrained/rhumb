"""Admin billing routes for metering, invoices, forecasting, and USDC settlement."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.billing_aggregation import BillingAggregator, get_billing_aggregator
from services.error_envelope import RhumbError
from services.settlement import (
    create_daily_settlement_batch,
    get_pending_batches,
    mark_batch_converted,
)
from services.stripe_integration import (
    StripeIntegrationManager,
    get_stripe_integration_manager,
)
from services.service_slugs import public_service_slug
from services.usage_metering import COST_PER_CALL_USD, UsageMeterEngine, get_usage_meter_engine

router = APIRouter(tags=["admin-billing"])


class GenerateInvoiceRequest(BaseModel):
    """Request payload for invoice generation."""

    organization_id: str = Field(...)
    month: str = Field(..., description="Month in YYYY-MM format")


_test_usage_meter: Optional[UsageMeterEngine] = None
_test_billing_aggregator: Optional[BillingAggregator] = None
_test_stripe_manager: Optional[StripeIntegrationManager] = None


def set_test_billing_stores(
    usage_meter: Optional[UsageMeterEngine] = None,
    billing_aggregator: Optional[BillingAggregator] = None,
    stripe_manager: Optional[StripeIntegrationManager] = None,
) -> None:
    """Inject test stores (call with ``None`` to reset)."""
    global _test_usage_meter, _test_billing_aggregator, _test_stripe_manager
    _test_usage_meter = usage_meter
    _test_billing_aggregator = billing_aggregator
    _test_stripe_manager = stripe_manager


def _get_usage_meter() -> UsageMeterEngine:
    return _test_usage_meter or get_usage_meter_engine()


def _get_billing_aggregator() -> BillingAggregator:
    return _test_billing_aggregator or get_billing_aggregator()


def _get_stripe_manager() -> StripeIntegrationManager:
    return _test_stripe_manager or get_stripe_integration_manager()


def _normalize_billing_month(month: str) -> str:
    """Validate and normalize public admin billing month filters."""
    normalized = str(month).strip()
    try:
        datetime.strptime(normalized, "%Y-%m")
    except ValueError as exc:
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid 'month' filter.",
            detail="Use YYYY-MM.",
        ) from exc
    return normalized


def _normalize_billing_organization_id(organization_id: str) -> str:
    """Validate and normalize public admin billing organization filters."""
    normalized = str(organization_id).strip()
    if not normalized:
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid 'organization_id' filter.",
            detail="Provide a non-empty organization_id value.",
        )
    return normalized


def _normalize_settlement_batch_date(batch_date: str | None) -> str | None:
    """Validate and normalize public admin settlement batch dates."""
    if batch_date is None:
        return None

    normalized = str(batch_date).strip()
    try:
        datetime.strptime(normalized, "%Y-%m-%d")
    except ValueError as exc:
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid 'batch_date' filter.",
            detail="Use YYYY-MM-DD.",
        ) from exc
    return normalized


def _public_billing_service(service: Any) -> str:
    cleaned = str(service or "").strip().lower()
    if not cleaned:
        return ""
    return public_service_slug(cleaned) or cleaned


def _canonicalize_billing_services(services: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(services, dict):
        return {}

    merged: dict[str, dict[str, Any]] = {}
    for raw_service, summary in services.items():
        service = _public_billing_service(raw_service)
        if not service:
            continue

        call_count = int(getattr(summary, "call_count", 0) or 0)
        cost_estimate = float(getattr(summary, "cost_estimate", 0) or 0)

        bucket = merged.setdefault(service, {"call_count": 0, "cost_estimate": 0.0})
        bucket["call_count"] += call_count
        bucket["cost_estimate"] += cost_estimate

    for bucket in merged.values():
        bucket["cost_estimate"] = round(float(bucket["cost_estimate"]), 6)

    return merged


def _canonicalize_invoice_line_items(line_items: Any) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}

    for line in line_items or []:
        raw_service = line.get("service") if isinstance(line, dict) else getattr(line, "service", None)
        service = _public_billing_service(raw_service)
        if not service:
            continue

        call_count = int((line.get("call_count") if isinstance(line, dict) else getattr(line, "call_count", 0)) or 0)
        total_cost = float((line.get("total_cost") if isinstance(line, dict) else getattr(line, "total_cost", 0)) or 0)
        unit_cost = float((line.get("unit_cost") if isinstance(line, dict) else getattr(line, "unit_cost", 0)) or 0)

        bucket = merged.setdefault(
            service,
            {"service": service, "call_count": 0, "unit_cost": unit_cost, "total_cost": 0.0},
        )
        bucket["call_count"] += call_count
        bucket["total_cost"] += total_cost

    rows = []
    for service in sorted(merged):
        bucket = merged[service]
        call_count = int(bucket["call_count"])
        total_cost = round(float(bucket["total_cost"]), 6)
        unit_cost = round(total_cost / call_count, 6) if call_count else float(bucket["unit_cost"])
        rows.append(
            {
                "service": service,
                "call_count": call_count,
                "unit_cost": unit_cost,
                "total_cost": total_cost,
            }
        )

    return rows


@router.get("/admin/billing/usage")
async def get_usage_report(
    organization_id: str = Query(...),
    month: str = Query(..., description="Month in YYYY-MM format"),
) -> Dict[str, Any]:
    """Return organization monthly usage report."""
    normalized_organization_id = _normalize_billing_organization_id(organization_id)
    normalized_month = _normalize_billing_month(month)
    usage_meter = _get_usage_meter()
    usage = await usage_meter.get_org_monthly_usage(normalized_organization_id, normalized_month)

    return {
        "organization_id": usage.organization_id,
        "month": usage.month,
        "total_calls": usage.total_calls,
        "cost_estimate": usage.cost_estimate,
        "by_service": _canonicalize_billing_services(usage.by_service),
        "by_agent": {
            agent_id: {
                "total_calls": summary.total_calls,
                "cost_estimate": summary.cost_estimate,
            }
            for agent_id, summary in usage.by_agent.items()
        },
    }


@router.get("/admin/billing/invoices")
async def list_invoices(organization_id: str = Query(...)) -> List[Dict[str, Any]]:
    """List invoices for one organization."""
    normalized_organization_id = _normalize_billing_organization_id(organization_id)
    aggregator = _get_billing_aggregator()
    invoices = aggregator.list_invoices(normalized_organization_id)

    return [
        {
            "invoice_id": invoice.invoice_id,
            "organization_id": invoice.organization_id,
            "month": invoice.month,
            "subtotal": invoice.subtotal,
            "tax": invoice.tax,
            "total": invoice.total,
            "status": invoice.status,
            "created_at": invoice.created_at.isoformat(),
            "due_at": invoice.due_at.isoformat(),
        }
        for invoice in invoices
    ]


@router.post("/admin/billing/invoices/generate")
async def generate_invoice(body: GenerateInvoiceRequest) -> Dict[str, Any]:
    """Generate a draft invoice for organization + month."""
    normalized_organization_id = _normalize_billing_organization_id(body.organization_id)
    normalized_month = _normalize_billing_month(body.month)
    aggregator = _get_billing_aggregator()
    invoice = await aggregator.generate_invoice(normalized_organization_id, normalized_month)

    return {
        "invoice_id": invoice.invoice_id,
        "organization_id": invoice.organization_id,
        "month": invoice.month,
        "subtotal": invoice.subtotal,
        "tax": invoice.tax,
        "total": invoice.total,
        "status": invoice.status,
        "line_items": _canonicalize_invoice_line_items(invoice.line_items),
    }


@router.post("/admin/billing/invoices/{invoice_id}/send")
async def send_invoice(invoice_id: str) -> Dict[str, Any]:
    """Send an invoice by creating a payment intent and marking it sent."""
    aggregator = _get_billing_aggregator()
    stripe_manager = _get_stripe_manager()

    invoice = aggregator.get_invoice(invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")

    payment_intent = stripe_manager.create_payment_intent(
        organization_id=invoice.organization_id,
        amount_cents=max(0, int(round(invoice.total * 100))),
        invoice_id=invoice.invoice_id,
    )
    aggregator.mark_invoice_status(invoice_id, "sent")

    return {
        "status": "sent",
        "invoice_id": invoice.invoice_id,
        "payment_intent": payment_intent,
    }


@router.get("/admin/billing/forecast")
async def forecast_spend(organization_id: str = Query(...)) -> Dict[str, Any]:
    """Forecast monthly spend from trailing 7-day daily average."""
    normalized_organization_id = _normalize_billing_organization_id(organization_id)
    usage_meter = _get_usage_meter()
    window_calls, daily_average_calls = await usage_meter.get_org_daily_average_calls(
        organization_id=normalized_organization_id,
        days=7,
    )

    projected_monthly_calls = daily_average_calls * 30
    projected_monthly_spend = projected_monthly_calls * COST_PER_CALL_USD

    return {
        "organization_id": normalized_organization_id,
        "window_days": 7,
        "window_calls": window_calls,
        "daily_average_calls": round(daily_average_calls, 4),
        "projected_monthly_calls": round(projected_monthly_calls, 4),
        "projected_monthly_spend": round(projected_monthly_spend, 6),
        "generated_at": datetime.now(tz=UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# USDC Settlement (Phase 1 — semi-manual)
# ---------------------------------------------------------------------------


@router.post("/admin/settlement/run")
async def run_settlement(
    batch_date: str | None = Query(default=None, description="Date in YYYY-MM-DD (default: yesterday)"),
) -> Dict[str, Any]:
    """Trigger daily settlement batch creation. Admin only."""
    normalized_batch_date = _normalize_settlement_batch_date(batch_date)
    result = await create_daily_settlement_batch(normalized_batch_date)
    if result is None:
        return {"status": "skipped", "reason": "no_receipts_or_already_exists"}
    return {"status": "created", **result}


@router.get("/admin/settlement/pending")
async def pending_settlements() -> Dict[str, Any]:
    """List pending settlement batches (not yet converted to USD)."""
    batches = await get_pending_batches()
    return {"batches": batches, "count": len(batches)}


class MarkConvertedRequest(BaseModel):
    """Request payload for marking a batch as converted."""

    total_usd_cents: int = Field(..., gt=0, description="Total USD received in cents")
    coinbase_conversion_id: str | None = Field(
        default=None, description="Coinbase conversion ID (optional in Phase 1)"
    )


@router.post("/admin/settlement/{batch_id}/converted")
async def mark_converted(
    batch_id: str,
    body: MarkConvertedRequest,
) -> Dict[str, Any]:
    """Mark a settlement batch as converted to USD (manual Phase 1 step)."""
    success = await mark_batch_converted(
        batch_id,
        body.total_usd_cents,
        body.coinbase_conversion_id,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Batch not found")
    return {"status": "converted", "batch_id": batch_id}
