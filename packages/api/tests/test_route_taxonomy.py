"""PP-1 route taxonomy policy tests."""

from __future__ import annotations

from schemas.route_taxonomy import (
    PROVENANCE_ORIGINS,
    SOURCE_RISKS,
    SUBSTRATES,
    lint_public_claim_boundary,
    route_recommendation_policy,
)


def test_route_taxonomy_exposes_required_substrate_provenance_and_risk_dimensions() -> None:
    assert {
        "official_api",
        "official_cli",
        "official_mcp",
        "sdk_code_mode",
        "generated_adapter",
        "browser_discovered_private_endpoint",
    }.issubset(SUBSTRATES)
    assert {"vendor_official", "rhumb_managed", "browser_observed", "unknown"}.issubset(PROVENANCE_ORIGINS)
    assert {"verified_low", "community_unverified", "anti_bot_or_tos_sensitive", "unsupported"}.issubset(SOURCE_RISKS)


def test_verified_official_api_route_is_default_recommendable() -> None:
    policy = route_recommendation_policy(
        {
            "substrate": "official_api",
            "provenance_origin": "rhumb_managed",
            "source_risk": "verified_low",
            "side_effect_class": "read",
        }
    )

    assert policy["default_recommendable"] is True
    assert policy["recommendable"] is True
    assert policy["reasons"] == []


def test_private_or_unverified_routes_are_excluded_until_explicit_and_policy_allowed() -> None:
    route = {
        "substrate": "browser_discovered_private_endpoint",
        "provenance_origin": "browser_observed",
        "source_risk": "experimental_private",
        "side_effect_class": "read",
    }

    default_policy = route_recommendation_policy(route)
    assert default_policy["default_recommendable"] is False
    assert default_policy["recommendable"] is False
    assert default_policy["requires_explicit_request"] is True
    assert "private_or_sniffed_route_requires_explicit_policy" in default_policy["reasons"]

    override_policy = route_recommendation_policy(route, explicit_request=True, policy_allowed=True)
    assert override_policy["default_recommendable"] is False
    assert override_policy["recommendable"] is True


def test_anti_bot_routes_remain_blocked_even_with_explicit_override() -> None:
    policy = route_recommendation_policy(
        {
            "substrate": "browser_discovered_private_endpoint",
            "provenance_origin": "browser_observed",
            "source_risk": "anti_bot_or_tos_sensitive",
            "side_effect_class": "read",
        },
        explicit_request=True,
        policy_allowed=True,
    )

    assert policy["recommendable"] is False
    assert policy["blocked"] is True
    assert "source_risk_anti_bot_or_tos_sensitive_not_default" in policy["reasons"]


def test_public_claim_linter_rejects_overclaims_for_weak_routes() -> None:
    errors = lint_public_claim_boundary(
        {
            "substrate": "generated_adapter",
            "provenance_origin": "rhumb_generated",
            "source_risk": "community_unverified",
            "side_effect_class": "read",
            "public_claim_boundary": "This is a vendor-approved production-grade route.",
        }
    )

    assert errors == ["public_claim_overstates_route_evidence"]
