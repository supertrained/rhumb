"""Free-tier monthly quota enforcement."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional, Tuple

from schemas.agent_identity import AgentIdentityStore, get_agent_identity_store
from services.usage_metering import UsageMeterEngine, get_usage_meter_engine

FREE_TIER_LIMIT = 1000


class FreeTierQuotaManager:
    """Enforce free-tier monthly call quotas."""

    def __init__(
        self,
        usage_meter: Optional[UsageMeterEngine] = None,
        identity_store: Optional[AgentIdentityStore] = None,
    ) -> None:
        self._usage_meter = usage_meter
        self._identity_store = identity_store

    @property
    def usage_meter(self) -> UsageMeterEngine:
        """Get usage meter dependency."""
        if self._usage_meter is None:
            self._usage_meter = get_usage_meter_engine(identity_store=self.identity_store)
        return self._usage_meter

    @property
    def identity_store(self) -> AgentIdentityStore:
        """Get identity store dependency."""
        if self._identity_store is None:
            self._identity_store = get_agent_identity_store()
        return self._identity_store

    async def is_free_tier(self, agent_id: str) -> bool:
        """Return True when agent has no Stripe customer mapping."""
        agent = await self.identity_store.get_agent(agent_id)
        if agent is None:
            return True

        custom_attributes = getattr(agent, "custom_attributes", {})
        stripe_customer_id = None
        if isinstance(custom_attributes, dict):
            stripe_customer_id = custom_attributes.get("stripe_customer_id")

        if not stripe_customer_id:
            stripe_customer_id = getattr(agent, "stripe_customer_id", None)

        return not bool(stripe_customer_id)

    async def check_quota(self, agent_id: str) -> Tuple[bool, int]:
        """Check if an agent can make another free-tier call.

        Returns:
            ``(allowed, remaining)`` where paid agents bypass quota and return
            ``(True, -1)``.
        """
        if not await self.is_free_tier(agent_id):
            return True, -1

        month = datetime.now(tz=UTC).strftime("%Y-%m")
        usage = await self.usage_meter.get_monthly_usage(agent_id, month)
        remaining = max(0, FREE_TIER_LIMIT - usage.total_calls)
        allowed = remaining > 0
        return allowed, remaining


_free_tier_quota_manager: Optional[FreeTierQuotaManager] = None


def get_free_tier_quota_manager(
    usage_meter: Optional[UsageMeterEngine] = None,
    identity_store: Optional[AgentIdentityStore] = None,
) -> FreeTierQuotaManager:
    """Return (or create) the global :class:`FreeTierQuotaManager`."""
    global _free_tier_quota_manager
    if _free_tier_quota_manager is None:
        _free_tier_quota_manager = FreeTierQuotaManager(usage_meter, identity_store)
    return _free_tier_quota_manager


def reset_free_tier_quota_manager() -> None:
    """Reset quota manager singleton (for tests)."""
    global _free_tier_quota_manager
    _free_tier_quota_manager = None
