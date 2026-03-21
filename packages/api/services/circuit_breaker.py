"""Circuit breaker used to protect Supabase calls."""

from __future__ import annotations

import enum
import logging
import threading
import time
from typing import Awaitable, Callable, TypeVar


logger = logging.getLogger(__name__)
FALLBACK_MISS = object()
T = TypeVar("T")


class CircuitState(str, enum.Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class ServiceDegradedError(RuntimeError):
    """Raised when a protected service is unavailable and no fallback exists."""

    def __init__(
        self,
        *,
        service_name: str,
        resolution: str,
        error: str = "service_degraded",
        status_code: int = 503,
    ) -> None:
        self.service_name = service_name
        self.status_code = status_code
        self.response_body = {
            "error": error,
            "resolution": resolution,
        }
        super().__init__(f"{service_name} is temporarily unavailable")


class CircuitBreaker:
    """Protect a service with CLOSED / OPEN / HALF_OPEN states."""

    def __init__(
        self,
        *,
        service_name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        success_threshold: int = 2,
        resolution: str = "The service is temporarily unavailable.",
        clock: Callable[[], float] | None = None,
    ) -> None:
        if failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive")
        if recovery_timeout <= 0:
            raise ValueError("recovery_timeout must be positive")
        if success_threshold <= 0:
            raise ValueError("success_threshold must be positive")

        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.resolution = resolution
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._half_open_successes = 0
        self._opened_at = 0.0

    @property
    def state(self) -> CircuitState:
        """Return the current state, promoting OPEN to HALF_OPEN after timeout."""
        with self._lock:
            self._maybe_move_to_half_open_locked()
            return self._state

    def _transition_locked(self, new_state: CircuitState) -> None:
        previous_state = self._state
        if previous_state == new_state:
            return

        self._state = new_state
        if new_state == CircuitState.OPEN:
            self._opened_at = self._clock()
            self._half_open_successes = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._half_open_successes = 0
        elif new_state == CircuitState.CLOSED:
            self._consecutive_failures = 0
            self._half_open_successes = 0
            self._opened_at = 0.0

        logger.warning(
            "circuit breaker transition service=%s from=%s to=%s",
            self.service_name,
            previous_state.value,
            new_state.value,
        )

    def _maybe_move_to_half_open_locked(self) -> None:
        if self._state != CircuitState.OPEN:
            return
        if (self._clock() - self._opened_at) >= self.recovery_timeout:
            self._transition_locked(CircuitState.HALF_OPEN)

    def allow_request(self) -> bool:
        """Return True when the protected call should be attempted."""
        with self._lock:
            self._maybe_move_to_half_open_locked()
            return self._state != CircuitState.OPEN

    def record_success(self) -> None:
        """Record a successful upstream call."""
        with self._lock:
            self._maybe_move_to_half_open_locked()
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_successes += 1
                if self._half_open_successes >= self.success_threshold:
                    self._transition_locked(CircuitState.CLOSED)
                return

            self._consecutive_failures = 0

    def record_failure(self) -> None:
        """Record a failed upstream call."""
        with self._lock:
            self._maybe_move_to_half_open_locked()
            if self._state == CircuitState.HALF_OPEN:
                self._consecutive_failures = self.failure_threshold
                self._transition_locked(CircuitState.OPEN)
                return

            self._consecutive_failures += 1
            if self._consecutive_failures >= self.failure_threshold:
                self._transition_locked(CircuitState.OPEN)

    def _service_degraded_error(self) -> ServiceDegradedError:
        return ServiceDegradedError(
            service_name=self.service_name,
            resolution=self.resolution,
        )

    def fail_fast(self, fallback: Callable[[], T | object] | None = None) -> T:
        """Return a fallback value or raise the degraded error when OPEN."""
        if fallback is not None:
            candidate = fallback()
            if candidate is not FALLBACK_MISS:
                logger.warning(
                    "circuit breaker using fallback service=%s state=%s",
                    self.service_name,
                    self.state.value,
                )
                return candidate
        raise self._service_degraded_error()

    async def call(
        self,
        operation: Callable[[], Awaitable[T]],
        *,
        fallback: Callable[[], T | object] | None = None,
    ) -> T:
        """Execute an async operation behind the breaker."""
        if not self.allow_request():
            return self.fail_fast(fallback)

        try:
            result = await operation()
        except Exception:
            self.record_failure()
            raise

        self.record_success()
        return result

    def reset(self) -> None:
        """Reset state and counters back to CLOSED."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._half_open_successes = 0
            self._opened_at = 0.0
