"""Kill switch system — per-agent, per-provider, per-recipe, and global (WU-42.4).

Four levels per Resolve spec §4.7:
  L1: Per-agent kill switch (abuse/compromise)
  L2: Per-provider circuit breaker (existing proxy_breaker.py, integrated here)
  L3: Per-recipe kill switch (cost runaway/harmful output)
  L4: Global kill switch (security breach — requires two-person auth)

Recovery:
  - Per-provider: automated via probe/half-open (existing breaker)
  - Per-agent/recipe: manual lift via admin API
  - Global: requires incident post-mortem → phased restoration → two-person sign-off

Two-person auth for global:
  - Two distinct authorized principals must approve within a time window.
  - Single-person kill switch is itself a risk vector (spec D10).
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ── Kill Switch Types ─────────────────────────────────────────────────


class KillSwitchLevel(str, Enum):
    AGENT = "L1_agent"
    PROVIDER = "L2_provider"
    RECIPE = "L3_recipe"
    GLOBAL = "L4_global"


class KillSwitchState(str, Enum):
    ACTIVE = "active"  # Normal operation
    KILLED = "killed"  # Switch is engaged — block all traffic
    RESTORING = "restoring"  # In phased restoration


@dataclass(frozen=True, slots=True)
class KillSwitchEntry:
    """An active kill switch."""

    switch_id: str
    level: KillSwitchLevel
    target: str  # agent_id, provider_slug, recipe_id, or "global"
    state: KillSwitchState
    reason: str
    activated_by: str  # principal who activated
    activated_at: datetime
    second_approver: str | None = None  # For L4 global
    restoration_phase: str | None = None  # "read_only" | "non_financial" | "full"
    chain_hash: str = ""


@dataclass(frozen=True, slots=True)
class KillSwitchAuditEntry:
    """Immutable audit record for kill switch operations."""

    entry_id: str
    switch_id: str
    action: str  # "activate" | "approve" | "restore_phase" | "lift"
    principal: str
    timestamp: datetime
    details: str
    chain_hash: str
    prev_hash: str


# ── Kill Switch Registry ──────────────────────────────────────────────


class KillSwitchRegistry:
    """Central registry for all kill switches.

    Thread-safe. Enforces two-person auth for global kill switch.
    Maintains chain-hashed audit trail.
    """

    GENESIS_HASH = "0" * 64
    GLOBAL_APPROVAL_WINDOW_SECONDS = 900  # 15 minutes

    def __init__(self) -> None:
        self._switches: dict[str, KillSwitchEntry] = {}
        self._audit: list[KillSwitchAuditEntry] = []
        self._pending_global: dict[str, _PendingGlobalKill] = {}
        self._lock = threading.RLock()
        self._prev_hash = self.GENESIS_HASH
        self._entry_counter = 0

    # ── Check methods (hot path — must be fast) ───────────────────

    def is_blocked(
        self,
        *,
        agent_id: str | None = None,
        provider_slug: str | None = None,
        recipe_id: str | None = None,
    ) -> tuple[bool, str]:
        """Check if any kill switch blocks this execution.

        Returns (blocked, reason). Hot path — O(1) lookups.
        """
        with self._lock:
            # L4: Global kill
            global_switch = self._switches.get("global")
            if global_switch and global_switch.state == KillSwitchState.KILLED:
                return True, f"Global kill switch active: {global_switch.reason}"

            # Check restoration phase
            if global_switch and global_switch.state == KillSwitchState.RESTORING:
                phase = global_switch.restoration_phase
                if phase == "read_only":
                    return True, "Global restoration in progress: read-only mode"
                # "non_financial" and "full" allow execution

            # L1: Per-agent
            if agent_id:
                agent_key = f"agent:{agent_id}"
                agent_switch = self._switches.get(agent_key)
                if agent_switch and agent_switch.state == KillSwitchState.KILLED:
                    return True, f"Agent kill switch active: {agent_switch.reason}"

            # L2: Per-provider (checking conceptually — actual circuit breaker
            # is in proxy_breaker.py, this is an administrative override)
            if provider_slug:
                provider_key = f"provider:{provider_slug}"
                provider_switch = self._switches.get(provider_key)
                if provider_switch and provider_switch.state == KillSwitchState.KILLED:
                    return True, f"Provider kill switch active: {provider_switch.reason}"

            # L3: Per-recipe
            if recipe_id:
                recipe_key = f"recipe:{recipe_id}"
                recipe_switch = self._switches.get(recipe_key)
                if recipe_switch and recipe_switch.state == KillSwitchState.KILLED:
                    return True, f"Recipe kill switch active: {recipe_switch.reason}"

        return False, ""

    # ── Activation methods ────────────────────────────────────────

    def kill_agent(self, agent_id: str, reason: str, principal: str) -> KillSwitchEntry:
        """Activate L1 per-agent kill switch. Single-person auth."""
        return self._activate(
            level=KillSwitchLevel.AGENT,
            target=agent_id,
            key=f"agent:{agent_id}",
            reason=reason,
            principal=principal,
        )

    def kill_provider(self, provider_slug: str, reason: str, principal: str) -> KillSwitchEntry:
        """Activate L2 per-provider administrative kill switch."""
        return self._activate(
            level=KillSwitchLevel.PROVIDER,
            target=provider_slug,
            key=f"provider:{provider_slug}",
            reason=reason,
            principal=principal,
        )

    def kill_recipe(self, recipe_id: str, reason: str, principal: str) -> KillSwitchEntry:
        """Activate L3 per-recipe kill switch."""
        return self._activate(
            level=KillSwitchLevel.RECIPE,
            target=recipe_id,
            key=f"recipe:{recipe_id}",
            reason=reason,
            principal=principal,
        )

    def request_global_kill(self, reason: str, principal: str) -> dict[str, Any]:
        """Request L4 global kill switch. Requires second approver.

        Returns a pending approval object. The switch is NOT active until
        a second principal approves within the time window.
        """
        with self._lock:
            request_id = f"gkill_{self._entry_counter + 1:08d}"
            self._pending_global[request_id] = _PendingGlobalKill(
                request_id=request_id,
                reason=reason,
                requester=principal,
                requested_at=time.monotonic(),
                expires_at=time.monotonic() + self.GLOBAL_APPROVAL_WINDOW_SECONDS,
            )
            self._append_audit(
                switch_id=request_id,
                action="request_global_kill",
                principal=principal,
                details=f"Global kill requested: {reason}",
            )

        logger.critical(
            "GLOBAL_KILL_REQUESTED requester=%s reason=%s request_id=%s",
            principal, reason, request_id,
        )

        return {
            "request_id": request_id,
            "status": "pending_approval",
            "requester": principal,
            "reason": reason,
            "expires_in_seconds": self.GLOBAL_APPROVAL_WINDOW_SECONDS,
            "message": "A second authorized principal must approve this request.",
        }

    def approve_global_kill(self, request_id: str, approver: str) -> KillSwitchEntry | None:
        """Approve a pending global kill switch request.

        The approver MUST be different from the requester.
        Returns the activated KillSwitchEntry, or None if invalid.
        """
        with self._lock:
            pending = self._pending_global.get(request_id)
            if pending is None:
                logger.warning("global_kill_approve_failed: request %s not found", request_id)
                return None

            # Expired?
            if time.monotonic() > pending.expires_at:
                self._pending_global.pop(request_id, None)
                logger.warning("global_kill_approve_failed: request %s expired", request_id)
                return None

            # Same person?
            if approver == pending.requester:
                logger.warning(
                    "global_kill_approve_failed: %s cannot approve their own request",
                    approver,
                )
                return None

            # Approved — activate
            self._pending_global.pop(request_id, None)
            entry = self._activate(
                level=KillSwitchLevel.GLOBAL,
                target="global",
                key="global",
                reason=pending.reason,
                principal=pending.requester,
                second_approver=approver,
            )
            self._append_audit(
                switch_id=entry.switch_id,
                action="approve_global_kill",
                principal=approver,
                details=f"Global kill approved by {approver} (requested by {pending.requester})",
            )

        logger.critical(
            "GLOBAL_KILL_ACTIVATED requester=%s approver=%s switch_id=%s",
            pending.requester, approver, entry.switch_id,
        )

        return entry

    # ── Restoration methods ───────────────────────────────────────

    def begin_restoration(
        self,
        key: str,
        phase: str,
        principal: str,
    ) -> KillSwitchEntry | None:
        """Begin phased restoration for a kill switch.

        Global restoration phases: read_only → non_financial → full
        """
        with self._lock:
            existing = self._switches.get(key)
            if existing is None:
                return None

            restored = KillSwitchEntry(
                switch_id=existing.switch_id,
                level=existing.level,
                target=existing.target,
                state=KillSwitchState.RESTORING,
                reason=existing.reason,
                activated_by=existing.activated_by,
                activated_at=existing.activated_at,
                second_approver=existing.second_approver,
                restoration_phase=phase,
                chain_hash=existing.chain_hash,
            )
            self._switches[key] = restored
            self._append_audit(
                switch_id=existing.switch_id,
                action="restore_phase",
                principal=principal,
                details=f"Restoration phase: {phase}",
            )
            return restored

    def lift(self, key: str, principal: str) -> bool:
        """Lift (deactivate) a kill switch. Returns True if found and removed."""
        with self._lock:
            existing = self._switches.pop(key, None)
            if existing is None:
                return False
            self._append_audit(
                switch_id=existing.switch_id,
                action="lift",
                principal=principal,
                details=f"Kill switch lifted for {key}",
            )
        logger.info("kill_switch_lifted key=%s principal=%s", key, principal)
        return True

    # ── Query methods ─────────────────────────────────────────────

    def list_active(self) -> list[KillSwitchEntry]:
        """Return all active kill switches."""
        with self._lock:
            return [
                entry for entry in self._switches.values()
                if entry.state in (KillSwitchState.KILLED, KillSwitchState.RESTORING)
            ]

    def get(self, key: str) -> KillSwitchEntry | None:
        """Get a specific kill switch by key."""
        with self._lock:
            return self._switches.get(key)

    def audit_trail(self, limit: int = 50) -> list[KillSwitchAuditEntry]:
        """Return recent audit trail entries."""
        with self._lock:
            return self._audit[-limit:]

    def verify_audit_chain(self) -> bool:
        """Verify integrity of the audit chain."""
        with self._lock:
            prev_hash = self.GENESIS_HASH
            for entry in self._audit:
                expected = self._compute_hash(
                    prev_hash, entry.entry_id, entry.action,
                    entry.principal, entry.timestamp.isoformat(),
                )
                if entry.chain_hash != expected or entry.prev_hash != prev_hash:
                    return False
                prev_hash = entry.chain_hash
            return True

    @property
    def active_count(self) -> int:
        with self._lock:
            return sum(
                1 for e in self._switches.values()
                if e.state in (KillSwitchState.KILLED, KillSwitchState.RESTORING)
            )

    # ── Internal ──────────────────────────────────────────────────

    def _activate(
        self,
        level: KillSwitchLevel,
        target: str,
        key: str,
        reason: str,
        principal: str,
        second_approver: str | None = None,
    ) -> KillSwitchEntry:
        with self._lock:
            self._entry_counter += 1
            switch_id = f"ks_{self._entry_counter:08d}"
            now = datetime.now(timezone.utc)

            entry = KillSwitchEntry(
                switch_id=switch_id,
                level=level,
                target=target,
                state=KillSwitchState.KILLED,
                reason=reason,
                activated_by=principal,
                activated_at=now,
                second_approver=second_approver,
            )
            self._switches[key] = entry
            self._append_audit(
                switch_id=switch_id,
                action="activate",
                principal=principal,
                details=f"{level.value} kill switch activated for {target}: {reason}",
            )
        logger.warning(
            "kill_switch_activated level=%s target=%s principal=%s reason=%s",
            level.value, target, principal, reason,
        )
        return entry

    def _append_audit(
        self,
        switch_id: str,
        action: str,
        principal: str,
        details: str,
    ) -> KillSwitchAuditEntry:
        """Append a chain-hashed audit entry. Must be called under _lock."""
        self._entry_counter += 1
        entry_id = f"ksaud_{self._entry_counter:08d}"
        now = datetime.now(timezone.utc)
        chain_hash = self._compute_hash(
            self._prev_hash, entry_id, action, principal, now.isoformat(),
        )
        entry = KillSwitchAuditEntry(
            entry_id=entry_id,
            switch_id=switch_id,
            action=action,
            principal=principal,
            timestamp=now,
            details=details,
            chain_hash=chain_hash,
            prev_hash=self._prev_hash,
        )
        self._audit.append(entry)
        self._prev_hash = chain_hash
        return entry

    @staticmethod
    def _compute_hash(
        prev_hash: str,
        entry_id: str,
        action: str,
        principal: str,
        timestamp: str,
    ) -> str:
        payload = f"{prev_hash}|{entry_id}|{action}|{principal}|{timestamp}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class _PendingGlobalKill:
    """Internal: pending global kill request awaiting second approval."""

    request_id: str
    reason: str
    requester: str
    requested_at: float
    expires_at: float


# ── Module singleton ──────────────────────────────────────────────────

_registry: KillSwitchRegistry | None = None


def get_kill_switch_registry() -> KillSwitchRegistry:
    """Return the module-level kill switch registry singleton."""
    global _registry
    if _registry is None:
        _registry = KillSwitchRegistry()
    return _registry
