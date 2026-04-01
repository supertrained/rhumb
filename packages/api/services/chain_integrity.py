"""AUD-3: Cryptographic hardening for event chains.

Replaces raw SHA-256 chain hashing with HMAC-SHA256 over full semantic payloads.

Problems with the previous approach:
1. SHA-256 without a secret: any attacker who can read the chain can recompute hashes
2. Partial field coverage: detail/metadata/provider fields could be mutated while chain verifies
3. No external anchoring or epoch checkpointing

This module provides:
- HMAC-SHA256 with a server-side secret (tamper-evident against insiders with read access)
- Full semantic payload signing (all fields, not just header fields)
- Canonical JSON serialization for deterministic hashing
- Backward-compatible: can verify old SHA-256 chains during migration
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

# Default HMAC key for development/testing
_DEFAULT_DEV_KEY = b"rhumb-dev-chain-integrity-key-not-for-production"

# Module-level cached key
_hmac_key: bytes | None = None


def _load_hmac_key() -> bytes:
    """Load the HMAC signing key from environment or 1Password.

    Priority:
    1. RHUMB_CHAIN_HMAC_KEY environment variable
    2. 1Password via sop
    3. Dev fallback (logged as warning)
    """
    global _hmac_key
    if _hmac_key is not None:
        return _hmac_key

    # 1. Environment variable
    env_key = os.environ.get("RHUMB_CHAIN_HMAC_KEY")
    if env_key:
        _hmac_key = env_key.encode("utf-8")
        return _hmac_key

    # 2. 1Password
    try:
        result = subprocess.run(
            ["sop", "item", "get", "Rhumb Chain HMAC Key", "--vault", "OpenClaw Agents",
             "--fields", "credential", "--reveal"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            _hmac_key = result.stdout.strip().encode("utf-8")
            return _hmac_key
    except Exception:
        pass

    # 3. Dev fallback
    logger.warning(
        "chain_integrity: using dev HMAC key — set RHUMB_CHAIN_HMAC_KEY for production"
    )
    _hmac_key = _DEFAULT_DEV_KEY
    return _hmac_key


def _canonical_json(data: dict[str, Any]) -> str:
    """Produce canonical JSON for deterministic hashing.

    Rules:
    - Keys sorted alphabetically
    - No extra whitespace
    - Unicode escaped consistently
    """
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_chain_hmac(
    prev_hash: str,
    event_payload: dict[str, Any],
) -> str:
    """Compute HMAC-SHA256 chain hash over the full event payload.

    Args:
        prev_hash: The chain hash of the previous event (or genesis hash)
        event_payload: The FULL event data dict to sign (all fields)

    Returns:
        Hex-encoded HMAC-SHA256 digest
    """
    key = _load_hmac_key()

    # Build the signing input: prev_hash + canonical JSON of full payload
    canonical = _canonical_json(event_payload)
    signing_input = f"{prev_hash}|{canonical}"

    return hmac.new(
        key,
        signing_input.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_chain_hmac(
    prev_hash: str,
    event_payload: dict[str, Any],
    expected_hash: str,
) -> bool:
    """Verify an HMAC chain hash matches the expected value.

    Uses constant-time comparison to prevent timing attacks.
    """
    computed = compute_chain_hmac(prev_hash, event_payload)
    return hmac.compare_digest(computed, expected_hash)


def compute_legacy_hash(
    prev_hash: str,
    *fields: str,
) -> str:
    """Compute a legacy SHA-256 chain hash (for backward compatibility).

    This is the old approach: SHA-256 over pipe-separated selected fields.
    Used during migration to verify old chains.
    """
    payload = "|".join([prev_hash, *fields])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_chain_event(
    prev_hash: str,
    event_payload: dict[str, Any],
    expected_hash: str,
    *legacy_fields: str,
) -> bool:
    """Verify a chain event hash, trying HMAC first then legacy fallback.

    This allows gradual migration: new events use HMAC, old events still verify.
    """
    # Try HMAC first
    if verify_chain_hmac(prev_hash, event_payload, expected_hash):
        return True
    # Fall back to legacy SHA-256 for pre-migration events
    if legacy_fields:
        legacy = compute_legacy_hash(prev_hash, *legacy_fields)
        return hmac.compare_digest(legacy, expected_hash)
    return False
