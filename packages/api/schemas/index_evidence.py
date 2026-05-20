"""Rhumb Index evidence packet and manifest model.

PP-15 creates the minimal Index substrate that backs Resolve route decisions:
versioned manifests, evidence packets, deterministic digests, validation, and a
core `search.query` / `brave-search-api` official API fixture.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
from typing import Any

REVIEW_STATES = frozenset({"draft", "current", "stale", "expired", "quarantined", "superseded", "missing"})
PROMOTION_STATES = frozenset({"indexed", "candidate", "fixture_only", "experimental_non_default", "beta_executable", "production_executable", "blocked", "deprecated"})
SUBSTRATES = frozenset({"official_api", "documented_public_endpoint", "official_cli", "official_mcp", "official_sdk", "sdk_code_mode", "generated_adapter", "browser_discovered_private_endpoint", "user_authorized_private_endpoint"})
PROVENANCE_ORIGINS = frozenset({"vendor_official", "vendor_authorized", "rhumb_managed", "community_submitted", "rhumb_generated", "user_authorized", "browser_observed", "unknown"})
SOURCE_RISKS = frozenset({"verified_low", "community_unverified", "experimental_private", "deprecated_fragile", "anti_bot_or_tos_sensitive", "payment_or_real_world_write", "unsupported"})

DIGEST_FIELDS = frozenset({"manifest_digest", "evidence_packet_digest"})

INDEX_ENTITY_VOCABULARY = {
    "service": "Stable vendor/service identity, e.g. Brave Search.",
    "provider": "Concrete execution/catalog provider/config under a service, e.g. brave-search-api.",
    "capability": "User-intent/action class, e.g. search.query.",
    "route": "Stable way to perform a capability through a provider/substrate.",
    "adapter_artifact": "Executable or descriptive artifact used by a route.",
    "manifest": "Versioned machine-readable contract for a route/action.",
    "evidence_packet": "Versioned bundle supporting a manifest/route.",
    "route_review": "Freshness, security, claim-safety, and promotion review state.",
    "public_claim_boundary": "Text Rhumb is allowed to say publicly about the route.",
    "an_score_input": "General trust evidence, separate from per-user Resolve route choice.",
}


def _without_digest_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _without_digest_fields(item)
            for key, item in value.items()
            if str(key) not in DIGEST_FIELDS
        }
    if isinstance(value, list):
        return [_without_digest_fields(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    """Serialize deterministic canonical JSON for Index digests."""

    return json.dumps(
        _without_digest_fields(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def canonical_sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def manifest_digest(manifest: dict[str, Any]) -> str:
    return canonical_sha256(manifest)


def evidence_packet_digest(evidence_packet: dict[str, Any]) -> str:
    return canonical_sha256(evidence_packet)


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def lint_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = [
        "manifest_id",
        "manifest_version",
        "route_id",
        "service_id",
        "provider_id",
        "capability_id",
        "substrate",
        "provenance_origin",
        "source_risk",
        "credential_modes",
        "side_effect_class",
        "owner",
        "expires_at",
        "public_claim_boundary",
    ]
    for field in required:
        if manifest.get(field) in (None, "", []):
            errors.append(f"missing_{field}")

    if manifest.get("substrate") not in SUBSTRATES:
        errors.append("invalid_substrate")
    if manifest.get("provenance_origin") not in PROVENANCE_ORIGINS:
        errors.append("invalid_provenance_origin")
    if manifest.get("source_risk") not in SOURCE_RISKS:
        errors.append("invalid_source_risk")
    if manifest.get("side_effect_class") not in {"read", "write", "admin", "payment", "destructive"}:
        errors.append("invalid_side_effect_class")
    if not isinstance(manifest.get("credential_modes"), list) or not all(isinstance(item, str) and item for item in manifest.get("credential_modes", [])):
        errors.append("invalid_credential_modes")
    if _parse_time(manifest.get("expires_at")) is None:
        errors.append("invalid_expires_at")

    expected_digest = manifest_digest(manifest)
    if manifest.get("manifest_digest") != expected_digest:
        errors.append("manifest_digest_mismatch")
    return sorted(set(errors))


def lint_evidence_packet(evidence_packet: dict[str, Any], manifest: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    required = [
        "evidence_packet_id",
        "route_id",
        "service_id",
        "provider_id",
        "capability_id",
        "manifest_id",
        "manifest_version",
        "manifest_digest",
        "sources",
        "reviews",
        "owner",
        "reviewer",
        "freshness_checked_at",
        "evidence_expires_at",
        "review_status",
        "promotion_state",
        "public_claim_boundary",
    ]
    for field in required:
        if evidence_packet.get(field) in (None, "", []):
            errors.append(f"missing_{field}")

    if evidence_packet.get("review_status") not in REVIEW_STATES:
        errors.append("invalid_review_status")
    if evidence_packet.get("promotion_state") not in PROMOTION_STATES:
        errors.append("invalid_promotion_state")
    if evidence_packet.get("substrate") not in SUBSTRATES:
        errors.append("invalid_substrate")
    if evidence_packet.get("provenance_origin") not in PROVENANCE_ORIGINS:
        errors.append("invalid_provenance_origin")
    if evidence_packet.get("source_risk") not in SOURCE_RISKS:
        errors.append("invalid_source_risk")
    if _parse_time(evidence_packet.get("freshness_checked_at")) is None:
        errors.append("invalid_freshness_checked_at")
    if _parse_time(evidence_packet.get("evidence_expires_at")) is None:
        errors.append("invalid_evidence_expires_at")

    sources = evidence_packet.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append("missing_sources")
    elif not all(isinstance(source, dict) and source.get("url") and source.get("kind") for source in sources):
        errors.append("invalid_sources")

    reviews = evidence_packet.get("reviews")
    if not isinstance(reviews, list) or not reviews:
        errors.append("missing_reviews")
    elif not all(isinstance(review, dict) and review.get("reviewer") and review.get("verdict") for review in reviews):
        errors.append("invalid_reviews")

    if manifest is not None:
        if evidence_packet.get("manifest_digest") != manifest_digest(manifest):
            errors.append("linked_manifest_digest_mismatch")
        for field in ("route_id", "service_id", "provider_id", "capability_id", "manifest_id", "manifest_version"):
            if evidence_packet.get(field) != manifest.get(field):
                errors.append(f"linked_{field}_mismatch")

    expected_digest = evidence_packet_digest(evidence_packet)
    if evidence_packet.get("evidence_packet_digest") != expected_digest:
        errors.append("evidence_packet_digest_mismatch")
    return sorted(set(errors))


def lint_index_route_fixture(route_fixture: dict[str, Any]) -> list[str]:
    manifest = route_fixture.get("manifest") if isinstance(route_fixture.get("manifest"), dict) else {}
    evidence_packet = route_fixture.get("evidence_packet") if isinstance(route_fixture.get("evidence_packet"), dict) else {}
    errors = [f"manifest:{error}" for error in lint_manifest(manifest)]
    errors.extend(f"evidence_packet:{error}" for error in lint_evidence_packet(evidence_packet, manifest))
    if route_fixture.get("entity_vocabulary") != INDEX_ENTITY_VOCABULARY:
        errors.append("entity_vocabulary_mismatch")
    return sorted(set(errors))


def _base_search_query_manifest() -> dict[str, Any]:
    return {
        "manifest_id": "manifest_search_query_brave_search_api_official_api_v1",
        "manifest_version": "2026-05-19.1",
        "route_id": "route_search_query_brave_search_api_official_api_v1",
        "service_id": "brave-search",
        "provider_id": "brave-search-api",
        "capability_id": "search.query",
        "substrate": "official_api",
        "provenance_origin": "rhumb_managed",
        "source_risk": "verified_low",
        "adapter_artifact_id": "adapter_config_brave_search_api_v1",
        "credential_modes": ["rhumb_managed"],
        "required_scopes": [],
        "data_classes": ["web_search_query", "public_web_results"],
        "side_effect_class": "read",
        "endpoint_pattern": "GET /res/v1/web/search",
        "cost_model": {"unit": "call", "estimated_cost_usd": 0.003},
        "rate_limit_model": {"provider_limit_source": "vendor_dashboard", "enforced_by": "Rhumb budget and provider account limits"},
        "confirmation_policy": "none",
        "sandbox_profile_class": "network_official_api_readonly",
        "owner": "Pedro",
        "expires_at": "2026-08-17T00:00:00Z",
        "public_claim_boundary": "Rhumb can route read-only web search queries through a Rhumb-managed Brave Search API route when the caller has a valid governed Rhumb key and available credit.",
        "an_score_input_refs": ["scores:service:brave-search"],
    }


def search_query_brave_manifest() -> dict[str, Any]:
    manifest = _base_search_query_manifest()
    manifest["manifest_digest"] = manifest_digest(manifest)
    return manifest


def _base_search_query_evidence_packet(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "evidence_packet_id": "evidence_search_query_brave_search_api_official_api_2026_05_19",
        "route_id": manifest["route_id"],
        "service_id": manifest["service_id"],
        "provider_id": manifest["provider_id"],
        "capability_id": manifest["capability_id"],
        "manifest_id": manifest["manifest_id"],
        "manifest_version": manifest["manifest_version"],
        "manifest_digest": manifest["manifest_digest"],
        "substrate": manifest["substrate"],
        "provenance_origin": manifest["provenance_origin"],
        "source_risk": manifest["source_risk"],
        "side_effect_class": manifest["side_effect_class"],
        "credential_modes": manifest["credential_modes"],
        "sources": [
            {
                "kind": "vendor_docs",
                "url": "https://api-dashboard.search.brave.com/app/documentation/web-search/get-started",
                "observed_at": "2026-05-19T17:05:18Z",
                "observed_title": "Documentation - Brave Search API",
            },
            {
                "kind": "rhumb_contract",
                "url": "docs/INDEX-RESOLVE-VNEXT-PRD-ROADMAP-2026-05-19.md#core-searchquery-index-fixture",
                "observed_at": "2026-05-19T17:05:18Z",
            },
        ],
        "runtime_witnesses": [
            {
                "kind": "planned_first_call_fixture",
                "status": "pending_PP-9_live_receipt",
                "capability_id": "search.query",
                "provider_id": "brave-search-api",
            }
        ],
        "reviews": [
            {
                "reviewer": "Pedro",
                "verdict": "current_for_core_fixture",
                "reviewed_at": "2026-05-19T17:05:18Z",
                "scope": "schema_and_source_fixture; live first-call receipt lands in PP-9",
            }
        ],
        "owner": "Pedro",
        "reviewer": "Pedro",
        "freshness_checked_at": "2026-05-19T17:05:18Z",
        "evidence_expires_at": "2026-08-17T00:00:00Z",
        "review_status": "current",
        "promotion_state": "beta_executable",
        "public_claim_boundary": manifest["public_claim_boundary"],
        "an_score_input_refs": manifest["an_score_input_refs"],
        "resolve_separation_note": "This packet supports route trust. Resolve still decides per-user auth, budget, policy, and risk at request time.",
    }


def search_query_brave_evidence_packet() -> dict[str, Any]:
    manifest = search_query_brave_manifest()
    evidence_packet = _base_search_query_evidence_packet(manifest)
    evidence_packet["evidence_packet_digest"] = evidence_packet_digest(evidence_packet)
    return evidence_packet


def search_query_brave_route_fixture() -> dict[str, Any]:
    manifest = search_query_brave_manifest()
    evidence_packet = _base_search_query_evidence_packet(manifest)
    evidence_packet["evidence_packet_digest"] = evidence_packet_digest(evidence_packet)
    return {
        "fixture_id": "index_fixture_search_query_brave_search_api_2026_05_19",
        "entity_vocabulary": deepcopy(INDEX_ENTITY_VOCABULARY),
        "manifest": manifest,
        "evidence_packet": evidence_packet,
    }


def route_fixture_for(capability_id: str, provider_id: str) -> dict[str, Any] | None:
    if capability_id == "search.query" and provider_id == "brave-search-api":
        return search_query_brave_route_fixture()
    return None
