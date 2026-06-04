"""Pure-Python HMAC helper for Resolve-issued Runtime route plans."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime
from typing import Any

from schemas.resolve_boundary_contract import ROUTE_PLAN_ENFORCEMENT_CHECKS

TOKEN_PREFIX = "rhrp1"
ROUTE_PLAN_VERSION = 1

REQUIRED_PAYLOAD_FIELDS = (
    "version",
    "route_plan_id",
    "nonce",
    "org_id",
    "agent_id",
    "principal_id",
    "auth_rail",
    "capability_id",
    "service_id",
    "provider_id",
    "route_id",
    "credential_mode",
    "required_scopes",
    "input_hash",
    "manifest_digest",
    "policy_snapshot_digest",
    "budget_snapshot_digest",
    "artifact_hashes",
    "issued_at",
    "expires_at",
)

OPTIONAL_MATCH_FIELDS = (
    "credential_handle_id",
    "evidence_packet_digest",
    "sandbox_profile_id",
)

SUPPLEMENTAL_CHECKS = (
    "version_matches",
    "route_plan_id_present",
    "nonce_present",
    "auth_rail_matches",
    "capability_id_matches",
    "service_id_matches",
    "provider_id_matches",
    "credential_mode_matches",
    "required_scopes_covered",
    "sandbox_profile_matches",
    "artifact_hashes_match",
)

EXPECTED_CHECK_FIELDS = (
    ("org_id", "org_matches"),
    ("agent_id", "agent_matches"),
    ("auth_rail", "auth_rail_matches"),
    ("capability_id", "capability_id_matches"),
    ("service_id", "service_id_matches"),
    ("provider_id", "provider_id_matches"),
    ("route_id", "route_id_matches"),
    ("credential_mode", "credential_mode_matches"),
    ("credential_handle_id", "credential_handle_matches"),
    ("input_hash", "input_hash_matches"),
    ("manifest_digest", "manifest_digest_matches"),
    ("evidence_packet_digest", "evidence_packet_digest_matches"),
    ("policy_snapshot_digest", "policy_snapshot_current_or_allowed"),
    ("budget_snapshot_digest", "budget_still_allowed"),
    ("sandbox_profile_id", "sandbox_profile_matches"),
    ("artifact_hashes", "artifact_hashes_match"),
)


def canonical_json_sha256(value: Any) -> str:
    """Return a stable sha256 digest for JSON-compatible input values."""

    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def issue_route_plan(
    payload: dict[str, Any],
    secret: str | bytes,
    now: int | float | datetime | None = None,
    ttl_seconds: int = 300,
) -> str:
    """Issue an opaque signed route-plan token."""

    if ttl_seconds <= 0:
        raise ValueError("ttl_seconds must be positive")

    issued_at = _unix_seconds(now)
    route_plan = dict(payload)
    route_plan.setdefault("version", ROUTE_PLAN_VERSION)
    route_plan.setdefault("route_plan_id", "rp_" + secrets.token_urlsafe(18))
    route_plan.setdefault("nonce", route_plan["route_plan_id"])
    route_plan.setdefault("issued_at", issued_at)
    route_plan.setdefault("expires_at", int(route_plan["issued_at"]) + ttl_seconds)

    missing = _missing_payload_fields(route_plan)
    if missing:
        raise ValueError(f"route plan payload missing required fields: {', '.join(missing)}")
    if not isinstance(route_plan.get("required_scopes"), list):
        raise ValueError("required_scopes must be a list")
    if not isinstance(route_plan.get("artifact_hashes"), list):
        raise ValueError("artifact_hashes must be a list")

    payload_segment = _b64url_encode(_canonical_json_bytes(route_plan))
    signature_segment = _signature_segment(payload_segment, secret)
    return f"{TOKEN_PREFIX}.{payload_segment}.{signature_segment}"


def validate_route_plan(
    token: str | None,
    expected: dict[str, Any],
    secret: str | bytes,
    now: int | float | datetime | None = None,
    revoked_nonces: set[str] | frozenset[str] | list[str] | tuple[str, ...] | None = None,
    seen_nonces: set[str] | frozenset[str] | list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Validate a signed route plan against expected Runtime boundary facts."""

    checks = _blank_checks()
    if not token:
        return _result(False, "route_plan_missing", checks)

    parts = token.split(".")
    if len(parts) != 3 or parts[0] != TOKEN_PREFIX or not parts[1] or not parts[2]:
        return _result(False, "route_plan_missing", checks)

    payload_segment, signature_segment = parts[1], parts[2]
    try:
        expected_signature_segment = _signature_segment(payload_segment, secret)
    except (TypeError, ValueError):
        return _result(False, "route_plan_signature_invalid", checks)

    if not hmac.compare_digest(signature_segment, expected_signature_segment):
        return _result(False, "route_plan_signature_invalid", checks)
    checks["signature_valid"] = True

    try:
        payload = json.loads(_b64url_decode(payload_segment).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return _result(False, "route_plan_signature_invalid", checks)
    if not isinstance(payload, dict):
        return _result(False, "route_plan_missing", checks)

    if _missing_payload_fields(payload):
        return _result(False, "route_plan_missing", checks)
    if not isinstance(payload.get("required_scopes"), list):
        return _result(False, "route_plan_missing", checks)
    if not isinstance(payload.get("artifact_hashes"), list):
        return _result(False, "route_plan_missing", checks)

    checks["version_matches"] = payload.get("version") == ROUTE_PLAN_VERSION
    checks["route_plan_id_present"] = bool(payload.get("route_plan_id"))
    checks["nonce_present"] = bool(payload.get("nonce"))
    if not (checks["version_matches"] and checks["route_plan_id_present"] and checks["nonce_present"]):
        return _result(False, "route_plan_mismatch", checks)

    try:
        expires_at = int(payload["expires_at"])
    except (TypeError, ValueError):
        return _result(False, "route_plan_missing", checks)
    checks["not_expired"] = _unix_seconds(now) < expires_at
    if not checks["not_expired"]:
        return _result(False, "route_plan_expired", checks)

    nonce = str(payload["nonce"])
    revoked = set(revoked_nonces or ())
    checks["not_revoked"] = nonce not in revoked
    if not checks["not_revoked"]:
        return _result(False, "route_plan_revoked", checks)

    seen = set(seen_nonces or ())
    checks["replay_not_seen"] = nonce not in seen
    if not checks["replay_not_seen"]:
        return _result(False, "route_plan_replay", checks)

    expected = expected if isinstance(expected, dict) else {}
    checks["principal_matches"] = payload.get("principal_id") == expected.get("principal_id")
    if not checks["principal_matches"]:
        return _result(False, "route_plan_principal_mismatch", checks)

    for field, check_name in EXPECTED_CHECK_FIELDS:
        checks[check_name] = _field_matches(payload, expected, field)

    checks["required_scopes_covered"] = _required_scopes_covered(payload, expected)
    if not checks["required_scopes_covered"]:
        return _result(False, "credential_scope_mismatch", checks)

    checks["kill_switch_allows_execution"] = _kill_switch_allows_execution(expected)

    mismatch_checks = [
        check_name
        for _, check_name in EXPECTED_CHECK_FIELDS
        if checks.get(check_name) is not True
    ]
    if mismatch_checks or checks["kill_switch_allows_execution"] is not True:
        return _result(False, "route_plan_mismatch", checks)

    _remember_nonce(seen_nonces, nonce)
    result = _result(True, None, checks)
    result.update(
        {
            "nonce": nonce,
            "route_plan_id": str(payload["route_plan_id"]),
            "expires_at": expires_at,
        }
    )
    return result


def _blank_checks() -> dict[str, bool]:
    checks = {name: False for name in ROUTE_PLAN_ENFORCEMENT_CHECKS}
    checks.update({name: False for name in SUPPLEMENTAL_CHECKS})
    return checks


def _result(allowed: bool, stop_condition: str | None, checks: dict[str, bool]) -> dict[str, Any]:
    return {
        "allowed": allowed,
        "stop_condition": stop_condition,
        "checks": checks,
    }


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _unix_seconds(value: int | float | datetime | None) -> int:
    if value is None:
        return int(time.time())
    if isinstance(value, datetime):
        return int(value.timestamp())
    return int(value)


def _missing_payload_fields(payload: dict[str, Any]) -> list[str]:
    return [field for field in REQUIRED_PAYLOAD_FIELDS if payload.get(field) is None]


def _field_matches(payload: dict[str, Any], expected: dict[str, Any], field: str) -> bool:
    if field in OPTIONAL_MATCH_FIELDS and payload.get(field) is None and expected.get(field) is None:
        return True
    if field == "policy_snapshot_digest":
        return _digest_matches(payload, expected, field, "allowed_policy_snapshot_digests")
    if field == "budget_snapshot_digest":
        return _digest_matches(payload, expected, field, "allowed_budget_snapshot_digests")
    if field == "evidence_packet_digest":
        return _digest_matches(payload, expected, field, "allowed_evidence_packet_digests")
    return field in expected and payload.get(field) == expected.get(field)


def _digest_matches(
    payload: dict[str, Any], expected: dict[str, Any], field: str, allowed_field: str
) -> bool:
    if field in OPTIONAL_MATCH_FIELDS and payload.get(field) is None and expected.get(field) is None:
        return True
    if field in expected:
        return payload.get(field) == expected.get(field)
    allowed = expected.get(allowed_field)
    if isinstance(allowed, (list, tuple, set, frozenset)):
        return payload.get(field) in set(allowed)
    return False


def _required_scopes_covered(payload: dict[str, Any], expected: dict[str, Any]) -> bool:
    required_scopes = payload.get("required_scopes")
    if not isinstance(required_scopes, list) or not all(isinstance(scope, str) for scope in required_scopes):
        return False
    required = set(required_scopes)
    if not required:
        return True

    for field in ("granted_scopes", "credential_scopes", "available_scopes", "allowed_scopes"):
        scopes = expected.get(field)
        if isinstance(scopes, (list, tuple, set, frozenset)):
            return required.issubset(set(scopes))

    expected_required = expected.get("required_scopes")
    if isinstance(expected_required, (list, tuple, set, frozenset)):
        return required == set(expected_required)
    return False


def _kill_switch_allows_execution(expected: dict[str, Any]) -> bool:
    if expected.get("kill_switch_active") is True:
        return False
    if expected.get("execution_disabled") is True:
        return False
    return expected.get("kill_switch_allows_execution", True) is True


def _remember_nonce(seen_nonces: Any, nonce: str) -> None:
    add = getattr(seen_nonces, "add", None)
    if callable(add):
        add(nonce)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _signature_segment(payload_segment: str, secret: str | bytes) -> str:
    digest = hmac.new(_secret_bytes(secret), payload_segment.encode("ascii"), hashlib.sha256).digest()
    return _b64url_encode(digest)


def _secret_bytes(secret: str | bytes) -> bytes:
    if isinstance(secret, str):
        secret_bytes = secret.encode("utf-8")
    elif isinstance(secret, bytes):
        secret_bytes = secret
    else:
        raise TypeError("secret must be str or bytes")
    if not secret_bytes:
        raise ValueError("secret must be non-empty")
    return secret_bytes
