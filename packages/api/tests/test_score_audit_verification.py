from __future__ import annotations

from pathlib import Path

from services.chain_integrity import (
    build_score_audit_payload,
    canonicalize_payload,
    compute_chain_hmac,
    get_signing_key_version,
)
from services.score_audit_verification import (
    LEGACY_SCORE_AUDIT_FORENSIC_NOTE_REFERENCE,
    SCORE_AUDIT_VERIFICATION_POLICY_REFERENCE,
    SCORE_AUDIT_VERIFICATION_POLICY_VERSION,
    describe_score_audit_entry_verification,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def test_describe_score_audit_entry_verification_marks_known_quarantine() -> None:
    result = describe_score_audit_entry_verification(
        {"entry_id": "saud_5565e543fcc248dbbe515e38103ac518", "key_version": None}
    )

    assert result["is_anchor_eligible"] is False
    assert result["verification_status"] == "unverifiable_legacy"
    assert result["quarantine_decision"] == "exclude_from_verified_head"
    assert result["verification_policy_version"] == SCORE_AUDIT_VERIFICATION_POLICY_VERSION
    assert result["verification_policy_reference"] == SCORE_AUDIT_VERIFICATION_POLICY_REFERENCE
    assert result["forensic_note"] == LEGACY_SCORE_AUDIT_FORENSIC_NOTE_REFERENCE


def test_describe_score_audit_entry_verification_marks_missing_key_version() -> None:
    result = describe_score_audit_entry_verification(
        {"entry_id": "saud_missing_key_version", "key_version": None}
    )

    assert result["is_anchor_eligible"] is False
    assert result["verification_status"] == "unattributed_legacy"
    assert result["verification_policy_version"] == SCORE_AUDIT_VERIFICATION_POLICY_VERSION
    assert result["verification_policy_reference"] == SCORE_AUDIT_VERIFICATION_POLICY_REFERENCE


def test_describe_score_audit_entry_verification_replays_from_row_fields() -> None:
    prev_hash = "ab" * 32
    key_version = get_signing_key_version()
    row = {
        "entry_id": "saud_verified_reconstructed",
        "service_slug": "stripe",
        "old_score": 8.1,
        "new_score": 8.1,
        "change_reason": "recalculation",
        "created_at": "2026-04-03T19:28:03.601436+00:00",
        "prev_hash": prev_hash,
        "key_version": key_version,
    }
    payload = build_score_audit_payload(row)
    row["chain_hash"] = compute_chain_hmac(prev_hash, payload, key_version=key_version)

    result = describe_score_audit_entry_verification(row)

    assert result["is_anchor_eligible"] is True
    assert result["verification_status"] == "verified"
    assert result["verification_method"] == "reconstructed_from_row_fields"


def test_describe_score_audit_entry_verification_replays_from_stored_canonical_payload() -> None:
    prev_hash = "cd" * 32
    payload = build_score_audit_payload(
        {
            "entry_id": "saud_verified_stored_payload",
            "service_slug": "stripe",
            "old_score": 8.1,
            "new_score": 8.2,
            "change_reason": "recalculation",
            "created_at": "2026-04-03T19:30:35.190409+00:00",
        }
    )
    row = {
        "entry_id": "saud_verified_stored_payload",
        "prev_hash": prev_hash,
        "chain_hash": compute_chain_hmac(prev_hash, payload, key_version=1),
        "payload_canonical_json": canonicalize_payload(payload),
        "key_version": 1,
    }

    result = describe_score_audit_entry_verification(row)

    assert result["is_anchor_eligible"] is True
    assert result["verification_status"] == "verified"
    assert result["verification_method"] == "stored_canonical_payload"


def test_describe_score_audit_entry_verification_blocks_payload_mismatch() -> None:
    prev_hash = "ef" * 32
    payload = build_score_audit_payload(
        {
            "entry_id": "saud_bad_payload",
            "service_slug": "stripe",
            "old_score": 8.1,
            "new_score": 8.2,
            "change_reason": "recalculation",
            "created_at": "2026-04-03T19:30:35.190409+00:00",
        }
    )
    row = {
        "entry_id": "saud_bad_payload",
        "prev_hash": prev_hash,
        "chain_hash": "00" * 32,
        "payload_canonical_json": canonicalize_payload(payload),
        "key_version": 1,
    }

    result = describe_score_audit_entry_verification(row)

    assert result["is_anchor_eligible"] is False
    assert result["verification_status"] == "unverifiable_payload_mismatch"
    assert result["verification_method"] == "stored_canonical_payload"
    assert result["quarantine_decision"] == "exclude_from_verified_head"


def test_score_audit_verification_references_docs_in_product_repo() -> None:
    assert (REPO_ROOT / SCORE_AUDIT_VERIFICATION_POLICY_REFERENCE).exists()
    assert (REPO_ROOT / LEGACY_SCORE_AUDIT_FORENSIC_NOTE_REFERENCE).exists()
