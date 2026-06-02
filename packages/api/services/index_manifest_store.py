"""Index manifest store seam for route truth facts.

PP-1/PP-2 currently use an in-repo fixture registry, but callers should depend
on this service rather than importing fixture constructors directly.  That gives
Resolve, explanations, receipts/log surfaces, and future durable storage one
stable lookup interface for command manifests and route facts.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from schemas.capability_manifest import command_manifest_fixtures
from schemas.index_evidence import route_fixture_for
from schemas.route_taxonomy import route_recommendation_policy


class IndexManifestStore:
    """Read-only PP-2 manifest registry abstraction."""

    source = "PP-2"
    status = "fixture_registry_until_index_store"
    contract_id = "index_command_manifest_v1"

    def __init__(self, manifests: list[dict[str, Any]] | None = None) -> None:
        self._manifests = [deepcopy(manifest) for manifest in (manifests or command_manifest_fixtures())]
        self._by_route_id = {str(manifest.get("route_id")): manifest for manifest in self._manifests}

    def list_manifests(
        self,
        *,
        capability_id: str | None = None,
        substrate: str | None = None,
        provenance_origin: str | None = None,
        source_risk: str | None = None,
    ) -> list[dict[str, Any]]:
        manifests = [
            manifest
            for manifest in self._manifests
            if (capability_id is None or manifest.get("capability_id") == capability_id)
            and (substrate is None or manifest.get("substrate") == substrate)
            and (provenance_origin is None or manifest.get("provenance_origin") == provenance_origin)
            and (source_risk is None or manifest.get("source_risk") == source_risk)
        ]
        manifests.sort(key=lambda item: (str(item.get("capability_id") or ""), str(item.get("route_id") or "")))
        return [deepcopy(manifest) for manifest in manifests]

    def get_manifest(self, route_id: str) -> dict[str, Any] | None:
        manifest = self._by_route_id.get(route_id)
        return deepcopy(manifest) if manifest is not None else None

    def route_facts_for_provider(self, capability_id: str, provider_id: str) -> dict[str, Any]:
        """Return manifest/evidence route facts for a capability/provider pair."""

        fixture = route_fixture_for(capability_id, provider_id)
        manifest = fixture.get("manifest") if isinstance(fixture, dict) else None
        evidence_packet = fixture.get("evidence_packet") if isinstance(fixture, dict) else None

        if not isinstance(manifest, dict):
            candidates = self.list_manifests(capability_id=capability_id)
            for candidate in candidates:
                if candidate.get("provider_id") == provider_id:
                    manifest = candidate
                    break

        if not isinstance(manifest, dict):
            return {}

        route: dict[str, Any] = {
            "route_id": manifest.get("route_id"),
            "service_id": manifest.get("service_id"),
            "provider_id": manifest.get("provider_id"),
            "substrate": manifest.get("substrate"),
            "provenance_origin": manifest.get("provenance_origin"),
            "source_risk": manifest.get("source_risk"),
            "manifest_id": manifest.get("manifest_id"),
            "manifest_digest": manifest.get("manifest_digest"),
            "manifest_version": manifest.get("manifest_version"),
            "side_effect_class": manifest.get("side_effect_class"),
            "public_claim_boundary": manifest.get("public_claim_boundary"),
        }
        if isinstance(evidence_packet, dict):
            route.update(
                {
                    "evidence_packet_id": evidence_packet.get("evidence_packet_id"),
                    "evidence_packet_digest": evidence_packet.get("evidence_packet_digest"),
                    "review_status": evidence_packet.get("review_status"),
                    "promotion_state": evidence_packet.get("promotion_state"),
                    "evidence_expires_at": evidence_packet.get("evidence_expires_at"),
                }
            )

        policy = route_recommendation_policy(route)
        route["recommendation_policy"] = {
            "default_recommendable": policy["default_recommendable"],
            "recommendable": policy["recommendable"],
            "requires_explicit_request": policy["requires_explicit_request"],
            "blocked": policy["blocked"],
            "reasons": policy["reasons"],
        }
        return {key: value for key, value in route.items() if value is not None}


def with_recommendation_policy(manifest: dict[str, Any]) -> dict[str, Any]:
    policy = route_recommendation_policy(manifest)
    return {
        **manifest,
        "recommendation_policy": {
            "default_recommendable": policy["default_recommendable"],
            "recommendable": policy["recommendable"],
            "requires_explicit_request": policy["requires_explicit_request"],
            "blocked": policy["blocked"],
            "reasons": policy["reasons"],
        },
    }


def get_index_manifest_store() -> IndexManifestStore:
    return IndexManifestStore()
