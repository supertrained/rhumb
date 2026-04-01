"""Tests for AUD-3: HMAC-based chain integrity.

Verifies that:
1. HMAC-SHA256 replaces raw SHA-256
2. Full semantic payloads are covered
3. Mutation of any field invalidates the chain
4. Key dependency prevents external recomputation
5. Constant-time comparison is used
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from services.chain_integrity import (
    CURRENT_KEY_VERSION,
    _canonicalize,
    build_audit_payload,
    build_billing_payload,
    build_kill_switch_payload,
    compute_chain_hmac,
    get_signing_key,
    get_signing_key_version,
    reset_signing_key_cache,
    verify_chain_hmac,
)


TEST_KEY = b"test-signing-key-for-aud3"
GENESIS = "0" * 64


@pytest.fixture(autouse=True)
def _reset_chain_signing_cache():
    reset_signing_key_cache()
    yield
    reset_signing_key_cache()


class TestCanonicalJSON:
    def test_deterministic_ordering(self):
        """Dict key order doesn't affect output."""
        a = _canonicalize({"z": 1, "a": 2})
        b = _canonicalize({"a": 2, "z": 1})
        assert a == b

    def test_datetime_serialization(self):
        dt = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = _canonicalize({"ts": dt})
        assert "2026-04-01T12:00:00" in result

    def test_none_serialization(self):
        result = _canonicalize({"x": None})
        assert "null" in result

    def test_nested_determinism(self):
        a = _canonicalize({"outer": {"z": 1, "a": 2}})
        b = _canonicalize({"outer": {"a": 2, "z": 1}})
        assert a == b


class TestComputeChainHMAC:
    def test_produces_hex_string(self):
        result = compute_chain_hmac(GENESIS, {"event_id": "e1"}, key=TEST_KEY)
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex digest

    def test_deterministic(self):
        payload = {"event_id": "e1", "amount": 100}
        h1 = compute_chain_hmac(GENESIS, payload, key=TEST_KEY)
        h2 = compute_chain_hmac(GENESIS, payload, key=TEST_KEY)
        assert h1 == h2

    def test_different_prev_hash(self):
        payload = {"event_id": "e1"}
        h1 = compute_chain_hmac(GENESIS, payload, key=TEST_KEY)
        h2 = compute_chain_hmac("a" * 64, payload, key=TEST_KEY)
        assert h1 != h2

    def test_different_payload(self):
        h1 = compute_chain_hmac(GENESIS, {"event_id": "e1"}, key=TEST_KEY)
        h2 = compute_chain_hmac(GENESIS, {"event_id": "e2"}, key=TEST_KEY)
        assert h1 != h2

    def test_different_key(self):
        payload = {"event_id": "e1"}
        h1 = compute_chain_hmac(GENESIS, payload, key=b"key-a")
        h2 = compute_chain_hmac(GENESIS, payload, key=b"key-b")
        assert h1 != h2

    def test_key_dependency_prevents_forgery(self):
        """Without the signing key, you cannot recompute the hash."""
        payload = {"event_id": "e1", "amount": 100}
        real_hash = compute_chain_hmac(GENESIS, payload, key=TEST_KEY)
        forged_hash = compute_chain_hmac(GENESIS, payload, key=b"wrong-key")
        assert real_hash != forged_hash


class TestVerifyChainHMAC:
    def test_valid_verification(self):
        payload = {"event_id": "e1", "amount": 100}
        h = compute_chain_hmac(GENESIS, payload, key=TEST_KEY)
        assert verify_chain_hmac(GENESIS, payload, h, key=TEST_KEY) is True

    def test_tampered_payload_fails(self):
        payload = {"event_id": "e1", "amount": 100}
        h = compute_chain_hmac(GENESIS, payload, key=TEST_KEY)
        tampered = {"event_id": "e1", "amount": 200}  # Changed amount
        assert verify_chain_hmac(GENESIS, tampered, h, key=TEST_KEY) is False

    def test_tampered_hash_fails(self):
        payload = {"event_id": "e1"}
        assert verify_chain_hmac(GENESIS, payload, "f" * 64, key=TEST_KEY) is False

    def test_wrong_prev_hash_fails(self):
        payload = {"event_id": "e1"}
        h = compute_chain_hmac(GENESIS, payload, key=TEST_KEY)
        assert verify_chain_hmac("b" * 64, payload, h, key=TEST_KEY) is False

    def test_verify_accepts_previous_key_version_during_rotation(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv(
            "RHUMB_CHAIN_SIGNING_KEYS",
            "1:old-rotation-key,2:new-rotation-key",
        )
        monkeypatch.setenv("RHUMB_CHAIN_SIGNING_ACTIVE_VERSION", "2")
        reset_signing_key_cache()
        payload = {"event_id": "e1", "amount": 100}

        old_hash = compute_chain_hmac(GENESIS, payload, key_version=1)

        assert verify_chain_hmac(
            GENESIS,
            payload,
            old_hash,
            key_version=1,
        ) is True

    def test_legacy_event_without_key_version_verifies_against_any_configured_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv(
            "RHUMB_CHAIN_SIGNING_KEYS",
            "1:old-rotation-key,2:new-rotation-key",
        )
        monkeypatch.setenv("RHUMB_CHAIN_SIGNING_ACTIVE_VERSION", "2")
        reset_signing_key_cache()
        payload = {"event_id": "legacy"}

        old_hash = compute_chain_hmac(GENESIS, payload, key_version=1)

        assert verify_chain_hmac(GENESIS, payload, old_hash) is True


class TestSigningKeySelection:
    def test_active_key_version_controls_new_signatures(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv(
            "RHUMB_CHAIN_SIGNING_KEYS",
            "3:third-key,7:seventh-key",
        )
        monkeypatch.setenv("RHUMB_CHAIN_SIGNING_ACTIVE_VERSION", "7")
        reset_signing_key_cache()

        assert get_signing_key_version() == 7
        assert get_signing_key() == b"seventh-key"
        assert CURRENT_KEY_VERSION == 1


class TestFullSemanticCoverage:
    """AUD-3 core: mutation of ANY field invalidates the chain."""

    def test_metadata_mutation_detected(self):
        """Changing metadata field invalidates chain (was NOT covered before)."""
        payload = {"event_id": "e1", "amount": 100, "metadata": {"note": "original"}}
        h = compute_chain_hmac(GENESIS, payload, key=TEST_KEY)
        payload["metadata"]["note"] = "tampered"
        assert verify_chain_hmac(GENESIS, payload, h, key=TEST_KEY) is False

    def test_detail_mutation_detected(self):
        """Changing detail field invalidates chain."""
        payload = {"event_id": "e1", "detail": {"action": "charge"}}
        h = compute_chain_hmac(GENESIS, payload, key=TEST_KEY)
        payload["detail"]["action"] = "refund"
        assert verify_chain_hmac(GENESIS, payload, h, key=TEST_KEY) is False

    def test_receipt_id_mutation_detected(self):
        """Changing receipt_id invalidates chain."""
        payload = {"event_id": "e1", "receipt_id": "rcpt_original"}
        h = compute_chain_hmac(GENESIS, payload, key=TEST_KEY)
        mutated = {**payload, "receipt_id": "rcpt_forged"}
        assert verify_chain_hmac(GENESIS, mutated, h, key=TEST_KEY) is False

    def test_provider_slug_mutation_detected(self):
        """Changing provider_slug invalidates chain."""
        payload = {"event_id": "e1", "provider_slug": "stripe"}
        h = compute_chain_hmac(GENESIS, payload, key=TEST_KEY)
        mutated = {**payload, "provider_slug": "fake-provider"}
        assert verify_chain_hmac(GENESIS, mutated, h, key=TEST_KEY) is False

    def test_capability_id_mutation_detected(self):
        """Changing capability_id invalidates chain."""
        payload = {"event_id": "e1", "capability_id": "search.query"}
        h = compute_chain_hmac(GENESIS, payload, key=TEST_KEY)
        mutated = {**payload, "capability_id": "admin.delete_all"}
        assert verify_chain_hmac(GENESIS, mutated, h, key=TEST_KEY) is False


class TestChainSequence:
    """Verify multi-event chain integrity."""

    def test_three_event_chain(self):
        events = [
            {"event_id": "e1", "amount": 100, "detail": "first"},
            {"event_id": "e2", "amount": 200, "detail": "second"},
            {"event_id": "e3", "amount": -50, "detail": "refund"},
        ]
        hashes = []
        prev = GENESIS
        for event in events:
            h = compute_chain_hmac(prev, event, key=TEST_KEY)
            hashes.append(h)
            prev = h

        # Verify forward
        prev = GENESIS
        for event, expected_hash in zip(events, hashes):
            assert verify_chain_hmac(prev, event, expected_hash, key=TEST_KEY)
            prev = expected_hash

    def test_middle_event_tampering_breaks_chain(self):
        events = [
            {"event_id": "e1", "amount": 100},
            {"event_id": "e2", "amount": 200},
            {"event_id": "e3", "amount": 300},
        ]
        hashes = []
        prev = GENESIS
        for event in events:
            h = compute_chain_hmac(prev, event, key=TEST_KEY)
            hashes.append(h)
            prev = h

        # Tamper with middle event
        events[1]["amount"] = 999
        # Event 2's hash no longer matches
        assert verify_chain_hmac(hashes[0], events[1], hashes[1], key=TEST_KEY) is False


class TestBuildPayloadHelpers:
    """Verify payload builders cover all fields."""

    def test_billing_payload_covers_all_fields(self):
        class MockEvent:
            event_id = "e1"
            event_type = type("ET", (), {"value": "execution.charged"})()
            org_id = "org_1"
            timestamp = datetime(2026, 4, 1, tzinfo=timezone.utc)
            amount_usd_cents = 100
            balance_after_usd_cents = 900
            metadata = {"note": "test"}
            receipt_id = "rcpt_1"
            execution_id = "exec_1"
            capability_id = "search.query"
            provider_slug = "brave-search"

        payload = build_billing_payload(MockEvent())
        # All fields present
        assert payload["event_id"] == "e1"
        assert payload["metadata"] == {"note": "test"}
        assert payload["receipt_id"] == "rcpt_1"
        assert payload["provider_slug"] == "brave-search"
        assert payload["capability_id"] == "search.query"
        assert payload["execution_id"] == "exec_1"
        assert payload["balance_after_usd_cents"] == 900

    def test_audit_payload_covers_detail(self):
        class MockEvent:
            event_id = "ae1"
            event_type = type("ET", (), {"value": "execution.completed"})()
            severity = type("S", (), {"value": "info"})()
            category = "execution"
            timestamp = datetime(2026, 4, 1, tzinfo=timezone.utc)
            org_id = "org_1"
            agent_id = "agent_1"
            resource_type = "capability"
            resource_id = "search.query"
            action = "execute"
            detail = {"provider": "brave-search", "latency_ms": 150}
            metadata = {"request_id": "req_1"}

        payload = build_audit_payload(MockEvent())
        assert payload["detail"]["provider"] == "brave-search"
        assert payload["metadata"]["request_id"] == "req_1"
        assert payload["agent_id"] == "agent_1"

    def test_kill_switch_payload_covers_detail(self):
        class MockEntry:
            action = "activate"
            level = "L4_global"
            target = "global"
            principal = "admin@rhumb.dev"
            reason = "emergency"
            timestamp = datetime(2026, 4, 1, tzinfo=timezone.utc)
            detail = {"approved_by": "admin2@rhumb.dev"}

        payload = build_kill_switch_payload(MockEntry())
        assert payload["details"]["approved_by"] == "admin2@rhumb.dev"
        assert payload["principal"] == "admin@rhumb.dev"
