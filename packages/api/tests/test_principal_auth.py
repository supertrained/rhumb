"""Tests for AUD-5: Authenticated principal verification.

Verifies that:
1. Principals must be registered (no arbitrary strings)
2. Verification returns VerifiedPrincipal with freshness
3. Secret-protected principals require correct secret
4. Two different verified principals are identity-distinct
5. Unknown principal_ids are rejected
"""

from __future__ import annotations

import hashlib
import time

import pytest

from services.principal_auth import (
    PrincipalRegistration,
    PrincipalRegistry,
    VerifiedPrincipal,
)


@pytest.fixture
def registry():
    return PrincipalRegistry(principals=[
        PrincipalRegistration(
            principal_id="pedro",
            name="Pedro",
            role="operator",
        ),
        PrincipalRegistration(
            principal_id="tom",
            name="Tom",
            role="admin",
        ),
        PrincipalRegistration(
            principal_id="secure_admin",
            name="Secure Admin",
            role="security",
            secret_hash=hashlib.sha256(b"correct-secret").hexdigest(),
        ),
    ])


class TestPrincipalRegistry:
    def test_verify_known_principal(self, registry):
        result = registry.verify("pedro")
        assert result is not None
        assert result.principal_id == "pedro"
        assert result.name == "Pedro"
        assert result.role == "operator"

    def test_verify_unknown_principal_returns_none(self, registry):
        result = registry.verify("attacker")
        assert result is None

    def test_verify_returns_verified_principal(self, registry):
        result = registry.verify("pedro")
        assert isinstance(result, VerifiedPrincipal)
        assert result.verification_method == "admin_key"

    def test_two_principals_are_distinct(self, registry):
        pedro = registry.verify("pedro")
        tom = registry.verify("tom")
        assert pedro is not None and tom is not None
        assert pedro.principal_id != tom.principal_id

    def test_count(self, registry):
        assert registry.count == 3

    def test_list_ids(self, registry):
        ids = registry.list_ids()
        assert "pedro" in ids
        assert "tom" in ids
        assert "secure_admin" in ids


class TestSecretProtectedPrincipal:
    def test_correct_secret_passes(self, registry):
        result = registry.verify("secure_admin", principal_secret="correct-secret")
        assert result is not None
        assert result.principal_id == "secure_admin"

    def test_wrong_secret_fails(self, registry):
        result = registry.verify("secure_admin", principal_secret="wrong-secret")
        assert result is None

    def test_missing_secret_fails(self, registry):
        result = registry.verify("secure_admin")
        assert result is None

    def test_non_secret_principal_ignores_secret(self, registry):
        """Principals without secret_hash don't need a secret."""
        result = registry.verify("pedro", principal_secret="anything")
        assert result is not None


class TestVerifiedPrincipalFreshness:
    def test_fresh_principal(self, registry):
        vp = registry.verify("pedro")
        assert vp is not None
        assert vp.is_fresh(max_age_seconds=10.0) is True

    def test_stale_principal(self):
        vp = VerifiedPrincipal(
            principal_id="old",
            name="Old",
            role="admin",
            verified_at=time.monotonic() - 600,  # 10 minutes ago
            verification_method="admin_key",
        )
        assert vp.is_fresh(max_age_seconds=300.0) is False


class TestTwoPersonAuthScenario:
    """End-to-end: verify that two verified principals are identity-distinct."""

    def test_same_person_different_calls(self, registry):
        """Same principal_id → same identity (would be caught by kill switch)."""
        p1 = registry.verify("pedro")
        p2 = registry.verify("pedro")
        assert p1 is not None and p2 is not None
        assert p1.principal_id == p2.principal_id  # Same person

    def test_different_people(self, registry):
        """Different principal_ids → different identities (valid two-person auth)."""
        pedro = registry.verify("pedro")
        tom = registry.verify("tom")
        assert pedro is not None and tom is not None
        assert pedro.principal_id != tom.principal_id  # Different people

    def test_attacker_cannot_supply_arbitrary_string(self, registry):
        """Unregistered principal_id is rejected — no arbitrary string identity."""
        result = registry.verify("admin1_fake")
        assert result is None

    def test_attacker_cannot_impersonate(self, registry):
        """Wrong secret for a secret-protected principal is rejected."""
        result = registry.verify("secure_admin", principal_secret="guessed")
        assert result is None


class TestDefaultRegistry:
    def test_default_operator_when_no_env(self):
        """Without RHUMB_ADMIN_PRINCIPALS, a default operator is created."""
        reg = PrincipalRegistry(principals=None)
        # Falls back to env loading; in test env, uses default operator
        assert reg.count >= 1
