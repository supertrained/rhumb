"""Circuit breaker for proxy service.

State machine: CLOSED (healthy) -> OPEN (failing) -> HALF_OPEN (testing) -> CLOSED.
Triggers on consecutive failures (5xx) or timeout thresholds.
"""

import enum
import time
from dataclasses import dataclass, field
from typing import Any, Optional


DEFAULT_TIMEOUT_THRESHOLD_MS = 5000.0


class BreakerState(enum.Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class BreakerMetrics:
    """Tracking metrics for a circuit breaker instance."""

    total_calls: int = 0
    total_failures: int = 0
    total_successes: int = 0
    consecutive_failures: int = 0
    times_opened: int = 0
    times_half_opened: int = 0
    times_closed: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    last_state_change: float = 0.0


@dataclass
class CircuitBreaker:
    """Circuit breaker for a single service+agent pair.

    State transitions:
      CLOSED -> OPEN: after failure_threshold consecutive failures or timeout
      OPEN -> HALF_OPEN: after cooldown_seconds have elapsed
      HALF_OPEN -> CLOSED: on first success
      HALF_OPEN -> OPEN: on any failure

    Args:
        service: Provider service name.
        agent_id: Agent identifier.
        failure_threshold: Number of consecutive failures to trigger OPEN.
        timeout_threshold_ms: Response time (ms) above which a call counts as a failure.
        cooldown_seconds: Seconds to wait in OPEN before transitioning to HALF_OPEN.
    """

    service: str
    agent_id: str = "default"
    failure_threshold: int = 5
    timeout_threshold_ms: float = DEFAULT_TIMEOUT_THRESHOLD_MS
    cooldown_seconds: float = 30.0
    _state: BreakerState = field(default=BreakerState.CLOSED, init=False)
    _opened_at: float = field(default=0.0, init=False)
    metrics: BreakerMetrics = field(default_factory=BreakerMetrics)

    @property
    def state(self) -> BreakerState:
        """Current breaker state, with automatic OPEN -> HALF_OPEN transition."""
        if self._state == BreakerState.OPEN:
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self.cooldown_seconds:
                self._transition_to(BreakerState.HALF_OPEN)
        return self._state

    def _transition_to(self, new_state: BreakerState) -> None:
        """Execute a state transition."""
        self._state = new_state
        self.metrics.last_state_change = time.monotonic()
        if new_state == BreakerState.OPEN:
            self._opened_at = time.monotonic()
            self.metrics.times_opened += 1
        elif new_state == BreakerState.HALF_OPEN:
            self.metrics.times_half_opened += 1
        elif new_state == BreakerState.CLOSED:
            self.metrics.times_closed += 1
            self.metrics.consecutive_failures = 0

    def allow_request(self) -> bool:
        """Check if a request should be allowed through.

        Returns:
            True if request is allowed, False if circuit is OPEN.
        """
        current = self.state  # triggers auto OPEN->HALF_OPEN check
        if current == BreakerState.CLOSED:
            return True
        if current == BreakerState.HALF_OPEN:
            return True  # Allow one probe request
        return False  # OPEN

    def record_success(self, latency_ms: float = 0.0) -> None:
        """Record a successful call.

        In HALF_OPEN state, transitions to CLOSED.
        Resets consecutive failure counter.

        Args:
            latency_ms: Response latency in milliseconds.
        """
        self.metrics.total_calls += 1
        self.metrics.total_successes += 1
        self.metrics.last_success_time = time.monotonic()

        # Check if latency exceeds timeout threshold (counts as failure)
        if latency_ms > self.timeout_threshold_ms:
            self._record_timeout_failure()
            return

        self.metrics.consecutive_failures = 0

        current = self.state
        if current == BreakerState.HALF_OPEN:
            self._transition_to(BreakerState.CLOSED)

    def _record_timeout_failure(self) -> None:
        """Handle a call that succeeded but exceeded timeout threshold."""
        self.metrics.consecutive_failures += 1
        self.metrics.last_failure_time = time.monotonic()

        if self.metrics.consecutive_failures >= self.failure_threshold:
            if self._state != BreakerState.OPEN:
                self._transition_to(BreakerState.OPEN)

    def record_failure(self, status_code: Optional[int] = None) -> None:
        """Record a failed call (5xx or exception).

        Increments consecutive failure counter. If threshold is reached,
        transitions to OPEN. In HALF_OPEN, any failure returns to OPEN.

        Args:
            status_code: HTTP status code if available.
        """
        self.metrics.total_calls += 1
        self.metrics.total_failures += 1
        self.metrics.consecutive_failures += 1
        self.metrics.last_failure_time = time.monotonic()

        current = self._state  # Don't trigger auto-transition here
        if current == BreakerState.HALF_OPEN:
            self._transition_to(BreakerState.OPEN)
        elif self.metrics.consecutive_failures >= self.failure_threshold:
            if current != BreakerState.OPEN:
                self._transition_to(BreakerState.OPEN)

    def fail_open_response(self) -> dict[str, Any]:
        """Generate a fail-open response when circuit is OPEN.

        Returns:
            Dict matching ProxyResponse shape with fail_open signal.
        """
        return {
            "status_code": 503,
            "headers": {},
            "body": {
                "error": "circuit_open",
                "reason": f"Provider '{self.service}' is unavailable",
                "fail_open": True,
                "retry_after_seconds": self.cooldown_seconds,
            },
            "latency_ms": 0.0,
            "upstream_latency_ms": 0.0,
            "service": self.service,
            "path": "",
            "timestamp": time.time(),
            "fail_open": True,
        }

    def reset(self) -> None:
        """Reset breaker to CLOSED state with clean metrics."""
        self._state = BreakerState.CLOSED
        self._opened_at = 0.0
        self.metrics = BreakerMetrics()


class BreakerRegistry:
    """Registry of circuit breakers, one per service+agent pair."""

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout_threshold_ms: float = DEFAULT_TIMEOUT_THRESHOLD_MS,
        cooldown_seconds: float = 30.0,
    ) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}
        self._failure_threshold = failure_threshold
        self._timeout_threshold_ms = timeout_threshold_ms
        self._cooldown_seconds = cooldown_seconds

    def _key(self, service: str, agent_id: str) -> str:
        """Generate registry lookup key."""
        return f"{service}:{agent_id}"

    def get(
        self,
        service: str,
        agent_id: str = "default",
        timeout_threshold_ms: Optional[float] = None,
    ) -> CircuitBreaker:
        """Get or create a circuit breaker for a service+agent pair.

        Args:
            service: Provider service name.
            agent_id: Agent identifier.
            timeout_threshold_ms: Optional timeout threshold override applied
                when a breaker is first created for this key.

        Returns:
            CircuitBreaker instance for this pair.
        """
        key = self._key(service, agent_id)
        if key not in self._breakers:
            self._breakers[key] = CircuitBreaker(
                service=service,
                agent_id=agent_id,
                failure_threshold=self._failure_threshold,
                timeout_threshold_ms=(
                    timeout_threshold_ms
                    if timeout_threshold_ms is not None
                    else self._timeout_threshold_ms
                ),
                cooldown_seconds=self._cooldown_seconds,
            )
        return self._breakers[key]

    def get_all_states(self) -> dict[str, str]:
        """Get state of all breakers.

        Returns:
            Dict mapping breaker keys to their current state string.
        """
        return {key: b.state.value for key, b in self._breakers.items()}

    def reset_all(self) -> None:
        """Reset all breakers to CLOSED."""
        for breaker in self._breakers.values():
            breaker.reset()
