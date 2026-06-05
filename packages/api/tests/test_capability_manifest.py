"""PP-2 command-level capability manifest schema tests."""

from __future__ import annotations

from copy import deepcopy

from schemas.capability_manifest import (
    capability_manifest_digest,
    command_manifest_fixtures,
    fixture_manifests_by_route_id,
    lint_capability_manifest,
)


def test_command_manifest_fixtures_cover_managed_and_non_native_substrates() -> None:
    manifests = command_manifest_fixtures()
    assert len(manifests) == 9
    assert all(lint_capability_manifest(manifest) == [] for manifest in manifests)

    by_capability = {manifest["capability_id"]: manifest for manifest in manifests}
    for capability_id in {
        "search.query",
        "email.verify",
        "crm.contact.lookup",
        "support.ticket.create",
        "warehouse.query",
    }:
        assert by_capability[capability_id]["substrate"] == "official_api"
        assert by_capability[capability_id]["auth_mode"] == "rhumb_managed"

    substrates = {manifest["substrate"] for manifest in manifests}
    assert {"official_cli", "official_mcp", "sdk_code_mode", "generated_adapter"}.issubset(substrates)


def test_command_manifest_digest_is_deterministic_and_route_index_is_stable() -> None:
    manifests = command_manifest_fixtures()
    first = manifests[0]
    shuffled = {"manifest_digest": "sha256:old", **{key: first[key] for key in reversed(first.keys()) if key != "manifest_digest"}}

    assert capability_manifest_digest(first) == capability_manifest_digest(shuffled)
    assert first["manifest_digest"] == capability_manifest_digest(first)

    by_route = fixture_manifests_by_route_id()
    assert by_route[first["route_id"]]["manifest_id"] == first["manifest_id"]


def test_manifest_linter_fails_closed_on_missing_allowlists_evidence_expiry_and_digest() -> None:
    manifest = command_manifest_fixtures()[0]
    broken = deepcopy(manifest)
    broken.pop("owner")
    broken["network_allowlist"] = []
    broken["tests"] = []
    broken["evidence_refs"] = []
    broken["expires_at"] = "not-a-time"
    broken["manifest_digest"] = "sha256:not-the-digest"

    assert lint_capability_manifest(broken) == [
        "invalid_evidence_refs",
        "invalid_expires_at",
        "invalid_network_allowlist",
        "invalid_tests",
        "manifest_digest_mismatch",
        "missing_owner",
    ]


def test_non_native_manifest_requires_sandbox_and_artifact_allowlist() -> None:
    cli_manifest = next(manifest for manifest in command_manifest_fixtures() if manifest["substrate"] == "official_cli")
    broken = deepcopy(cli_manifest)
    broken.pop("sandbox_profile_class")
    broken["artifact_allowlist"] = []

    assert lint_capability_manifest(broken) == [
        "invalid_artifact_allowlist",
        "manifest_digest_mismatch",
        "missing_sandbox_profile_class",
    ]


def test_high_risk_manifest_requires_confirmation_or_blocking_policy() -> None:
    manifest = command_manifest_fixtures()[0]
    broken = deepcopy(manifest)
    broken["side_effect_class"] = "payment"
    broken["confirmation_policy"] = "none"

    assert lint_capability_manifest(broken) == [
        "high_risk_requires_confirmation_policy",
        "manifest_digest_mismatch",
    ]
