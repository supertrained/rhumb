"""Tests for AUD-4: durable idempotency store.

Tests the DurableIdempotencyStore with a mock Supabase client
to verify atomic claim, TTL expiration, cleanup, and fail-open behavior.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.durable_idempotency import (
    DurableIdempotencyStore,
    IdempotencyRecord,
    IdempotencyUnavailable,
)


class MockQueryResult:
    """Mock Supabase query result."""
    def __init__(self, data=None):
        self.data = data


class MockQueryBuilder:
    """Mock Supabase query builder with chaining."""
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

    async def execute(self):
        return MockQueryResult(self._data)


class MockRpcBuilder:
    """Mock Supabase RPC call."""
    def __init__(self, data=None):
        self._data = data

    async def execute(self):
        return MockQueryResult(self._data)


class MockSupabase:
    """Mock Supabase client for testing."""

    def __init__(self):
        self._tables = {}
        self._rpc_responses = {}

    def table(self, name):
        return self._tables.get(name, MockQueryBuilder())

    def rpc(self, name, params=None):
        return self._rpc_responses.get(name, MockRpcBuilder())

    def set_table(self, name, builder):
        self._tables[name] = builder

    def set_rpc(self, name, builder):
        self._rpc_responses[name] = builder


@pytest.fixture
def mock_db():
    return MockSupabase()


@pytest.fixture
def store(mock_db):
    return DurableIdempotencyStore(mock_db, window_seconds=3600, cleanup_interval_seconds=0)


class TestGenerateKey:
    def test_deterministic(self):
        key1 = DurableIdempotencyStore.generate_key("r1", {"q": "test"}, "agent1")
        key2 = DurableIdempotencyStore.generate_key("r1", {"q": "test"}, "agent1")
        assert key1 == key2

    def test_prefix(self):
        key = DurableIdempotencyStore.generate_key("r1", {}, "")
        assert key.startswith("idem_")

    def test_different_inputs_different_keys(self):
        key1 = DurableIdempotencyStore.generate_key("r1", {"q": "a"}, "")
        key2 = DurableIdempotencyStore.generate_key("r1", {"q": "b"}, "")
        assert key1 != key2

    def test_different_agents_different_keys(self):
        key1 = DurableIdempotencyStore.generate_key("r1", {}, "agent1")
        key2 = DurableIdempotencyStore.generate_key("r1", {}, "agent2")
        assert key1 != key2


class TestCheck:
    @pytest.mark.asyncio
    async def test_miss_returns_none(self, store, mock_db):
        mock_db.set_table("idempotency_keys", MockQueryBuilder(None))
        result = await store.check("idem_nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_hit_returns_record(self, store, mock_db):
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        now = datetime.now(timezone.utc).isoformat()
        mock_db.set_table("idempotency_keys", MockQueryBuilder({
            "key": "idem_test",
            "execution_id": "exec_1",
            "recipe_id": "r1",
            "status": "completed",
            "result_hash": "abc123",
            "created_at": now,
            "expires_at": future,
        }))
        result = await store.check("idem_test")
        assert result is not None
        assert result.key == "idem_test"
        assert result.execution_id == "exec_1"
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_expired_returns_none(self, store, mock_db):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        now = datetime.now(timezone.utc).isoformat()

        class ExpiredBuilder(MockQueryBuilder):
            def __init__(self):
                self._deleted = False
            def select(self, *args):
                return self
            def eq(self, *args):
                return self
            def maybe_single(self):
                return self
            def delete(self):
                self._deleted = True
                return self
            async def execute(self):
                if self._deleted:
                    return MockQueryResult(None)
                return MockQueryResult({
                    "key": "idem_expired",
                    "execution_id": "exec_old",
                    "recipe_id": "r1",
                    "status": "completed",
                    "result_hash": "abc",
                    "created_at": now,
                    "expires_at": past,
                })

        mock_db.set_table("idempotency_keys", ExpiredBuilder())
        result = await store.check("idem_expired")
        assert result is None

    @pytest.mark.asyncio
    async def test_db_error_returns_none(self, store, mock_db):
        """Fail-open: DB errors return None (allow execution)."""
        class FailingBuilder(MockQueryBuilder):
            def select(self, *args):
                return self
            def eq(self, *args):
                return self
            def maybe_single(self):
                return self
            async def execute(self):
                raise ConnectionError("DB down")

        mock_db.set_table("idempotency_keys", FailingBuilder())
        result = await store.check("idem_test")
        assert result is None  # Fail-open

    @pytest.mark.asyncio
    async def test_db_error_can_fail_closed(self, store, mock_db):
        """Strict mode should surface unavailable durable idempotency."""
        class FailingBuilder(MockQueryBuilder):
            def select(self, *args):
                return self
            def eq(self, *args):
                return self
            def maybe_single(self):
                return self
            async def execute(self):
                raise ConnectionError("DB down")

        mock_db.set_table("idempotency_keys", FailingBuilder())
        with pytest.raises(IdempotencyUnavailable):
            await store.check("idem_test", allow_fallback=False)


class TestClaim:
    @pytest.mark.asyncio
    async def test_new_claim_succeeds(self, store, mock_db):
        mock_db.set_rpc("idempotency_claim", MockRpcBuilder([{
            "key": "idem_new",
            "execution_id": "exec_1",
            "recipe_id": "r1",
            "status": "pending",
            "result_hash": "",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "already_exists": False,
        }]))
        result = await store.claim("idem_new", "exec_1", "r1")
        assert result is None  # None means claim succeeded

    @pytest.mark.asyncio
    async def test_duplicate_claim_returns_existing(self, store, mock_db):
        mock_db.set_rpc("idempotency_claim", MockRpcBuilder([{
            "key": "idem_dup",
            "execution_id": "exec_original",
            "recipe_id": "r1",
            "status": "completed",
            "result_hash": "abc",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "already_exists": True,
        }]))
        result = await store.claim("idem_dup", "exec_2", "r1")
        assert result is not None
        assert result.execution_id == "exec_original"
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_db_error_returns_none(self, store, mock_db):
        """Fail-open: DB errors on claim allow execution."""
        class FailingRpc:
            async def execute(self):
                raise ConnectionError("DB down")

        mock_db.set_rpc("idempotency_claim", FailingRpc())
        result = await store.claim("idem_test", "exec_1", "r1")
        assert result is None  # Fail-open: claim "succeeds"

    @pytest.mark.asyncio
    async def test_claim_db_error_can_fail_closed(self, store, mock_db):
        """Strict mode claim should reject DB-unavailable protection."""
        class FailingRpc:
            async def execute(self):
                raise ConnectionError("DB down")

        mock_db.set_rpc("idempotency_claim", FailingRpc())
        with pytest.raises(IdempotencyUnavailable):
            await store.claim("idem_test", "exec_1", "r1", allow_fallback=False)


class TestStore:
    @pytest.mark.asyncio
    async def test_store_returns_record(self, store, mock_db):
        class UpsertBuilder:
            def upsert(self, data):
                return self
            async def execute(self):
                return MockQueryResult(None)

        mock_db.set_table("idempotency_keys", UpsertBuilder())
        record = await store.store("idem_test", "exec_1", "r1", "completed", "abc")
        assert record.key == "idem_test"
        assert record.status == "completed"

    @pytest.mark.asyncio
    async def test_store_survives_db_error(self, store, mock_db):
        """Fail-open: DB error on store doesn't raise."""
        class FailingUpsert:
            def upsert(self, data):
                return self
            async def execute(self):
                raise ConnectionError("DB down")

        mock_db.set_table("idempotency_keys", FailingUpsert())
        # Should not raise
        record = await store.store("idem_test", "exec_1", "r1", "completed", "abc")
        assert record.key == "idem_test"


class TestRelease:
    @pytest.mark.asyncio
    async def test_release_deletes_key(self, store, mock_db):
        class ReleaseBuilder:
            def __init__(self):
                self.deleted_key = None
            def delete(self):
                return self
            def eq(self, field, value):
                self.deleted_key = value
                return self
            async def execute(self):
                return MockQueryResult(None)

        builder = ReleaseBuilder()
        mock_db.set_table("idempotency_keys", builder)
        await store.release("idem_release")
        assert builder.deleted_key == "idem_release"


class TestCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_called_periodically(self, mock_db):
        """Cleanup runs when interval has elapsed."""
        cleanup_called = []

        class TrackingBuilder(MockQueryBuilder):
            def delete(self):
                cleanup_called.append(True)
                return self
            def lt(self, *args):
                return self
            def select(self, *args):
                return self
            def eq(self, *args):
                return self
            def maybe_single(self):
                return self
            async def execute(self):
                return MockQueryResult(None)

        mock_db.set_table("idempotency_keys", TrackingBuilder())
        store = DurableIdempotencyStore(mock_db, cleanup_interval_seconds=0)
        await store.check("idem_test")
        assert len(cleanup_called) >= 1
