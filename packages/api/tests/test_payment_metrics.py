"""Tests for payment_metrics and payment_health modules."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from services.payment_metrics import log_payment_event, payment_timer
from services import payment_health as payment_health_module
from services.payment_health import check_billing_health, get_payment_health


class TestLogPaymentEvent:
    """Unit tests for log_payment_event."""

    def test_success_event_emits_info(self):
        with patch("services.payment_metrics.logger") as mock_logger:
            log_payment_event(
                "credit_deducted",
                org_id="org_1",
                amount_usd_cents=500,
                execution_id="exec_1",
            )

            mock_logger.info.assert_called_once()
            args, kwargs = mock_logger.info.call_args
            assert args[0] == "payment.%s %s"
            assert args[1] == "credit_deducted"
            assert '"event": "credit_deducted"' in args[2]
            payment_data = kwargs["extra"]["payment"]
            assert payment_data["event"] == "credit_deducted"
            assert payment_data["org_id"] == "org_1"
            assert payment_data["amount_usd_cents"] == 500
            assert payment_data["success"] is True

    def test_failure_event_emits_warning(self):
        with patch("services.payment_metrics.logger") as mock_logger:
            log_payment_event(
                "credit_insufficient",
                org_id="org_2",
                success=False,
                error="insufficient_credits",
            )

            mock_logger.warning.assert_called_once()
            args, kwargs = mock_logger.warning.call_args
            assert args[0] == "payment.%s %s"
            assert args[1] == "credit_insufficient"
            assert '"event": "credit_insufficient"' in args[2]
            payment_data = kwargs["extra"]["payment"]
            assert payment_data["success"] is False
            assert payment_data["error"] == "insufficient_credits"

    def test_filters_none_values(self):
        with patch("services.payment_metrics.logger") as mock_logger:
            log_payment_event(
                "checkout_created",
                org_id="org_3",
                amount_usd_cents=None,
                execution_id=None,
            )

            mock_logger.info.assert_called_once()
            payment_data = mock_logger.info.call_args[1]["extra"]["payment"]
            assert "amount_usd_cents" not in payment_data
            assert "execution_id" not in payment_data
            assert payment_data["org_id"] == "org_3"
            assert payment_data["event"] == "checkout_created"

    def test_extra_kwargs_included(self):
        with patch("services.payment_metrics.logger") as mock_logger:
            log_payment_event(
                "settlement_batch_started",
                batch_count=5,
            )

            payment_data = mock_logger.info.call_args[1]["extra"]["payment"]
            assert payment_data["batch_count"] == 5

    def test_tx_hash_and_network_included(self):
        with patch("services.payment_metrics.logger") as mock_logger:
            log_payment_event(
                "x402_payment_verified",
                org_id="org_4",
                tx_hash="0xabc123",
                network="base-sepolia",
            )

            payment_data = mock_logger.info.call_args[1]["extra"]["payment"]
            assert payment_data["tx_hash"] == "0xabc123"
            assert payment_data["network"] == "base-sepolia"


class TestPaymentTimer:
    """Unit tests for payment_timer context manager."""

    def test_measures_duration(self):
        with patch("services.payment_metrics.logger") as mock_logger:
            with payment_timer("credit_deducted", org_id="org_t1"):
                pass  # fast operation

            mock_logger.info.assert_called_once()
            payment_data = mock_logger.info.call_args[1]["extra"]["payment"]
            assert "duration_ms" in payment_data
            assert isinstance(payment_data["duration_ms"], float)
            assert payment_data["duration_ms"] >= 0
            assert payment_data["success"] is True

    def test_logs_error_on_exception(self):
        with patch("services.payment_metrics.logger") as mock_logger:
            with pytest.raises(ValueError, match="boom"):
                with payment_timer("credit_deducted", org_id="org_t2"):
                    raise ValueError("boom")

            mock_logger.warning.assert_called_once()
            payment_data = mock_logger.warning.call_args[1]["extra"]["payment"]
            assert payment_data["success"] is False
            assert payment_data["error"] == "boom"
            assert "duration_ms" in payment_data


class TestPaymentHealth:
    """Unit tests for get_payment_health."""

    @pytest.mark.asyncio
    async def test_returns_correct_structure(self):
        """Health check returns expected keys regardless of env."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []

        with patch("services.payment_health.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            health = await get_payment_health("http://localhost:54321", "test-key")

        assert "stripe_configured" in health
        assert "usdc_configured" in health
        assert "billing_table_accessible" in health
        assert "billing_reason" in health
        assert "status" in health
        assert isinstance(health["stripe_configured"], bool)
        assert isinstance(health["usdc_configured"], bool)
        assert isinstance(health["billing_table_accessible"], bool)
        assert health["billing_table_accessible"] is True
        assert health["billing_reason"] == "ok"
        assert health["status"] == "operational"

    @pytest.mark.asyncio
    async def test_degraded_on_db_failure(self):
        """Health returns degraded when Supabase is unreachable."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500

        with patch("services.payment_health.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            health = await get_payment_health("http://localhost:54321", "test-key")

        assert health["billing_table_accessible"] is False
        assert health["billing_reason"] == "connection_error"
        assert health["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_degraded_on_exception(self):
        """Health returns degraded when httpx raises."""
        with patch("services.payment_health.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.side_effect = Exception("connection refused")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            health = await get_payment_health("http://localhost:54321", "test-key")

        assert health["billing_table_accessible"] is False
        assert health["billing_reason"] == "connection_error"
        assert health["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_check_billing_health_timeout(self):
        """Shared billing health probe maps timeouts to an explicit timeout reason."""
        with (
            patch.object(
                payment_health_module.settings,
                "supabase_url",
                "http://localhost:54321",
            ),
            patch.object(
                payment_health_module.settings,
                "supabase_service_role_key",
                "test-key",
            ),
            patch("services.payment_health.httpx.AsyncClient") as MockClient,
        ):
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ReadTimeout("timed out")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            healthy, reason = await check_billing_health()

        assert healthy is False
        assert reason == "timeout"

    @pytest.mark.asyncio
    async def test_check_billing_health_connection_error(self):
        """Shared billing health probe maps connection failures to connection_error."""
        with (
            patch.object(
                payment_health_module.settings,
                "supabase_url",
                "http://localhost:54321",
            ),
            patch.object(
                payment_health_module.settings,
                "supabase_service_role_key",
                "test-key",
            ),
            patch("services.payment_health.httpx.AsyncClient") as MockClient,
        ):
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("connection refused")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            healthy, reason = await check_billing_health()

        assert healthy is False
        assert reason == "connection_error"


def test_log_payment_event_includes_compact_payload_in_message(caplog):
    with caplog.at_level(logging.INFO, logger="rhumb.payments"):
        log_payment_event(
            "x402_payment_failed",
            org_id="org_123",
            capability_id="search.query",
            execution_id="exec_123",
            network="base",
            success=False,
            error="nonce already used",
        )

    assert caplog.records
    record = caplog.records[-1]
    message = record.getMessage()
    assert message.startswith("payment.x402_payment_failed ")
    assert '"capability_id": "search.query"' in message
    assert '"error": "nonce already used"' in message
    assert '"execution_id": "exec_123"' in message
    assert '"network": "base"' in message
