"""Tests for AUD-25: durable x402 replay prevention."""

from __future__ import annotations

import pytest

from services.durable_replay_guard import DurableReplayGuard, ReplayGuardUnavailable


class MockQueryResult:
    def __init__(self, data=None):
        self.data = data


class MockQueryBuilder:
    def __init__(self, data=None):
        self._data = data

    def select(self, *args):
        return self

    def eq(self, *args):
        return self

    def lt(self, *args):
        return self

    def maybe_single(self):
        return self

    def delete(self):
        return self

    def insert(self, data):
        return self

    async def execute(self):
        return MockQueryResult(self._data)


class MockSupabase:
    def __init__(self):
        self._tables = {}

    def table(self, name):
        return self._tables.get(name, MockQueryBuilder())

    def set_table(self, name, builder):
        self._tables[name] = builder


@pytest.fixture
def mock_db():
    return MockSupabase()


@pytest.fixture
def guard(mock_db):
    return DurableReplayGuard(mock_db, ttl_seconds=86400, cleanup_interval_seconds=99999)


class TestCheckAndClaim:
    @pytest.mark.asyncio
    async def test_first_use_allowed(self, guard, mock_db):
        """First use of a tx_hash is allowed."""
        mock_db.set_table("usdc_receipts", MockQueryBuilder(None))
        mock_db.set_table("tx_replay_guard", MockQueryBuilder(None))
        is_replay = await guard.check_and_claim("0xabc123")
        assert is_replay is False

    @pytest.mark.asyncio
    async def test_replay_from_usdc_receipts(self, guard, mock_db):
        """tx_hash found in usdc_receipts is a replay."""
        mock_db.set_table("usdc_receipts", MockQueryBuilder({"tx_hash": "0xabc123"}))
        is_replay = await guard.check_and_claim("0xabc123")
        assert is_replay is True

    @pytest.mark.asyncio
    async def test_replay_from_unique_violation(self, guard, mock_db):
        """Duplicate INSERT (unique violation) is detected as replay."""
        class ReplayBuilder(MockQueryBuilder):
            def insert(self, data):
                return self
            async def execute(self):
                raise Exception("duplicate key value violates unique constraint")

        mock_db.set_table("usdc_receipts", MockQueryBuilder(None))
        mock_db.set_table("tx_replay_guard", ReplayBuilder())
        is_replay = await guard.check_and_claim("0xabc123")
        assert is_replay is True

    @pytest.mark.asyncio
    async def test_empty_hash_rejected(self, guard):
        """Empty tx_hash is always rejected."""
        is_replay = await guard.check_and_claim("")
        assert is_replay is True

    @pytest.mark.asyncio
    async def test_case_normalized(self, guard, mock_db):
        """tx_hash is lowercased and stripped."""
        mock_db.set_table("usdc_receipts", MockQueryBuilder(None))
        mock_db.set_table("tx_replay_guard", MockQueryBuilder(None))
        is_replay = await guard.check_and_claim("  0xABC123  ")
        assert is_replay is False

    @pytest.mark.asyncio
    async def test_db_failure_falls_back(self, guard, mock_db):
        """DB failure falls back to in-memory when explicitly allowed."""
        class FailingBuilder(MockQueryBuilder):
            def select(self, *args):
                return self
            def eq(self, *args):
                return self
            def maybe_single(self):
                return self
            async def execute(self):
                raise ConnectionError("DB down")

        mock_db.set_table("usdc_receipts", FailingBuilder())
        mock_db.set_table("tx_replay_guard", FailingBuilder())
        # First use
        is_replay = await guard.check_and_claim("0xfallback")
        assert is_replay is False
        # Second use (in-memory replay)
        is_replay = await guard.check_and_claim("0xfallback")
        assert is_replay is True

    @pytest.mark.asyncio
    async def test_db_failure_can_fail_closed(self, guard, mock_db):
        """Financial paths can require durable replay protection and fail closed."""
        class FailingBuilder(MockQueryBuilder):
            def select(self, *args):
                return self
            def eq(self, *args):
                return self
            def maybe_single(self):
                return self
            async def execute(self):
                raise ConnectionError("DB down")

        mock_db.set_table("usdc_receipts", FailingBuilder())
        mock_db.set_table("tx_replay_guard", FailingBuilder())

        with pytest.raises(ReplayGuardUnavailable):
            await guard.check_and_claim("0xfailclosed", allow_fallback=False)


class TestIsKnown:
    @pytest.mark.asyncio
    async def test_unknown_hash(self, guard, mock_db):
        mock_db.set_table("tx_replay_guard", MockQueryBuilder(None))
        mock_db.set_table("usdc_receipts", MockQueryBuilder(None))
        assert await guard.is_known("0xunknown") is False

    @pytest.mark.asyncio
    async def test_known_in_guard(self, guard, mock_db):
        mock_db.set_table("tx_replay_guard", MockQueryBuilder({"tx_hash": "0xknown"}))
        assert await guard.is_known("0xknown") is True

    @pytest.mark.asyncio
    async def test_known_in_receipts(self, guard, mock_db):
        mock_db.set_table("tx_replay_guard", MockQueryBuilder(None))
        mock_db.set_table("usdc_receipts", MockQueryBuilder({"tx_hash": "0xold"}))
        assert await guard.is_known("0xold") is True
