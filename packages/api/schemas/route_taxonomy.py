"""Route substrate/provenance/source-risk taxonomy for Index + Resolve vNext.

PP-1 keeps route facts split into separate, machine-readable dimensions.
The helpers in this module are intentionally small and fail-closed so Resolve,
MCP, UI/logging, receipts, and manifest linting can share one vocabulary.
"""

from __future__ import annotations

from typing import Any

SUBSTRATES = frozenset(
    {
        "official_api",
        "documented_public_endpoint",
        "official_cli",
        "official_mcp",
        "official_sdk",
        "sdk_code_mode",
        "generated_adapter",
        "browser_discovered_private_endpoint",
        "user_authorized_private_endpoint",
    }
)

PROVENANCE_ORIGINS = frozenset(
    {
        "vendor_official",
        "vendor_authorized",
        "rhumb_managed",
        "community_submitted",
        "rhumb_generated",
        "user_authorized",
        "browser_observed",
        "unknown",
    }
)

SOURCE_RISKS = frozenset(
    {
        "verified_low",
        "community_unverified",
        "experimental_private",
        "deprecated_fragile",
        "anti_bot_or_tos_sensitive",
        "payment_or_real_world_write",
        "unsupported",
    }
)

PRIVATE_OR_SNIFFED_SUBSTRATES = frozenset(
    {
        "browser_discovered_private_endpoint",
        "user_authorized_private_endpoint",
    }
)

NON_NATIVE_SUBSTRATES = frozenset(
    {
        "official_cli",
        "official_mcp",
        "official_sdk",
        "sdk_code_mode",
        "generated_adapter",
        "browser_discovered_private_endpoint",
        "user_authorized_private_endpoint",
    }
)

DEFAULT_EXCLUDED_SOURCE_RISKS = frozenset(
    {
        "community_unverified",
        "experimental_private",
        "deprecated_fragile",
        "anti_bot_or_tos_sensitive",
        "payment_or_real_world_write",
        "unsupported",
    }
)

PUBLIC_CLAIM_UNSAFE_PHRASES = (
    "vendor approved",
    "vendor-approved",
    "officially approved",
    "production-grade",
    "production grade",
)


def normalize_taxonomy_value(value: Any, allowed: frozenset[str], default: str) -> str:
    cleaned = str(value or "").strip()
    return cleaned if cleaned in allowed else default


def route_recommendation_policy(
    route: dict[str, Any],
    *,
    explicit_request: bool = False,
    policy_allowed: bool = False,
) -> dict[str, Any]:
    """Return the default recommendation decision for one route fact.

    PP-1's safety rail: private/sniffed, anti-bot, unsupported, high-risk,
    deprecated, or unverified routes cannot become default recommendations just
    because they are present in Index. Explicit request + policy allowance is
    required for routes that are not fundamentally unsupported or anti-bot risky.
    """

    substrate = normalize_taxonomy_value(route.get("substrate"), SUBSTRATES, "generated_adapter")
    provenance_origin = normalize_taxonomy_value(route.get("provenance_origin"), PROVENANCE_ORIGINS, "unknown")
    source_risk = normalize_taxonomy_value(route.get("source_risk"), SOURCE_RISKS, "unsupported")
    side_effect_class = str(route.get("side_effect_class") or "").strip()

    reasons: list[str] = []
    if substrate in PRIVATE_OR_SNIFFED_SUBSTRATES:
        reasons.append("private_or_sniffed_route_requires_explicit_policy")
    if substrate == "generated_adapter" and provenance_origin != "vendor_official":
        reasons.append("generated_route_not_default")
    if provenance_origin in {"community_submitted", "browser_observed", "unknown"}:
        reasons.append("untrusted_provenance_requires_explicit_policy")
    if source_risk in DEFAULT_EXCLUDED_SOURCE_RISKS:
        reasons.append(f"source_risk_{source_risk}_not_default")
    if side_effect_class in {"write", "admin", "payment", "destructive"}:
        reasons.append("high_risk_side_effect_not_default")

    hard_blocked = source_risk in {"unsupported", "anti_bot_or_tos_sensitive"}
    allowed_by_override = explicit_request and policy_allowed and not hard_blocked
    default_recommendable = not reasons
    recommendable = default_recommendable or allowed_by_override

    return {
        "substrate": substrate,
        "provenance_origin": provenance_origin,
        "source_risk": source_risk,
        "default_recommendable": default_recommendable,
        "recommendable": recommendable,
        "requires_explicit_request": bool(reasons) and not hard_blocked,
        "policy_allowed": policy_allowed,
        "blocked": hard_blocked and bool(reasons),
        "reasons": reasons,
    }


def lint_public_claim_boundary(route: dict[str, Any]) -> list[str]:
    """Fail closed when public copy overclaims weak route evidence."""

    claim = str(route.get("public_claim_boundary") or "").strip().lower()
    if not claim:
        return ["missing_public_claim_boundary"]

    policy = route_recommendation_policy(route)
    if policy["default_recommendable"]:
        return []

    errors: list[str] = []
    for phrase in PUBLIC_CLAIM_UNSAFE_PHRASES:
        if phrase in claim:
            errors.append("public_claim_overstates_route_evidence")
            break
    return errors
