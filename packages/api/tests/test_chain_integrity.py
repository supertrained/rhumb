"""Tests for AUD-3: cryptographic chain integrity hardening.

Verifies HMAC-SHA256 signing, full semantic payload coverage,
canonical JSON determinism, backward-compatible legacy verification,
and tamper detection.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

# Set a deterministic key for tests BEFORE importing the module
os.environ["RHUMB_CHAIN_HMAC_KEY"] = "test-chain-hmac-key-for-unit-tests"

from services.chain_integrity import (
    _canonical_json,
    compute_chain_hmac,
    compute_legacy_hash,
    verify_chain_event,
    verify_chain_hmac,
)

GENESIS = "0" * 64


class TestCanonicalJson:
    def test_sorted_keys(self):
        """Keys are sorted alphabetically."""
        result = _canonical_json({"z": 1, "a": 2, "m": 3})
        assert result == '{"a":2,"m":3,"z":1}'

    def test_no_whitespace(self):
        """No extra whitespace in output."""
        result = _canonical_json({"key": "value", "num": 42})
        assert " " not in result.replace('"key"', "").replace('"value"', "")

    def test_nested_sorted(self):
        """Nested dicts have sorted keys."""
        result = _canonical_json({"b": {"z": 1, "a": 2}})
        assert '"a":2' in result
        assert result.index('"a"') < result.index('"z"')

    def test_deterministic(self):
        """Same data always produces same output."""
        data = {"type": "execution.charged", "amount": 100, "provider": "stripe"}
        assert _canonical_json(data) == _canonical_json(data)

    def test_unicode_escaped(self):
        """Non-ASCII characters are escaped (ensure_ascii=True)."""
        result = _canonical_json({"name": "café"})
        assert "\\u" in result


class TestComputeChainHmac:
    def test_returns_hex_string(self):
        """Hash is a 64-char hex string."""
        h = compute_chain_hmac(GENESIS, {"type": "test"})
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_deterministic(self):
        """Same inputs produce same hash."""
        payload = {"type": "execution.charged", "amount": 100}
        h1 = compute_chain_hmac(GENESIS, payload)
        h2 = compute_chain_hmac(GENESIS, payload)
        assert h1 == h2

    def test_different_prev_hash(self):
        """Different prev_hash produces different result."""
        payload = {"type": "test"}
        h1 = compute_chain_hmac(GENESIS, payload)
        h2 = compute_chain_hmac("a" * 64, payload)
        assert h1 != h2

    def test_different_payload(self):
        """Different payload produces different result."""
        h1 = compute_chain_hmac(GENESIS, {"type": "a"})
        h2 = compute_chain_hmac(GENESIS, {"type": "b"})
        assert h1 != h2

    def test_full_payload_coverage(self):
        """Changing ANY field changes the hash — proving full semantic coverage."""
        base = {
            "event_id": "evt_1",
            "type": "execution.charged",
            "org_id": "org_1",
            "amount": 100,
            "timestamp": "2026-04-01T00:00:00Z",
            "detail": "payment for search.query",
            "provider": "brave-search",
            "receipt_id": "rcpt_abc",
            "metadata": {"layer": 2, "capability": "search.query"},
        }
        base_hash = compute_chain_hmac(GENESIS, base)

        # Mutate each field individually and verify hash changes
        for field in base:
            mutated = dict(base)
            if isinstance(mutated[field], str):
                mutated[field] = mutated[field] + "_tampered"
            elif isinstance(mutated[field], int):
                mutated[field] = mutated[field] + 1
            elif isinstance(mutated[field], dict):
                mutated[field] = {**mutated[field], "tampered": True}
            h = compute_chain_hmac(GENESIS, mutated)
            assert h != base_hash, f"Mutating '{field}' did not change the hash"

    def test_key_order_irrelevant(self):
        """Hash is the same regardless of insertion order (canonical JSON)."""
        h1 = compute_chain_hmac(GENESIS, {"b": 2, "a": 1})
        h2 = compute_chain_hmac(GENESIS, {"a": 1, "b": 2})
        assert h1 == h2


class TestVerifyChainHmac:
    def test_valid_hash_verifies(self):
        payload = {"type": "test", "value": 42}
        h = compute_chain_hmac(GENESIS, payload)
        assert verify_chain_hmac(GENESIS, payload, h) is True

    def test_tampered_payload_fails(self):
        payload = {"type": "test", "value": 42}
        h = compute_chain_hmac(GENESIS, payload)
        payload["value"] = 999  # tamper
        assert verify_chain_hmac(GENESIS, payload, h) is False

    def test_wrong_hash_fails(self):
        payload = {"type": "test"}
        assert verify_chain_hmac(GENESIS, payload, "wrong" * 8) is False


class TestLegacyHash:
    def test_produces_sha256(self):
        h = compute_legacy_hash(GENESIS, "evt_1", "test", "org_1", "100", "2026-01-01")
        assert len(h) == 64

    def test_deterministic(self):
        h1 = compute_legacy_hash(GENESIS, "a", "b")
        h2 = compute_legacy_hash(GENESIS, "a", "b")
        assert h1 == h2


class TestVerifyChainEvent:
    def test_hmac_event_verifies(self):
        """New HMAC events verify correctly."""
        payload = {"type": "new_event", "detail": "important"}
        h = compute_chain_hmac(GENESIS, payload)
        assert verify_chain_event(GENESIS, payload, h) is True

    def test_legacy_event_verifies_via_fallback(self):
        """Old SHA-256 events still verify via legacy fallback."""
        legacy_fields = ("evt_1", "test", "org_1", "100", "2026-01-01")
        h = compute_legacy_hash(GENESIS, *legacy_fields)
        # HMAC will fail, then legacy fallback should succeed
        payload = {"type": "test"}  # irrelevant for legacy
        assert verify_chain_event(GENESIS, payload, h, *legacy_fields) is True

    def test_tampered_event_fails_both(self):
        """Tampered data fails both HMAC and legacy checks."""
        payload = {"type": "test"}
        assert verify_chain_event(GENESIS, payload, "bad" * 16) is False

    def test_tampered_event_fails_legacy_too(self):
        """Tampered legacy fields fail legacy check."""
        h = compute_legacy_hash(GENESIS, "a", "b")
        assert verify_chain_event(GENESIS, {}, h, "a", "TAMPERED") is False


class TestHmacKeyLoading:
    def test_env_key_used(self):
        """RHUMB_CHAIN_HMAC_KEY from env is used."""
        # Already set in module-level env setup
        payload = {"type": "test"}
        h = compute_chain_hmac(GENESIS, payload)
        assert len(h) == 64

    def test_different_key_different_hash(self):
        """Different HMAC keys produce different hashes (key matters)."""
        import services.chain_integrity as ci
        payload = {"type": "test"}

        # Save current key
        original_key = ci._hmac_key

        # Hash with original key
        h1 = compute_chain_hmac(GENESIS, payload)

        # Hash with different key
        ci._hmac_key = b"different-key"
        h2 = compute_chain_hmac(GENESIS, payload)

        # Restore
        ci._hmac_key = original_key

        assert h1 != h2
