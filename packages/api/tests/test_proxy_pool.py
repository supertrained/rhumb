"""Tests for proxy connection pool manager."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from services.proxy_pool import PoolManager, PoolMetrics


@pytest.fixture
def pool() -> PoolManager:
    """Create a fresh pool manager for each test."""
    return PoolManager()


@pytest.fixture
def pool_with_redis(fake_redis) -> PoolManager:
    """Create a pool manager with fakeredis."""
    return PoolManager(redis_client=fake_redis)


@pytest.fixture
def fake_redis():
    """Create a fakeredis async client."""
    import fakeredis.aioredis

    return fakeredis.aioredis.FakeRedis()


class TestPoolManagerAcquireRelease:
    """Test pool acquire/release lifecycle."""

    @pytest.mark.asyncio
    async def test_acquire_creates_client(self, pool: PoolManager) -> None:
        """First acquire for a service creates a new client."""
        client = await pool.acquire("stripe", base_url="https://api.stripe.com")
        assert client is not None
        assert pool.pool_count == 1
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_acquire_reuses_existing_pool(self, pool: PoolManager) -> None:
        """Second acquire for same service reuses existing pool."""
        client1 = await pool.acquire("stripe")
        client2 = await pool.acquire("stripe")
        assert client1 is client2
        assert pool.pool_count == 1
        metrics = pool.get_metrics("stripe")
        assert metrics is not None
        assert metrics.total_reused == 1
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_acquire_different_services(self, pool: PoolManager) -> None:
        """Different services get separate pools."""
        await pool.acquire("stripe")
        await pool.acquire("slack")
        assert pool.pool_count == 2
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_acquire_different_agents(self, pool: PoolManager) -> None:
        """Different agents for same service share one provider client."""
        client1 = await pool.acquire("stripe", "agent-1", base_url="https://api.stripe.com")
        client2 = await pool.acquire("stripe", "agent-2", base_url="https://api.stripe.com")
        assert client1 is client2
        assert pool.pool_count == 1
        agent_1_metrics = pool.get_metrics("stripe", "agent-1")
        agent_2_metrics = pool.get_metrics("stripe", "agent-2")
        assert agent_1_metrics is not None
        assert agent_2_metrics is not None
        assert agent_1_metrics.total_acquired == 1
        assert agent_2_metrics.total_acquired == 1
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_release_decrements_active(self, pool: PoolManager) -> None:
        """Release decrements active connection count."""
        await pool.acquire("stripe")
        metrics = pool.get_metrics("stripe")
        assert metrics is not None
        assert metrics.active_connections == 1

        await pool.release("stripe")
        metrics = pool.get_metrics("stripe")
        assert metrics is not None
        assert metrics.active_connections == 0
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_release_nonexistent_pool_is_noop(self, pool: PoolManager) -> None:
        """Releasing from a nonexistent pool doesn't raise."""
        await pool.release("nonexistent")  # Should not raise

    @pytest.mark.asyncio
    async def test_release_does_not_go_negative(self, pool: PoolManager) -> None:
        """Active connections can't go below zero."""
        await pool.acquire("stripe")
        await pool.release("stripe")
        await pool.release("stripe")  # Extra release
        metrics = pool.get_metrics("stripe")
        assert metrics is not None
        assert metrics.active_connections == 0
        await pool.shutdown()


class TestPoolManagerMetrics:
    """Test pool metrics tracking."""

    @pytest.mark.asyncio
    async def test_metrics_track_acquisitions(self, pool: PoolManager) -> None:
        """Metrics accurately track total acquisitions."""
        await pool.acquire("stripe")
        await pool.acquire("stripe")
        await pool.acquire("stripe")

        metrics = pool.get_metrics("stripe")
        assert metrics is not None
        assert metrics.total_acquired == 3
        assert metrics.total_reused == 2  # First is new, next 2 reuse
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_metrics_track_peak_active(self, pool: PoolManager) -> None:
        """Peak active connections are tracked."""
        await pool.acquire("stripe")
        await pool.acquire("stripe")
        await pool.release("stripe")

        metrics = pool.get_metrics("stripe")
        assert metrics is not None
        assert metrics.peak_active == 2
        assert metrics.active_connections == 1
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_metrics_utilization(self, pool: PoolManager) -> None:
        """Utilization ratio is computed correctly."""
        await pool.acquire("stripe")
        metrics = pool.get_metrics("stripe")
        assert metrics is not None
        assert metrics.utilization == pytest.approx(
            1.0 / pool.MAX_KEEPALIVE_CONNECTIONS, abs=0.01
        )
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_metrics_reuse_ratio(self, pool: PoolManager) -> None:
        """Reuse ratio is computed correctly."""
        await pool.acquire("stripe")  # new
        await pool.acquire("stripe")  # reuse
        await pool.acquire("stripe")  # reuse

        metrics = pool.get_metrics("stripe")
        assert metrics is not None
        assert metrics.reuse_ratio == pytest.approx(2.0 / 3.0, abs=0.01)
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_get_all_metrics(self, pool: PoolManager) -> None:
        """get_all_metrics returns metrics for all pools."""
        await pool.acquire("stripe", "agent-1")
        await pool.acquire("stripe", "agent-2")
        all_metrics = pool.get_all_metrics()
        assert len(all_metrics) == 2
        assert "stripe:agent-1" in all_metrics
        assert "stripe:agent-2" in all_metrics
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_get_metrics_nonexistent_returns_none(
        self, pool: PoolManager
    ) -> None:
        """Getting metrics for nonexistent pool returns None."""
        assert pool.get_metrics("nonexistent") is None

    def test_pool_metrics_defaults(self) -> None:
        """PoolMetrics has correct defaults."""
        m = PoolMetrics()
        assert m.utilization == 0.0
        assert m.reuse_ratio == 0.0
        assert m.total_acquired == 0


class TestPoolManagerProviderClients:
    """Test persistent provider-scoped client configuration."""

    @pytest.mark.asyncio
    async def test_agent_metrics_reflect_provider_pool_limits(
        self, pool: PoolManager
    ) -> None:
        """Per-agent metrics expose the shared provider keepalive limit."""
        await pool.acquire("stripe")
        metrics = pool.get_metrics("stripe")
        assert metrics is not None
        assert metrics.pool_size == pool.MAX_KEEPALIVE_CONNECTIONS
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_provider_client_has_persistent_keepalive_settings(
        self, pool: PoolManager
    ) -> None:
        """Provider client uses the contract's keepalive settings."""
        client = await pool.acquire("stripe", base_url="https://api.stripe.com")
        transport_pool = client._transport._pool  # type: ignore[attr-defined]

        assert client.base_url == "https://api.stripe.com"
        assert transport_pool._max_keepalive_connections == pool.MAX_KEEPALIVE_CONNECTIONS
        assert transport_pool._max_connections == pool.MAX_CONNECTIONS
        assert transport_pool._keepalive_expiry == pool.KEEPALIVE_EXPIRY
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_provider_client_is_only_closed_on_shutdown(
        self, pool: PoolManager
    ) -> None:
        """Normal acquire/release flow does not close the shared provider client."""
        client = await pool.acquire("stripe", base_url="https://api.stripe.com")
        await pool.release("stripe")

        close_spy = AsyncMock()
        client.aclose = close_spy  # type: ignore[method-assign]

        await pool.acquire("stripe", "agent-2", base_url="https://api.stripe.com")
        await pool.release("stripe", "agent-2")
        close_spy.assert_not_awaited()

        await pool.shutdown()
        close_spy.assert_awaited_once()


class TestPoolManagerShutdown:
    """Test graceful shutdown behavior."""

    @pytest.mark.asyncio
    async def test_shutdown_closes_all_clients(self, pool: PoolManager) -> None:
        """Shutdown closes all client instances."""
        await pool.acquire("stripe")
        await pool.acquire("slack")
        await pool.release("stripe")
        await pool.release("slack")

        await pool.shutdown()
        assert pool.pool_count == 0
        assert pool.is_shutting_down is True

    @pytest.mark.asyncio
    async def test_acquire_after_shutdown_raises(self, pool: PoolManager) -> None:
        """Acquiring after shutdown raises RuntimeError."""
        await pool.shutdown()
        with pytest.raises(RuntimeError, match="shutting down"):
            await pool.acquire("stripe")


class TestPoolManagerRedis:
    """Test Redis-backed state persistence."""

    @pytest.mark.asyncio
    async def test_redis_sync_on_acquire(
        self, pool_with_redis: PoolManager, fake_redis: object
    ) -> None:
        """Acquire syncs pool state to Redis."""
        await pool_with_redis.acquire("stripe", "agent-1")

        key = "proxy:pool:stripe:agent-1"
        exists = await fake_redis.exists(key)  # type: ignore[union-attr]
        assert exists

        pool_size = await fake_redis.hget(key, "pool_size")  # type: ignore[union-attr]
        assert pool_size == b"10"
        await pool_with_redis.shutdown()

    @pytest.mark.asyncio
    async def test_redis_sync_on_release(
        self, pool_with_redis: PoolManager, fake_redis: object
    ) -> None:
        """Release syncs updated state to Redis."""
        await pool_with_redis.acquire("stripe", "agent-1")
        await pool_with_redis.release("stripe", "agent-1")

        key = "proxy:pool:stripe:agent-1"
        active = await fake_redis.hget(key, "active_connections")  # type: ignore[union-attr]
        assert active == b"0"
        await pool_with_redis.shutdown()
