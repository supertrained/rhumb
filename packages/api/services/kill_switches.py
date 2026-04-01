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

import asyncio
import concurrent.futures
import inspect
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from services.chain_integrity import build_kill_switch_payload, compute_chain_hmac
from services.principal_auth import PrincipalIdentity, PrincipalType

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

    def __init__(self, persistence: Any | None = None) -> None:
        self._persistence = persistence
        self._switches: dict[str, KillSwitchEntry] = {}
        self._audit: list[KillSwitchAuditEntry] = []
        self._pending_global: dict[str, _PendingGlobalKill] = {}
        self._lock = threading.RLock()
        self._prev_hash = self.GENESIS_HASH
        self._entry_counter = 0
        self._restore_from_persistence()

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
            principal=self._principal_id(principal),
        )

    def kill_provider(self, provider_slug: str, reason: str, principal: str) -> KillSwitchEntry:
        """Activate L2 per-provider administrative kill switch."""
        return self._activate(
            level=KillSwitchLevel.PROVIDER,
            target=provider_slug,
            key=f"provider:{provider_slug}",
            reason=reason,
            principal=self._principal_id(principal),
        )

    def kill_recipe(self, recipe_id: str, reason: str, principal: str) -> KillSwitchEntry:
        """Activate L3 per-recipe kill switch."""
        return self._activate(
            level=KillSwitchLevel.RECIPE,
            target=recipe_id,
            key=f"recipe:{recipe_id}",
            reason=reason,
            principal=self._principal_id(principal),
        )

    def request_global_kill(self, reason: str, principal: PrincipalIdentity) -> dict[str, Any]:
        """Request L4 global kill switch. Requires second approver.

        Returns a pending approval object. The switch is NOT active until
        a second principal approves within the time window.
        """
        requester = self._require_principal(principal)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=self.GLOBAL_APPROVAL_WINDOW_SECONDS)
        with self._lock:
            request_id = f"gkill_{self._entry_counter + 1:08d}"
            pending = _PendingGlobalKill(
                request_id=request_id,
                reason=reason,
                requester=requester,
                requested_at=now,
                expires_at=expires_at,
            )
            self._pending_global[request_id] = pending
            self._append_audit(
                switch_id=request_id,
                action="request_global_kill",
                principal=requester.canonical_id,
                details=f"Global kill requested: {reason}",
            )
            self._entry_counter = max(self._entry_counter, self._parse_id_counter(request_id))
        self._persist_pending_global(pending)

        logger.critical(
            "GLOBAL_KILL_REQUESTED requester=%s reason=%s request_id=%s",
            requester.canonical_id, reason, request_id,
        )

        return {
            "request_id": request_id,
            "status": "pending_approval",
            "requester": requester.canonical_id,
            "reason": reason,
            "expires_in_seconds": self.GLOBAL_APPROVAL_WINDOW_SECONDS,
            "message": "A second authorized principal must approve this request.",
        }

    def approve_global_kill(self, request_id: str, approver: PrincipalIdentity) -> KillSwitchEntry | None:
        """Approve a pending global kill switch request.

        The approver MUST be different from the requester.
        Returns the activated KillSwitchEntry, or None if invalid.
        """
        approver_identity = self._require_principal(approver)
        with self._lock:
            pending = self._pending_global.get(request_id)
            if pending is None:
                logger.warning("global_kill_approve_failed: request %s not found", request_id)
                return None

            # Expired?
            if datetime.now(timezone.utc) > pending.expires_at:
                self._pending_global.pop(request_id, None)
                self._remove_pending_global(request_id)
                logger.warning("global_kill_approve_failed: request %s expired", request_id)
                return None

            # Same person?
            if pending.requester.is_same_principal(approver_identity):
                logger.warning(
                    "global_kill_approve_failed: %s cannot approve their own request",
                    approver_identity.canonical_id,
                )
                return None

            # Approved — activate
            self._pending_global.pop(request_id, None)
            self._remove_pending_global(request_id)
            entry = self._activate(
                level=KillSwitchLevel.GLOBAL,
                target="global",
                key="global",
                reason=pending.reason,
                principal=pending.requester.canonical_id,
                second_approver=approver_identity.canonical_id,
            )
            self._append_audit(
                switch_id=entry.switch_id,
                action="approve_global_kill",
                principal=approver_identity.canonical_id,
                details=(
                    "Global kill approved by "
                    f"{approver_identity.canonical_id} "
                    f"(requested by {pending.requester.canonical_id})"
                ),
            )

        logger.critical(
            "GLOBAL_KILL_ACTIVATED requester=%s approver=%s switch_id=%s",
            pending.requester.canonical_id, approver_identity.canonical_id, entry.switch_id,
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
            self._persist_switch_state(key, restored)
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
            self._remove_switch_state(key)
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
                expected = self._compute_hash(prev_hash, entry)
                if entry.chain_hash != expected or entry.prev_hash != prev_hash:
                    return False
                prev_hash = entry.chain_hash
            return True

    @staticmethod
    def _principal_id(principal: str | PrincipalIdentity) -> str:
        if isinstance(principal, PrincipalIdentity):
            return principal.canonical_id
        return principal

    @staticmethod
    def _require_principal(principal: PrincipalIdentity) -> PrincipalIdentity:
        if not isinstance(principal, PrincipalIdentity):
            raise TypeError("verified PrincipalIdentity required")
        return principal

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
            self._persist_switch_state(key, entry)
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
        entry = KillSwitchAuditEntry(
            entry_id=entry_id,
            switch_id=switch_id,
            action=action,
            principal=principal,
            timestamp=now,
            details=details,
            chain_hash="",
            prev_hash=self._prev_hash,
        )
        chain_hash = self._compute_hash(self._prev_hash, entry)
        entry = KillSwitchAuditEntry(
            entry_id=entry.entry_id,
            switch_id=entry.switch_id,
            action=entry.action,
            principal=entry.principal,
            timestamp=entry.timestamp,
            details=entry.details,
            chain_hash=chain_hash,
            prev_hash=entry.prev_hash,
        )
        self._audit.append(entry)
        self._prev_hash = chain_hash
        return entry

    @staticmethod
    def _compute_hash(
        prev_hash: str,
        entry: KillSwitchAuditEntry,
    ) -> str:
        payload = build_kill_switch_payload(entry)
        return compute_chain_hmac(prev_hash, payload)

    def _restore_from_persistence(self) -> None:
        if self._persistence is None:
            return

        active_rows = self._call_persistence("load_active_switches") or []
        pending_rows = self._call_persistence("load_pending_globals") or []

        with self._lock:
            for row in active_rows:
                try:
                    key = str(row["switch_key"])
                    entry = KillSwitchEntry(
                        switch_id=str(row["switch_id"]),
                        level=KillSwitchLevel(str(row["level"])),
                        target=str(row["target"]),
                        state=KillSwitchState(str(row["state"])),
                        reason=str(row.get("reason") or ""),
                        activated_by=str(row["activated_by"]),
                        activated_at=self._as_datetime(row.get("activated_at")),
                        second_approver=row.get("second_approver"),
                        restoration_phase=row.get("restoration_phase"),
                        chain_hash=str(row.get("chain_hash") or ""),
                    )
                    self._switches[key] = entry
                    self._entry_counter = max(self._entry_counter, self._parse_id_counter(entry.switch_id))
                except Exception:
                    logger.warning("kill_switch_restore_active_failed row=%s", row, exc_info=True)

            for row in pending_rows:
                try:
                    requester = PrincipalIdentity(
                        principal_type=PrincipalType(str(row["requester_type"])),
                        unique_id=str(row["requester_unique_id"]),
                        display_name=str(row.get("requester_display_name") or row["requester_unique_id"]),
                        verified_at=self._as_datetime(row.get("requester_verified_at")),
                    )
                    pending = _PendingGlobalKill(
                        request_id=str(row["request_id"]),
                        reason=str(row.get("reason") or ""),
                        requester=requester,
                        requested_at=self._as_datetime(row.get("requested_at")),
                        expires_at=self._as_datetime(row.get("expires_at")),
                    )
                    if datetime.now(timezone.utc) <= pending.expires_at:
                        self._pending_global[pending.request_id] = pending
                        self._entry_counter = max(self._entry_counter, self._parse_id_counter(pending.request_id))
                    else:
                        self._call_persistence("remove_pending_global", pending.request_id)
                except Exception:
                    logger.warning("kill_switch_restore_pending_failed row=%s", row, exc_info=True)

    def _persist_switch_state(self, key: str, entry: KillSwitchEntry) -> None:
        self._call_persistence("persist_switch_state", key, entry)

    def _remove_switch_state(self, key: str) -> None:
        self._call_persistence("remove_switch", key)

    def _persist_pending_global(self, pending: _PendingGlobalKill) -> None:
        self._call_persistence("persist_pending_global", pending)

    def _remove_pending_global(self, request_id: str) -> None:
        self._call_persistence("remove_pending_global", request_id)

    def _call_persistence(self, method_name: str, *args: Any) -> Any:
        if self._persistence is None:
            return None
        method = getattr(self._persistence, method_name, None)
        if method is None:
            return None
        try:
            result = method(*args)
            if inspect.isawaitable(result):
                return self._run_awaitable(result)
            return result
        except Exception:
            logger.warning("kill_switch_persistence_call_failed method=%s", method_name, exc_info=True)
            return None

    @staticmethod
    def _run_awaitable(awaitable: Any) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(awaitable)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(awaitable)).result()

    @staticmethod
    def _as_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        raise TypeError(f"Unsupported datetime value: {value!r}")

    @staticmethod
    def _parse_id_counter(identifier: str) -> int:
        try:
            return int(identifier.rsplit("_", 1)[-1])
        except (TypeError, ValueError):
            return 0


@dataclass
class _PendingGlobalKill:
    """Internal: pending global kill request awaiting second approval."""

    request_id: str
    reason: str
    requester: PrincipalIdentity
    requested_at: datetime
    expires_at: datetime


# ── Module singleton ──────────────────────────────────────────────────

_registry: KillSwitchRegistry | None = None


async def init_kill_switch_registry(supabase_client: Any | None = None) -> KillSwitchRegistry:
    """Initialize the module-level kill switch registry with durable persistence.

    Falls back to the in-memory registry if Supabase is unavailable so the
    control plane stays readable, but the preferred production path is the
    durable adapter.
    """
    global _registry
    if _registry is not None and getattr(_registry, "_persistence", None) is not None:
        return _registry

    try:
        if supabase_client is None:
            from db.client import get_supabase_client

            supabase_client = await get_supabase_client()

        from services.durable_event_persistence import DurableKillSwitchPersistence

        _registry = KillSwitchRegistry(
            persistence=DurableKillSwitchPersistence(supabase_client)
        )
    except Exception:
        logger.warning(
            "kill_switch_registry_init_failed; using in-memory fallback",
            exc_info=True,
        )
        if _registry is None:
            _registry = KillSwitchRegistry()

    return _registry


def get_kill_switch_registry() -> KillSwitchRegistry:
    """Return the module-level kill switch registry singleton."""
    global _registry
    if _registry is None:
        _registry = KillSwitchRegistry()
    return _registry
