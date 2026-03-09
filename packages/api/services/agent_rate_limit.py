"""Per-agent per-service rate limiting.

Enforces rate limits using the existing :class:`RateLimiter` from Round 10,
extended with per-agent per-service override logic. When an agent has a
``rate_limit_qpm_override`` on a specific service, that override takes
precedence over the agent's global ``rate_limit_qpm``.

Round 11 (WU 2.2): Integrates agent identity store with rate limiter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from schemas.agent_identity import AgentIdentityStore, get_agent_identity_store
from services.proxy_rate_limit import RateLimiter, RateLimitStatus, get_rate_limiter


@dataclass
class AgentRateLimitResult:
    """Result of a rate-limit check for an agent + service pair."""

    allowed: bool
    agent_id: str
    service: str
    effective_limit_qpm: int
    remaining: int
    error: Optional[str] = None
    retry_after_seconds: Optional[int] = None


class AgentRateLimitChecker:
    """Rate-limit enforcement per agent per service.

    Resolves the effective QPM limit:
      1. If the agent has a per-service override > 0, use that.
      2. Otherwise, use the agent's global ``rate_limit_qpm``.
      3. If the agent doesn't exist or is inactive, deny.

    Delegates actual sliding-window tracking to :class:`RateLimiter`.
    """

    def __init__(
        self,
        identity_store: Optional[AgentIdentityStore] = None,
        rate_limiter: Optional[RateLimiter] = None,
    ) -> None:
        self._identity_store = identity_store
        self._rate_limiter = rate_limiter

    @property
    def identity_store(self) -> AgentIdentityStore:
        if self._identity_store is None:
            self._identity_store = get_agent_identity_store()
        return self._identity_store

    @property
    def rate_limiter(self) -> RateLimiter:
        if self._rate_limiter is None:
            self._rate_limiter = get_rate_limiter()
        return self._rate_limiter

    async def check_rate_limit(
        self,
        agent_id: str,
        service: str,
    ) -> AgentRateLimitResult:
        """Check whether an agent can make a request to a service.

        Steps:
          1. Verify agent exists and is active.
          2. Verify agent has access to the service.
          3. Resolve effective QPM limit (override vs global).
          4. Delegate to :class:`RateLimiter` for sliding window check.

        Returns:
            :class:`AgentRateLimitResult` with allow/deny and metadata.
        """
        # 1. Agent exists?
        agent = await self.identity_store.get_agent(agent_id)
        if agent is None or agent.status != "active":
            return AgentRateLimitResult(
                allowed=False,
                agent_id=agent_id,
                service=service,
                effective_limit_qpm=0,
                remaining=0,
                error="agent_inactive_or_not_found",
            )

        # 2. Service access?
        access = await self.identity_store.get_service_access(agent_id, service)
        if access is None:
            return AgentRateLimitResult(
                allowed=False,
                agent_id=agent_id,
                service=service,
                effective_limit_qpm=0,
                remaining=0,
                error="no_service_access",
            )

        # 3. Resolve effective limit
        effective_qpm = (
            access.rate_limit_qpm_override
            if access.rate_limit_qpm_override > 0
            else agent.rate_limit_qpm
        )

        # 4. Sliding window check
        allowed, status = await self.rate_limiter.check_rate_limit(
            agent_id=agent_id,
            service=service,
            limit_qpm=effective_qpm,
        )

        if not allowed:
            retry_seconds = max(1, int(60 - (status.remaining or 0)))
            return AgentRateLimitResult(
                allowed=False,
                agent_id=agent_id,
                service=service,
                effective_limit_qpm=effective_qpm,
                remaining=0,
                error="rate_limited",
                retry_after_seconds=retry_seconds,
            )

        return AgentRateLimitResult(
            allowed=True,
            agent_id=agent_id,
            service=service,
            effective_limit_qpm=effective_qpm,
            remaining=status.remaining,
        )


# ── Singleton ────────────────────────────────────────────────────────

_checker: Optional[AgentRateLimitChecker] = None


def get_agent_rate_limit_checker(
    identity_store: Optional[AgentIdentityStore] = None,
    rate_limiter: Optional[RateLimiter] = None,
) -> AgentRateLimitChecker:
    """Return (or create) the global :class:`AgentRateLimitChecker`."""
    global _checker
    if _checker is None:
        _checker = AgentRateLimitChecker(identity_store, rate_limiter)
    return _checker


def reset_agent_rate_limit_checker() -> None:
    """Reset the singleton (for tests)."""
    global _checker
    _checker = None
