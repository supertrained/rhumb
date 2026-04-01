"""Tests for billing health integration with the durable event outbox."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.durable_event_persistence import EventOutboxHealth
from services.payment_health import check_billing_health


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
