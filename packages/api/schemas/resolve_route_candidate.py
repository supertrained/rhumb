"""Resolve route-candidate schema and state machine.

This is the PP-14 bridge from the existing v1-translate Resolve payload to the
canonical vNext route-decision contract.  It is intentionally additive: existing
Resolve fields remain stable while `route_candidates` gives agents typed states
and stop conditions they can branch on without parsing prose.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import re
from typing import Any, Literal

from schemas.index_evidence import route_fixture_for
from schemas.route_taxonomy import PROVENANCE_ORIGINS, SOURCE_RISKS, SUBSTRATES

Substrate = Literal[
    "official_api",
    "documented_public_endpoint",
    "official_cli",
    "official_mcp",
    "official_sdk",
    "sdk_code_mode",
    "generated_adapter",
    "browser_discovered_private_endpoint",
    "user_authorized_private_endpoint",
]

ProvenanceOrigin = Literal[
    "vendor_official",
    "vendor_authorized",
    "rhumb_managed",
    "community_submitted",
    "rhumb_generated",
    "user_authorized",
    "browser_observed",
    "unknown",
]

SourceRisk = Literal[
    "verified_low",
    "community_unverified",
    "experimental_private",
    "deprecated_fragile",
    "anti_bot_or_tos_sensitive",
    "payment_or_real_world_write",
    "unsupported",
]

PromotionState = Literal[
    "indexed",
    "candidate",
    "fixture_only",
    "experimental_non_default",
    "beta_executable",
    "production_executable",
    "blocked",
    "deprecated",
]

ReviewStatus = Literal[
    "draft",
    "current",
    "stale",
    "expired",
    "quarantined",
    "superseded",
    "missing",
]

SafetyState = Literal[
    "executable",
    "dry_run_only",
    "requires_credentials",
    "requires_confirmation",
    "experimental_non_default",
    "blocked_policy",
    "blocked_security",
    "unsupported",
]

ReceiptSupport = Literal["none", "compact", "full", "verifiable"]

PROMOTION_STATES = frozenset(PromotionState.__args__)  # type: ignore[attr-defined]
REVIEW_STATUSES = frozenset(ReviewStatus.__args__)  # type: ignore[attr-defined]
SAFETY_STATES = frozenset(SafetyState.__args__)  # type: ignore[attr-defined]
RECEIPT_SUPPORT_LEVELS = frozenset(ReceiptSupport.__args__)  # type: ignore[attr-defined]

STOP_CONDITIONS = frozenset(
    {
        "missing_manifest",
        "missing_provenance",
        "missing_evidence_packet",
        "evidence_expired",
        "review_state_invalid",
        "unverified_artifact",
        "sandbox_required",
        "sandbox_profile_missing",
        "unsupported_auth_mode",
        "missing_credentials",
        "invalid_rhumb_key",
        "missing_required_scope",
        "credential_scope_mismatch",
        "policy_denied",
        "budget_exceeded",
        "payment_required",
        "tos_risk",
        "anti_bot_or_access_control_risk",
        "high_risk_requires_confirmation",
        "kill_switch_state_unavailable",
        "unsupported",
    }
)

_SAFE_ID_RE = re.compile(r"[^a-zA-Z0-9_]+")


def _safe_id(value: Any) -> str:
    cleaned = _SAFE_ID_RE.sub("_", str(value or "unknown").strip()).strip("_").lower()
    return cleaned or "unknown"


def _first_string(values: Any) -> str | None:
    if isinstance(values, list):
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
    if isinstance(values, str) and values.strip():
        return values.strip()
    return None


def _enum_value(value: Any, allowed: frozenset[str], default: str) -> str:
    cleaned = str(value or "").strip()
    return cleaned if cleaned in allowed else default


def stable_route_id(capability_id: str, provider_id: str, substrate: str = "official_api") -> str:
    return f"route_{_safe_id(capability_id)}_{_safe_id(provider_id)}_{_safe_id(substrate)}_v1"


def stable_route_candidate_id(capability_id: str, provider_id: str, rank: int) -> str:
    seed = f"{capability_id}:{provider_id}:{rank}".encode("utf-8")
    digest = hashlib.sha256(seed).hexdigest()[:10]
    return f"route_candidate_{rank:02d}_{_safe_id(provider_id)}_{digest}"


def infer_safety_state_and_stop(provider: dict[str, Any]) -> tuple[str, str | None]:
    """Infer the PP-14 safety state and typed stop for one provider candidate."""

    explicit_state = provider.get("safety_state")
    explicit_stop = provider.get("stop_condition")
    if explicit_state in SAFETY_STATES:
        default_stops = {
            "requires_credentials": "missing_credentials",
            "requires_confirmation": "high_risk_requires_confirmation",
            "blocked_policy": "policy_denied",
            "blocked_security": "unverified_artifact",
            "unsupported": "unsupported",
        }
        stop = (
            str(explicit_stop)
            if explicit_stop in STOP_CONDITIONS
            else default_stops.get(str(explicit_state))
        )
        return str(explicit_state), None if explicit_state == "executable" else stop

    if provider.get("blocked_policy") or provider.get("policy_denied"):
        return "blocked_policy", "policy_denied"

    circuit_state = str(provider.get("circuit_state") or "").strip().lower()
    kill_switch_state = str(provider.get("kill_switch_state") or "").strip().lower()
    if circuit_state == "unavailable" or kill_switch_state == "unavailable":
        return "blocked_security", "kill_switch_state_unavailable"
    if provider.get("blocked_security") or circuit_state in {"open", "blocked"}:
        return "blocked_security", (
            str(explicit_stop) if explicit_stop in STOP_CONDITIONS else "unverified_artifact"
        )

    if (
        provider.get("experimental_non_default")
        or provider.get("promotion_state") == "experimental_non_default"
    ):
        return "experimental_non_default", (
            str(explicit_stop) if explicit_stop in STOP_CONDITIONS else None
        )

    if provider.get("requires_confirmation"):
        return "requires_confirmation", "high_risk_requires_confirmation"

    endpoint_pattern = str(provider.get("endpoint_pattern") or "").strip()
    if not endpoint_pattern:
        return "unsupported", "missing_manifest"

    if provider.get("available_for_execute") is False:
        return "blocked_security", "kill_switch_state_unavailable"

    if provider.get("configured") is False:
        return "requires_credentials", "missing_credentials"

    return "executable", None


def route_candidate_from_provider(
    *,
    capability_id: str,
    provider: dict[str, Any],
    rank: int,
    selected_provider_id: str | None,
    alternatives_considered: list[str],
) -> dict[str, Any]:
    """Build one canonical route-candidate object from current Resolve provider data."""

    provider_id = str(
        provider.get("provider_id")
        or provider.get("service_slug")
        or provider.get("provider")
        or "unknown"
    ).strip()
    fixture = route_fixture_for(capability_id, provider_id)
    fixture_manifest = fixture.get("manifest") if isinstance(fixture, dict) else None
    fixture_evidence = fixture.get("evidence_packet") if isinstance(fixture, dict) else None

    manifest_facts = fixture_manifest or {}
    evidence_facts = fixture_evidence or {}

    service_id = str(
        manifest_facts.get("service_id")
        or provider.get("service_id")
        or provider.get("service_slug")
        or provider_id
    ).strip()
    substrate = _enum_value(
        manifest_facts.get("substrate") or provider.get("substrate"),
        SUBSTRATES,
        "official_api",
    )
    provenance_origin = _enum_value(
        manifest_facts.get("provenance_origin") or provider.get("provenance_origin"),
        PROVENANCE_ORIGINS,
        "unknown",
    )
    source_risk = _enum_value(
        manifest_facts.get("source_risk") or provider.get("source_risk"),
        SOURCE_RISKS,
        "community_unverified",
    )
    promotion_state = _enum_value(
        evidence_facts.get("promotion_state") or provider.get("promotion_state"),
        PROMOTION_STATES,
        "candidate",
    )
    review_status = _enum_value(
        evidence_facts.get("review_status") or provider.get("review_status"),
        REVIEW_STATUSES,
        "missing",
    )
    safety_state, stop_condition = infer_safety_state_and_stop(provider)

    credential_mode = (
        provider.get("credential_mode")
        or provider.get("preferred_credential_mode")
        or _first_string(provider.get("credential_modes"))
    )
    cost_per_call = provider.get("cost_per_call")
    cost_estimate = {
        "amount_usd": cost_per_call,
        "currency": provider.get("cost_currency") or "USD",
        "free_tier_calls": provider.get("free_tier_calls"),
    }
    if cost_estimate["amount_usd"] is not None:
        try:
            cost_estimate["amount_usd"] = float(cost_estimate["amount_usd"])
        except (TypeError, ValueError):
            cost_estimate["amount_usd"] = None

    is_selected = selected_provider_id is not None and provider_id == selected_provider_id
    why_rejected: str | None = None
    if not is_selected:
        if stop_condition:
            why_rejected = f"typed_stop:{stop_condition}"
        elif selected_provider_id:
            why_rejected = "lower_ranked_candidate"

    return {
        "route_candidate_id": str(
            provider.get("route_candidate_id")
            or stable_route_candidate_id(capability_id, provider_id, rank)
        ),
        "route_id": str(
            manifest_facts.get("route_id")
            or provider.get("route_id")
            or stable_route_id(capability_id, provider_id, substrate)
        ),
        "route_plan_id": (
            provider.get("route_plan_id")
            if safety_state in {"executable", "dry_run_only"}
            else None
        ),
        "route_plan_expires_at": (
            provider.get("route_plan_expires_at")
            if safety_state in {"executable", "dry_run_only"}
            else None
        ),
        "capability_id": capability_id,
        "service_id": service_id,
        "provider_id": provider_id,
        "substrate": substrate,
        "provenance_origin": provenance_origin,
        "source_risk": source_risk,
        "promotion_state": promotion_state,
        "manifest_id": manifest_facts.get("manifest_id") or provider.get("manifest_id"),
        "manifest_digest": manifest_facts.get("manifest_digest") or provider.get("manifest_digest"),
        "manifest_version": manifest_facts.get("manifest_version")
        or provider.get("manifest_version"),
        "evidence_packet_id": evidence_facts.get("evidence_packet_id")
        or provider.get("evidence_packet_id"),
        "evidence_packet_digest": evidence_facts.get("evidence_packet_digest")
        or provider.get("evidence_packet_digest"),
        "evidence_expires_at": evidence_facts.get("evidence_expires_at")
        or provider.get("evidence_expires_at"),
        "review_status": review_status,
        "safety_state": safety_state,
        "stop_condition": stop_condition,
        "auth_mode": provider.get("auth_method"),
        "credential_mode": credential_mode,
        "required_scopes": (
            manifest_facts["required_scopes"]
            if "required_scopes" in manifest_facts
            else provider.get("required_scopes") or []
        ),
        "data_classes": (
            manifest_facts["data_classes"]
            if "data_classes" in manifest_facts
            else provider.get("data_classes") or []
        ),
        "side_effect_class": (
            manifest_facts["side_effect_class"]
            if "side_effect_class" in manifest_facts
            else provider.get("side_effect_class") or "read"
        ),
        "cost_estimate": cost_estimate,
        "rate_limit_estimate": provider.get("rate_limit_estimate"),
        "budget_impact": provider.get("budget_impact") or {"status": "not_estimated"},
        "confirmation_policy": provider.get("confirmation_policy")
        or ("required" if safety_state == "requires_confirmation" else "none"),
        "sandbox_profile_id": provider.get("sandbox_profile_id"),
        "receipt_support": _enum_value(
            provider.get("receipt_support"),
            RECEIPT_SUPPORT_LEVELS,
            "compact" if provider.get("endpoint_pattern") else "none",
        ),
        "verification_path": provider.get("verification_path"),
        "route_explanation_id": provider.get("route_explanation_id"),
        "alternatives_considered": alternatives_considered,
        "why_selected": (
            "highest_ranked_executable_candidate"
            if is_selected and safety_state == "executable"
            else ("selected_candidate" if is_selected else None)
        ),
        "why_rejected": why_rejected,
    }


def unsupported_route_candidate(capability_id: str, reason: str | None = None) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    provider_id = "unsupported"
    return {
        "route_candidate_id": stable_route_candidate_id(capability_id, provider_id, 1),
        "route_id": stable_route_id(capability_id, provider_id, "documented_public_endpoint"),
        "route_plan_id": None,
        "route_plan_expires_at": None,
        "capability_id": capability_id,
        "service_id": provider_id,
        "provider_id": provider_id,
        "substrate": "documented_public_endpoint",
        "provenance_origin": "unknown",
        "source_risk": "unsupported",
        "promotion_state": "blocked",
        "manifest_id": None,
        "manifest_digest": None,
        "manifest_version": None,
        "evidence_packet_id": None,
        "evidence_packet_digest": None,
        "evidence_expires_at": now,
        "review_status": "missing",
        "safety_state": "unsupported",
        "stop_condition": (
            "unsupported" if reason == "no_providers_registered" else "missing_manifest"
        ),
        "auth_mode": None,
        "credential_mode": None,
        "required_scopes": [],
        "data_classes": [],
        "side_effect_class": "read",
        "cost_estimate": {"amount_usd": None, "currency": "USD", "free_tier_calls": None},
        "rate_limit_estimate": None,
        "budget_impact": {"status": "not_estimated"},
        "confirmation_policy": "none",
        "sandbox_profile_id": None,
        "receipt_support": "none",
        "verification_path": None,
        "route_explanation_id": None,
        "alternatives_considered": [],
        "why_selected": None,
        "why_rejected": reason or "no_verified_route",
    }


def route_candidates_from_resolve_data(data: dict[str, Any]) -> list[dict[str, Any]]:
    capability_id = str(data.get("capability") or data.get("capability_id") or "unknown")
    providers = data.get("providers")
    if (not isinstance(providers, list) or not providers) and data.get("provider"):
        readiness: dict[str, Any] = (
            data.get("execute_readiness") if isinstance(data.get("execute_readiness"), dict) else {}
        )
        provider: dict[str, Any] = {
            "provider_id": data.get("provider"),
            "service_slug": data.get("provider"),
            "endpoint_pattern": data.get("endpoint_pattern"),
            "credential_mode": data.get("credential_mode"),
            "auth_method": data.get("auth_method"),
            "cost_per_call": data.get("cost_estimate_usd"),
            "cost_currency": data.get("cost_currency") or "USD",
            "route_explanation_id": data.get("route_explanation_id"),
        }
        readiness_status = str(readiness.get("status") or "").strip().lower()
        if readiness_status in {"auth_required", "credentials_required", "missing_credentials"}:
            provider["safety_state"] = "requires_credentials"
            provider["stop_condition"] = "missing_credentials"
        elif readiness_status in {"policy_denied", "blocked_policy"}:
            provider["safety_state"] = "blocked_policy"
            provider["stop_condition"] = "policy_denied"
        elif readiness_status in {"confirmation_required", "requires_confirmation"}:
            provider["safety_state"] = "requires_confirmation"
            provider["stop_condition"] = "high_risk_requires_confirmation"
        elif readiness_status in {"blocked_security", "kill_switch_state_unavailable"}:
            provider["safety_state"] = "blocked_security"
            provider["stop_condition"] = "kill_switch_state_unavailable"
        elif readiness_status in {"ready", "executable"}:
            provider["configured"] = True
        return [
            route_candidate_from_provider(
                capability_id=capability_id,
                provider=provider,
                rank=1,
                selected_provider_id=str(data.get("provider")),
                alternatives_considered=[str(data.get("provider"))],
            )
        ]
    if not isinstance(providers, list) or not providers:
        recovery_hint: dict[str, Any] = (
            data.get("recovery_hint") if isinstance(data.get("recovery_hint"), dict) else {}
        )
        return [
            unsupported_route_candidate(
                capability_id, str(recovery_hint.get("reason") or "no_candidate")
            )
        ]

    execute_hint = data.get("execute_hint") if isinstance(data.get("execute_hint"), dict) else {}
    selected_provider_id = (
        execute_hint.get("preferred_provider") if isinstance(execute_hint, dict) else None
    )
    if selected_provider_id is not None:
        selected_provider_id = str(selected_provider_id)
    alternatives = [
        str(
            provider.get("provider_id")
            or provider.get("service_slug")
            or provider.get("provider")
            or "unknown"
        )
        for provider in providers
        if isinstance(provider, dict)
    ]

    candidates: list[dict[str, Any]] = []
    for index, provider in enumerate(providers, start=1):
        if not isinstance(provider, dict):
            continue
        candidates.append(
            route_candidate_from_provider(
                capability_id=capability_id,
                provider=provider,
                rank=index,
                selected_provider_id=selected_provider_id,
                alternatives_considered=alternatives,
            )
        )
    return candidates


def annotate_resolve_body_with_route_candidates(body: dict[str, Any]) -> dict[str, Any]:
    """Add PP-14 route candidates to a Resolve/estimate response body."""

    data = body.get("data")
    if not isinstance(data, dict):
        return body

    annotated = dict(body)
    annotated_data = dict(data)
    route_candidates = route_candidates_from_resolve_data(annotated_data)
    annotated_data["route_candidates"] = route_candidates
    has_index_fixture = any(candidate.get("evidence_packet_id") for candidate in route_candidates)
    annotated_data["route_contract"] = {
        "contract_id": "resolve_route_candidate_v1",
        "source": "PP-14",
        "status": "compat_bridge",
        "index_fact_source": (
            "index_evidence_fixture_and_v1_catalog_compat"
            if has_index_fixture
            else "v1_catalog_compat_until_PP-15"
        ),
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "safety_states": sorted(SAFETY_STATES),
        "stop_conditions": sorted(STOP_CONDITIONS),
    }
    annotated["data"] = annotated_data
    return annotated
