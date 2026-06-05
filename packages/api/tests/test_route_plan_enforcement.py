from __future__ import annotations

from schemas.resolve_boundary_contract import ROUTE_PLAN_ENFORCEMENT_CHECKS
from services.route_plan_enforcement import (
    canonical_json_sha256,
    issue_route_plan,
    validate_route_plan,
)

SECRET = "test-route-plan-secret"
NOW = 1_800_000_000


def _payload() -> dict[str, object]:
    return {
        "route_plan_id": "rp_test_001",
        "nonce": "nonce-test-001",
        "org_id": "org_123",
        "agent_id": "agent_456",
        "principal_id": "principal_789",
        "auth_rail": "oauth",
        "capability_id": "cap_search_query",
        "service_id": "search",
        "provider_id": "brave-search-api",
        "route_id": "route_search_query_brave_api_v1",
        "credential_mode": "delegated",
        "credential_handle_id": "cred_abc",
        "required_scopes": ["search.query", "search.read"],
        "input_hash": canonical_json_sha256({"query": "weather", "filters": {"freshness": "day"}}),
        "manifest_digest": "sha256:manifest",
        "evidence_packet_digest": "sha256:evidence",
        "policy_snapshot_digest": "sha256:policy",
        "budget_snapshot_digest": "sha256:budget",
        "sandbox_profile_id": "sandbox_readonly_net",
        "artifact_hashes": ["sha256:artifact-a", "sha256:artifact-b"],
    }


def _expected() -> dict[str, object]:
    expected = _payload()
    expected["granted_scopes"] = ["search.query", "search.read", "search.admin"]
    return expected


def _token(payload: dict[str, object] | None = None, *, ttl_seconds: int = 300) -> str:
    return issue_route_plan(payload or _payload(), SECRET, now=NOW, ttl_seconds=ttl_seconds)


def test_valid_route_plan_round_trip_allows_and_records_nonce() -> None:
    seen_nonces: set[str] = set()
    token = _token()

    result = validate_route_plan(token, _expected(), SECRET, now=NOW + 1, seen_nonces=seen_nonces)

    assert token.startswith("rhrp1.")
    assert token.count(".") == 2
    assert result["allowed"] is True
    assert result["stop_condition"] is None
    assert set(ROUTE_PLAN_ENFORCEMENT_CHECKS).issubset(result["checks"])
    assert all(result["checks"].values())
    assert seen_nonces == {"nonce-test-001"}


def test_expired_route_plan_fails_closed() -> None:
    result = validate_route_plan(_token(ttl_seconds=5), _expected(), SECRET, now=NOW + 5)

    assert result["allowed"] is False
    assert result["stop_condition"] == "route_plan_expired"
    assert result["checks"]["signature_valid"] is True
    assert result["checks"]["not_expired"] is False


def test_bad_signature_fails_closed() -> None:
    token = _token()
    bad_token = token[:-1] + ("A" if token[-1] != "A" else "B")

    result = validate_route_plan(bad_token, _expected(), SECRET, now=NOW + 1)

    assert result["allowed"] is False
    assert result["stop_condition"] == "route_plan_signature_invalid"
    assert result["checks"]["signature_valid"] is False


def test_principal_mismatch_uses_principal_stop() -> None:
    expected = _expected()
    expected["principal_id"] = "principal_other"

    result = validate_route_plan(_token(), expected, SECRET, now=NOW + 1)

    assert result["allowed"] is False
    assert result["stop_condition"] == "route_plan_principal_mismatch"
    assert result["checks"]["principal_matches"] is False


def test_route_and_provider_mismatch_uses_route_plan_mismatch() -> None:
    expected = _expected()
    expected["route_id"] = "route_search_query_other_v1"
    expected["provider_id"] = "other-provider"

    result = validate_route_plan(_token(), expected, SECRET, now=NOW + 1)

    assert result["allowed"] is False
    assert result["stop_condition"] == "route_plan_mismatch"
    assert result["checks"]["route_id_matches"] is False
    assert result["checks"]["provider_id_matches"] is False


def test_missing_required_scope_uses_credential_scope_stop() -> None:
    expected = _expected()
    expected["granted_scopes"] = ["search.query"]

    result = validate_route_plan(_token(), expected, SECRET, now=NOW + 1)

    assert result["allowed"] is False
    assert result["stop_condition"] == "credential_scope_mismatch"
    assert result["checks"]["required_scopes_covered"] is False


def test_revoked_nonce_fails_closed() -> None:
    result = validate_route_plan(
        _token(),
        _expected(),
        SECRET,
        now=NOW + 1,
        revoked_nonces={"nonce-test-001"},
    )

    assert result["allowed"] is False
    assert result["stop_condition"] == "route_plan_revoked"
    assert result["checks"]["not_revoked"] is False


def test_replay_nonce_fails_closed() -> None:
    result = validate_route_plan(
        _token(),
        _expected(),
        SECRET,
        now=NOW + 1,
        seen_nonces={"nonce-test-001"},
    )

    assert result["allowed"] is False
    assert result["stop_condition"] == "route_plan_replay"
    assert result["checks"]["replay_not_seen"] is False


def test_canonical_input_hash_is_stable_for_key_order() -> None:
    left = {"b": [2, 1], "a": {"z": True, "x": None}}
    right = {"a": {"x": None, "z": True}, "b": [2, 1]}

    assert canonical_json_sha256(left) == canonical_json_sha256(right)
    assert canonical_json_sha256(left).startswith("sha256:")
    assert canonical_json_sha256(left) != canonical_json_sha256({"b": [1, 2], "a": right["a"]})
