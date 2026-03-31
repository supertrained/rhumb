"""Resolve v2 policy engine (slice 1).

This slice focuses on provider-selection controls that are immediately useful and
can be enforced truthfully on the current v2 compatibility gateway:

- pin
- provider_preference
- provider_deny
- allow_only
- max_cost_usd (enforced by the route after estimate)

Approval workflows and persistent account-level policy storage are intentionally
left for later slices once an actual approval rail exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from services.error_envelope import RhumbError


AutoSelector = Callable[[list[dict[str, Any]], str], Awaitable[dict[str, Any] | None]]


@dataclass
class PolicyProviderDecision:
    """Resolved provider decision after applying provider controls."""

    selected_provider: str | None
    selected_reason: str | None
    candidate_providers: list[str]
    policy_applied: bool
    policy_summary: dict[str, Any]


class PolicyEngine:
    """Apply v2 execution policy controls to provider selection."""

    @staticmethod
    def has_provider_controls(policy: Any | None) -> bool:
        if policy is None:
            return False
        return any(
            [
                bool(getattr(policy, "pin", None)),
                bool(getattr(policy, "provider_preference", None)),
                bool(getattr(policy, "provider_deny", None)),
                bool(getattr(policy, "allow_only", None)),
            ]
        )

    async def resolve_provider(
        self,
        *,
        mappings: list[dict[str, Any]],
        agent_id: str,
        policy: Any | None,
        auto_selector: AutoSelector,
    ) -> PolicyProviderDecision:
        """Apply provider controls and choose a provider when needed."""
        if not mappings:
            return PolicyProviderDecision(
                selected_provider=None,
                selected_reason=None,
                candidate_providers=[],
                policy_applied=False,
                policy_summary=self._policy_summary(policy, []),
            )

        if policy is None:
            return PolicyProviderDecision(
                selected_provider=None,
                selected_reason=None,
                candidate_providers=[m["service_slug"] for m in mappings if m.get("service_slug")],
                policy_applied=False,
                policy_summary=self._policy_summary(policy, mappings),
            )

        pin = self._normalize_slug(getattr(policy, "pin", None))
        preferences = self._normalize_slug_list(getattr(policy, "provider_preference", []) or [])
        deny = set(self._normalize_slug_list(getattr(policy, "provider_deny", []) or []))
        allow_only = set(self._normalize_slug_list(getattr(policy, "allow_only", []) or []))

        if pin and allow_only and pin not in allow_only:
            raise RhumbError(
                "INVALID_PARAMETERS",
                message=f"Pinned provider '{pin}' is not present in allow_only.",
                detail="Align pin with allow_only, or remove one of the conflicting policy controls.",
            )
        if pin and pin in deny:
            raise RhumbError(
                "INVALID_PARAMETERS",
                message=f"Pinned provider '{pin}' is also denied by policy.",
                detail="Remove the provider from provider_deny, or choose a different pin target.",
            )

        filtered: list[dict[str, Any]] = []
        for mapping in mappings:
            slug = self._normalize_slug(mapping.get("service_slug"))
            if not slug:
                continue
            if allow_only and slug not in allow_only:
                continue
            if slug in deny:
                continue
            filtered.append(mapping)

        if not filtered:
            raise RhumbError(
                "NO_PROVIDER_AVAILABLE",
                message="No providers satisfy the execution policy.",
                detail="Relax allow_only/provider_deny controls or choose a different capability.",
                extra={
                    "policy": {
                        "pin": pin,
                        "provider_preference": preferences,
                        "provider_deny": sorted(deny),
                        "allow_only": sorted(allow_only),
                    }
                },
            )

        candidate_providers = [m["service_slug"] for m in filtered if m.get("service_slug")]

        if pin:
            pinned = next(
                (m for m in filtered if self._normalize_slug(m.get("service_slug")) == pin),
                None,
            )
            if pinned is None:
                raise RhumbError(
                    "NO_PROVIDER_AVAILABLE",
                    message=f"Pinned provider '{pin}' is not available for this capability under the current policy.",
                    detail="Choose a different pin target or relax the provider filters.",
                    extra={
                        "policy": {
                            "pin": pin,
                            "provider_preference": preferences,
                            "provider_deny": sorted(deny),
                            "allow_only": sorted(allow_only),
                        }
                    },
                )
            return PolicyProviderDecision(
                selected_provider=pinned["service_slug"],
                selected_reason="policy_pin",
                candidate_providers=candidate_providers,
                policy_applied=True,
                policy_summary=self._policy_summary(policy, filtered),
            )

        for preferred in preferences:
            preferred_mapping = next(
                (m for m in filtered if self._normalize_slug(m.get("service_slug")) == preferred),
                None,
            )
            if preferred_mapping is not None:
                return PolicyProviderDecision(
                    selected_provider=preferred_mapping["service_slug"],
                    selected_reason="policy_preference_match",
                    candidate_providers=candidate_providers,
                    policy_applied=True,
                    policy_summary=self._policy_summary(policy, filtered),
                )

        if len(filtered) == 1:
            return PolicyProviderDecision(
                selected_provider=filtered[0]["service_slug"],
                selected_reason="policy_single_candidate",
                candidate_providers=candidate_providers,
                policy_applied=True,
                policy_summary=self._policy_summary(policy, filtered),
            )

        auto_selected = await auto_selector(filtered, agent_id)
        if auto_selected is None:
            raise RhumbError(
                "NO_PROVIDER_AVAILABLE",
                message="No providers remain executable after applying policy filters.",
                detail="Retry later or relax the current provider policy constraints.",
                extra={
                    "policy": {
                        "pin": pin,
                        "provider_preference": preferences,
                        "provider_deny": sorted(deny),
                        "allow_only": sorted(allow_only),
                    }
                },
            )

        return PolicyProviderDecision(
            selected_provider=auto_selected["service_slug"],
            selected_reason="routing_with_policy_filters",
            candidate_providers=candidate_providers,
            policy_applied=True,
            policy_summary=self._policy_summary(policy, filtered),
        )

    @staticmethod
    def _normalize_slug(value: Any) -> str | None:
        if value is None:
            return None
        slug = str(value).strip().lower()
        return slug or None

    def _normalize_slug_list(self, values: list[Any]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            slug = self._normalize_slug(value)
            if not slug or slug in seen:
                continue
            normalized.append(slug)
            seen.add(slug)
        return normalized

    def _policy_summary(self, policy: Any | None, mappings: list[dict[str, Any]]) -> dict[str, Any]:
        if policy is None:
            return {
                "controls": [],
                "candidate_providers": [m["service_slug"] for m in mappings if m.get("service_slug")],
            }

        controls: list[str] = []
        if getattr(policy, "pin", None):
            controls.append("pin")
        if getattr(policy, "provider_preference", None):
            controls.append("provider_preference")
        if getattr(policy, "provider_deny", None):
            controls.append("provider_deny")
        if getattr(policy, "allow_only", None):
            controls.append("allow_only")
        if getattr(policy, "max_cost_usd", None) is not None:
            controls.append("max_cost_usd")

        return {
            "controls": controls,
            "pin": self._normalize_slug(getattr(policy, "pin", None)),
            "provider_preference": self._normalize_slug_list(getattr(policy, "provider_preference", []) or []),
            "provider_deny": self._normalize_slug_list(getattr(policy, "provider_deny", []) or []),
            "allow_only": self._normalize_slug_list(getattr(policy, "allow_only", []) or []),
            "max_cost_usd": getattr(policy, "max_cost_usd", None),
            "candidate_providers": [m["service_slug"] for m in mappings if m.get("service_slug")],
        }


_policy_engine: PolicyEngine | None = None


def get_policy_engine() -> PolicyEngine:
    global _policy_engine
    if _policy_engine is None:
        _policy_engine = PolicyEngine()
    return _policy_engine
