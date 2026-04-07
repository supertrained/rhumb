"""Verification policy for historical score-audit-chain rows.

AUD-3 follow-on:
- preserve honest verification semantics for legacy score-chain rows
- prevent external anchoring from silently treating an unreconstructible tail row
  as the current verified head
- cryptographically replay score-audit rows when the persisted surface is rich
  enough, while keeping honest fallback semantics for older sparse rows
"""

from __future__ import annotations

from datetime import datetime, timezone
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


def _parse_optional_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
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


def _score_audit_report_row(row: Any) -> dict[str, Any]:
    verification = describe_score_audit_entry_verification(row)
    return {
        "entry_id": verification.get("entry_id") or _field(row, "entry_id"),
        "service_slug": _field(row, "service_slug"),
        "created_at": _field(row, "created_at"),
        "key_version": _parse_optional_int(_field(row, "key_version")),
        "verification_status": verification.get("verification_status"),
        "verification_method": verification.get("verification_method"),
        "quarantine_decision": verification.get("quarantine_decision"),
        "reason": verification.get("reason"),
        "forensic_note": verification.get("forensic_note"),
        "is_anchor_eligible": bool(verification.get("is_anchor_eligible")),
    }


def build_score_audit_verification_report(rows: list[Any]) -> dict[str, Any]:
    """Summarize score-audit-chain verification truth across a full row set.

    The report is intentionally honest about three states:
    - replay-verified rows
    - legacy rows that are only anchor-eligible via key-version semantics
    - quarantined / unattributed rows that cannot qualify as the verified head

    Rows are ordered oldest -> newest by ``created_at`` when possible, with
    input order preserved for ties or unparsable timestamps.
    """

    parsed_rows: list[dict[str, Any]] = [row for row in rows if isinstance(row, dict)]
    ordered_rows = sorted(
        enumerate(parsed_rows),
        key=lambda item: (
            _parse_optional_timestamp(item[1].get("created_at")) or datetime.min.replace(tzinfo=timezone.utc),
            item[0],
        ),
    )
    report_rows = [_score_audit_report_row(row) for _, row in ordered_rows]

    status_counts: dict[str, int] = {}
    verification_method_counts: dict[str, int] = {}
    anchor_eligible_rows = 0
    replay_verified_rows = 0
    key_version_only_rows = 0
    latest_anchor_eligible_index: int | None = None

    for index, row in enumerate(report_rows):
        status = str(row.get("verification_status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

        method = row.get("verification_method")
        if method:
            method_key = str(method)
            verification_method_counts[method_key] = verification_method_counts.get(method_key, 0) + 1
            if method_key in {"stored_canonical_payload", "reconstructed_from_row_fields"}:
                replay_verified_rows += 1
            elif method_key == "key_version_only_surface":
                key_version_only_rows += 1

        if row.get("is_anchor_eligible"):
            anchor_eligible_rows += 1
            latest_anchor_eligible_index = index

    latest_observed = report_rows[-1] if report_rows else None
    latest_anchor_eligible = (
        report_rows[latest_anchor_eligible_index]
        if latest_anchor_eligible_index is not None and report_rows
        else None
    )

    quarantined_tail_rows = (
        report_rows[latest_anchor_eligible_index + 1 :]
        if latest_anchor_eligible_index is not None
        else report_rows
    )
    quarantined_tail_entry_ids = [
        str(row["entry_id"])
        for row in quarantined_tail_rows
        if row.get("entry_id") and not row.get("is_anchor_eligible")
    ]

    head_selection_mode = "none"
    if latest_observed is not None:
        head_selection_mode = (
            "latest_head"
            if latest_observed.get("is_anchor_eligible")
            else "latest_verified_head"
            if latest_anchor_eligible is not None
            else "none"
        )

    return {
        **_verification_policy_metadata(),
        "total_rows": len(report_rows),
        "anchor_eligible_rows": anchor_eligible_rows,
        "replay_verified_rows": replay_verified_rows,
        "key_version_only_rows": key_version_only_rows,
        "head_selection_mode": head_selection_mode,
        "status_counts": status_counts,
        "verification_method_counts": verification_method_counts,
        "latest_observed": latest_observed,
        "latest_anchor_eligible": latest_anchor_eligible,
        "quarantined_tail_count": len(quarantined_tail_entry_ids),
        "quarantined_tail_entry_ids": quarantined_tail_entry_ids,
        "rows": report_rows,
    }
