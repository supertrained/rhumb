"""Tests for proxy circuit breaker."""

import time
from unittest.mock import patch

import pytest

from services.proxy_breaker import (
    DEFAULT_TIMEOUT_THRESHOLD_MS,
    BreakerRegistry,
    BreakerState,
    CircuitBreaker,
)


@pytest.fixture
def breaker() -> CircuitBreaker:
    """Create a fresh circuit breaker."""
    return CircuitBreaker(service="stripe", agent_id="default")


@pytest.fixture
def fast_breaker() -> CircuitBreaker:
    """Create a breaker with short cooldown for testing transitions."""
    return CircuitBreaker(
        service="stripe",
        agent_id="default",
        failure_threshold=3,
        cooldown_seconds=0.1,  # 100ms cooldown for fast tests
    )


@pytest.fixture
def registry() -> BreakerRegistry:
    """Create a fresh breaker registry."""
    return BreakerRegistry()


class TestBreakerStateTransitions:
    """Test circuit breaker state machine."""

    def test_initial_state_is_closed(self, breaker: CircuitBreaker) -> None:
        """Breaker starts in CLOSED state."""
        assert breaker.state == BreakerState.CLOSED

    def test_closed_allows_requests(self, breaker: CircuitBreaker) -> None:
        """CLOSED state allows requests."""
        assert breaker.allow_request() is True

    def test_transitions_to_open_after_failures(
        self, breaker: CircuitBreaker
    ) -> None:
        """CLOSED -> OPEN after failure_threshold consecutive failures."""
        for _ in range(5):
            breaker.record_failure(status_code=500)
        assert breaker.state == BreakerState.OPEN

    def test_open_blocks_requests(self, breaker: CircuitBreaker) -> None:
        """OPEN state blocks requests."""
        for _ in range(5):
            breaker.record_failure(status_code=500)
        assert breaker.allow_request() is False

    def test_open_to_half_open_after_cooldown(
        self, fast_breaker: CircuitBreaker
    ) -> None:
        """OPEN -> HALF_OPEN after cooldown period."""
        # Capture real time before failures
        real_now = time.monotonic()
        with patch("services.proxy_breaker.time.monotonic") as mock_time:
            # First call during record_failure sets _opened_at
            mock_time.return_value = real_now
            for _ in range(3):
                fast_breaker.record_failure(status_code=500)
            assert fast_breaker._state == BreakerState.OPEN

            # Second call during state property check should be past cooldown
            mock_time.return_value = real_now + 1.0  # Past 0.1s cooldown
            assert fast_breaker.state == BreakerState.HALF_OPEN

    def test_half_open_allows_one_request(
        self, fast_breaker: CircuitBreaker
    ) -> None:
        """HALF_OPEN allows requests (probe request)."""
        real_now = time.monotonic()
        with patch("services.proxy_breaker.time.monotonic") as mock_time:
            mock_time.return_value = real_now
            for _ in range(3):
                fast_breaker.record_failure(status_code=500)

            # Advance time past cooldown
            mock_time.return_value = real_now + 1.0
            assert fast_breaker.allow_request() is True

    def test_half_open_to_closed_on_success(
        self, fast_breaker: CircuitBreaker
    ) -> None:
        """HALF_OPEN -> CLOSED on successful probe request."""
        real_now = time.monotonic()
        with patch("services.proxy_breaker.time.monotonic") as mock_time:
            mock_time.return_value = real_now
            for _ in range(3):
                fast_breaker.record_failure(status_code=500)

            # Force transition to HALF_OPEN
            mock_time.return_value = real_now + 1.0
            _ = fast_breaker.state  # Trigger auto-transition

            fast_breaker.record_success(latency_ms=5.0)
            assert fast_breaker.state == BreakerState.CLOSED

    def test_half_open_to_open_on_failure(
        self, fast_breaker: CircuitBreaker
    ) -> None:
        """HALF_OPEN -> OPEN on failed probe request."""
        real_now = time.monotonic()
        with patch("services.proxy_breaker.time.monotonic") as mock_time:
            mock_time.return_value = real_now
            for _ in range(3):
                fast_breaker.record_failure(status_code=500)

            # Force transition to HALF_OPEN
            mock_time.return_value = real_now + 1.0
            _ = fast_breaker.state  # Trigger auto-transition

        fast_breaker.record_failure(status_code=503)
        assert fast_breaker._state == BreakerState.OPEN

    def test_success_resets_consecutive_failures(
        self, breaker: CircuitBreaker
    ) -> None:
        """A success resets the consecutive failure counter."""
        breaker.record_failure(status_code=500)
        breaker.record_failure(status_code=500)
        breaker.record_failure(status_code=500)
        assert breaker.metrics.consecutive_failures == 3

        breaker.record_success(latency_ms=5.0)
        assert breaker.metrics.consecutive_failures == 0

    def test_below_threshold_stays_closed(
        self, breaker: CircuitBreaker
    ) -> None:
        """Fewer than threshold failures keeps breaker CLOSED."""
        for _ in range(4):  # threshold is 5
            breaker.record_failure(status_code=500)
        assert breaker.state == BreakerState.CLOSED


class TestBreakerTimeoutDetection:
    """Test timeout-based failure detection."""

    def test_default_timeout_threshold_is_launch_safe(
        self, breaker: CircuitBreaker
    ) -> None:
        """Default timeout threshold matches the launch-safe value."""
        assert breaker.timeout_threshold_ms == DEFAULT_TIMEOUT_THRESHOLD_MS

    def test_slow_response_counts_as_failure(
        self, breaker: CircuitBreaker
    ) -> None:
        """Response exceeding timeout_threshold_ms counts as failure."""
        breaker.record_success(latency_ms=6000.0)
        assert breaker.metrics.consecutive_failures == 1

    def test_fast_response_does_not_count_as_failure(
        self, breaker: CircuitBreaker
    ) -> None:
        """Response under timeout_threshold_ms doesn't count as failure."""
        breaker.record_success(latency_ms=220.0)
        assert breaker.metrics.consecutive_failures == 0

    def test_timeout_failures_trigger_open(
        self, breaker: CircuitBreaker
    ) -> None:
        """Consecutive timeout failures trigger OPEN state."""
        for _ in range(5):
            breaker.record_success(latency_ms=6000.0)
        assert breaker.state == BreakerState.OPEN


class TestBreakerMetrics:
    """Test breaker metrics tracking."""

    def test_metrics_count_calls(self, breaker: CircuitBreaker) -> None:
        """Total calls are tracked."""
        breaker.record_success(latency_ms=5.0)
        breaker.record_failure(status_code=500)
        assert breaker.metrics.total_calls == 2
        assert breaker.metrics.total_successes == 1
        assert breaker.metrics.total_failures == 1

    def test_metrics_track_state_changes(
        self, fast_breaker: CircuitBreaker
    ) -> None:
        """State change counts are tracked."""
        for _ in range(3):
            fast_breaker.record_failure(status_code=500)
        assert fast_breaker.metrics.times_opened == 1

    def test_reset_clears_state(self, breaker: CircuitBreaker) -> None:
        """Reset restores to initial state."""
        breaker.record_failure(status_code=500)
        breaker.record_failure(status_code=500)
        breaker.reset()
        assert breaker.state == BreakerState.CLOSED
        assert breaker.metrics.total_calls == 0


class TestBreakerFailOpenResponse:
    """Test fail-open response generation."""

    def test_fail_open_response_format(self, breaker: CircuitBreaker) -> None:
        """Fail-open response has correct structure."""
        response = breaker.fail_open_response()
        assert response["status_code"] == 503
        assert response["fail_open"] is True
        assert "Provider" in response["body"]["reason"]
        assert response["body"]["retry_after_seconds"] == 30.0
        assert response["service"] == "stripe"


class TestBreakerRegistry:
    """Test breaker registry behavior."""

    def test_get_creates_new_breaker(self, registry: BreakerRegistry) -> None:
        """Getting a breaker for a new service creates it."""
        breaker = registry.get("stripe")
        assert breaker is not None
        assert breaker.service == "stripe"
        assert breaker.timeout_threshold_ms == DEFAULT_TIMEOUT_THRESHOLD_MS

    def test_get_returns_same_instance(
        self, registry: BreakerRegistry
    ) -> None:
        """Getting same service returns same instance."""
        b1 = registry.get("stripe")
        b2 = registry.get("stripe")
        assert b1 is b2

    def test_get_different_services(
        self, registry: BreakerRegistry
    ) -> None:
        """Different services get separate breakers."""
        b1 = registry.get("stripe")
        b2 = registry.get("slack")
        assert b1 is not b2

    def test_get_applies_timeout_override_on_creation(
        self, registry: BreakerRegistry
    ) -> None:
        """Per-service overrides are applied when a breaker is first created."""
        breaker = registry.get("slack", timeout_threshold_ms=2500.0)
        assert breaker.timeout_threshold_ms == 2500.0

    def test_get_all_states(self, registry: BreakerRegistry) -> None:
        """get_all_states returns current states."""
        registry.get("stripe")
        registry.get("slack")
        states = registry.get_all_states()
        assert states == {"stripe:default": "closed", "slack:default": "closed"}

    def test_reset_all(self, registry: BreakerRegistry) -> None:
        """reset_all resets all breakers."""
        b = registry.get("stripe")
        for _ in range(5):
            b.record_failure(status_code=500)
        assert b.state == BreakerState.OPEN

        registry.reset_all()
        assert b.state == BreakerState.CLOSED
