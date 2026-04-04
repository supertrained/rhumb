"""Tests for AUD-R1-12 / AUD-R4-04: production signing-key health guard."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from services.chain_integrity import (
    _TEST_KEY,
    check_signing_key_health,
    reset_signing_key_cache,
)


@pytest.fixture(autouse=True)
def _reset_keyring():
    """Clear keyring cache before each test."""
    reset_signing_key_cache()
    yield
    reset_signing_key_cache()


class TestSigningKeyHealth:
    """check_signing_key_health must block production start with the test key."""

    def test_healthy_with_real_key(self, monkeypatch):
        monkeypatch.setenv("RHUMB_CHAIN_SIGNING_KEY", "a-real-production-key-abc123")
        monkeypatch.delenv("RHUMB_CHAIN_SIGNING_KEYS", raising=False)
        monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
        assert check_signing_key_health() is True

    def test_healthy_with_keyring(self, monkeypatch):
        monkeypatch.setenv("RHUMB_CHAIN_SIGNING_KEYS", "1:key-alpha,2:key-beta")
        monkeypatch.delenv("RHUMB_CHAIN_SIGNING_KEY", raising=False)
        monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
        assert check_signing_key_health() is True

    def test_warns_in_dev_with_test_key(self, monkeypatch):
        monkeypatch.delenv("RHUMB_CHAIN_SIGNING_KEY", raising=False)
        monkeypatch.delenv("RHUMB_CHAIN_SIGNING_KEYS", raising=False)
        monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
        # Block sop fallback so we actually hit the test key path
        with patch("services.chain_integrity.subprocess.run", side_effect=FileNotFoundError):
            assert check_signing_key_health() is False

    def test_raises_in_production_with_test_key(self, monkeypatch):
        monkeypatch.delenv("RHUMB_CHAIN_SIGNING_KEY", raising=False)
        monkeypatch.delenv("RHUMB_CHAIN_SIGNING_KEYS", raising=False)
        monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
        with patch("services.chain_integrity.subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="test fallback in production"):
                check_signing_key_health()

    def test_no_raise_when_fail_in_production_disabled(self, monkeypatch):
        monkeypatch.delenv("RHUMB_CHAIN_SIGNING_KEY", raising=False)
        monkeypatch.delenv("RHUMB_CHAIN_SIGNING_KEYS", raising=False)
        monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
        with patch("services.chain_integrity.subprocess.run", side_effect=FileNotFoundError):
            assert check_signing_key_health(fail_in_production=False) is False

    def test_healthy_ignores_test_key_fallback_when_real_key_set(self, monkeypatch):
        """Even if the test key exists in the fallback path, a real env key wins."""
        monkeypatch.setenv("RHUMB_CHAIN_SIGNING_KEY", "not-the-test-key")
        monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
        assert check_signing_key_health() is True
