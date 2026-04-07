"""Verification policy for historical score-audit-chain rows.

AUD-3 follow-on:
- preserve honest verification semantics for legacy score-chain rows
- prevent external anchoring from silently treating an unreconstructible tail row
  as the current verified head
- cryptographically replay score-audit rows when the persisted surface is rich
  enough, while keeping honest fallback semantics for older sparse rows
"""

from __future__ import annotations

import json
from typing import Any

from services.chain_integrity import build_score_audit_payload, compute_chain_hmac


SCORE_AUDIT_VERIFICATION_POLICY_VERSION = "2026-04-06"
SCORE_AUDIT_VERIFICATION_POLICY_REFERENCE = (
    "docs/specs/AUD-3-SCORE-AUDIT-QUARANTINE-POLICY-2026-04-06.md"
)
LEGACY_SCORE_AUDIT_FORENSIC_NOTE_REFERENCE = (
    "docs/specs/AUD-3-LEGACY-SCORE-AUDIT-FORENSIC-NOTE-2026-04-04.md"
)
SCORE_AUDIT_VERIFICATION_SELECT_FIELDS = ",".join(
    [
        "entry_id",
        "service_slug",
        "old_score",
        "new_score",
        "change_reason",
        "created_at",
        "prev_hash",
        "chain_hash",
        "key_version",
        "payload_canonical_json",
    ]
)

KNOWN_SCORE_AUDIT_QUARANTINE: dict[str, dict[str, Any]] = {
    "saud_5565e543fcc248dbbe515e38103ac518": {
        "verification_status": "unverifiable_legacy",
        "reason": (
            "Legacy reconstruction failure: forensic verification on 2026-04-04 "
            "could not reproduce this row from the preserved payload surface and "
            "preserved keyring under the current verifier."
        ),
        "forensic_note": LEGACY_SCORE_AUDIT_FORENSIC_NOTE_REFERENCE,
        "quarantine_decision": "exclude_from_verified_head",
    },
}


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _parse_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _verification_policy_metadata() -> dict[str, Any]:
    return {
        "verification_policy_version": SCORE_AUDIT_VERIFICATION_POLICY_VERSION,
        "verification_policy_reference": SCORE_AUDIT_VERIFICATION_POLICY_REFERENCE,
    }


def _try_build_replay_payload(row: Any) -> tuple[dict[str, Any] | None, str | None, str | None]:
    stored_canonical = _field(row, "payload_canonical_json")
    if isinstance(stored_canonical, str) and stored_canonical.strip():
        try:
            return json.loads(stored_canonical), "stored_canonical_payload", None
        except json.JSONDecodeError:
            return None, "stored_canonical_payload", "Stored payload_canonical_json is invalid JSON."

    required_fields = [
        "entry_id",
        "service_slug",
        "change_reason",
        "created_at",
        "old_score",
        "new_score",
    ]
    if any(_field(row, field) is None for field in required_fields):
        return None, None, None

    return (
        build_score_audit_payload(
            {
                "entry_id": _field(row, "entry_id"),
                "service_slug": _field(row, "service_slug"),
                "old_score": _field(row, "old_score"),
                "new_score": _field(row, "new_score"),
                "change_reason": _field(row, "change_reason"),
                "created_at": _field(row, "created_at"),
            }
        ),
        "reconstructed_from_row_fields",
        None,
    )


def _cryptographic_replay_verification(row: Any, key_version: int) -> dict[str, Any] | None:
    prev_hash = _field(row, "prev_hash")
    chain_hash = _field(row, "chain_hash")
    if not prev_hash or not chain_hash:
        return None

    payload, verification_method, payload_error = _try_build_replay_payload(row)
    if payload_error:
        return {
            "verification_status": "unverifiable_payload_mismatch",
            "reason": payload_error,
            "quarantine_decision": "exclude_from_verified_head",
            "verification_method": verification_method,
            "is_anchor_eligible": False,
        }
    if payload is None or verification_method is None:
        return None

    expected_chain_hash = compute_chain_hmac(str(prev_hash), payload, key_version=key_version)
    if expected_chain_hash == str(chain_hash):
        return {
            "verification_status": "verified",
            "reason": "Row cryptographically replays under the preserved signing key and payload surface.",
            "quarantine_decision": "none",
            "verification_method": verification_method,
            "is_anchor_eligible": True,
        }

    return {
        "verification_status": "unverifiable_payload_mismatch",
        "reason": (
            "Row has an explicit key_version but its preserved payload surface does not replay to the "
            "persisted chain_hash under that key."
        ),
        "quarantine_decision": "exclude_from_verified_head",
        "verification_method": verification_method,
        "is_anchor_eligible": False,
    }


def describe_score_audit_entry_verification(row: Any) -> dict[str, Any]:
    """Describe whether a score-audit-chain row is anchor-eligible.

    Verified-head eligibility is intentionally strict:
    - explicitly quarantined legacy rows are never eligible
    - rows without an explicit key version are treated as unattributed legacy rows
      and are not eligible for a "verified head" anchor selection
    - when enough persisted surface exists, rows are cryptographically replayed
      instead of being trusted on key-version presence alone
    """

    entry_id = _field(row, "entry_id")
    known = KNOWN_SCORE_AUDIT_QUARANTINE.get(str(entry_id)) if entry_id else None
    if known:
        return {
            "entry_id": entry_id,
            "is_anchor_eligible": False,
            **_verification_policy_metadata(),
            **known,
        }

    key_version = _parse_optional_int(_field(row, "key_version"))
    if key_version is None:
        return {
            "entry_id": entry_id,
            **_verification_policy_metadata(),
            "verification_status": "unattributed_legacy",
            "reason": "Row has no persisted key_version, so it cannot qualify as a verified head.",
            "quarantine_decision": "exclude_from_verified_head",
            "is_anchor_eligible": False,
        }

    cryptographic_result = _cryptographic_replay_verification(row, key_version)
    if cryptographic_result is not None:
        return {
            "entry_id": entry_id,
            **_verification_policy_metadata(),
            **cryptographic_result,
        }

    return {
        "entry_id": entry_id,
        **_verification_policy_metadata(),
        "verification_status": "verified",
        "reason": (
            "Row has an explicit persisted key_version, but the current row surface does not preserve enough "
            "material for cryptographic replay, so verification falls back to key-version-only legacy semantics."
        ),
        "quarantine_decision": "none",
        "verification_method": "key_version_only_surface",
        "is_anchor_eligible": True,
    }
