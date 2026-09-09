"""Tests for billing health integration with the durable event outbox."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.durable_event_persistence import EventOutboxHealth
from services.payment_health import check_billing_health, get_payment_health


@pytest.mark.asyncio
async def test_check_billing_health_fails_when_event_outbox_unhealthy():
    with (
        patch(
            "services.payment_health._probe_billing_health",
            new_callable=AsyncMock,
            return_value=(True, "ok"),
        ),
        patch(
            "services.payment_health.get_event_outbox_health",
            return_value=EventOutboxHealth(
                available=True,
                writable=True,
                pending_count=1200,
                max_pending_count=1000,
                oldest_pending_age_seconds=30.0,
                reason="Durable event backlog exceeded safe threshold (1200>1000).",
            ),
        ),
    ):
        healthy, reason = await check_billing_health()

    assert healthy is False
    assert "threshold" in reason.lower()


@pytest.mark.asyncio
async def test_get_payment_health_degrades_when_outbox_exceeds_published_slo():
    with (
        patch(
            "services.payment_health._probe_billing_health",
            new_callable=AsyncMock,
            return_value=(True, "ok"),
        ),
        patch(
            "services.payment_health.get_event_outbox_health",
            return_value=EventOutboxHealth(
                available=True,
                writable=True,
                pending_count=202,
                max_pending_count=1000,
                oldest_pending_age_seconds=8_351_864.0,
                reason="",
            ),
        ),
        patch(
            "services.payment_health._probe_settlement_wallet_balance",
            new_callable=AsyncMock,
            return_value={
                "settlement_wallet_configured": True,
                "settlement_wallet_eth_low": False,
                "settlement_wallet_eth_critical": False,
            },
        ),
    ):
        health = await get_payment_health("http://localhost:54321", "test-key")

    assert health["status"] == "degraded"
    assert health["event_outbox_slo_ok"] is False
    assert health["event_outbox_pending_count"] == 202
    assert "pending_count 202 exceeds SLO 25" in health["event_outbox_reason"]
    assert "settlement_wallet_eth_balance" not in health


@pytest.mark.asyncio
async def test_get_payment_health_stays_operational_inside_outbox_slo():
    with (
        patch(
            "services.payment_health._probe_billing_health",
            new_callable=AsyncMock,
            return_value=(True, "ok"),
        ),
        patch(
            "services.payment_health.get_event_outbox_health",
            return_value=EventOutboxHealth(
                available=True,
                writable=True,
                pending_count=3,
                max_pending_count=1000,
                oldest_pending_age_seconds=120.0,
                reason="",
            ),
        ),
        patch(
            "services.payment_health._probe_settlement_wallet_balance",
            new_callable=AsyncMock,
            return_value={
                "settlement_wallet_configured": True,
                "settlement_wallet_eth_low": False,
                "settlement_wallet_eth_critical": False,
            },
        ),
    ):
        health = await get_payment_health("http://localhost:54321", "test-key")

    assert health["status"] == "operational"
    assert health["event_outbox_slo_ok"] is True
    assert "settlement_wallet_eth_balance" not in health
