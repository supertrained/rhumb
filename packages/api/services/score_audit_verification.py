"""Verification policy for historical score-audit-chain rows.

AUD-3 follow-on:
- preserve honest verification semantics for legacy score-chain rows
- prevent external anchoring from silently treating an unreconstructible tail row
  as the current verified head

This module intentionally starts with a small explicit registry for known legacy
exceptions rather than pretending every historical row can already be verified
from the stored truth surface.
"""

from __future__ import annotations

from typing import Any


KNOWN_SCORE_AUDIT_QUARANTINE: dict[str, dict[str, Any]] = {
    "saud_5565e543fcc248dbbe515e38103ac518": {
        "verification_status": "unverifiable_legacy",
        "reason": (
            "Legacy reconstruction failure: forensic verification on 2026-04-04 "
            "could not reproduce this row from the preserved payload surface and "
            "preserved keyring under the current verifier."
        ),
        "forensic_note": "docs/specs/AUD-3-LEGACY-SCORE-AUDIT-FORENSIC-NOTE-2026-04-04.md",
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


def describe_score_audit_entry_verification(row: Any) -> dict[str, Any]:
    """Describe whether a score-audit-chain row is anchor-eligible.

    Verified-head eligibility is intentionally strict:
    - explicitly quarantined legacy rows are never eligible
    - rows without an explicit key version are treated as unattributed legacy rows
      and are not eligible for a "verified head" anchor selection
    """

    entry_id = _field(row, "entry_id")
    known = KNOWN_SCORE_AUDIT_QUARANTINE.get(str(entry_id)) if entry_id else None
    if known:
        return {
            "entry_id": entry_id,
            "is_anchor_eligible": False,
            **known,
        }

    key_version = _parse_optional_int(_field(row, "key_version"))
    if key_version is None:
        return {
            "entry_id": entry_id,
            "verification_status": "unattributed_legacy",
            "reason": "Row has no persisted key_version, so it cannot qualify as a verified head.",
            "quarantine_decision": "exclude_from_verified_head",
            "is_anchor_eligible": False,
        }

    return {
        "entry_id": entry_id,
        "verification_status": "verified",
        "reason": "Row has an explicit persisted key_version and no active quarantine exception.",
        "quarantine_decision": "none",
        "is_anchor_eligible": True,
    }

