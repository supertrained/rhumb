"""Connection pool manager for proxy service.

Maintains one persistent httpx.AsyncClient per provider/service and tracks
per-agent accounting separately at proxy:pool:{service}:{agent_id}.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Optional

import httpx


@dataclass
class PoolMetrics:
    """Per-agent utilization metrics over a shared provider client."""

    total_acquired: int = 0
    total_released: int = 0
    total_reused: int = 0
    active_connections: int = 0
    pool_size: int = 10
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


class PoolManager:
    """Connection pool manager with persistent provider-scoped clients."""

    DEFAULT_TIMEOUT: float = 10.0
    KEEPALIVE_EXPIRY: float = 30.0
    MAX_KEEPALIVE_CONNECTIONS: int = 10
    MAX_CONNECTIONS: int = 40

    def __init__(self, redis_client: Optional[object] = None) -> None:
        self._provider_clients: dict[str, httpx.AsyncClient] = {}
        self._agent_metrics: dict[str, PoolMetrics] = {}
        self._redis = redis_client
        self._lock = asyncio.Lock()
        self._shutting_down = False

    def _agent_key(self, service: str, agent_id: str) -> str:
        """Generate the per-agent metrics lookup key."""
        return f"{service}:{agent_id}"

    async def _get_or_create_provider_client(
        self, service: str, base_url: str = ""
    ) -> httpx.AsyncClient:
        """Get the persistent client for a provider, creating it on first use."""
        client = self._provider_clients.get(service)
        if client is None:
            client = httpx.AsyncClient(
                base_url=base_url,
                timeout=self.DEFAULT_TIMEOUT,
                limits=httpx.Limits(
                    max_keepalive_connections=self.MAX_KEEPALIVE_CONNECTIONS,
                    max_connections=self.MAX_CONNECTIONS,
                    keepalive_expiry=self.KEEPALIVE_EXPIRY,
                ),
            )
            self._provider_clients[service] = client
        return client

    async def _sync_to_redis(
        self, service: str, agent_id: str, metrics: PoolMetrics
    ) -> None:
        """Persist per-agent pool state to Redis."""
        if self._redis is None:
            return
        key = f"proxy:pool:{service}:{agent_id}"
        state = {
            "pool_size": str(metrics.pool_size),
            "active_connections": str(metrics.active_connections),
            "total_acquired": str(metrics.total_acquired),
            "total_released": str(metrics.total_released),
            "total_reused": str(metrics.total_reused),
            "utilization": f"{metrics.utilization:.3f}",
        }
        if hasattr(self._redis, "hset"):
            await self._redis.hset(key, mapping=state)
            await self._redis.expire(key, 300)  # 5m TTL

    async def acquire(
        self,
        service: str,
        agent_id: str = "default",
        *,
        base_url: str = "",
    ) -> httpx.AsyncClient:
        """Acquire the shared provider client and update per-agent metrics.

        Args:
            service: Provider service name (e.g., 'stripe').
            agent_id: Agent identifier for per-agent accounting.
            base_url: Provider base URL used when the client is first created.

        Returns:
            An httpx.AsyncClient configured for the service.

        Raises:
            RuntimeError: If pool manager is shutting down.
        """
        if self._shutting_down:
            raise RuntimeError("Pool manager is shutting down")

        key = self._agent_key(service, agent_id)

        async with self._lock:
            client = await self._get_or_create_provider_client(service, base_url)
            metrics = self._agent_metrics.get(key)
            if metrics is None:
                metrics = PoolMetrics(pool_size=self.MAX_KEEPALIVE_CONNECTIONS)
                self._agent_metrics[key] = metrics
            else:
                metrics.total_reused += 1

            metrics.total_acquired += 1
            metrics.active_connections += 1
            if metrics.active_connections > metrics.peak_active:
                metrics.peak_active = metrics.active_connections
            metrics.last_request_time = time.monotonic()

            await self._sync_to_redis(service, agent_id, metrics)

        return client

    async def release(self, service: str, agent_id: str = "default") -> None:
        """Release a connection back to the shared provider client.

        Args:
            service: Provider service name.
            agent_id: Agent identifier.
        """
        key = self._agent_key(service, agent_id)

        async with self._lock:
            metrics = self._agent_metrics.get(key)
            if metrics is not None:
                metrics.active_connections = max(0, metrics.active_connections - 1)
                metrics.total_released += 1
                await self._sync_to_redis(service, agent_id, metrics)

    def get_metrics(self, service: str, agent_id: str = "default") -> Optional[PoolMetrics]:
        """Get per-agent metrics for a service+agent pair.

        Args:
            service: Provider service name.
            agent_id: Agent identifier.

        Returns:
            PoolMetrics if pool exists, None otherwise.
        """
        return self._agent_metrics.get(self._agent_key(service, agent_id))

    def get_all_metrics(self) -> dict[str, PoolMetrics]:
        """Get metrics for all active service+agent accounting entries.

        Returns:
            Dict mapping service:agent keys to their metrics.
        """
        return dict(self._agent_metrics)

    async def shutdown(self) -> None:
        """Gracefully shut down all provider clients.

        Marks manager as shutting down, waits for active connections to drain
        (up to 5s), then closes all clients.
        """
        self._shutting_down = True

        # Wait for active connections to drain (up to 5s)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            total_active = sum(
                metrics.active_connections for metrics in self._agent_metrics.values()
            )
            if total_active == 0:
                break
            await asyncio.sleep(0.1)

        # Close all clients
        async with self._lock:
            for client in self._provider_clients.values():
                await client.aclose()
            self._provider_clients.clear()
            self._agent_metrics.clear()

    @property
    def pool_count(self) -> int:
        """Number of provider clients currently managed."""
        return len(self._provider_clients)

    @property
    def is_shutting_down(self) -> bool:
        """Whether the pool manager is shutting down."""
        return self._shutting_down
