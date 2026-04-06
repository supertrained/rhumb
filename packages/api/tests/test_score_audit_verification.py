from __future__ import annotations

from pathlib import Path

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


def test_score_audit_verification_references_docs_in_product_repo() -> None:
    assert (REPO_ROOT / SCORE_AUDIT_VERIFICATION_POLICY_REFERENCE).exists()
    assert (REPO_ROOT / LEGACY_SCORE_AUDIT_FORENSIC_NOTE_REFERENCE).exists()
