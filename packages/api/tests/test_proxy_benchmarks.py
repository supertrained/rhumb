"""Performance benchmarks for proxy overhead.

Verifies:
- Baseline proxy overhead < 10ms
- Pool reuse ratio > 80%
- Circuit breaker transitions within 100ms
- P95 < 15ms, P99 < 25ms on 100 calls
"""

import asyncio
import time

import pytest

from services.proxy_breaker import BreakerState, CircuitBreaker
from services.proxy_latency import LatencyTracker
from services.proxy_pool import PoolManager


class TestBaselineLatency:
    """Verify proxy overhead is sub-10ms."""

    @pytest.mark.asyncio
    async def test_pool_acquire_release_under_10ms(self) -> None:
        """Pool acquire+release overhead is under 10ms."""
        pool = PoolManager()
        timings: list[float] = []

        for _ in range(50):
            start = time.perf_counter()
            client = await pool.acquire("stripe")
            await pool.release("stripe")
            elapsed_ms = (time.perf_counter() - start) * 1000
            timings.append(elapsed_ms)

        mean_ms = sum(timings) / len(timings)
        assert mean_ms < 10.0, f"Mean acquire+release time {mean_ms:.2f}ms exceeds 10ms"
        await pool.shutdown()

    def test_breaker_check_under_1ms(self) -> None:
        """Circuit breaker check overhead is under 1ms."""
        breaker = CircuitBreaker(service="stripe")
        timings: list[float] = []

        for _ in range(100):
            start = time.perf_counter()
            breaker.allow_request()
            elapsed_ms = (time.perf_counter() - start) * 1000
            timings.append(elapsed_ms)

        mean_ms = sum(timings) / len(timings)
        assert mean_ms < 1.0, f"Mean breaker check time {mean_ms:.2f}ms exceeds 1ms"

    def test_latency_record_under_1ms(self) -> None:
        """Latency recording overhead is under 1ms."""
        tracker = LatencyTracker()
        timings: list[float] = []

        for _ in range(100):
            start = time.perf_counter()
            tracker.record(
                service="stripe",
                agent_id="default",
                latency_ms=5.0,
                perf_start=start,
                perf_end=start + 0.005,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            timings.append(elapsed_ms)

        mean_ms = sum(timings) / len(timings)
        assert mean_ms < 1.0, f"Mean record time {mean_ms:.2f}ms exceeds 1ms"

    @pytest.mark.asyncio
    async def test_full_proxy_overhead_under_10ms(self) -> None:
        """Full proxy overhead (pool + breaker + latency) < 10ms."""
        pool = PoolManager()
        breaker = CircuitBreaker(service="stripe")
        tracker = LatencyTracker()
        timings: list[float] = []

        for _ in range(50):
            perf_start = time.perf_counter()

            # Simulate full proxy overhead (everything except the actual HTTP call)
            breaker.allow_request()
            client = await pool.acquire("stripe")
            await pool.release("stripe")
            perf_end = time.perf_counter()
            latency_ms = (perf_end - perf_start) * 1000
            tracker.record(
                service="stripe",
                agent_id="default",
                latency_ms=latency_ms,
                perf_start=perf_start,
                perf_end=perf_end,
            )
            breaker.record_success(latency_ms=latency_ms)

            timings.append(latency_ms)

        mean_ms = sum(timings) / len(timings)
        assert mean_ms < 10.0, f"Mean full overhead {mean_ms:.2f}ms exceeds 10ms"
        await pool.shutdown()


class TestPoolReuse:
    """Verify pool reuse efficiency."""

    @pytest.mark.asyncio
    async def test_pool_reuse_above_80_percent(self) -> None:
        """Pool reuse ratio exceeds 80% over 100 sequential calls."""
        pool = PoolManager()

        for _ in range(100):
            await pool.acquire("stripe")
            await pool.release("stripe")

        metrics = pool.get_metrics("stripe")
        assert metrics is not None
        assert metrics.reuse_ratio > 0.80, (
            f"Pool reuse ratio {metrics.reuse_ratio:.2%} is below 80%"
        )
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_pool_reuse_multiple_services(self) -> None:
        """Pool reuse works across multiple services."""
        pool = PoolManager()
        services = ["stripe", "slack", "github"]

        for _ in range(30):
            for svc in services:
                await pool.acquire(svc)
                await pool.release(svc)

        for svc in services:
            metrics = pool.get_metrics(svc)
            assert metrics is not None
            assert metrics.reuse_ratio > 0.80
        await pool.shutdown()


class TestCircuitBreakerTransitions:
    """Verify circuit breaker state transitions are fast."""

    def test_transition_to_open_within_100ms(self) -> None:
        """5 failures -> OPEN transition completes within 100ms."""
        breaker = CircuitBreaker(service="stripe")

        start = time.perf_counter()
        for _ in range(5):
            breaker.record_failure(status_code=500)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert breaker.state == BreakerState.OPEN
        assert elapsed_ms < 100.0, (
            f"Transition to OPEN took {elapsed_ms:.2f}ms, exceeds 100ms"
        )

    def test_full_cycle_within_200ms(self) -> None:
        """Full CLOSED->OPEN->HALF_OPEN->CLOSED cycle is fast."""
        from unittest.mock import patch

        breaker = CircuitBreaker(
            service="stripe", failure_threshold=3, cooldown_seconds=0.05
        )

        start = time.perf_counter()

        # CLOSED -> OPEN
        for _ in range(3):
            breaker.record_failure(status_code=500)
        assert breaker._state == BreakerState.OPEN

        # OPEN -> HALF_OPEN (via mock time)
        # Capture the real time when OPEN state was entered
        real_opened_at = breaker._opened_at
        with patch("services.proxy_breaker.time.monotonic") as mock_time:
            # Return a time value that is enough to exceed cooldown_seconds
            mock_time.return_value = real_opened_at + 1.0
            assert breaker.state == BreakerState.HALF_OPEN

        # HALF_OPEN -> CLOSED
        breaker.record_success(latency_ms=5.0)
        assert breaker.state == BreakerState.CLOSED

        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 200.0, (
            f"Full cycle took {elapsed_ms:.2f}ms, exceeds 200ms"
        )


class TestLatencyPercentileBenchmarks:
    """Verify P95/P99 latency targets on bulk operations."""

    @pytest.mark.asyncio
    async def test_p95_under_15ms_p99_under_25ms(self) -> None:
        """100 proxy overhead measurements: P95 < 15ms, P99 < 25ms."""
        pool = PoolManager()
        breaker = CircuitBreaker(service="stripe")
        tracker = LatencyTracker()

        for _ in range(100):
            perf_start = time.perf_counter()

            breaker.allow_request()
            client = await pool.acquire("stripe")
            await pool.release("stripe")
            perf_end = time.perf_counter()
            latency_ms = (perf_end - perf_start) * 1000

            tracker.record(
                service="stripe",
                agent_id="default",
                latency_ms=latency_ms,
                perf_start=perf_start,
                perf_end=perf_end,
            )
            breaker.record_success(latency_ms=latency_ms)

        snapshot = tracker.get_snapshot("stripe")
        assert snapshot.count == 100

        assert snapshot.p95_ms < 15.0, (
            f"P95 latency {snapshot.p95_ms:.2f}ms exceeds 15ms"
        )
        assert snapshot.p99_ms < 25.0, (
            f"P99 latency {snapshot.p99_ms:.2f}ms exceeds 25ms"
        )
        await pool.shutdown()
