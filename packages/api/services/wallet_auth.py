"""Wallet authentication service — EIP-191 challenge/verify for pseudonymous identity.

Handles:
- Challenge generation with nonce + expiry
- EIP-191 personal_sign signature recovery and verification
- Address normalization and validation
- Per-address + per-IP throttling (in-memory, single-replica safe)

Does NOT handle org/agent creation or billing bootstrap — that is the caller's
responsibility (see ``routes/auth_wallet.py``).
"""

from __future__ import annotations

import logging
import re
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from eth_account import Account
from eth_account.messages import encode_defunct

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

CHALLENGE_TTL_SECONDS = 600  # 10 minutes
CHALLENGE_NONCE_BYTES = 32

# Throttle: max challenges per address per window
THROTTLE_WINDOW_SECONDS = 300  # 5 minutes
THROTTLE_MAX_PER_ADDRESS = 10
THROTTLE_MAX_PER_IP = 30

# Supported chains
SUPPORTED_CHAINS = {"base"}

# EIP-55 mixed-case checksum address pattern
_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


# ── Address Utilities ──────────────────────────────────────────────────────


def normalize_address(address: str) -> str:
    """Normalize an Ethereum address to lowercase without checksum.

    Raises ValueError if the address is not a valid 20-byte hex string.
    """
    address = address.strip()
    if not _ADDRESS_RE.match(address):
        raise ValueError(f"Invalid Ethereum address: {address}")
    return address.lower()


def validate_chain(chain: str) -> str:
    """Validate and normalize a chain identifier.

    Raises ValueError if the chain is not supported.
    """
    chain = chain.strip().lower()
    if chain not in SUPPORTED_CHAINS:
        raise ValueError(f"Unsupported chain: {chain}. Supported: {', '.join(sorted(SUPPORTED_CHAINS))}")
    return chain


def derive_subnet(ip: str) -> str:
    """Derive a /24 subnet from an IP address for throttle bucketing."""
    parts = ip.split(".")
    if len(parts) == 4:
        return ".".join(parts[:3]) + ".0/24"
    return ip


# ── Challenge Message Builder ──────────────────────────────────────────────


def build_challenge_message(
    *,
    chain: str,
    address: str,
    nonce: str,
    purpose: str,
    expires_at: datetime,
) -> str:
    """Build the human-readable message that the wallet signs.

    Format is designed to be:
    - Human-readable in wallet signing prompts
    - Parseable if needed later
    - Replay-resistant via nonce + expiry
    """
    return (
        f"Sign in to Rhumb\n"
        f"Chain: {chain}\n"
        f"Address: {address}\n"
        f"Nonce: {nonce}\n"
        f"Purpose: {purpose}\n"
        f"Expires: {expires_at.strftime('%Y-%m-%dT%H:%M:%SZ')}"
    )


# ── Signature Recovery ─────────────────────────────────────────────────────


def recover_signer(message: str, signature: str) -> str:
    """Recover the signer address from an EIP-191 personal_sign signature.

    Args:
        message: The exact plaintext message that was signed.
        signature: Hex-encoded signature (with or without 0x prefix).

    Returns:
        Checksummed Ethereum address of the signer.

    Raises:
        ValueError: If signature is malformed or recovery fails.
    """
    try:
        sig_hex = signature if signature.startswith("0x") else f"0x{signature}"
        signable = encode_defunct(text=message)
        recovered = Account.recover_message(signable, signature=sig_hex)
        return recovered
    except Exception as exc:
        raise ValueError(f"Signature recovery failed: {exc}") from exc


def verify_challenge_signature(
    message: str,
    signature: str,
    expected_address: str,
) -> dict[str, Any]:
    """Verify that a signed challenge message was signed by the expected address.

    Returns:
        ``{"valid": True, "recovered_signer": "0x..."}`` on success,
        ``{"valid": False, "error": "reason"}`` on failure.
    """
    try:
        recovered = recover_signer(message, signature)
    except ValueError as exc:
        return {"valid": False, "error": str(exc)}

    expected_norm = normalize_address(expected_address)
    recovered_norm = recovered.lower()

    if recovered_norm != expected_norm:
        return {
            "valid": False,
            "error": f"Signer mismatch: expected {expected_norm}, recovered {recovered_norm}",
        }

    return {"valid": True, "recovered_signer": recovered}


# ── In-Memory Throttle ─────────────────────────────────────────────────────


class ChallengeThrottle:
    """In-memory rate limiter for challenge requests.

    Tracks request timestamps per address and per IP within a sliding window.
    Sufficient for single-replica Railway deployment.
    """

    def __init__(
        self,
        *,
        window_seconds: int = THROTTLE_WINDOW_SECONDS,
        max_per_address: int = THROTTLE_MAX_PER_ADDRESS,
        max_per_ip: int = THROTTLE_MAX_PER_IP,
    ) -> None:
        self._window = window_seconds
        self._max_addr = max_per_address
        self._max_ip = max_per_ip
        self._addr_buckets: dict[str, list[float]] = {}
        self._ip_buckets: dict[str, list[float]] = {}

    def _prune(self, bucket: list[float], now: float) -> list[float]:
        cutoff = now - self._window
        return [t for t in bucket if t > cutoff]

    def check_and_record(self, address_normalized: str, request_ip: str) -> bool:
        """Check if a challenge request is allowed and record it.

        Returns True if allowed, False if throttled.
        """
        now = time.time()

        # Check address limit
        addr_bucket = self._prune(
            self._addr_buckets.get(address_normalized, []), now
        )
        if len(addr_bucket) >= self._max_addr:
            return False

        # Check IP limit
        if request_ip:
            ip_bucket = self._prune(self._ip_buckets.get(request_ip, []), now)
            if len(ip_bucket) >= self._max_ip:
                return False
            ip_bucket.append(now)
            self._ip_buckets[request_ip] = ip_bucket

        addr_bucket.append(now)
        self._addr_buckets[address_normalized] = addr_bucket
        return True

    def reset(self) -> None:
        """Clear all throttle state (for testing)."""
        self._addr_buckets.clear()
        self._ip_buckets.clear()


# ── Module-level singleton ─────────────────────────────────────────────────

_throttle: ChallengeThrottle | None = None


def get_challenge_throttle() -> ChallengeThrottle:
    global _throttle
    if _throttle is None:
        _throttle = ChallengeThrottle()
    return _throttle


def reset_challenge_throttle() -> None:
    global _throttle
    _throttle = None
