"""AUD-3: Cryptographic chain integrity with HMAC signing.

Shared module for all chain-hashed event streams (billing, audit, kill switches).

Design changes from raw SHA-256:
1. HMAC-SHA256 with a secret key — prevents external hash recomputation
2. Full semantic payload coverage — all fields hashed, not just headers
3. Canonical JSON serialization — deterministic field ordering
4. Key rotation support — chain entries store key_version for future rotation

The signing key MUST be kept secret. It should come from:
- Environment variable RHUMB_CHAIN_SIGNING_KEY (production)
- 1Password via sop (operator fallback)
- Hardcoded test key (tests only)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import subprocess
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# Key version for future rotation support
CURRENT_KEY_VERSION = 1

# Test-only fallback key (never use in production)
_TEST_KEY = b"rhumb-test-chain-signing-key-do-not-use-in-production"


def _get_signing_key() -> bytes:
    """Retrieve the chain signing key.

    Priority:
    1. RHUMB_CHAIN_SIGNING_KEY env var
    2. 1Password via sop
    3. Test fallback (with warning)
    """
    env_key = os.environ.get("RHUMB_CHAIN_SIGNING_KEY")
    if env_key:
        return env_key.encode("utf-8")

    try:
        result = subprocess.run(
            ["sop", "item", "get", "Rhumb Chain Signing Key", "--vault", "OpenClaw Agents",
             "--fields", "credential", "--reveal"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().encode("utf-8")
    except Exception:
        pass

    logger.warning(
        "chain_integrity: using test signing key — set RHUMB_CHAIN_SIGNING_KEY in production"
    )
    return _TEST_KEY


# Cache the key at module load
_SIGNING_KEY: bytes | None = None


def get_signing_key() -> bytes:
    """Get the cached signing key (lazy init)."""
    global _SIGNING_KEY
    if _SIGNING_KEY is None:
        _SIGNING_KEY = _get_signing_key()
    return _SIGNING_KEY


def _canonicalize(obj: Any) -> str:
    """Convert an object to canonical JSON for deterministic hashing.

    Rules:
    - dict keys sorted
    - No whitespace
    - datetime → ISO 8601 string
    - None → null
    - Enums → their value
    """
    def _serialize(o: Any) -> Any:
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, (set, frozenset)):
            return sorted(list(o))
        if hasattr(o, "value"):  # Enum
            return o.value
        raise TypeError(f"Cannot serialize {type(o)}")

    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=_serialize)


def compute_chain_hmac(
    prev_hash: str,
    payload: dict[str, Any],
    *,
    key: bytes | None = None,
) -> str:
    """Compute HMAC-SHA256 chain hash over the full semantic payload.

    Args:
        prev_hash: The chain hash of the previous event (or genesis hash)
        payload: ALL fields of the event to sign (not just headers)
        key: Optional override signing key (for testing)

    Returns:
        Hex-encoded HMAC-SHA256 digest
    """
    signing_key = key or get_signing_key()
    # Prepend prev_hash to the canonical payload
    message = f"{prev_hash}|{_canonicalize(payload)}"
    return hmac.new(signing_key, message.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_chain_hmac(
    prev_hash: str,
    payload: dict[str, Any],
    expected_hash: str,
    *,
    key: bytes | None = None,
) -> bool:
    """Verify an HMAC chain hash against expected.

    Uses constant-time comparison to prevent timing attacks.
    """
    computed = compute_chain_hmac(prev_hash, payload, key=key)
    return hmac.compare_digest(computed, expected_hash)


def build_billing_payload(event: Any) -> dict[str, Any]:
    """Build the full semantic payload for a billing event.

    Covers ALL fields — not just event_id/type/org/amount/timestamp.
    This prevents mutation of detail fields while chain verification passes.
    """
    return {
        "event_id": event.event_id,
        "event_type": event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type),
        "org_id": event.org_id,
        "timestamp": event.timestamp.isoformat() if isinstance(event.timestamp, datetime) else str(event.timestamp),
        "amount_usd_cents": event.amount_usd_cents,
        "balance_after_usd_cents": event.balance_after_usd_cents,
        "metadata": event.metadata if isinstance(event.metadata, dict) else {},
        "receipt_id": event.receipt_id,
        "execution_id": event.execution_id,
        "capability_id": event.capability_id,
        "provider_slug": event.provider_slug,
    }


def build_audit_payload(event: Any) -> dict[str, Any]:
    """Build the full semantic payload for an audit event."""
    return {
        "event_id": event.event_id,
        "event_type": event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type),
        "severity": event.severity.value if hasattr(event.severity, "value") else str(event.severity),
        "category": event.category,
        "timestamp": event.timestamp.isoformat() if isinstance(event.timestamp, datetime) else str(event.timestamp),
        "org_id": event.org_id,
        "agent_id": getattr(event, "agent_id", None),
        "resource_type": getattr(event, "resource_type", None),
        "resource_id": getattr(event, "resource_id", None),
        "action": getattr(event, "action", None),
        "detail": getattr(event, "detail", None) or {},
        "metadata": getattr(event, "metadata", None) or {},
    }


def build_kill_switch_payload(entry: Any) -> dict[str, Any]:
    """Build the full semantic payload for a kill switch audit entry."""
    return {
        "action": entry.action,
        "level": entry.level,
        "target": entry.target,
        "principal": entry.principal,
        "reason": entry.reason,
        "timestamp": entry.timestamp.isoformat() if isinstance(entry.timestamp, datetime) else str(entry.timestamp),
        "detail": getattr(entry, "detail", None) or {},
    }
