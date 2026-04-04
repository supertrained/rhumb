"""Tests for the external-anchor publication path (scripts/publish_chain_anchor.py).

These tests exercise bundle construction, hash determinism, and file writing
without requiring a live API -- they mock the HTTP checkpoint call.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

# The script lives outside packages/api, so import it by path.
import importlib.util
import sys

_SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "publish_chain_anchor.py"
_spec = importlib.util.spec_from_file_location("publish_chain_anchor", _SCRIPT_PATH)
assert _spec and _spec.loader
publish_chain_anchor = importlib.util.module_from_spec(_spec)
sys.modules["publish_chain_anchor"] = publish_chain_anchor
_spec.loader.exec_module(publish_chain_anchor)


# ── Fixtures ──────────────────────────────────────────────────────────────────

SAMPLE_CHECKPOINT_RESPONSE_AUDIT = {
    "status": "created",
    "stream_name": "audit_events",
    "checkpoint": {
        "checkpoint_id": "chk_abc123def456ghi7",
        "stream_name": "audit_events",
        "reason": "external_anchor",
        "source_head_hash": "a1b2c3d4e5f6" + "0" * 52,
        "source_head_sequence": 42,
        "source_key_version": 1,
        "checkpoint_hash": "ff" * 32,
        "key_version": 1,
        "created_at": "2026-04-04T12:00:00+00:00",
        "metadata": {
            "checkpoint_origin": "manual_head_snapshot",
            "event_count": 42,
            "operator": "pedro",
        },
    },
}

SAMPLE_CHECKPOINT_RESPONSE_BILLING_SKIPPED = {
    "status": "skipped",
    "stream_name": "billing_events",
    "reason": "external_anchor",
    "detail": "Stream is empty; no checkpoint created.",
}

SAMPLE_CHECKPOINT_RESPONSE_BILLING_CREATED = {
    "status": "created",
    "stream_name": "billing_events",
    "checkpoint": {
        "checkpoint_id": "chk_xyz789uvw012rst3",
        "stream_name": "billing_events",
        "reason": "external_anchor",
        "source_head_hash": "b2c3d4e5f6a1" + "0" * 52,
        "source_head_sequence": 17,
        "source_key_version": 1,
        "checkpoint_hash": "ee" * 32,
        "key_version": 1,
        "created_at": "2026-04-04T12:00:01+00:00",
        "metadata": {
            "checkpoint_origin": "manual_head_snapshot",
            "event_count": 17,
            "operator": "pedro",
        },
    },
}

FIXED_TIME = datetime(2026, 4, 4, 12, 0, 0, tzinfo=timezone.utc)


# ── Bundle construction ───────────────────────────────────────────────────────

def test_build_anchor_bundle_both_anchored():
    checkpoints = {
        "audit_events": SAMPLE_CHECKPOINT_RESPONSE_AUDIT,
        "billing_events": SAMPLE_CHECKPOINT_RESPONSE_BILLING_CREATED,
    }
    bundle = publish_chain_anchor.build_anchor_bundle(
        checkpoints,
        operator="pedro",
        reason="external_anchor",
        published_at=FIXED_TIME,
    )

    assert bundle["schema_version"] == "1.0.0"
    assert bundle["bundle_type"] == "chain_anchor"
    assert bundle["published_at"] == FIXED_TIME.isoformat()
    assert bundle["provenance"]["operator"] == "pedro"
    assert bundle["streams"]["audit_events"]["status"] == "anchored"
    assert bundle["streams"]["billing_events"]["status"] == "anchored"
    assert bundle["streams"]["audit_events"]["checkpoint_id"] == "chk_abc123def456ghi7"
    assert bundle["streams"]["billing_events"]["checkpoint_id"] == "chk_xyz789uvw012rst3"
    assert len(bundle["bundle_hash"]) == 64  # SHA-256 hex


def test_build_anchor_bundle_with_skipped_stream():
    checkpoints = {
        "audit_events": SAMPLE_CHECKPOINT_RESPONSE_AUDIT,
        "billing_events": SAMPLE_CHECKPOINT_RESPONSE_BILLING_SKIPPED,
    }
    bundle = publish_chain_anchor.build_anchor_bundle(
        checkpoints,
        operator="pedro",
        reason="external_anchor",
        published_at=FIXED_TIME,
    )

    assert bundle["streams"]["audit_events"]["status"] == "anchored"
    assert bundle["streams"]["billing_events"]["status"] == "skipped"
    assert "checkpoint_id" not in bundle["streams"]["billing_events"]


# ── Hash determinism ──────────────────────────────────────────────────────────

def test_bundle_hash_is_deterministic():
    checkpoints = {
        "audit_events": SAMPLE_CHECKPOINT_RESPONSE_AUDIT,
        "billing_events": SAMPLE_CHECKPOINT_RESPONSE_BILLING_CREATED,
    }
    b1 = publish_chain_anchor.build_anchor_bundle(
        checkpoints, operator="pedro", reason="external_anchor", published_at=FIXED_TIME,
    )
    b2 = publish_chain_anchor.build_anchor_bundle(
        checkpoints, operator="pedro", reason="external_anchor", published_at=FIXED_TIME,
    )

    assert b1["bundle_hash"] == b2["bundle_hash"]


def test_bundle_hash_matches_manual_computation():
    checkpoints = {"audit_events": SAMPLE_CHECKPOINT_RESPONSE_AUDIT}
    bundle = publish_chain_anchor.build_anchor_bundle(
        checkpoints, operator="test", reason="test", published_at=FIXED_TIME,
    )

    # Recompute manually
    canonical = json.dumps(bundle["streams"], sort_keys=True, separators=(",", ":"))
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert bundle["bundle_hash"] == expected


def test_compute_bundle_hash_canonical_ordering():
    """Key ordering shouldn't affect the hash."""
    streams_a = {"audit_events": {"status": "anchored", "x": 1}, "billing_events": {"status": "anchored", "y": 2}}
    streams_b = {"billing_events": {"status": "anchored", "y": 2}, "audit_events": {"status": "anchored", "x": 1}}
    assert publish_chain_anchor.compute_bundle_hash(streams_a) == publish_chain_anchor.compute_bundle_hash(streams_b)


def test_api_base_prefers_modern_env_fallbacks(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("RHUMB_API_URL", raising=False)
    monkeypatch.setenv("AUTH_API_URL", "https://api.rhumb.dev")
    assert publish_chain_anchor._api_base() == "https://api.rhumb.dev"


def test_admin_key_falls_back_to_rhumb_admin_secret(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("RHUMB_ADMIN_KEY", raising=False)
    monkeypatch.setenv("RHUMB_ADMIN_SECRET", "prod-secret")
    assert publish_chain_anchor._admin_key() == "prod-secret"


# ── File writing ──────────────────────────────────────────────────────────────

def test_write_anchor_bundle_creates_file(tmp_path: Path):
    checkpoints = {"audit_events": SAMPLE_CHECKPOINT_RESPONSE_AUDIT}
    bundle = publish_chain_anchor.build_anchor_bundle(
        checkpoints, operator="test", reason="test", published_at=FIXED_TIME,
    )

    path = publish_chain_anchor.write_anchor_bundle(bundle, tmp_path, published_at=FIXED_TIME)

    assert path.exists()
    assert path.name == "chain-anchor-20260404T120000Z.json"
    content = json.loads(path.read_text(encoding="utf-8"))
    assert content["bundle_hash"] == bundle["bundle_hash"]
    assert content["streams"]["audit_events"]["status"] == "anchored"


def test_write_anchor_bundle_creates_parent_dirs(tmp_path: Path):
    deep_dir = tmp_path / "nested" / "anchors"
    checkpoints = {"audit_events": SAMPLE_CHECKPOINT_RESPONSE_AUDIT}
    bundle = publish_chain_anchor.build_anchor_bundle(
        checkpoints, operator="test", reason="test", published_at=FIXED_TIME,
    )

    path = publish_chain_anchor.write_anchor_bundle(bundle, deep_dir, published_at=FIXED_TIME)
    assert path.exists()
    assert deep_dir.is_dir()


# ── CLI main() with mocked API ───────────────────────────────────────────────

def _mock_create_checkpoint(stream_name, reason, metadata, **kwargs):
    if stream_name == "audit_events":
        return SAMPLE_CHECKPOINT_RESPONSE_AUDIT
    if stream_name == "billing_events":
        return SAMPLE_CHECKPOINT_RESPONSE_BILLING_CREATED
    raise RuntimeError(f"Unknown stream: {stream_name}")


def test_main_dry_run(capsys):
    with patch.object(publish_chain_anchor, "create_checkpoint", side_effect=_mock_create_checkpoint):
        rc = publish_chain_anchor.main([
            "--streams", "audit_events",
            "--operator", "test-operator",
            "--dry-run",
        ])

    assert rc == 0
    stdout = capsys.readouterr().out
    bundle = json.loads(stdout)
    assert bundle["provenance"]["operator"] == "test-operator"
    assert bundle["streams"]["audit_events"]["status"] == "anchored"


def test_main_writes_file(tmp_path: Path):
    with patch.object(publish_chain_anchor, "create_checkpoint", side_effect=_mock_create_checkpoint):
        rc = publish_chain_anchor.main([
            "--streams", "audit_events,billing_events",
            "--operator", "pedro",
            "--output-dir", str(tmp_path),
        ])

    assert rc == 0
    files = list(tmp_path.glob("chain-anchor-*.json"))
    assert len(files) == 1
    content = json.loads(files[0].read_text(encoding="utf-8"))
    assert content["streams"]["audit_events"]["status"] == "anchored"
    assert content["streams"]["billing_events"]["status"] == "anchored"


def test_main_fails_on_api_error():
    def _failing_checkpoint(*args, **kwargs):
        raise RuntimeError("HTTP 503 — outbox unavailable")

    with patch.object(publish_chain_anchor, "create_checkpoint", side_effect=_failing_checkpoint):
        rc = publish_chain_anchor.main([
            "--streams", "audit_events",
            "--dry-run",
        ])

    assert rc == 1


def test_main_single_stream(tmp_path: Path):
    with patch.object(publish_chain_anchor, "create_checkpoint", side_effect=_mock_create_checkpoint):
        rc = publish_chain_anchor.main([
            "--streams", "audit_events",
            "--output-dir", str(tmp_path),
        ])

    assert rc == 0
    files = list(tmp_path.glob("chain-anchor-*.json"))
    content = json.loads(files[0].read_text(encoding="utf-8"))
    assert "audit_events" in content["streams"]
    assert "billing_events" not in content["streams"]
