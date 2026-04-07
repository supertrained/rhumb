"""Tests for scripts/audit_score_audit_chain.py."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "scripts"
    / "audit_score_audit_chain.py"
)
_spec = importlib.util.spec_from_file_location("audit_score_audit_chain", _SCRIPT_PATH)
assert _spec and _spec.loader

audit_score_audit_chain = importlib.util.module_from_spec(_spec)
sys.modules["audit_score_audit_chain"] = audit_score_audit_chain
_spec.loader.exec_module(audit_score_audit_chain)

FIXED_TIME = datetime(2026, 4, 7, 1, 30, 0, tzinfo=timezone.utc)
SAMPLE_REPORT = {
    "verification_policy_version": "2026-04-06",
    "verification_policy_reference": "docs/specs/AUD-3-SCORE-AUDIT-QUARANTINE-POLICY-2026-04-06.md",
    "total_rows": 2,
    "anchor_eligible_rows": 1,
    "replay_verified_rows": 0,
    "key_version_only_rows": 1,
    "head_selection_mode": "latest_verified_head",
    "status_counts": {"verified": 1, "unverifiable_legacy": 1},
    "verification_method_counts": {"key_version_only_surface": 1},
    "latest_observed": {
        "entry_id": "saud_5565e543fcc248dbbe515e38103ac518",
        "verification_status": "unverifiable_legacy",
    },
    "latest_anchor_eligible": {
        "entry_id": "saud_verified_prior_head",
        "verification_status": "verified",
        "verification_method": "key_version_only_surface",
    },
    "quarantined_tail_count": 1,
    "quarantined_tail_entry_ids": ["saud_5565e543fcc248dbbe515e38103ac518"],
    "rows": [],
}


def test_build_report_bundle_wraps_report_with_provenance() -> None:
    bundle = audit_score_audit_chain.build_report_bundle(
        SAMPLE_REPORT,
        operator="pedro",
        reason="score_audit_chain_verification_snapshot",
        generated_at=FIXED_TIME,
    )

    assert bundle["schema_version"] == "1.0.0"
    assert bundle["report_type"] == "score_audit_chain_verification"
    assert bundle["generated_at"] == FIXED_TIME.isoformat()
    assert bundle["provenance"]["system"] == "rhumb"
    assert bundle["provenance"]["operator"] == "pedro"
    assert bundle["provenance"]["reason"] == "score_audit_chain_verification_snapshot"
    assert bundle["report"] == SAMPLE_REPORT


def test_write_report_bundle_writes_timestamped_json(tmp_path: Path) -> None:
    bundle = audit_score_audit_chain.build_report_bundle(
        SAMPLE_REPORT,
        operator="pedro",
        reason="score_audit_chain_verification_snapshot",
        generated_at=FIXED_TIME,
    )

    path = audit_score_audit_chain.write_report_bundle(
        bundle,
        tmp_path,
        generated_at=FIXED_TIME,
    )

    assert path.name == "score-audit-chain-verification-20260407T013000Z.json"
    assert path.exists()
    assert '"report_type": "score_audit_chain_verification"' in path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_fetch_all_score_audit_rows_paginates(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def fake_supabase_fetch(path: str):
        calls.append(path)
        if "offset=0" in path:
            return [
                {"entry_id": "saud_1", "created_at": "2026-04-03T19:28:03+00:00"},
                {"entry_id": "saud_2", "created_at": "2026-04-03T19:29:03+00:00"},
            ]
        if "offset=2" in path:
            return [
                {"entry_id": "saud_3", "created_at": "2026-04-03T19:30:03+00:00"},
            ]
        return []

    monkeypatch.setattr(audit_score_audit_chain, "supabase_fetch", fake_supabase_fetch)

    rows = await audit_score_audit_chain.fetch_all_score_audit_rows(page_size=2)

    assert [row["entry_id"] for row in rows] == ["saud_1", "saud_2", "saud_3"]
    assert len(calls) == 2
    assert "limit=2&offset=0" in calls[0]
    assert "limit=2&offset=2" in calls[1]
