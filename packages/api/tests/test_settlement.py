"""Tests for USDC settlement pipeline (WU-1.6).

Covers:
- services/settlement.py — batch creation, idempotency, pending query, conversion marking
- routes/admin_billing.py — settlement admin endpoints

All Supabase calls are mocked — no real DB required.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app import create_app


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ADMIN_SECRET = "rhumb_test_admin_secret_0000"
BATCH_DATE = "2026-03-16"
BATCH_ID = str(uuid.uuid4())


def _admin_headers() -> dict[str, str]:
    return {"X-Rhumb-Admin-Key": ADMIN_SECRET}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


# ---------------------------------------------------------------------------
# Mock data builders
# ---------------------------------------------------------------------------


def _receipt(rid: str | None = None, amount: str = "150000") -> dict:
    return {
        "id": rid or str(uuid.uuid4()),
        "amount_usdc_atomic": amount,
    }


def _batch_row(
    batch_id: str = BATCH_ID,
    batch_date: str = BATCH_DATE,
    total_usdc: str = "300000",
    status: str = "pending",
) -> dict:
    return {
        "id": batch_id,
        "batch_date": batch_date,
        "total_usdc_atomic": total_usdc,
        "total_usd_cents": None,
        "status": status,
        "coinbase_conversion_id": None,
        "created_at": "2026-03-17T02:00:00Z",
    }


# ---------------------------------------------------------------------------
# Service unit tests: create_daily_settlement_batch
# ---------------------------------------------------------------------------


class TestCreateDailySettlementBatch:
    """Tests for services.settlement.create_daily_settlement_batch."""

    @pytest.mark.anyio
    async def test_returns_none_when_no_receipts(self) -> None:
        """No unsettled receipts → returns None."""
        from services.settlement import create_daily_settlement_batch

        async def _mock_fetch(path: str):
            if "settlement_batches" in path:
                return []  # no existing batch
            if "usdc_receipts" in path:
                return []  # no receipts
            return []

        with patch("services.settlement.supabase_fetch", side_effect=_mock_fetch):
            result = await create_daily_settlement_batch(BATCH_DATE)

        assert result is None

    @pytest.mark.anyio
    async def test_creates_batch_with_correct_total(self) -> None:
        """Two receipts (150000 + 250000) → batch with total 400000."""
        from services.settlement import create_daily_settlement_batch

        r1 = _receipt(amount="150000")
        r2 = _receipt(amount="250000")

        async def _mock_fetch(path: str):
            if "settlement_batches" in path:
                return []  # no existing batch
            if "usdc_receipts" in path:
                return [r1, r2]
            return []

        created_batch = _batch_row(total_usdc="400000")

        with (
            patch("services.settlement.supabase_fetch", side_effect=_mock_fetch),
            patch(
                "services.settlement.supabase_insert_returning",
                new_callable=AsyncMock,
                return_value=created_batch,
            ) as mock_insert,
            patch(
                "services.settlement.supabase_patch",
                new_callable=AsyncMock,
                return_value=[{}],
            ) as mock_patch,
        ):
            result = await create_daily_settlement_batch(BATCH_DATE)

        assert result is not None
        assert result["total_usdc_atomic"] == "400000"
        assert result["receipt_count"] == 2
        assert result["batch_date"] == BATCH_DATE
        assert result["batch_id"] == BATCH_ID

        # Verify insert was called with correct payload
        insert_args = mock_insert.call_args
        assert insert_args[0][0] == "settlement_batches"
        assert insert_args[0][1]["total_usdc_atomic"] == "400000"
        assert insert_args[0][1]["status"] == "pending"

        # Verify both receipts were patched
        assert mock_patch.call_count == 2

    @pytest.mark.anyio
    async def test_idempotent_returns_none_when_batch_exists(self) -> None:
        """Second call for same date → returns None."""
        from services.settlement import create_daily_settlement_batch

        async def _mock_fetch(path: str):
            if "settlement_batches" in path:
                return [{"id": BATCH_ID}]  # batch already exists
            return []

        with patch("services.settlement.supabase_fetch", side_effect=_mock_fetch):
            result = await create_daily_settlement_batch(BATCH_DATE)

        assert result is None

    @pytest.mark.anyio
    async def test_receipt_linking_sets_settled_and_batch_id(self) -> None:
        """Receipts get settled=true, settled_at, and settlement_batch_id."""
        from services.settlement import create_daily_settlement_batch

        r1_id = str(uuid.uuid4())
        r1 = _receipt(rid=r1_id, amount="100000")

        async def _mock_fetch(path: str):
            if "settlement_batches" in path:
                return []
            if "usdc_receipts" in path:
                return [r1]
            return []

        created_batch = _batch_row()

        captured_patches: list[tuple[str, dict]] = []

        async def _capture_patch(path: str, payload: dict):
            captured_patches.append((path, payload))
            return [{}]

        with (
            patch("services.settlement.supabase_fetch", side_effect=_mock_fetch),
            patch(
                "services.settlement.supabase_insert_returning",
                new_callable=AsyncMock,
                return_value=created_batch,
            ),
            patch("services.settlement.supabase_patch", side_effect=_capture_patch),
        ):
            await create_daily_settlement_batch(BATCH_DATE)

        assert len(captured_patches) == 1
        path, payload = captured_patches[0]
        assert f"id=eq.{r1_id}" in path
        assert payload["settled"] is True
        assert "settled_at" in payload
        assert payload["settlement_batch_id"] == BATCH_ID

    @pytest.mark.anyio
    async def test_defaults_to_yesterday(self) -> None:
        """When batch_date is None, uses yesterday (UTC)."""
        from datetime import datetime, timedelta, timezone

        from services.settlement import create_daily_settlement_batch

        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        captured_paths: list[str] = []

        async def _mock_fetch(path: str):
            captured_paths.append(path)
            if "settlement_batches" in path:
                return []
            if "usdc_receipts" in path:
                return []  # no receipts — that's fine for this test
            return []

        with patch("services.settlement.supabase_fetch", side_effect=_mock_fetch):
            await create_daily_settlement_batch(None)

        # The batch check should use yesterday's date
        assert any(yesterday in p for p in captured_paths)

    @pytest.mark.anyio
    async def test_returns_none_when_insert_fails(self) -> None:
        """If supabase_insert_returning fails (returns None), returns None."""
        from services.settlement import create_daily_settlement_batch

        async def _mock_fetch(path: str):
            if "settlement_batches" in path:
                return []
            if "usdc_receipts" in path:
                return [_receipt()]
            return []

        with (
            patch("services.settlement.supabase_fetch", side_effect=_mock_fetch),
            patch(
                "services.settlement.supabase_insert_returning",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await create_daily_settlement_batch(BATCH_DATE)

        assert result is None


# ---------------------------------------------------------------------------
# Service unit tests: get_pending_batches
# ---------------------------------------------------------------------------


class TestGetPendingBatches:
    """Tests for services.settlement.get_pending_batches."""

    @pytest.mark.anyio
    async def test_returns_pending_batches(self) -> None:
        from services.settlement import get_pending_batches

        batches = [_batch_row(status="pending"), _batch_row(batch_id=str(uuid.uuid4()), status="pending")]

        with patch(
            "services.settlement.supabase_fetch",
            new_callable=AsyncMock,
            return_value=batches,
        ):
            result = await get_pending_batches()

        assert len(result) == 2

    @pytest.mark.anyio
    async def test_returns_empty_list_when_none(self) -> None:
        from services.settlement import get_pending_batches

        with patch(
            "services.settlement.supabase_fetch",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await get_pending_batches()

        assert result == []


# ---------------------------------------------------------------------------
# Service unit tests: mark_batch_converted
# ---------------------------------------------------------------------------


class TestMarkBatchConverted:
    """Tests for services.settlement.mark_batch_converted."""

    @pytest.mark.anyio
    async def test_updates_status_and_usd(self) -> None:
        from services.settlement import mark_batch_converted

        updated = [_batch_row(status="converted")]

        captured_patches: list[tuple[str, dict]] = []

        async def _capture_patch(path: str, payload: dict):
            captured_patches.append((path, payload))
            return updated

        with patch("services.settlement.supabase_patch", side_effect=_capture_patch):
            result = await mark_batch_converted(BATCH_ID, 29850, "cb_conv_123")

        assert result is True
        path, payload = captured_patches[0]
        assert f"id=eq.{BATCH_ID}" in path
        assert payload["status"] == "converted"
        assert payload["total_usd_cents"] == 29850
        assert payload["coinbase_conversion_id"] == "cb_conv_123"

    @pytest.mark.anyio
    async def test_returns_false_when_not_found(self) -> None:
        from services.settlement import mark_batch_converted

        with patch(
            "services.settlement.supabase_patch",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await mark_batch_converted(BATCH_ID, 100)

        assert result is False

    @pytest.mark.anyio
    async def test_returns_false_on_error(self) -> None:
        from services.settlement import mark_batch_converted

        with patch(
            "services.settlement.supabase_patch",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await mark_batch_converted(BATCH_ID, 100)

        assert result is False

    @pytest.mark.anyio
    async def test_omits_coinbase_id_when_none(self) -> None:
        from services.settlement import mark_batch_converted

        captured_patches: list[tuple[str, dict]] = []

        async def _capture_patch(path: str, payload: dict):
            captured_patches.append((path, payload))
            return [_batch_row()]

        with patch("services.settlement.supabase_patch", side_effect=_capture_patch):
            await mark_batch_converted(BATCH_ID, 500)

        _, payload = captured_patches[0]
        assert "coinbase_conversion_id" not in payload


# ---------------------------------------------------------------------------
# Admin route tests
# ---------------------------------------------------------------------------


class TestSettlementAdminRoutes:
    """Tests for settlement endpoints in routes/admin_billing.py."""

    def test_run_settlement_created(self, client: TestClient) -> None:
        mock_result = {
            "batch_id": BATCH_ID,
            "batch_date": BATCH_DATE,
            "total_usdc_atomic": "300000",
            "receipt_count": 2,
        }
        with patch(
            "routes.admin_billing.create_daily_settlement_batch",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = client.post(
                "/v1/admin/settlement/run",
                params={"batch_date": BATCH_DATE},
                headers=_admin_headers(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "created"
        assert data["batch_date"] == BATCH_DATE
        assert data["receipt_count"] == 2

    def test_run_settlement_skipped(self, client: TestClient) -> None:
        with patch(
            "routes.admin_billing.create_daily_settlement_batch",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post(
                "/v1/admin/settlement/run",
                headers=_admin_headers(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "skipped"
        assert data["reason"] == "no_receipts_or_already_exists"

    def test_pending_settlements(self, client: TestClient) -> None:
        batches = [_batch_row(), _batch_row(batch_id=str(uuid.uuid4()))]
        with patch(
            "routes.admin_billing.get_pending_batches",
            new_callable=AsyncMock,
            return_value=batches,
        ):
            resp = client.get(
                "/v1/admin/settlement/pending",
                headers=_admin_headers(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert len(data["batches"]) == 2

    def test_mark_converted_success(self, client: TestClient) -> None:
        with patch(
            "routes.admin_billing.mark_batch_converted",
            new_callable=AsyncMock,
            return_value=True,
        ):
            resp = client.post(
                f"/v1/admin/settlement/{BATCH_ID}/converted",
                json={"total_usd_cents": 29850, "coinbase_conversion_id": "cb_123"},
                headers=_admin_headers(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "converted"
        assert data["batch_id"] == BATCH_ID

    def test_mark_converted_not_found(self, client: TestClient) -> None:
        with patch(
            "routes.admin_billing.mark_batch_converted",
            new_callable=AsyncMock,
            return_value=False,
        ):
            resp = client.post(
                f"/v1/admin/settlement/{BATCH_ID}/converted",
                json={"total_usd_cents": 100},
                headers=_admin_headers(),
            )

        assert resp.status_code == 404
        assert "Batch not found" in resp.json()["detail"]

    def test_settlement_routes_require_admin_key(self, client: TestClient) -> None:
        """Settlement endpoints are protected by admin auth."""
        # No admin key header
        resp_run = client.post("/v1/admin/settlement/run")
        resp_pending = client.get("/v1/admin/settlement/pending")
        resp_convert = client.post(
            f"/v1/admin/settlement/{BATCH_ID}/converted",
            json={"total_usd_cents": 100},
        )

        assert resp_run.status_code == 401
        assert resp_pending.status_code == 401
        assert resp_convert.status_code == 401

    def test_mark_converted_validation_requires_positive_cents(self, client: TestClient) -> None:
        """total_usd_cents must be > 0."""
        resp = client.post(
            f"/v1/admin/settlement/{BATCH_ID}/converted",
            json={"total_usd_cents": 0},
            headers=_admin_headers(),
        )
        assert resp.status_code == 422
