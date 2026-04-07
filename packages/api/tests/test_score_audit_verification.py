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
    build_score_audit_verification_report,
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


def test_build_score_audit_verification_report_summarizes_mixed_row_states() -> None:
    prev_hash = "ab" * 32
    replay_payload = build_score_audit_payload(
        {
            "entry_id": "saud_replay_verified",
            "service_slug": "stripe",
            "old_score": 8.1,
            "new_score": 8.2,
            "change_reason": "recalculation",
            "created_at": "2026-04-03T19:28:03.601436+00:00",
        }
    )
    replay_row = {
        "entry_id": "saud_replay_verified",
        "service_slug": "stripe",
        "created_at": "2026-04-03T19:28:03.601436+00:00",
        "prev_hash": prev_hash,
        "chain_hash": compute_chain_hmac(prev_hash, replay_payload, key_version=1),
        "payload_canonical_json": canonicalize_payload(replay_payload),
        "key_version": 1,
    }
    key_version_only_row = {
        "entry_id": "saud_key_version_only",
        "service_slug": "stripe",
        "created_at": "2026-04-03T19:29:03.601436+00:00",
        "key_version": 1,
    }
    known_quarantine_row = {
        "entry_id": "saud_5565e543fcc248dbbe515e38103ac518",
        "service_slug": "stripe",
        "created_at": "2026-04-03T19:30:35.190409+00:00",
        "key_version": None,
    }

    report = build_score_audit_verification_report(
        [known_quarantine_row, key_version_only_row, replay_row]
    )

    assert report["total_rows"] == 3
    assert report["anchor_eligible_rows"] == 2
    assert report["replay_verified_rows"] == 1
    assert report["key_version_only_rows"] == 1
    assert report["head_selection_mode"] == "latest_verified_head"
    assert report["status_counts"] == {"verified": 2, "unverifiable_legacy": 1}
    assert report["verification_method_counts"] == {
        "stored_canonical_payload": 1,
        "key_version_only_surface": 1,
    }
    assert report["latest_observed"]["entry_id"] == "saud_5565e543fcc248dbbe515e38103ac518"
    assert report["latest_observed"]["verification_status"] == "unverifiable_legacy"
    assert report["latest_anchor_eligible"]["entry_id"] == "saud_key_version_only"
    assert report["latest_anchor_eligible"]["verification_method"] == "key_version_only_surface"
    assert report["quarantined_tail_count"] == 1
    assert report["quarantined_tail_entry_ids"] == ["saud_5565e543fcc248dbbe515e38103ac518"]
    assert [row["entry_id"] for row in report["rows"]] == [
        "saud_replay_verified",
        "saud_key_version_only",
        "saud_5565e543fcc248dbbe515e38103ac518",
    ]


def test_build_score_audit_verification_report_handles_empty_input() -> None:
    report = build_score_audit_verification_report([])

    assert report["total_rows"] == 0
    assert report["anchor_eligible_rows"] == 0
    assert report["replay_verified_rows"] == 0
    assert report["key_version_only_rows"] == 0
    assert report["head_selection_mode"] == "none"
    assert report["status_counts"] == {}
    assert report["verification_method_counts"] == {}
    assert report["latest_observed"] is None
    assert report["latest_anchor_eligible"] is None
    assert report["quarantined_tail_count"] == 0
    assert report["quarantined_tail_entry_ids"] == []
    assert report["rows"] == []


def test_score_audit_verification_references_docs_in_product_repo() -> None:
    assert (REPO_ROOT / SCORE_AUDIT_VERIFICATION_POLICY_REFERENCE).exists()
    assert (REPO_ROOT / LEGACY_SCORE_AUDIT_FORENSIC_NOTE_REFERENCE).exists()
