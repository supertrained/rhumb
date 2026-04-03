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
            [
                "sop",
                "item",
                "get",
                "Rhumb Chain Signing Key",
                "--vault",
                "OpenClaw Agents",
                "--fields",
                "credential",
                "--reveal",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().encode("utf-8")
    except Exception:
        pass

    logger.warning(
        "chain_integrity: using test signing key — set RHUMB_CHAIN_SIGNING_KEY in production"
    )
    return _TEST_KEY


_SIGNING_KEYRING: dict[int, bytes] | None = None
_ACTIVE_KEY_VERSION: int | None = None


def _parse_keyring(raw: str) -> dict[int, bytes]:
    keyring: dict[int, bytes] = {}
    for part in raw.replace("\n", ",").split(","):
        item = part.strip()
        if not item or ":" not in item:
            continue
        version_text, secret = item.split(":", 1)
        try:
            version = int(version_text.strip())
        except ValueError:
            continue
        secret = secret.strip()
        if secret:
            keyring[version] = secret.encode("utf-8")
    return keyring


def _get_signing_keyring() -> tuple[dict[int, bytes], int]:
    env_keyring = os.environ.get("RHUMB_CHAIN_SIGNING_KEYS")
    active_version_env = os.environ.get("RHUMB_CHAIN_SIGNING_ACTIVE_VERSION")

    if env_keyring:
        parsed = _parse_keyring(env_keyring)
        if parsed:
            if active_version_env:
                try:
                    active_version = int(active_version_env)
                except ValueError:
                    active_version = max(parsed)
            else:
                active_version = max(parsed)
            if active_version not in parsed:
                active_version = max(parsed)
            return parsed, active_version

    single_key = _get_signing_key()
    if active_version_env:
        try:
            active_version = int(active_version_env)
        except ValueError:
            active_version = CURRENT_KEY_VERSION
    else:
        active_version = CURRENT_KEY_VERSION
    return {active_version: single_key}, active_version


def reset_signing_key_cache() -> None:
    """Clear cached key material (tests / controlled runtime refresh)."""
    global _SIGNING_KEYRING, _ACTIVE_KEY_VERSION
    _SIGNING_KEYRING = None
    _ACTIVE_KEY_VERSION = None


def get_signing_keyring() -> dict[int, bytes]:
    """Get the cached signing keyring (lazy init)."""
    global _SIGNING_KEYRING, _ACTIVE_KEY_VERSION
    if _SIGNING_KEYRING is None or _ACTIVE_KEY_VERSION is None:
        _SIGNING_KEYRING, _ACTIVE_KEY_VERSION = _get_signing_keyring()
    return dict(_SIGNING_KEYRING)


def get_signing_key_version() -> int:
    """Return the active signing key version for new chain entries."""
    global _SIGNING_KEYRING, _ACTIVE_KEY_VERSION
    if _SIGNING_KEYRING is None or _ACTIVE_KEY_VERSION is None:
        _SIGNING_KEYRING, _ACTIVE_KEY_VERSION = _get_signing_keyring()
    return int(_ACTIVE_KEY_VERSION)


def get_signing_key() -> bytes:
    """Get the active signing key for new chain entries."""
    keyring = get_signing_keyring()
    return keyring[get_signing_key_version()]


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
    key_version: int | None = None,
) -> str:
    """Compute HMAC-SHA256 chain hash over the full semantic payload.

    Args:
        prev_hash: The chain hash of the previous event (or genesis hash)
        payload: ALL fields of the event to sign (not just headers)
        key: Optional override signing key (for testing)

    Returns:
        Hex-encoded HMAC-SHA256 digest
    """
    if key is not None:
        signing_key = key
    elif key_version is not None:
        signing_key = get_signing_keyring()[key_version]
    else:
        signing_key = get_signing_key()
    # Prepend prev_hash to the canonical payload
    message = f"{prev_hash}|{_canonicalize(payload)}"
    return hmac.new(signing_key, message.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_chain_hmac(
    prev_hash: str,
    payload: dict[str, Any],
    expected_hash: str,
    *,
    key: bytes | None = None,
    key_version: int | None = None,
) -> bool:
    """Verify an HMAC chain hash against expected.

    Uses constant-time comparison to prevent timing attacks.
    """
    if key is not None:
        computed = compute_chain_hmac(prev_hash, payload, key=key)
        return hmac.compare_digest(computed, expected_hash)

    keyring = get_signing_keyring()
    if key_version is not None and key_version in keyring:
        computed = compute_chain_hmac(
            prev_hash,
            payload,
            key=keyring[key_version],
        )
        return hmac.compare_digest(computed, expected_hash)

    for candidate in keyring.values():
        computed = compute_chain_hmac(prev_hash, payload, key=candidate)
        if hmac.compare_digest(computed, expected_hash):
            return True
    return False


def build_billing_payload(event: Any) -> dict[str, Any]:
    """Build the full semantic payload for a billing event.

    Covers ALL fields — not just event_id/type/org/amount/timestamp.
    This prevents mutation of detail fields while chain verification passes.
    """
    return {
        "event_id": event.event_id,
        "event_type": event.event_type.value
        if hasattr(event.event_type, "value")
        else str(event.event_type),
        "org_id": event.org_id,
        "timestamp": event.timestamp.isoformat()
        if isinstance(event.timestamp, datetime)
        else str(event.timestamp),
        "amount_usd_cents": event.amount_usd_cents,
        "balance_after_usd_cents": event.balance_after_usd_cents,
        "metadata": event.metadata if isinstance(event.metadata, dict) else {},
        "receipt_id": event.receipt_id,
        "execution_id": event.execution_id,
        "capability_id": event.capability_id,
        "provider_slug": event.provider_slug,
    }


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def build_audit_payload(event: Any) -> dict[str, Any]:
    """Build the full semantic payload for an audit event."""
    return {
        "event_id": _field(event, "event_id"),
        "event_type": (
            _field(event, "event_type").value
            if hasattr(_field(event, "event_type"), "value")
            else str(_field(event, "event_type"))
        ),
        "severity": (
            _field(event, "severity").value
            if hasattr(_field(event, "severity"), "value")
            else str(_field(event, "severity"))
        ),
        "category": _field(event, "category"),
        "timestamp": _field(event, "timestamp").isoformat()
        if isinstance(_field(event, "timestamp"), datetime)
        else str(_field(event, "timestamp")),
        "org_id": _field(event, "org_id"),
        "agent_id": _field(event, "agent_id"),
        "principal": _field(event, "principal"),
        "resource_type": _field(event, "resource_type"),
        "resource_id": _field(event, "resource_id"),
        "action": _field(event, "action"),
        "detail": _field(event, "detail") or {},
        "metadata": _field(event, "metadata") or {},
        "receipt_id": _field(event, "receipt_id"),
        "execution_id": _field(event, "execution_id"),
        "provider_slug": _field(event, "provider_slug"),
    }


def build_kill_switch_payload(entry: Any) -> dict[str, Any]:
    """Build the full semantic payload for a kill switch audit entry."""
    return {
        "entry_id": _field(entry, "entry_id"),
        "switch_id": _field(entry, "switch_id"),
        "action": _field(entry, "action"),
        "principal": _field(entry, "principal"),
        "timestamp": _field(entry, "timestamp").isoformat()
        if isinstance(_field(entry, "timestamp"), datetime)
        else str(_field(entry, "timestamp")),
        "details": _field(entry, "details") or _field(entry, "detail") or {},
    }


def build_score_audit_payload(entry: Any) -> dict[str, Any]:
    """Build the semantic payload for a score-audit-chain entry."""
    created_at = _field(entry, "created_at") or _field(entry, "timestamp")
    if isinstance(created_at, datetime):
        created_at_value = created_at.isoformat()
    else:
        created_at_value = str(created_at)

    return {
        "entry_id": _field(entry, "entry_id"),
        "service_slug": _field(entry, "service_slug"),
        "old_score": _field(entry, "old_score"),
        "new_score": _field(entry, "new_score"),
        "change_reason": _field(entry, "change_reason", "recalculation"),
        "created_at": created_at_value,
    }
