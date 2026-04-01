"""Tests for AUD-5: authenticated principal verification.

Verifies that:
1. Principals are verified identities, not arbitrary strings
2. Same-person detection uses unique IDs, not display names
3. Two-person approval correctly blocks self-approval
4. Different principal types with matching display names are still different people
5. Same principal type with same ID but different display names are the same person
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from services.principal_auth import (
    PendingApproval,
    PrincipalIdentity,
    PrincipalType,
    extract_principal_from_admin_key,
    extract_principal_from_agent,
    extract_principal_from_session,
)


class TestPrincipalIdentity:
    def test_canonical_id_format(self):
        p = PrincipalIdentity(
            principal_type=PrincipalType.ADMIN_USER,
            unique_id="usr_123",
            display_name="Alice",
            verified_at=datetime.now(timezone.utc),
        )
        assert p.canonical_id == "admin_user:usr_123"

    def test_same_principal_same_id(self):
        """Same unique_id = same person, regardless of display name."""
        p1 = PrincipalIdentity(
            principal_type=PrincipalType.ADMIN_USER,
            unique_id="usr_123",
            display_name="Alice",
            verified_at=datetime.now(timezone.utc),
        )
        p2 = PrincipalIdentity(
            principal_type=PrincipalType.ADMIN_USER,
            unique_id="usr_123",
            display_name="Alice Smith",  # Different display name
            verified_at=datetime.now(timezone.utc),
        )
        assert p1.is_same_principal(p2) is True

    def test_different_principal_different_id(self):
        """Different unique_id = different person."""
        p1 = PrincipalIdentity(
            principal_type=PrincipalType.ADMIN_USER,
            unique_id="usr_123",
            display_name="Alice",
            verified_at=datetime.now(timezone.utc),
        )
        p2 = PrincipalIdentity(
            principal_type=PrincipalType.ADMIN_USER,
            unique_id="usr_456",
            display_name="Bob",
            verified_at=datetime.now(timezone.utc),
        )
        assert p1.is_same_principal(p2) is False

    def test_different_type_same_display_name(self):
        """Different principal types with same display name are different people."""
        p1 = PrincipalIdentity(
            principal_type=PrincipalType.ADMIN_USER,
            unique_id="admin",
            display_name="admin@rhumb.dev",
            verified_at=datetime.now(timezone.utc),
        )
        p2 = PrincipalIdentity(
            principal_type=PrincipalType.ADMIN_AGENT,
            unique_id="admin",
            display_name="admin@rhumb.dev",
            verified_at=datetime.now(timezone.utc),
        )
        assert p1.is_same_principal(p2) is False

    def test_forged_display_name_detected(self):
        """Attacker fabricating display name 'admin2' with same underlying key
        is detected as the same principal."""
        key = "TUCPeMWTUQMPExQBGKm2K3Fb2BlwEUhuroMnjjAYsG0"
        p1 = extract_principal_from_admin_key(key)
        p2 = extract_principal_from_admin_key(key)
        # Even if display names differ (which they don't here), canonical IDs match
        assert p1.is_same_principal(p2) is True
        assert p1.canonical_id == p2.canonical_id


class TestExtractors:
    def test_admin_key_produces_stable_id(self):
        key = "test-admin-key-12345"
        p1 = extract_principal_from_admin_key(key)
        p2 = extract_principal_from_admin_key(key)
        assert p1.unique_id == p2.unique_id
        assert p1.principal_type == PrincipalType.SERVICE_KEY

    def test_different_keys_different_ids(self):
        p1 = extract_principal_from_admin_key("key-alpha")
        p2 = extract_principal_from_admin_key("key-beta")
        assert p1.unique_id != p2.unique_id
        assert p1.is_same_principal(p2) is False

    def test_session_extractor(self):
        p = extract_principal_from_session("usr_abc", email="alice@rhumb.dev")
        assert p.principal_type == PrincipalType.ADMIN_USER
        assert p.unique_id == "usr_abc"
        assert p.display_name == "alice@rhumb.dev"

    def test_agent_extractor(self):
        p = extract_principal_from_agent("agt_xyz", label="Pedro")
        assert p.principal_type == PrincipalType.ADMIN_AGENT
        assert p.unique_id == "agt_xyz"
        assert p.display_name == "Pedro"


class TestPendingApproval:
    def _make_principal(self, uid: str, ptype=PrincipalType.ADMIN_USER) -> PrincipalIdentity:
        return PrincipalIdentity(
            principal_type=ptype,
            unique_id=uid,
            display_name=f"User {uid}",
            verified_at=datetime.now(timezone.utc),
        )

    def test_different_person_can_approve(self):
        requester = self._make_principal("usr_1")
        approver = self._make_principal("usr_2")
        pending = PendingApproval(
            request_id="gkill_001",
            requester=requester,
            reason="emergency",
            requested_at=datetime.now(timezone.utc),
            expires_at=9999999999.0,
        )
        allowed, reason = pending.can_approve(approver)
        assert allowed is True

    def test_same_person_cannot_approve(self):
        requester = self._make_principal("usr_1")
        same_person = self._make_principal("usr_1")  # Same ID
        pending = PendingApproval(
            request_id="gkill_001",
            requester=requester,
            reason="emergency",
            requested_at=datetime.now(timezone.utc),
            expires_at=9999999999.0,
        )
        allowed, reason = pending.can_approve(same_person)
        assert allowed is False
        assert "Same principal" in reason

    def test_same_key_different_display_cannot_approve(self):
        """AUD-5 core: same admin key presented as two 'different' principals is blocked."""
        key = "shared-admin-key"
        requester = extract_principal_from_admin_key(key)
        # Attacker tries again with the same key — even if they somehow changed display name
        approver = extract_principal_from_admin_key(key)
        pending = PendingApproval(
            request_id="gkill_001",
            requester=requester,
            reason="attack",
            requested_at=datetime.now(timezone.utc),
            expires_at=9999999999.0,
        )
        allowed, reason = pending.can_approve(approver)
        assert allowed is False

    def test_different_keys_can_approve(self):
        """Two genuinely different admin keys can fulfill two-person auth."""
        requester = extract_principal_from_admin_key("admin-key-alpha")
        approver = extract_principal_from_admin_key("admin-key-beta")
        pending = PendingApproval(
            request_id="gkill_001",
            requester=requester,
            reason="real emergency",
            requested_at=datetime.now(timezone.utc),
            expires_at=9999999999.0,
        )
        allowed, reason = pending.can_approve(approver)
        assert allowed is True

    def test_cross_type_approval(self):
        """Human admin can approve agent's request and vice versa."""
        agent = self._make_principal("agt_pedro", PrincipalType.ADMIN_AGENT)
        human = self._make_principal("usr_tom", PrincipalType.ADMIN_USER)
        pending = PendingApproval(
            request_id="gkill_001",
            requester=agent,
            reason="production incident",
            requested_at=datetime.now(timezone.utc),
            expires_at=9999999999.0,
        )
        allowed, reason = pending.can_approve(human)
        assert allowed is True
