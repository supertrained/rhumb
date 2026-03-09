"""Tests for schema alert pipeline (Round 13 Module 3)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.schema_alert_pipeline import AlertDispatcher  # noqa: E402
from services.schema_change_detector import SchemaChange  # noqa: E402


def _breaking_changes() -> tuple[SchemaChange, ...]:
    return (
        SchemaChange(
            change_type="remove",
            path="customer.email",
            severity="breaking",
            old_type="string",
            new_type=None,
        ),
    )


def _non_breaking_changes() -> tuple[SchemaChange, ...]:
    return (
        SchemaChange(
            change_type="add",
            path="customer.nickname",
            severity="non_breaking",
            old_type=None,
            new_type="string",
        ),
    )


class TestSchemaAlertPipeline:
    """Alert dispatcher behavior."""

    @pytest.mark.asyncio
    async def test_breaking_change_dispatches_webhook(self, httpx_mock) -> None:
        dispatcher = AlertDispatcher()
        httpx_mock.add_response(url="https://ops.example/webhook", status_code=200)

        result = await dispatcher.dispatch(
            service="stripe",
            endpoint="default:v1/customers",
            changes=_breaking_changes(),
            webhook_url="https://ops.example/webhook",
        )

        assert result["status"] == "sent"
        assert len(httpx_mock.get_requests()) == 1

    @pytest.mark.asyncio
    async def test_non_breaking_change_filtered_by_default(self, httpx_mock) -> None:
        dispatcher = AlertDispatcher()

        result = await dispatcher.dispatch(
            service="stripe",
            endpoint="default:v1/customers",
            changes=_non_breaking_changes(),
            webhook_url="https://ops.example/webhook",
        )

        assert result["status"] == "skipped"
        assert result["reason"] == "non_breaking_filtered"
        assert len(httpx_mock.get_requests()) == 0

    @pytest.mark.asyncio
    async def test_webhook_success_marked_sent(self, httpx_mock) -> None:
        dispatcher = AlertDispatcher()
        httpx_mock.add_response(url="https://ops.example/webhook", status_code=200)

        result = await dispatcher.dispatch(
            service="stripe",
            endpoint="default:v1/customers",
            changes=_breaking_changes(),
            webhook_url="https://ops.example/webhook",
        )

        alert = dispatcher.query_alerts(limit=1)[0]
        assert result["webhook"]["status_code"] == 200
        assert alert.alert_sent_at is not None

    @pytest.mark.asyncio
    async def test_webhook_failure_schedules_retry(self, httpx_mock) -> None:
        dispatcher = AlertDispatcher()
        httpx_mock.add_response(url="https://ops.example/webhook", status_code=500)

        result = await dispatcher.dispatch(
            service="stripe",
            endpoint="default:v1/customers",
            changes=_breaking_changes(),
            webhook_url="https://ops.example/webhook",
        )

        alert = dispatcher.query_alerts(limit=1)[0]
        assert result["status"] == "pending"
        assert alert.retry_count == 1
        assert alert.retry_at is not None

    @pytest.mark.asyncio
    async def test_alert_dedup_within_window(self, httpx_mock) -> None:
        dispatcher = AlertDispatcher()
        httpx_mock.add_response(url="https://ops.example/webhook", status_code=200)

        first = await dispatcher.dispatch(
            service="stripe",
            endpoint="default:v1/customers",
            changes=_breaking_changes(),
            webhook_url="https://ops.example/webhook",
        )
        second = await dispatcher.dispatch(
            service="stripe",
            endpoint="default:v1/customers",
            changes=_breaking_changes(),
            webhook_url="https://ops.example/webhook",
        )

        assert first["status"] == "sent"
        assert second["status"] == "deduped"
        assert len(httpx_mock.get_requests()) == 1

    @pytest.mark.asyncio
    async def test_payload_shape_includes_required_fields(self, httpx_mock) -> None:
        dispatcher = AlertDispatcher()
        httpx_mock.add_response(url="https://ops.example/webhook", status_code=200)

        result = await dispatcher.dispatch(
            service="stripe",
            endpoint="default:v1/payment-intents",
            changes=_breaking_changes(),
            webhook_url="https://ops.example/webhook",
            webhook_token="secret",
        )

        payload = result["payload"]
        assert payload["service"] == "stripe"
        assert payload["endpoint"] == "default:v1/payment-intents"
        assert payload["severity"] == "breaking"
        assert payload["changes"]

    @pytest.mark.asyncio
    async def test_email_dispatch_logged_with_recipient(self, httpx_mock) -> None:
        dispatcher = AlertDispatcher()
        httpx_mock.add_response(url="https://ops.example/webhook", status_code=200)

        result = await dispatcher.dispatch(
            service="stripe",
            endpoint="default:v1/customers",
            changes=_breaking_changes(),
            webhook_url="https://ops.example/webhook",
        )

        assert result["email"]["sent"] is True
        assert result["email"]["recipient"] == "operators@rhumb.dev"

    @pytest.mark.asyncio
    async def test_alert_query_filters_service_and_limit(self, httpx_mock) -> None:
        dispatcher = AlertDispatcher()
        httpx_mock.add_response(url="https://ops.example/webhook", status_code=200)
        httpx_mock.add_response(url="https://ops.example/webhook", status_code=200)

        await dispatcher.dispatch(
            service="stripe",
            endpoint="default:v1/customers",
            changes=_breaking_changes(),
            webhook_url="https://ops.example/webhook",
        )
        await dispatcher.dispatch(
            service="github",
            endpoint="default:repos",
            changes=_breaking_changes(),
            webhook_url="https://ops.example/webhook",
        )

        alerts = dispatcher.query_alerts(service="stripe", limit=10)
        assert len(alerts) == 1
        assert alerts[0].service == "stripe"
