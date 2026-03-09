"""Monthly billing aggregation and invoice generation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from services.usage_metering import COST_PER_CALL_USD, UsageMeterEngine, get_usage_meter_engine

TAX_RATE = 0.085


@dataclass
class BillingLineItem:
    """One invoice line item grouped by service."""

    service: str
    call_count: int
    unit_cost: float
    total_cost: float


@dataclass
class MonthlyInvoice:
    """Monthly invoice aggregate for one organization."""

    invoice_id: str
    organization_id: str
    month: str
    line_items: List[BillingLineItem]
    subtotal: float
    tax: float
    total: float
    status: str
    created_at: datetime
    due_at: datetime


class BillingAggregator:
    """Generate and manage monthly invoices from metered usage."""

    def __init__(self, usage_meter: Optional[UsageMeterEngine] = None) -> None:
        self._usage_meter = usage_meter
        self._invoices: Dict[str, MonthlyInvoice] = {}
        self._invoice_index: Dict[Tuple[str, str], str] = {}

    @property
    def usage_meter(self) -> UsageMeterEngine:
        """Get usage meter dependency."""
        if self._usage_meter is None:
            self._usage_meter = get_usage_meter_engine()
        return self._usage_meter

    async def generate_invoice(self, organization_id: str, month: str) -> MonthlyInvoice:
        """Generate or return a monthly draft invoice for an organization."""
        key = (organization_id, month)
        existing_id = self._invoice_index.get(key)
        if existing_id is not None:
            return self._invoices[existing_id]

        usage = await self.usage_meter.get_org_monthly_usage(organization_id, month)

        line_items = [
            BillingLineItem(
                service=service,
                call_count=service_usage.call_count,
                unit_cost=COST_PER_CALL_USD,
                total_cost=round(service_usage.call_count * COST_PER_CALL_USD, 6),
            )
            for service, service_usage in sorted(usage.by_service.items())
        ]

        subtotal = round(sum(line.total_cost for line in line_items), 6)
        tax = round(subtotal * TAX_RATE, 6)
        total = round(subtotal + tax, 6)
        now = datetime.now(tz=UTC)

        invoice = MonthlyInvoice(
            invoice_id=str(uuid.uuid4()),
            organization_id=organization_id,
            month=month,
            line_items=line_items,
            subtotal=subtotal,
            tax=tax,
            total=total,
            status="draft",
            created_at=now,
            due_at=now + timedelta(days=30),
        )

        self._invoices[invoice.invoice_id] = invoice
        self._invoice_index[key] = invoice.invoice_id
        return invoice

    def list_invoices(self, organization_id: str) -> List[MonthlyInvoice]:
        """List invoices for one organization, newest first."""
        invoices = [
            invoice
            for invoice in self._invoices.values()
            if invoice.organization_id == organization_id
        ]
        invoices.sort(key=lambda invoice: invoice.created_at, reverse=True)
        return invoices

    def get_invoice(self, invoice_id: str) -> Optional[MonthlyInvoice]:
        """Get invoice by ID."""
        return self._invoices.get(invoice_id)

    def mark_invoice_status(self, invoice_id: str, status: str) -> Optional[MonthlyInvoice]:
        """Update invoice status if present."""
        invoice = self._invoices.get(invoice_id)
        if invoice is None:
            return None
        invoice.status = status
        return invoice


_billing_aggregator: Optional[BillingAggregator] = None


def get_billing_aggregator(
    usage_meter: Optional[UsageMeterEngine] = None,
) -> BillingAggregator:
    """Return (or create) the global :class:`BillingAggregator`."""
    global _billing_aggregator
    if _billing_aggregator is None:
        _billing_aggregator = BillingAggregator(usage_meter)
    return _billing_aggregator


def reset_billing_aggregator() -> None:
    """Reset billing aggregator singleton (for tests)."""
    global _billing_aggregator
    _billing_aggregator = None
