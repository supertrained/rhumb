"""Connection pool manager for proxy service.

Redis-backed pool state with adaptive sizing based on request frequency.
Each service+agent pair gets its own pool tracked at proxy:pool:{service}:{agent_id}.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx


@dataclass
class PoolMetrics:
    """Utilization metrics for a connection pool."""

    total_acquired: int = 0
    total_released: int = 0
    total_reused: int = 0
    active_connections: int = 0
    pool_size: int = 3
    peak_active: int = 0
    last_request_time: float = 0.0

    @property
    def utilization(self) -> float:
        """Current pool utilization ratio (0.0–1.0)."""
        if self.pool_size == 0:
            return 0.0
        return min(self.active_connections / self.pool_size, 1.0)

    @property
    def reuse_ratio(self) -> float:
        """Fraction of acquisitions that reused an existing connection."""
        if self.total_acquired == 0:
            return 0.0
        return self.total_reused / self.total_acquired


@dataclass
class PoolEntry:
    """A single pool entry for a service+agent pair."""

    service: str
    agent_id: str
    client: httpx.AsyncClient
    metrics: PoolMetrics = field(default_factory=PoolMetrics)
    _request_timestamps: list[float] = field(default_factory=list)

    def record_request(self) -> None:
        """Record a request timestamp for QPS calculation."""
        now = time.monotonic()
        self._request_timestamps.append(now)
        self.metrics.last_request_time = now
        # Keep only last 60s of timestamps
        cutoff = now - 60.0
        self._request_timestamps = [t for t in self._request_timestamps if t > cutoff]

    @property
    def qps(self) -> float:
        """Requests per second over the last 60s window."""
        now = time.monotonic()
        cutoff = now - 60.0
        recent = [t for t in self._request_timestamps if t > cutoff]
        if not recent:
            return 0.0
        elapsed = now - recent[0]
        if elapsed < 0.01:
            return float(len(recent))
        return len(recent) / elapsed

    @property
    def redis_key(self) -> str:
        """Redis key for this pool entry."""
        return f"proxy:pool:{self.service}:{self.agent_id}"


class PoolManager:
    """Connection pool manager with adaptive sizing.

    Manages httpx.AsyncClient instances per service+agent pair.
    Pool sizing: base=3, scale=+1 per 10 QPS, capped at max_pool_size.
    """

    BASE_POOL_SIZE: int = 3
    QPS_SCALE_FACTOR: int = 10  # +1 connection per 10 qps
    MAX_POOL_SIZE: int = 20
    DEFAULT_TIMEOUT: float = 10.0

    def __init__(self, redis_client: Optional[object] = None) -> None:
        self._pools: dict[str, PoolEntry] = {}
        self._redis = redis_client
        self._lock = asyncio.Lock()
        self._shutting_down = False

    def _pool_key(self, service: str, agent_id: str) -> str:
        """Generate pool lookup key."""
        return f"{service}:{agent_id}"

    def _compute_pool_size(self, qps: float) -> int:
        """Compute target pool size based on QPS.

        base=3, +1 per 10 QPS, capped at MAX_POOL_SIZE.
        """
        extra = int(qps / self.QPS_SCALE_FACTOR)
        return min(self.BASE_POOL_SIZE + extra, self.MAX_POOL_SIZE)

    async def _create_client(self, pool_size: int) -> httpx.AsyncClient:
        """Create a new httpx.AsyncClient with the given pool size."""
        return httpx.AsyncClient(
            timeout=self.DEFAULT_TIMEOUT,
            limits=httpx.Limits(
                max_keepalive_connections=pool_size,
                max_connections=pool_size * 2,
            ),
        )

    async def _sync_to_redis(self, entry: PoolEntry) -> None:
        """Persist pool state to Redis."""
        if self._redis is None:
            return
        key = entry.redis_key
        state = {
            "pool_size": str(entry.metrics.pool_size),
            "active_connections": str(entry.metrics.active_connections),
            "total_acquired": str(entry.metrics.total_acquired),
            "total_released": str(entry.metrics.total_released),
            "total_reused": str(entry.metrics.total_reused),
            "utilization": f"{entry.metrics.utilization:.3f}",
        }
        if hasattr(self._redis, "hset"):
            await self._redis.hset(key, mapping=state)
            await self._redis.expire(key, 300)  # 5m TTL

    async def acquire(self, service: str, agent_id: str = "default") -> httpx.AsyncClient:
        """Acquire an HTTP client from the pool.

        Creates a new pool entry if one doesn't exist for this service+agent pair.
        Tracks metrics and adapts pool size based on request frequency.

        Args:
            service: Provider service name (e.g., 'stripe').
            agent_id: Agent identifier for per-agent pooling.

        Returns:
            An httpx.AsyncClient configured for the service.

        Raises:
            RuntimeError: If pool manager is shutting down.
        """
        if self._shutting_down:
            raise RuntimeError("Pool manager is shutting down")

        key = self._pool_key(service, agent_id)

        async with self._lock:
            if key not in self._pools:
                client = await self._create_client(self.BASE_POOL_SIZE)
                entry = PoolEntry(
                    service=service,
                    agent_id=agent_id,
                    client=client,
                )
                entry.metrics.pool_size = self.BASE_POOL_SIZE
                self._pools[key] = entry
            else:
                entry = self._pools[key]
                entry.metrics.total_reused += 1

            entry.record_request()
            entry.metrics.total_acquired += 1
            entry.metrics.active_connections += 1
            if entry.metrics.active_connections > entry.metrics.peak_active:
                entry.metrics.peak_active = entry.metrics.active_connections

            # Adaptive sizing: check if pool needs to grow
            target_size = self._compute_pool_size(entry.qps)
            if target_size != entry.metrics.pool_size:
                old_client = entry.client
                entry.client = await self._create_client(target_size)
                entry.metrics.pool_size = target_size
                await old_client.aclose()

            await self._sync_to_redis(entry)

        return entry.client

    async def release(self, service: str, agent_id: str = "default") -> None:
        """Release a connection back to the pool.

        Args:
            service: Provider service name.
            agent_id: Agent identifier.
        """
        key = self._pool_key(service, agent_id)

        async with self._lock:
            if key in self._pools:
                entry = self._pools[key]
                entry.metrics.active_connections = max(
                    0, entry.metrics.active_connections - 1
                )
                entry.metrics.total_released += 1
                await self._sync_to_redis(entry)

    def get_metrics(self, service: str, agent_id: str = "default") -> Optional[PoolMetrics]:
        """Get pool metrics for a service+agent pair.

        Args:
            service: Provider service name.
            agent_id: Agent identifier.

        Returns:
            PoolMetrics if pool exists, None otherwise.
        """
        key = self._pool_key(service, agent_id)
        entry = self._pools.get(key)
        if entry is None:
            return None
        return entry.metrics

    def get_all_metrics(self) -> dict[str, PoolMetrics]:
        """Get metrics for all active pools.

        Returns:
            Dict mapping pool keys to their metrics.
        """
        return {key: entry.metrics for key, entry in self._pools.items()}

    async def shutdown(self) -> None:
        """Gracefully shut down all pools.

        Marks manager as shutting down, waits for active connections to drain
        (up to 5s), then closes all clients.
        """
        self._shutting_down = True

        # Wait for active connections to drain (up to 5s)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            total_active = sum(
                e.metrics.active_connections for e in self._pools.values()
            )
            if total_active == 0:
                break
            await asyncio.sleep(0.1)

        # Close all clients
        async with self._lock:
            for entry in self._pools.values():
                await entry.client.aclose()
            self._pools.clear()

    @property
    def pool_count(self) -> int:
        """Number of active pool entries."""
        return len(self._pools)

    @property
    def is_shutting_down(self) -> bool:
        """Whether the pool manager is shutting down."""
        return self._shutting_down
