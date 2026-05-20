"""PP-15 Index evidence packet + manifest model tests."""

from __future__ import annotations

from copy import deepcopy

from schemas.index_evidence import (
    INDEX_ENTITY_VOCABULARY,
    canonical_json,
    evidence_packet_digest,
    lint_evidence_packet,
    lint_index_route_fixture,
    lint_manifest,
    manifest_digest,
    route_fixture_for,
    search_query_brave_route_fixture,
)
from schemas.resolve_route_candidate import route_candidate_from_provider


def test_canonical_json_digest_is_deterministic_and_ignores_digest_fields() -> None:
    left = {"b": 2, "a": {"z": 1, "manifest_digest": "sha256:old"}}
    right = {"a": {"manifest_digest": "sha256:new", "z": 1}, "b": 2}

    assert canonical_json(left) == canonical_json(right)
    assert manifest_digest(left) == manifest_digest(right)


def test_search_query_brave_fixture_lints_cleanly_and_distinguishes_index_entities() -> None:
    fixture = search_query_brave_route_fixture()

    assert lint_index_route_fixture(fixture) == []
    assert fixture["entity_vocabulary"] == INDEX_ENTITY_VOCABULARY

    manifest = fixture["manifest"]
    evidence = fixture["evidence_packet"]
    assert manifest["route_id"] == "route_search_query_brave_search_api_official_api_v1"
    assert manifest["service_id"] == "brave-search"
    assert manifest["provider_id"] == "brave-search-api"
    assert manifest["capability_id"] == "search.query"
    assert manifest["substrate"] == "official_api"
    assert manifest["provenance_origin"] == "rhumb_managed"
    assert manifest["source_risk"] == "verified_low"
    assert manifest["side_effect_class"] == "read"
    assert manifest["credential_modes"] == ["rhumb_managed"]
    assert manifest["manifest_digest"] == manifest_digest(manifest)

    assert evidence["manifest_digest"] == manifest["manifest_digest"]
    assert evidence["review_status"] == "current"
    assert evidence["promotion_state"] == "beta_executable"
    assert evidence["evidence_packet_digest"] == evidence_packet_digest(evidence)
    assert evidence["sources"]
    assert evidence["reviews"]
    assert evidence["public_claim_boundary"] == manifest["public_claim_boundary"]


def test_manifest_linter_fails_on_missing_owner_expiry_claim_and_bad_digest() -> None:
    manifest = search_query_brave_route_fixture()["manifest"]
    broken = deepcopy(manifest)
    broken.pop("owner")
    broken.pop("expires_at")
    broken["public_claim_boundary"] = ""
    broken["manifest_digest"] = "sha256:not-the-digest"

    assert lint_manifest(broken) == [
        "invalid_expires_at",
        "manifest_digest_mismatch",
        "missing_expires_at",
        "missing_owner",
        "missing_public_claim_boundary",
    ]


def test_evidence_linter_fails_on_missing_sources_review_owner_expiry_claim_and_digest() -> None:
    fixture = search_query_brave_route_fixture()
    evidence = deepcopy(fixture["evidence_packet"])
    evidence["sources"] = []
    evidence["reviews"] = []
    evidence.pop("owner")
    evidence.pop("reviewer")
    evidence.pop("evidence_expires_at")
    evidence["public_claim_boundary"] = ""
    evidence["evidence_packet_digest"] = "sha256:not-the-digest"

    assert lint_evidence_packet(evidence, fixture["manifest"]) == [
        "evidence_packet_digest_mismatch",
        "invalid_evidence_expires_at",
        "missing_evidence_expires_at",
        "missing_owner",
        "missing_public_claim_boundary",
        "missing_reviewer",
        "missing_reviews",
        "missing_sources",
    ]


def test_route_candidate_uses_index_fixture_for_search_query_brave_search_api() -> None:
    candidate = route_candidate_from_provider(
        capability_id="search.query",
        provider={
            "service_slug": "brave-search-api",
            "service_id": "fake-service",
            "route_id": "route_fake_override",
            "substrate": "browser_discovered_private_endpoint",
            "provenance_origin": "browser_observed",
            "source_risk": "anti_bot_or_tos_sensitive",
            "promotion_state": "blocked",
            "review_status": "quarantined",
            "manifest_id": "manifest_fake_override",
            "manifest_digest": "sha256:fake-manifest",
            "manifest_version": "fake-version",
            "evidence_packet_id": "evidence_fake_override",
            "evidence_packet_digest": "sha256:fake-evidence",
            "evidence_expires_at": "2000-01-01T00:00:00Z",
            "endpoint_pattern": "GET /res/v1/web/search",
            "credential_mode": "rhumb_managed",
            "configured": True,
            "required_scopes": ["fake.scope"],
            "data_classes": ["fake_private_data"],
            "side_effect_class": "destructive",
        },
        rank=1,
        selected_provider_id="brave-search-api",
        alternatives_considered=["brave-search-api"],
    )

    fixture = route_fixture_for("search.query", "brave-search-api")
    assert fixture is not None
    assert candidate["route_id"] == fixture["manifest"]["route_id"]
    assert candidate["service_id"] == "brave-search"
    assert candidate["substrate"] == fixture["manifest"]["substrate"]
    assert candidate["provenance_origin"] == fixture["manifest"]["provenance_origin"]
    assert candidate["source_risk"] == fixture["manifest"]["source_risk"]
    assert candidate["promotion_state"] == fixture["evidence_packet"]["promotion_state"]
    assert candidate["manifest_id"] == fixture["manifest"]["manifest_id"]
    assert candidate["manifest_digest"] == fixture["manifest"]["manifest_digest"]
    assert candidate["manifest_version"] == fixture["manifest"]["manifest_version"]
    assert candidate["evidence_packet_id"] == fixture["evidence_packet"]["evidence_packet_id"]
    assert candidate["evidence_packet_digest"] == fixture["evidence_packet"]["evidence_packet_digest"]
    assert candidate["evidence_expires_at"] == fixture["evidence_packet"]["evidence_expires_at"]
    assert candidate["review_status"] == "current"
    assert candidate["required_scopes"] == fixture["manifest"]["required_scopes"]
    assert candidate["data_classes"] == fixture["manifest"]["data_classes"]
    assert candidate["side_effect_class"] == "read"
