"""Tests for kill switch system — per-agent, per-provider, per-recipe, global (WU-42.4)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from services.kill_switches import (
    KillSwitchEntry,
    KillSwitchLevel,
    KillSwitchRegistry,
    KillSwitchState,
    get_kill_switch_registry,
)
from services.principal_auth import extract_principal_from_session


def _principal(user_id: str) -> object:
    return extract_principal_from_session(user_id, email=f"{user_id}@rhumb.dev")


class AsyncInMemoryKillSwitchPersistence:
    def __init__(self) -> None:
        self.switches: dict[str, dict[str, object]] = {}
        self.pending: dict[str, dict[str, object]] = {}

    async def persist_switch_state(self, key: str, entry: KillSwitchEntry) -> bool:
        self.switches[key] = {
            "switch_key": key,
            "switch_id": entry.switch_id,
            "level": entry.level.value,
            "target": entry.target,
            "state": entry.state.value,
            "reason": entry.reason,
            "activated_by": entry.activated_by,
            "activated_at": entry.activated_at.isoformat(),
            "second_approver": entry.second_approver,
            "restoration_phase": entry.restoration_phase,
            "chain_hash": entry.chain_hash,
        }
        return True

    async def load_active_switches(self) -> list[dict[str, object]]:
        return list(self.switches.values())

    async def remove_switch(self, key: str) -> bool:
        self.switches.pop(key, None)
        return True

    async def persist_pending_global(self, pending: object) -> bool:
        requester = pending.requester
        self.pending[pending.request_id] = {
            "request_id": pending.request_id,
            "reason": pending.reason,
            "requester_type": requester.principal_type.value,
            "requester_unique_id": requester.unique_id,
            "requester_display_name": requester.display_name,
            "requester_verified_at": requester.verified_at.isoformat(),
            "requested_at": pending.requested_at.isoformat(),
            "expires_at": pending.expires_at.isoformat(),
        }
        return True

    async def load_pending_globals(self) -> list[dict[str, object]]:
        return list(self.pending.values())

    async def remove_pending_global(self, request_id: str) -> bool:
        self.pending.pop(request_id, None)
        return True


# ── Basic kill switch operations ──────────────────────────────────────


class TestAgentKillSwitch:
    def test_kill_agent_blocks(self):
        reg = KillSwitchRegistry()
        reg.kill_agent("agent_bad", "Suspicious activity", "admin_1")
        blocked, reason = reg.is_blocked(agent_id="agent_bad")
        assert blocked is True
        assert "agent_bad" not in reason or "Agent kill switch" in reason

    def test_other_agents_unaffected(self):
        reg = KillSwitchRegistry()
        reg.kill_agent("agent_bad", "Abuse", "admin_1")
        blocked, _ = reg.is_blocked(agent_id="agent_good")
        assert blocked is False

    def test_lift_agent_unblocks(self):
        reg = KillSwitchRegistry()
        reg.kill_agent("agent_1", "Test", "admin")
        assert reg.is_blocked(agent_id="agent_1")[0] is True
        reg.lift("agent:agent_1", "admin")
        assert reg.is_blocked(agent_id="agent_1")[0] is False


class TestProviderKillSwitch:
    def test_kill_provider_blocks(self):
        reg = KillSwitchRegistry()
        reg.kill_provider("stripe", "Outage detected", "ops_1")
        blocked, reason = reg.is_blocked(provider_slug="stripe")
        assert blocked is True
        assert "Provider kill switch" in reason

    def test_other_providers_unaffected(self):
        reg = KillSwitchRegistry()
        reg.kill_provider("stripe", "Outage", "ops")
        blocked, _ = reg.is_blocked(provider_slug="openai")
        assert blocked is False


class TestRecipeKillSwitch:
    def test_kill_recipe_blocks(self):
        reg = KillSwitchRegistry()
        reg.kill_recipe("recipe_expensive", "Cost runaway", "ops")
        blocked, reason = reg.is_blocked(recipe_id="recipe_expensive")
        assert blocked is True
        assert "Recipe kill switch" in reason

    def test_other_recipes_unaffected(self):
        reg = KillSwitchRegistry()
        reg.kill_recipe("recipe_a", "Bad", "ops")
        blocked, _ = reg.is_blocked(recipe_id="recipe_b")
        assert blocked is False


# ── Global kill switch (two-person auth) ──────────────────────────────


class TestGlobalKillSwitch:
    def test_request_returns_pending(self):
        reg = KillSwitchRegistry()
        result = reg.request_global_kill("Security breach", _principal("tom"))
        assert result["status"] == "pending_approval"
        assert result["requester"] == "admin_user:tom"

    def test_same_person_cannot_approve(self):
        reg = KillSwitchRegistry()
        result = reg.request_global_kill("Breach", _principal("tom"))
        entry = reg.approve_global_kill(result["request_id"], _principal("tom"))
        assert entry is None
        # Global should NOT be active
        blocked, _ = reg.is_blocked()
        assert blocked is False

    def test_second_person_approves(self):
        reg = KillSwitchRegistry()
        result = reg.request_global_kill("Breach", _principal("tom"))
        entry = reg.approve_global_kill(result["request_id"], _principal("pedro"))
        assert entry is not None
        assert entry.level == KillSwitchLevel.GLOBAL
        assert entry.state == KillSwitchState.KILLED
        assert entry.second_approver == "admin_user:pedro"
        # Everything should be blocked
        blocked, reason = reg.is_blocked(agent_id="any")
        assert blocked is True
        assert "Global" in reason

    def test_expired_request_rejected(self):
        reg = KillSwitchRegistry()
        result = reg.request_global_kill("Breach", _principal("tom"))
        # Simulate expiry by modifying the pending entry
        with reg._lock:
            pending = reg._pending_global[result["request_id"]]
            reg._pending_global[result["request_id"]] = type(pending)(
                request_id=pending.request_id,
                reason=pending.reason,
                requester=pending.requester,
                requested_at=pending.requested_at,
                expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            )
        entry = reg.approve_global_kill(result["request_id"], _principal("pedro"))
        assert entry is None

    def test_nonexistent_request_rejected(self):
        reg = KillSwitchRegistry()
        entry = reg.approve_global_kill("fake_id", _principal("pedro"))
        assert entry is None

    def test_global_blocks_all_levels(self):
        reg = KillSwitchRegistry()
        result = reg.request_global_kill("Critical", _principal("tom"))
        reg.approve_global_kill(result["request_id"], _principal("pedro"))

        # All types should be blocked
        assert reg.is_blocked(agent_id="any")[0] is True
        assert reg.is_blocked(provider_slug="stripe")[0] is True
        assert reg.is_blocked(recipe_id="recipe_1")[0] is True


# ── Phased restoration ────────────────────────────────────────────────


class TestPhasedRestoration:
    def test_read_only_phase_still_blocks(self):
        reg = KillSwitchRegistry()
        result = reg.request_global_kill("Incident", _principal("tom"))
        reg.approve_global_kill(result["request_id"], _principal("pedro"))
        reg.begin_restoration("global", "read_only", "tom")

        blocked, reason = reg.is_blocked()
        assert blocked is True
        assert "read-only" in reason

    def test_full_phase_allows(self):
        reg = KillSwitchRegistry()
        result = reg.request_global_kill("Incident", _principal("tom"))
        reg.approve_global_kill(result["request_id"], _principal("pedro"))
        reg.begin_restoration("global", "full", "tom")

        blocked, _ = reg.is_blocked()
        assert blocked is False

    def test_lift_after_restoration(self):
        reg = KillSwitchRegistry()
        result = reg.request_global_kill("Incident", _principal("tom"))
        reg.approve_global_kill(result["request_id"], _principal("pedro"))
        reg.begin_restoration("global", "full", "tom")
        reg.lift("global", "pedro")

        assert reg.get("global") is None
        assert reg.is_blocked()[0] is False


# ── Registry queries ──────────────────────────────────────────────────


class TestRegistryQueries:
    def test_list_active(self):
        reg = KillSwitchRegistry()
        reg.kill_agent("a1", "Test", "admin")
        reg.kill_provider("p1", "Test", "admin")
        active = reg.list_active()
        assert len(active) == 2

    def test_active_count(self):
        reg = KillSwitchRegistry()
        assert reg.active_count == 0
        reg.kill_agent("a1", "Test", "admin")
        assert reg.active_count == 1

    def test_get_specific_switch(self):
        reg = KillSwitchRegistry()
        reg.kill_agent("agent_x", "Abuse", "admin")
        entry = reg.get("agent:agent_x")
        assert entry is not None
        assert entry.target == "agent_x"

    def test_get_nonexistent_returns_none(self):
        reg = KillSwitchRegistry()
        assert reg.get("agent:nonexistent") is None


class TestDurablePersistence:
    def test_pending_global_survives_restart(self):
        persistence = AsyncInMemoryKillSwitchPersistence()
        reg = KillSwitchRegistry(persistence=persistence)

        result = reg.request_global_kill("Security breach", _principal("tom"))
        assert result["request_id"] in persistence.pending

        restored = KillSwitchRegistry(persistence=persistence)
        entry = restored.approve_global_kill(result["request_id"], _principal("pedro"))

        assert entry is not None
        assert entry.level == KillSwitchLevel.GLOBAL
        assert result["request_id"] not in persistence.pending

    def test_active_switch_survives_restart(self):
        persistence = AsyncInMemoryKillSwitchPersistence()
        reg = KillSwitchRegistry(persistence=persistence)

        reg.kill_agent("agent_1", "Abuse", "admin")

        restored = KillSwitchRegistry(persistence=persistence)
        assert restored.is_blocked(agent_id="agent_1")[0] is True

    def test_expired_pending_removed_on_restore(self):
        persistence = AsyncInMemoryKillSwitchPersistence()
        reg = KillSwitchRegistry(persistence=persistence)

        result = reg.request_global_kill("Breach", _principal("tom"))
        persistence.pending[result["request_id"]]["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(seconds=1)
        ).isoformat()

        restored = KillSwitchRegistry(persistence=persistence)
        assert result["request_id"] not in restored._pending_global
        assert result["request_id"] not in persistence.pending


# ── Audit trail ───────────────────────────────────────────────────────


class TestAuditTrail:
    def test_audit_trail_records_operations(self):
        reg = KillSwitchRegistry()
        reg.kill_agent("a1", "Test", "admin")
        trail = reg.audit_trail()
        assert len(trail) >= 1
        assert trail[-1].action == "activate"
        assert trail[-1].principal == "admin"

    def test_audit_chain_verification(self):
        reg = KillSwitchRegistry()
        reg.kill_agent("a1", "Test", "admin_1")
        reg.kill_provider("p1", "Test", "admin_2")
        reg.lift("agent:a1", "admin_1")
        assert reg.verify_audit_chain() is True

    def test_audit_chain_tamper_detection(self):
        reg = KillSwitchRegistry()
        reg.kill_agent("a1", "Test", "admin")
        assert reg.verify_audit_chain() is True

        # Tamper
        with reg._lock:
            original = reg._audit[0]
            from services.kill_switches import KillSwitchAuditEntry
            tampered = KillSwitchAuditEntry(
                entry_id=original.entry_id,
                switch_id=original.switch_id,
                action="fake_action",  # Tampered
                principal=original.principal,
                timestamp=original.timestamp,
                details=original.details,
                chain_hash=original.chain_hash,
                prev_hash=original.prev_hash,
            )
            reg._audit[0] = tampered
        assert reg.verify_audit_chain() is False


# ── Combined scenarios ────────────────────────────────────────────────


class TestCombinedScenarios:
    def test_multiple_kill_levels_block(self):
        reg = KillSwitchRegistry()
        reg.kill_agent("agent_1", "Abuse", "admin")
        reg.kill_recipe("recipe_1", "Cost", "ops")

        # Agent blocked
        assert reg.is_blocked(agent_id="agent_1")[0] is True
        # Recipe blocked
        assert reg.is_blocked(recipe_id="recipe_1")[0] is True
        # Clean agent with blocked recipe
        blocked, _ = reg.is_blocked(agent_id="agent_clean", recipe_id="recipe_1")
        assert blocked is True

    def test_global_overrides_everything(self):
        reg = KillSwitchRegistry()
        result = reg.request_global_kill("Critical", _principal("tom"))
        reg.approve_global_kill(result["request_id"], _principal("pedro"))

        # Even "clean" entities are blocked
        blocked, _ = reg.is_blocked(agent_id="clean", provider_slug="healthy", recipe_id="safe")
        assert blocked is True

    def test_no_kills_means_no_blocks(self):
        reg = KillSwitchRegistry()
        blocked, reason = reg.is_blocked(
            agent_id="a", provider_slug="p", recipe_id="r"
        )
        assert blocked is False
        assert reason == ""


# ── Module singleton ──────────────────────────────────────────────────


class TestModuleSingleton:
    def test_get_registry_returns_instance(self):
        reg = get_kill_switch_registry()
        assert isinstance(reg, KillSwitchRegistry)
        assert get_kill_switch_registry() is reg
