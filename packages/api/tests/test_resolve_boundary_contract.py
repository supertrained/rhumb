"""PP-0 boundary contract coverage for Index / Resolve / Runtime vNext."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app
from schemas.resolve_boundary_contract import (
    FIELD_OWNERSHIP_MATRIX,
    INDEX_STORED_FIELDS,
    ROUTE_PLAN_ENFORCEMENT_CHECKS,
    RUNTIME_FORBIDDEN_DECISION_FIELDS,
    boundary_contract_payload,
    missing_route_plan_enforcement_checks,
    runtime_decision_mutations,
    unexpected_resolve_owned_index_fields,
)


@pytest.mark.asyncio
async def test_boundary_contract_endpoint_exposes_pp0_ownership_interface() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/v2/boundary-contract")

    assert response.status_code == 200
    payload = response.json()
    assert payload["error"] is None
    data = payload["data"]

    assert data["contract_id"] == "index_resolve_runtime_boundary_v1"
    assert data["source"] == "PP-0"
    assert data["status"] == "active"
    assert {layer["owner"] for layer in data["layers"]} == {"index", "resolve", "runtime"}

    matrix = {row["group"]: row for row in data["field_ownership_matrix"]}
    assert "stable_identity" in matrix
    assert "route_id" in matrix["stable_identity"]["index_stored"]
    assert "selected_route_id" in matrix["stable_identity"]["resolve_computed"]
    assert "execution_id" in matrix["stable_identity"]["runtime_issued"]

    runtime_layer = next(layer for layer in data["layers"] if layer["owner"] == "runtime")
    assert "rank or rerank route candidates" in runtime_layer["must_not"]
    assert "an_score" in data["runtime_forbidden_decision_fields"]
    assert "principal_matches" in data["route_plan_enforcement_checks"]
    assert data["_rhumb_v2"]["layer"] == 2


def test_contract_has_single_owner_for_core_field_groups() -> None:
    payload = boundary_contract_payload()
    matrix = payload["field_ownership_matrix"]

    for row in matrix:
        assert row["index_stored"] or row["resolve_computed"] or row["runtime_issued"]
        assert not set(row["index_stored"]).intersection(row["resolve_computed"])
        assert not set(row["index_stored"]).intersection(row["runtime_issued"])
        assert not set(row["resolve_computed"]).intersection(row["runtime_issued"])

    assert {"service_id", "provider_id", "capability_id", "route_id"}.issubset(INDEX_STORED_FIELDS)


def test_contract_fields_have_single_global_owner() -> None:
    seen: dict[str, str] = {}
    for row in FIELD_OWNERSHIP_MATRIX:
        for bucket in ("index_stored", "resolve_computed", "runtime_issued"):
            for field in getattr(row, bucket):
                owner = f"{row.group}.{bucket}"
                assert field not in seen, f"{field} is owned by both {seen[field]} and {owner}"
                seen[field] = owner


def test_resolve_computed_blob_cannot_smuggle_index_truth() -> None:
    candidate = {
        "route_id": "route_search_query_brave_api_v1",
        "provider_id": "brave-search-api",
        "resolve_computed": {
            "selected_route_id": "route_search_query_brave_api_v1",
            "safety_state": "executable",
            "manifest_digest": "sha256:resolve-must-not-invent-this",
        },
    }

    assert unexpected_resolve_owned_index_fields(candidate) == {"manifest_digest"}


def test_runtime_payload_cannot_rerank_or_mutate_resolve_decision() -> None:
    runtime_payload = {
        "execution_id": "exec_123",
        "receipt_id": "rcpt_123",
        "runtime_issued": {
            "receipt_status": "issued",
            "an_score": 9.9,
        },
        "selected_route_id": "runtime-picked-route",
    }

    assert runtime_decision_mutations(runtime_payload) == {"an_score", "selected_route_id"}
    assert "an_score" in RUNTIME_FORBIDDEN_DECISION_FIELDS


def test_route_plan_checks_fail_closed_until_every_required_check_passes() -> None:
    checks = {name: True for name in ROUTE_PLAN_ENFORCEMENT_CHECKS}
    checks["principal_matches"] = False
    del checks["not_revoked"]

    assert missing_route_plan_enforcement_checks(checks) == {"principal_matches", "not_revoked"}
    assert missing_route_plan_enforcement_checks({name: True for name in ROUTE_PLAN_ENFORCEMENT_CHECKS}) == set()
