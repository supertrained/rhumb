"""Tests for AUD-21: durable rate limiting.

Tests the DurableRateLimiter with mock Supabase client to verify
atomic check-and-increment, fallback behavior, and cleanup.
"""

from __future__ import annotations

import pytest

from services.durable_rate_limit import DurableRateLimiter


class MockQueryResult:
    def __init__(self, data=None):
        self.data = data


class MockRpcBuilder:
    def __init__(self, data=None):
        self._data = data

    async def execute(self):
        return MockQueryResult(self._data)


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

    async def execute(self):
        return MockQueryResult(self._data)


class MockSupabase:
    def __init__(self):
        self._rpc_responses = {}
        self._tables = {}

    def rpc(self, name, params=None):
        return self._rpc_responses.get(name, MockRpcBuilder())

    def table(self, name):
        return self._tables.get(name, MockQueryBuilder())

    def set_rpc(self, name, builder):
        self._rpc_responses[name] = builder

    def set_table(self, name, builder):
        self._tables[name] = builder


@pytest.fixture
def mock_db():
    return MockSupabase()


@pytest.fixture
def limiter(mock_db):
    return DurableRateLimiter(mock_db, cleanup_interval_seconds=99999)


class TestCheckAndIncrement:
    @pytest.mark.asyncio
    async def test_allowed_returns_true(self, limiter, mock_db):
        mock_db.set_rpc("rate_limit_check", MockRpcBuilder([{
            "allowed": True,
            "remaining": 9,
            "request_count": 1,
            "window_start": "2026-04-01T00:00:00Z",
            "window_end": "2026-04-01T00:01:00Z",
        }]))
        allowed, remaining = await limiter.check_and_increment("ip:1.2.3.4:read", 10, 60)
        assert allowed is True
        assert remaining == 9

    @pytest.mark.asyncio
    async def test_rate_limited_returns_false(self, limiter, mock_db):
        mock_db.set_rpc("rate_limit_check", MockRpcBuilder([{
            "allowed": False,
            "remaining": 0,
            "request_count": 10,
            "window_start": "2026-04-01T00:00:00Z",
            "window_end": "2026-04-01T00:01:00Z",
        }]))
        allowed, remaining = await limiter.check_and_increment("ip:1.2.3.4:read", 10, 60)
        assert allowed is False
        assert remaining == 0

    @pytest.mark.asyncio
    async def test_db_failure_falls_back_to_memory(self, limiter, mock_db):
        """Fail-open: DB errors fall back to in-memory rate limiting."""
        class FailingRpc:
            async def execute(self):
                raise ConnectionError("DB down")

        mock_db.set_rpc("rate_limit_check", FailingRpc())
        # First call should be allowed (new in-memory window)
        allowed, remaining = await limiter.check_and_increment("ip:1.2.3.4:read", 2, 60)
        assert allowed is True
        assert remaining == 1

    @pytest.mark.asyncio
    async def test_fallback_enforces_limit(self, limiter, mock_db):
        """In-memory fallback still enforces rate limits."""
        class FailingRpc:
            async def execute(self):
                raise ConnectionError("DB down")

        mock_db.set_rpc("rate_limit_check", FailingRpc())
        # Use up the limit
        for _ in range(3):
            await limiter.check_and_increment("ip:test:fallback", 3, 60)
        # 4th should be blocked
        allowed, remaining = await limiter.check_and_increment("ip:test:fallback", 3, 60)
        assert allowed is False
        assert remaining == 0


class TestReset:
    @pytest.mark.asyncio
    async def test_reset_succeeds(self, limiter, mock_db):
        mock_db.set_table("rate_limit_windows", MockQueryBuilder())
        result = await limiter.reset("ip:1.2.3.4:read")
        assert result is True

    @pytest.mark.asyncio
    async def test_reset_survives_db_error(self, limiter, mock_db):
        class FailingBuilder(MockQueryBuilder):
            def delete(self):
                return self
            def eq(self, *args):
                return self
            async def execute(self):
                raise ConnectionError("DB down")

        mock_db.set_table("rate_limit_windows", FailingBuilder())
        result = await limiter.reset("ip:1.2.3.4:read")
        assert result is False


class TestGetState:
    @pytest.mark.asyncio
    async def test_get_existing_state(self, limiter, mock_db):
        mock_db.set_table("rate_limit_windows", MockQueryBuilder({
            "key": "ip:1.2.3.4:read",
            "request_count": 5,
            "window_start": "2026-04-01T00:00:00Z",
            "window_end": "2026-04-01T00:01:00Z",
        }))
        state = await limiter.get_state("ip:1.2.3.4:read")
        assert state is not None
        assert state["request_count"] == 5

    @pytest.mark.asyncio
    async def test_get_missing_state(self, limiter, mock_db):
        mock_db.set_table("rate_limit_windows", MockQueryBuilder(None))
        state = await limiter.get_state("ip:nonexistent")
        assert state is None
