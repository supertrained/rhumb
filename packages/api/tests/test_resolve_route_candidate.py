"""PP-14 route candidate schema/state-machine coverage."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app
from schemas.resolve_route_candidate import (
    SAFETY_STATES,
    STOP_CONDITIONS,
    infer_safety_state_and_stop,
    route_candidate_from_provider,
    route_candidates_from_resolve_data,
)


@pytest.mark.parametrize(
    ("provider", "expected_state", "expected_stop"),
    [
        ({"endpoint_pattern": "GET /res/v1/web/search", "configured": True}, "executable", None),
        ({"endpoint_pattern": "GET /res/v1/web/search", "configured": False}, "requires_credentials", "missing_credentials"),
        ({"endpoint_pattern": "POST /danger", "requires_confirmation": True}, "requires_confirmation", "high_risk_requires_confirmation"),
        ({"endpoint_pattern": "GET /x", "blocked_security": True}, "blocked_security", "unverified_artifact"),
        ({"endpoint_pattern": "GET /x", "blocked_policy": True}, "blocked_policy", "policy_denied"),
        ({"endpoint_pattern": None}, "unsupported", "missing_manifest"),
        ({"endpoint_pattern": "GET /x", "promotion_state": "experimental_non_default"}, "experimental_non_default", None),
        ({"endpoint_pattern": "GET /x", "kill_switch_state": "unavailable"}, "blocked_security", "kill_switch_state_unavailable"),
        ({"safety_state": "requires_credentials"}, "requires_credentials", "missing_credentials"),
        ({"safety_state": "requires_confirmation"}, "requires_confirmation", "high_risk_requires_confirmation"),
        ({"safety_state": "blocked_policy"}, "blocked_policy", "policy_denied"),
        ({"safety_state": "blocked_security"}, "blocked_security", "unverified_artifact"),
        ({"safety_state": "unsupported"}, "unsupported", "unsupported"),
    ],
)

def test_route_candidate_state_machine_covers_required_pp14_states(provider, expected_state, expected_stop) -> None:
    assert infer_safety_state_and_stop(provider) == (expected_state, expected_stop)
    assert expected_state in SAFETY_STATES
    if expected_stop is not None:
        assert expected_stop in STOP_CONDITIONS


def test_route_candidate_contains_canonical_core_fields() -> None:
    candidate = route_candidate_from_provider(
        capability_id="search.query",
        provider={
            "service_slug": "brave-search-api",
            "provider_id": "brave-search-api",
            "endpoint_pattern": "GET /res/v1/web/search",
            "credential_modes": ["byok"],
            "configured": True,
            "substrate": "official_api",
            "provenance_origin": "vendor_official",
            "source_risk": "verified_low",
            "promotion_state": "production_executable",
            "review_status": "current",
            "manifest_id": "manifest_brave_search_v1",
            "manifest_digest": "sha256:manifest",
            "evidence_packet_id": "evidence_brave_search_v1",
            "evidence_packet_digest": "sha256:evidence",
            "receipt_support": "verifiable",
        },
        rank=1,
        selected_provider_id="brave-search-api",
        alternatives_considered=["brave-search-api"],
    )

    assert candidate["route_candidate_id"].startswith("route_candidate_01_brave_search_api_")
    assert candidate["route_id"] == "route_search_query_brave_search_api_official_api_v1"
    assert candidate["capability_id"] == "search.query"
    assert candidate["service_id"] == "brave-search"
    assert candidate["provider_id"] == "brave-search-api"
    assert candidate["substrate"] == "official_api"
    assert candidate["provenance_origin"] == "rhumb_managed"
    assert candidate["source_risk"] == "verified_low"
    assert candidate["promotion_state"] == "beta_executable"
    assert candidate["review_status"] == "current"
    assert candidate["safety_state"] == "executable"
    assert candidate["stop_condition"] is None
    assert candidate["credential_mode"] == "byok"
    assert candidate["receipt_support"] == "verifiable"
    assert candidate["why_selected"] == "highest_ranked_executable_candidate"


def test_estimate_payload_builds_single_route_candidate_with_auth_stop() -> None:
    candidates = route_candidates_from_resolve_data(
        {
            "capability_id": "workflow_run.list",
            "provider": "github",
            "credential_mode": "byok",
            "endpoint_pattern": "POST /v2/capabilities/workflow_run.list/execute",
            "execute_readiness": {"status": "auth_required"},
        }
    )

    assert len(candidates) == 1
    assert candidates[0]["provider_id"] == "github"
    assert candidates[0]["safety_state"] == "requires_credentials"
    assert candidates[0]["stop_condition"] == "missing_credentials"


@pytest.mark.anyio
async def test_v2_resolve_exposes_route_candidates_from_current_resolve_payload(monkeypatch) -> None:
    async def mock_forward(*_args, **_kwargs):
        class Response:
            status_code = 200
            headers = {}

            @staticmethod
            def json():
                return {
                    "data": {
                        "capability": "search.query",
                        "providers": [
                            {
                                "service_slug": "brave-search-api",
                                "endpoint_pattern": "GET /res/v1/web/search",
                                "credential_modes": ["byok"],
                                "configured": True,
                                "available_for_execute": True,
                            },
                            {
                                "service_slug": "browser-private-search",
                                "endpoint_pattern": "GET /private/search",
                                "credential_modes": ["byok"],
                                "blocked_security": True,
                                "stop_condition": "anti_bot_or_access_control_risk",
                                "substrate": "browser_discovered_private_endpoint",
                                "provenance_origin": "browser_observed",
                                "source_risk": "anti_bot_or_tos_sensitive",
                            },
                        ],
                        "fallback_chain": [],
                        "related_bundles": [],
                        "execute_hint": {"preferred_provider": "brave-search-api"},
                    },
                    "error": None,
                }

        return Response()

    monkeypatch.setattr("routes.resolve_v2._forward_internal", mock_forward)

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v2/capabilities/search.query/resolve")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["route_contract"]["contract_id"] == "resolve_route_candidate_v1"
    assert data["route_contract"]["source"] == "PP-14"
    assert [candidate["provider_id"] for candidate in data["route_candidates"]] == [
        "brave-search-api",
        "browser-private-search",
    ]
    assert data["route_candidates"][0]["safety_state"] == "executable"
    assert data["route_candidates"][1]["safety_state"] == "blocked_security"
    assert data["route_candidates"][1]["stop_condition"] == "anti_bot_or_access_control_risk"


@pytest.mark.anyio
async def test_v2_estimate_exposes_route_candidate_from_estimate_payload(monkeypatch) -> None:
    async def mock_forward(*_args, **_kwargs):
        class Response:
            status_code = 200
            headers = {}

            @staticmethod
            def json():
                return {
                    "data": {
                        "capability_id": "workflow_run.list",
                        "provider": "github",
                        "credential_mode": "byo",
                        "endpoint_pattern": "POST /v1/capabilities/workflow_run.list/execute",
                        "cost_estimate_usd": 0.01,
                        "execute_readiness": {"status": "auth_required"},
                    },
                    "error": None,
                }

        return Response()

    monkeypatch.setattr("routes.resolve_v2._forward_internal", mock_forward)

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v2/capabilities/workflow_run.list/execute/estimate")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["credential_mode"] == "byok"
    assert data["route_candidates"][0]["provider_id"] == "github"
    assert data["route_candidates"][0]["safety_state"] == "requires_credentials"
    assert data["route_candidates"][0]["stop_condition"] == "missing_credentials"
