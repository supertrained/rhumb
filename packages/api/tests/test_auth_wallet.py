"""Tests for wallet authentication (DF-15/DF-16 — WU-W1/WU-W2).

Covers:
- Challenge generation (request-challenge endpoint)
- Signature verification (verify endpoint)
- Wallet identity + org + agent bootstrap on first verify
- Existing wallet identity reuse on repeat verify
- Wrong signer rejection
- Expired challenge rejection
- Throttle enforcement
- Wallet session (/me endpoint)
- API key rotation via wallet session
- Billing bootstrap creates org with zero starter credits
"""

from __future__ import annotations

import asyncio
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient

from app import app as _shared_app
from schemas.agent_identity import AgentIdentityStore, reset_identity_store
from middleware.rate_limit import _buckets as _rate_limit_buckets
from services.wallet_auth import (
    CHALLENGE_TTL_SECONDS,
    build_challenge_message,
    normalize_address,
    recover_signer,
    verify_challenge_signature,
    ChallengeThrottle,
    reset_challenge_throttle,
)


def _reset_all_rate_limits():
    """Clear both the wallet challenge throttle and the app-level rate limiter."""
    reset_challenge_throttle()
    _rate_limit_buckets.clear()


# ── Helpers ──────────────────────────────────────────────────────────

def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# Deterministic test keys (DO NOT use on mainnet!)
TEST_PRIVATE_KEY_1 = "0x" + "ab" * 32
TEST_PRIVATE_KEY_2 = "0x" + "cd" * 32

TEST_ACCOUNT_1 = Account.from_key(TEST_PRIVATE_KEY_1)
TEST_ACCOUNT_2 = Account.from_key(TEST_PRIVATE_KEY_2)

TEST_ADDRESS_1 = TEST_ACCOUNT_1.address
TEST_ADDRESS_2 = TEST_ACCOUNT_2.address


def _sign_message(message: str, private_key: str) -> str:
    """Sign a message using EIP-191 personal_sign and return hex signature."""
    signable = encode_defunct(text=message)
    signed = Account.sign_message(signable, private_key=private_key)
    return signed.signature.hex()


# ── Unit Tests: wallet_auth service ──────────────────────────────────


class TestNormalizeAddress:
    def test_valid_lowercase(self):
        addr = "0xabcdef1234567890abcdef1234567890abcdef12"
        assert normalize_address(addr) == addr

    def test_valid_checksummed(self):
        result = normalize_address(TEST_ADDRESS_1)
        assert result == TEST_ADDRESS_1.lower()

    def test_strips_whitespace(self):
        result = normalize_address(f"  {TEST_ADDRESS_1}  ")
        assert result == TEST_ADDRESS_1.lower()

    def test_rejects_short(self):
        with pytest.raises(ValueError, match="Invalid Ethereum address"):
            normalize_address("0xabc")

    def test_rejects_no_prefix(self):
        with pytest.raises(ValueError, match="Invalid Ethereum address"):
            normalize_address("abcdef1234567890abcdef1234567890abcdef12")

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="Invalid Ethereum address"):
            normalize_address("")


class TestBuildChallengeMessage:
    def test_contains_all_fields(self):
        expires = datetime(2026, 3, 27, 20, 0, 0, tzinfo=UTC)
        msg = build_challenge_message(
            chain="base",
            address=TEST_ADDRESS_1,
            nonce="abc123",
            purpose="access",
            expires_at=expires,
        )
        assert "Sign in to Rhumb" in msg
        assert "Chain: base" in msg
        assert f"Address: {TEST_ADDRESS_1}" in msg
        assert "Nonce: abc123" in msg
        assert "Purpose: access" in msg
        assert "Expires: 2026-03-27T20:00:00Z" in msg


class TestRecoverSigner:
    def test_recovers_correct_address(self):
        message = "Test message for recovery"
        signature = _sign_message(message, TEST_PRIVATE_KEY_1)
        recovered = recover_signer(message, signature)
        assert recovered.lower() == TEST_ADDRESS_1.lower()

    def test_with_0x_prefix(self):
        message = "Test message"
        signature = _sign_message(message, TEST_PRIVATE_KEY_1)
        sig_hex = "0x" + signature if not signature.startswith("0x") else signature
        recovered = recover_signer(message, sig_hex)
        assert recovered.lower() == TEST_ADDRESS_1.lower()

    def test_rejects_garbage_signature(self):
        with pytest.raises(ValueError, match="Signature recovery failed"):
            recover_signer("message", "not-a-real-signature")


class TestVerifyChallengeSignature:
    def test_valid_signature(self):
        message = "Sign in to Rhumb\nChain: base\nNonce: abc"
        signature = _sign_message(message, TEST_PRIVATE_KEY_1)
        result = verify_challenge_signature(message, signature, TEST_ADDRESS_1)
        assert result["valid"] is True
        assert result["recovered_signer"].lower() == TEST_ADDRESS_1.lower()

    def test_wrong_signer(self):
        message = "Sign in to Rhumb\nChain: base\nNonce: abc"
        # Sign with key 2, but expect address 1
        signature = _sign_message(message, TEST_PRIVATE_KEY_2)
        result = verify_challenge_signature(message, signature, TEST_ADDRESS_1)
        assert result["valid"] is False
        assert "mismatch" in result["error"].lower()

    def test_mangled_signature(self):
        message = "Sign in to Rhumb"
        result = verify_challenge_signature(message, "0xdeadbeef", TEST_ADDRESS_1)
        assert result["valid"] is False


class TestChallengeThrottle:
    def test_allows_initial_requests(self):
        throttle = ChallengeThrottle(max_per_address=3, max_per_ip=5, window_seconds=60)
        assert throttle.check_and_record("0xabc", "1.2.3.4") is True
        assert throttle.check_and_record("0xabc", "1.2.3.4") is True
        assert throttle.check_and_record("0xabc", "1.2.3.4") is True

    def test_blocks_after_address_limit(self):
        throttle = ChallengeThrottle(max_per_address=2, max_per_ip=100, window_seconds=60)
        assert throttle.check_and_record("0xabc", "1.2.3.4") is True
        assert throttle.check_and_record("0xabc", "1.2.3.5") is True
        assert throttle.check_and_record("0xabc", "1.2.3.6") is False

    def test_blocks_after_ip_limit(self):
        throttle = ChallengeThrottle(max_per_address=100, max_per_ip=2, window_seconds=60)
        assert throttle.check_and_record("0xaaa", "1.2.3.4") is True
        assert throttle.check_and_record("0xbbb", "1.2.3.4") is True
        assert throttle.check_and_record("0xccc", "1.2.3.4") is False

    def test_different_addresses_independent(self):
        throttle = ChallengeThrottle(max_per_address=1, max_per_ip=100, window_seconds=60)
        assert throttle.check_and_record("0xaaa", "1.2.3.4") is True
        assert throttle.check_and_record("0xbbb", "1.2.3.5") is True

    def test_reset_clears_state(self):
        throttle = ChallengeThrottle(max_per_address=1, max_per_ip=100, window_seconds=60)
        assert throttle.check_and_record("0xabc", "1.2.3.4") is True
        assert throttle.check_and_record("0xabc", "1.2.3.5") is False
        throttle.reset()
        assert throttle.check_and_record("0xabc", "1.2.3.4") is True


# ── Integration Tests: API endpoints ─────────────────────────────────

# Mock Supabase responses for the test flow
_MOCK_CHALLENGE_ID = "c0ffee00-0000-0000-0000-000000000001"
_MOCK_WALLET_ID = "wa11e700-0000-0000-0000-000000000001"


def _mock_supabase_for_challenge() -> dict[str, AsyncMock]:
    """Build mock patches for the challenge creation flow."""
    mock_insert = AsyncMock(return_value={
        "id": _MOCK_CHALLENGE_ID,
        "chain": "base",
        "address": TEST_ADDRESS_1,
        "address_normalized": TEST_ADDRESS_1.lower(),
        "nonce": "test_nonce",
        "message": "test_message",
        "expires_at": (datetime.now(tz=UTC) + timedelta(minutes=10)).isoformat(),
    })
    return {"insert_returning": mock_insert}


def _mock_supabase_for_verify_new_wallet() -> dict[str, Any]:
    """Build mock patches for verifying a brand-new wallet."""
    now = datetime.now(tz=UTC)
    expires = now + timedelta(minutes=10)

    challenge_message = build_challenge_message(
        chain="base",
        address=TEST_ADDRESS_1,
        nonce="verify_nonce",
        purpose="access",
        expires_at=expires,
    )

    mock_fetch_results = {
        # First call: load challenge
        0: [{
            "id": _MOCK_CHALLENGE_ID,
            "chain": "base",
            "address": TEST_ADDRESS_1,
            "address_normalized": TEST_ADDRESS_1.lower(),
            "purpose": "access",
            "nonce": "verify_nonce",
            "message": challenge_message,
            "expires_at": expires.isoformat(),
            "used_at": None,
        }],
        # Second call: check existing wallet_identities (none found)
        1: [],
    }
    _call_counter = {"count": 0}

    async def mock_fetch(path: str) -> Any:
        idx = _call_counter["count"]
        _call_counter["count"] += 1
        return mock_fetch_results.get(idx, [])

    return {
        "fetch": mock_fetch,
        "challenge_message": challenge_message,
    }


class TestRequestChallengeEndpoint:
    """Test POST /v1/auth/wallet/request-challenge."""

    def setup_method(self):
        _reset_all_rate_limits()

    @patch("routes.auth_wallet.supabase_insert_returning")
    def test_returns_challenge(self, mock_insert):
        mock_insert.return_value = {
            "id": _MOCK_CHALLENGE_ID,
            "chain": "base",
            "address": TEST_ADDRESS_1,
        }

        client = TestClient(_shared_app)
        resp = client.post("/v1/auth/wallet/request-challenge", json={
            "chain": "base",
            "address": TEST_ADDRESS_1,
            "purpose": "access",
        })

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["challenge_id"] == _MOCK_CHALLENGE_ID
        assert data["chain"] == "base"
        assert "Sign in to Rhumb" in data["message"]
        assert "expires_at" in data

    @patch("routes.auth_wallet.supabase_insert_returning")
    def test_rejects_non_object_body_before_store(self, mock_insert):
        client = TestClient(_shared_app)
        resp = client.post("/v1/auth/wallet/request-challenge", json=[])
        assert resp.status_code == 400
        assert "Invalid JSON object body" in resp.json()["detail"]
        mock_insert.assert_not_called()

    @patch("routes.auth_wallet.supabase_insert_returning")
    def test_rejects_invalid_chain(self, mock_insert):
        client = TestClient(_shared_app)
        resp = client.post("/v1/auth/wallet/request-challenge", json={
            "chain": "solana",
            "address": TEST_ADDRESS_1,
        })
        assert resp.status_code == 400
        assert "Unsupported chain" in resp.json()["detail"]

    @patch("routes.auth_wallet.supabase_insert_returning")
    def test_rejects_invalid_address(self, mock_insert):
        client = TestClient(_shared_app)
        resp = client.post("/v1/auth/wallet/request-challenge", json={
            "chain": "base",
            "address": "not-an-address",
        })
        assert resp.status_code == 400
        assert "Invalid Ethereum address" in resp.json()["detail"]

    @patch("routes.auth_wallet.supabase_insert_returning")
    def test_rejects_invalid_purpose(self, mock_insert):
        client = TestClient(_shared_app)
        resp = client.post("/v1/auth/wallet/request-challenge", json={
            "chain": "base",
            "address": TEST_ADDRESS_1,
            "purpose": "hack_the_planet",
        })
        assert resp.status_code == 400
        assert "Invalid purpose" in resp.json()["detail"]


class TestVerifyEndpoint:
    """Test POST /v1/auth/wallet/verify."""

    def setup_method(self):
        _reset_all_rate_limits()
        reset_identity_store()

    @patch("routes.auth_wallet.ensure_org_billing_bootstrap", new_callable=AsyncMock)
    @patch("routes.auth_wallet.supabase_insert_returning")
    @patch("routes.auth_wallet.supabase_patch", new_callable=AsyncMock)
    @patch("routes.auth_wallet.supabase_fetch")
    def test_new_wallet_creates_identity_and_org(
        self, mock_fetch, mock_patch, mock_insert_ret, mock_bootstrap
    ):
        """First-time wallet verification should create wallet identity, org, agent."""
        now = datetime.now(tz=UTC)
        expires = now + timedelta(minutes=10)
        challenge_message = build_challenge_message(
            chain="base",
            address=TEST_ADDRESS_1,
            nonce="test_nonce",
            purpose="access",
            expires_at=expires,
        )

        # Sign the challenge with test key 1
        signature = _sign_message(challenge_message, TEST_PRIVATE_KEY_1)

        _call_count = {"n": 0}
        async def _mock_fetch(path: str):
            idx = _call_count["n"]
            _call_count["n"] += 1
            if idx == 0:
                # Load challenge
                return [{
                    "id": _MOCK_CHALLENGE_ID,
                    "chain": "base",
                    "address": TEST_ADDRESS_1,
                    "address_normalized": TEST_ADDRESS_1.lower(),
                    "purpose": "access",
                    "nonce": "test_nonce",
                    "message": challenge_message,
                    "expires_at": expires.isoformat(),
                    "used_at": None,
                }]
            elif idx == 1:
                # Check existing wallet_identities — none
                return []
            return []

        mock_fetch.side_effect = _mock_fetch
        mock_insert_ret.return_value = {
            "id": _MOCK_WALLET_ID,
            "chain": "base",
            "address": TEST_ADDRESS_1,
            "address_normalized": TEST_ADDRESS_1.lower(),
            "org_id": "org_test",
            "default_agent_id": "agent_test",
        }
        mock_bootstrap.return_value = {
            "org_created": True,
            "wallet_created": True,
            "seeded_credits_cents": 0,
        }

        client = TestClient(_shared_app)
        resp = client.post("/v1/auth/wallet/verify", json={
            "challenge_id": _MOCK_CHALLENGE_ID,
            "signature": "0x" + signature if not signature.startswith("0x") else signature,
        })

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["new_wallet_identity"] is True
        assert data["api_key"] is not None
        assert data["api_key"].startswith("rhumb_")
        assert data["wallet"]["chain"] == "base"
        assert "wallet_session_token" in data

        # Verify billing bootstrap was called with zero starter credits
        mock_bootstrap.assert_called_once()
        call_kwargs = mock_bootstrap.call_args
        assert call_kwargs.kwargs.get("starter_credits_cents") == 0

    @patch("routes.auth_wallet.supabase_patch", new_callable=AsyncMock)
    @patch("routes.auth_wallet.supabase_fetch")
    def test_existing_wallet_reuses_identity(self, mock_fetch, mock_patch):
        """Repeat verification should reuse existing wallet identity."""
        now = datetime.now(tz=UTC)
        expires = now + timedelta(minutes=10)
        challenge_message = build_challenge_message(
            chain="base",
            address=TEST_ADDRESS_1,
            nonce="repeat_nonce",
            purpose="access",
            expires_at=expires,
        )
        signature = _sign_message(challenge_message, TEST_PRIVATE_KEY_1)

        existing_org_id = "org_existing_123"
        existing_agent_id = "agent_existing_456"

        # Pre-register the agent so get_agent works
        identity_store = get_agent_identity_store()
        _run(identity_store.register_agent(
            name="Existing Agent",
            organization_id=existing_org_id,
        ))

        _call_count = {"n": 0}
        async def _mock_fetch(path: str):
            idx = _call_count["n"]
            _call_count["n"] += 1
            if idx == 0:
                return [{
                    "id": _MOCK_CHALLENGE_ID,
                    "chain": "base",
                    "address": TEST_ADDRESS_1,
                    "address_normalized": TEST_ADDRESS_1.lower(),
                    "purpose": "access",
                    "nonce": "repeat_nonce",
                    "message": challenge_message,
                    "expires_at": expires.isoformat(),
                    "used_at": None,
                }]
            elif idx == 1:
                return [{
                    "id": _MOCK_WALLET_ID,
                    "chain": "base",
                    "address": TEST_ADDRESS_1,
                    "address_normalized": TEST_ADDRESS_1.lower(),
                    "org_id": existing_org_id,
                    "default_agent_id": existing_agent_id,
                    "status": "active",
                }]
            return []

        mock_fetch.side_effect = _mock_fetch

        client = TestClient(_shared_app)
        resp = client.post("/v1/auth/wallet/verify", json={
            "challenge_id": _MOCK_CHALLENGE_ID,
            "signature": "0x" + signature if not signature.startswith("0x") else signature,
        })

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["new_wallet_identity"] is False
        assert data["api_key"] is None  # not shown again
        assert data["wallet"]["org_id"] == existing_org_id
        assert "wallet_session_token" in data

    @patch("routes.auth_wallet.supabase_patch", new_callable=AsyncMock)
    @patch("routes.auth_wallet.supabase_fetch")
    def test_wrong_signer_rejected(self, mock_fetch, mock_patch):
        """Signing with the wrong key should fail verification."""
        now = datetime.now(tz=UTC)
        expires = now + timedelta(minutes=10)
        challenge_message = build_challenge_message(
            chain="base",
            address=TEST_ADDRESS_1,
            nonce="wrong_signer_nonce",
            purpose="access",
            expires_at=expires,
        )
        # Sign with key 2 but challenge is for address 1
        signature = _sign_message(challenge_message, TEST_PRIVATE_KEY_2)

        async def _mock_fetch(path: str):
            return [{
                "id": _MOCK_CHALLENGE_ID,
                "chain": "base",
                "address": TEST_ADDRESS_1,
                "address_normalized": TEST_ADDRESS_1.lower(),
                "purpose": "access",
                "nonce": "wrong_signer_nonce",
                "message": challenge_message,
                "expires_at": expires.isoformat(),
                "used_at": None,
            }]

        mock_fetch.side_effect = _mock_fetch

        client = TestClient(_shared_app)
        resp = client.post("/v1/auth/wallet/verify", json={
            "challenge_id": _MOCK_CHALLENGE_ID,
            "signature": "0x" + signature if not signature.startswith("0x") else signature,
        })

        assert resp.status_code == 400
        assert "Signature verification failed" in resp.json()["detail"]
        assert "mismatch" in resp.json()["detail"].lower()

    @patch("routes.auth_wallet.supabase_fetch")
    def test_expired_challenge_rejected(self, mock_fetch):
        """An expired challenge should be rejected."""
        expired = datetime.now(tz=UTC) - timedelta(minutes=5)
        challenge_message = build_challenge_message(
            chain="base",
            address=TEST_ADDRESS_1,
            nonce="expired_nonce",
            purpose="access",
            expires_at=expired,
        )
        signature = _sign_message(challenge_message, TEST_PRIVATE_KEY_1)

        async def _mock_fetch(path: str):
            return [{
                "id": _MOCK_CHALLENGE_ID,
                "chain": "base",
                "address": TEST_ADDRESS_1,
                "address_normalized": TEST_ADDRESS_1.lower(),
                "purpose": "access",
                "nonce": "expired_nonce",
                "message": challenge_message,
                "expires_at": expired.isoformat(),
                "used_at": None,
            }]

        mock_fetch.side_effect = _mock_fetch

        client = TestClient(_shared_app)
        resp = client.post("/v1/auth/wallet/verify", json={
            "challenge_id": _MOCK_CHALLENGE_ID,
            "signature": "0x" + signature,
        })

        assert resp.status_code == 400
        assert "expired" in resp.json()["detail"].lower()

    @patch("routes.auth_wallet.supabase_fetch")
    def test_missing_challenge_rejected(self, mock_fetch):
        """A nonexistent challenge ID should be rejected."""
        mock_fetch.return_value = []

        client = TestClient(_shared_app)
        resp = client.post("/v1/auth/wallet/verify", json={
            "challenge_id": "nonexistent-id",
            "signature": "0x" + "ab" * 65,
        })

        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"].lower()

    @patch("routes.auth_wallet.supabase_fetch")
    def test_rejects_non_object_body_before_challenge_read(self, mock_fetch):
        client = TestClient(_shared_app)
        resp = client.post("/v1/auth/wallet/verify", json=[])
        assert resp.status_code == 400
        assert "Invalid JSON object body" in resp.json()["detail"]
        mock_fetch.assert_not_called()

    def test_missing_fields_rejected(self):
        """Missing required fields should return 400."""
        client = TestClient(_shared_app)

        resp = client.post("/v1/auth/wallet/verify", json={
            "challenge_id": "some-id",
        })
        assert resp.status_code == 400

        resp = client.post("/v1/auth/wallet/verify", json={
            "signature": "0xabc",
        })
        assert resp.status_code == 400


class TestWalletMeEndpoint:
    """Test GET /v1/auth/wallet/me."""

    def setup_method(self):
        _reset_all_rate_limits()

    def _make_wallet_token(self, **overrides) -> str:
        """Issue a test wallet session token."""
        from routes.auth_wallet import _issue_wallet_jwt
        claims = {
            "wallet_identity_id": _MOCK_WALLET_ID,
            "wallet_address": TEST_ADDRESS_1.lower(),
            "chain": "base",
            "org_id": "org_test",
            "agent_id": "agent_test",
            "purpose": "wallet_access",
        }
        claims.update(overrides)
        return _issue_wallet_jwt(claims)

    def test_unauthenticated_returns_401(self):
        client = TestClient(_shared_app)
        resp = client.get("/v1/auth/wallet/me")
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self):
        client = TestClient(_shared_app)
        resp = client.get(
            "/v1/auth/wallet/me",
            headers={"Authorization": "Bearer garbage-token"},
        )
        assert resp.status_code == 401

    @patch("routes.auth_wallet.supabase_fetch")
    def test_returns_wallet_profile(self, mock_fetch):
        token = self._make_wallet_token()

        _call_count = {"n": 0}
        async def _mock_fetch(path: str):
            idx = _call_count["n"]
            _call_count["n"] += 1
            if idx == 0:
                # wallet_identities lookup
                return [{
                    "id": _MOCK_WALLET_ID,
                    "status": "active",
                    "linked_user_id": None,
                    "first_seen_at": "2026-03-27T14:00:00+00:00",
                    "last_verified_at": "2026-03-27T14:00:00+00:00",
                }]
            elif idx == 1:
                # org_credits lookup
                return [{"balance_usd_cents": 2500}]
            return []

        mock_fetch.side_effect = _mock_fetch

        client = TestClient(_shared_app)
        resp = client.get(
            "/v1/auth/wallet/me",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["wallet_identity_id"] == _MOCK_WALLET_ID
        assert data["chain"] == "base"
        assert data["balance_usd_cents"] == 2500
        assert data["balance_usd"] == 25.0
        assert data["status"] == "active"


class TestWalletRotateKeyEndpoint:
    """Test POST /v1/auth/wallet/rotate-key."""

    def setup_method(self):
        _reset_all_rate_limits()
        reset_identity_store()

    def _make_wallet_token(self, agent_id: str = "agent_test") -> str:
        from routes.auth_wallet import _issue_wallet_jwt
        return _issue_wallet_jwt({
            "wallet_identity_id": _MOCK_WALLET_ID,
            "wallet_address": TEST_ADDRESS_1.lower(),
            "chain": "base",
            "org_id": "org_test",
            "agent_id": agent_id,
            "purpose": "wallet_access",
        })

    def test_unauthenticated_returns_401(self):
        client = TestClient(_shared_app)
        resp = client.post("/v1/auth/wallet/rotate-key")
        assert resp.status_code == 401

    def test_rotate_returns_new_key(self):
        """Rotating key should return a new rhumb_ prefixed key."""
        # Register an agent in-memory to rotate
        identity_store = get_agent_identity_store()
        agent_id, original_key = _run(identity_store.register_agent(
            name="Rotate Test Agent",
            organization_id="org_test",
        ))

        token = self._make_wallet_token(agent_id=agent_id)

        client = TestClient(_shared_app)
        resp = client.post(
            "/v1/auth/wallet/rotate-key",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["api_key"].startswith("rhumb_")
        assert data["api_key"] != original_key


# ── Billing bootstrap integration ────────────────────────────────────


class TestBillingBootstrapEmailOptional:
    """Verify ensure_org_billing_bootstrap works with email=None."""

    @patch("services.billing_bootstrap._sb_get", new_callable=AsyncMock)
    @patch("services.billing_bootstrap._sb_post", new_callable=AsyncMock)
    def test_bootstrap_with_no_email(self, mock_post, mock_get):
        """Wallet-linked orgs should bootstrap successfully without email."""
        from services.billing_bootstrap import ensure_org_billing_bootstrap

        mock_get.return_value = None  # no existing org/wallet
        mock_post.return_value = {}  # creation succeeds

        result = _run(ensure_org_billing_bootstrap(
            "org_wallet_test",
            name="Wallet 0xAb..ef12",
            starter_credits_cents=0,
            signup_method="wallet_auth",
            credit_policy="wallet_no_trial",
        ))

        assert result["org_created"] is True
        assert result["seeded_credits_cents"] == 0

        # Verify the org payload did NOT include an email key
        create_call = mock_post.call_args_list[0]
        org_payload = create_call.args[1] if len(create_call.args) > 1 else create_call.kwargs.get("payload", {})
        assert "email" not in org_payload

    @patch("services.billing_bootstrap._sb_get", new_callable=AsyncMock)
    @patch("services.billing_bootstrap._sb_post", new_callable=AsyncMock)
    def test_bootstrap_with_email_still_works(self, mock_post, mock_get):
        """Existing callers passing email should still work identically."""
        from services.billing_bootstrap import ensure_org_billing_bootstrap

        mock_get.return_value = None
        mock_post.return_value = {}

        result = _run(ensure_org_billing_bootstrap(
            "org_email_test",
            email="user@example.com",
            name="Test User",
            starter_credits_cents=100,
        ))

        assert result["org_created"] is True

        # Verify the org payload includes email
        create_call = mock_post.call_args_list[0]
        org_payload = create_call.args[1] if len(create_call.args) > 1 else create_call.kwargs.get("payload", {})
        assert org_payload.get("email") == "user@example.com"


# ── Inline import helper for tests ───────────────────────────────────

def get_agent_identity_store():
    """Get the in-memory identity store for tests."""
    from schemas.agent_identity import get_agent_identity_store as _get
    return _get()
