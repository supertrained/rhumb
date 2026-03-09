"""Admin billing routes for metering, invoices, and forecasting."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.billing_aggregation import BillingAggregator, get_billing_aggregator
from services.stripe_integration import (
    StripeIntegrationManager,
    get_stripe_integration_manager,
)
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


@router.get("/admin/billing/usage")
async def get_usage_report(
    organization_id: str = Query(...),
    month: str = Query(..., description="Month in YYYY-MM format"),
) -> Dict[str, Any]:
    """Return organization monthly usage report."""
    usage_meter = _get_usage_meter()
    usage = await usage_meter.get_org_monthly_usage(organization_id, month)

    return {
        "organization_id": usage.organization_id,
        "month": usage.month,
        "total_calls": usage.total_calls,
        "cost_estimate": usage.cost_estimate,
        "by_service": {
            service: {
                "call_count": summary.call_count,
                "cost_estimate": summary.cost_estimate,
            }
            for service, summary in usage.by_service.items()
        },
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
    aggregator = _get_billing_aggregator()
    invoices = aggregator.list_invoices(organization_id)

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
    aggregator = _get_billing_aggregator()
    invoice = await aggregator.generate_invoice(body.organization_id, body.month)

    return {
        "invoice_id": invoice.invoice_id,
        "organization_id": invoice.organization_id,
        "month": invoice.month,
        "subtotal": invoice.subtotal,
        "tax": invoice.tax,
        "total": invoice.total,
        "status": invoice.status,
        "line_items": [
            {
                "service": line.service,
                "call_count": line.call_count,
                "unit_cost": line.unit_cost,
                "total_cost": line.total_cost,
            }
            for line in invoice.line_items
        ],
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
    usage_meter = _get_usage_meter()
    window_calls, daily_average_calls = await usage_meter.get_org_daily_average_calls(
        organization_id=organization_id,
        days=7,
    )

    projected_monthly_calls = daily_average_calls * 30
    projected_monthly_spend = projected_monthly_calls * COST_PER_CALL_USD

    return {
        "organization_id": organization_id,
        "window_days": 7,
        "window_calls": window_calls,
        "daily_average_calls": round(daily_average_calls, 4),
        "projected_monthly_calls": round(projected_monthly_calls, 4),
        "projected_monthly_spend": round(projected_monthly_spend, 6),
        "generated_at": datetime.now(tz=UTC).isoformat(),
    }
