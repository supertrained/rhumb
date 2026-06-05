"""Command-level capability manifest schema for Index + Resolve vNext.

PP-2 defines one manifest shape that can describe official APIs, official CLIs,
official MCPs, official SDK/code-mode paths, and generated adapters without
substrate-specific schema branches.  The linter is deliberately fail-closed:
missing ownership, scope, allowlist, evidence, expiry, cost/rate, or public claim
fields make the manifest non-executable.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from schemas.index_evidence import canonical_sha256
from schemas.route_taxonomy import (
    NON_NATIVE_SUBSTRATES,
    PROVENANCE_ORIGINS,
    SOURCE_RISKS,
    SUBSTRATES,
    lint_public_claim_boundary,
    route_recommendation_policy,
)

SIDE_EFFECT_CLASSES = frozenset({"read", "write", "admin", "payment", "destructive"})
AUTH_MODES = frozenset({"none", "byok", "rhumb_managed", "agent_vault", "oauth", "user_session"})
CONFIRMATION_POLICIES = frozenset({"none", "required", "dry_run_then_confirm", "blocked"})
CACHE_BEHAVIORS = frozenset(
    {"none", "read_through", "write_through", "ephemeral", "provider_controlled"}
)

REQUIRED_MANIFEST_FIELDS = (
    "manifest_id",
    "manifest_version",
    "route_id",
    "route_name",
    "service_id",
    "provider_id",
    "vendor",
    "capability_id",
    "substrate",
    "provenance_origin",
    "source_risk",
    "auth_mode",
    "required_scopes",
    "data_classes",
    "side_effect_class",
    "required_credentials",
    "network_allowlist",
    "filesystem_allowlist",
    "process_allowlist",
    "cost_model",
    "rate_limit_model",
    "dry_run_supported",
    "confirmation_policy",
    "cache_behavior",
    "tests",
    "evidence_refs",
    "owner",
    "reviewer",
    "expires_at",
    "public_claim_boundary",
)

_LIST_FIELDS = frozenset(
    {
        "required_scopes",
        "data_classes",
        "required_credentials",
        "network_allowlist",
        "filesystem_allowlist",
        "process_allowlist",
        "tests",
        "evidence_refs",
    }
)


def capability_manifest_digest(manifest: dict[str, Any]) -> str:
    return canonical_sha256(manifest)


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_string_list(value: Any, *, allow_empty: bool = True) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(_non_empty_string(item) for item in value)
    )


def lint_capability_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_MANIFEST_FIELDS:
        value = manifest.get(field)
        if field in _LIST_FIELDS:
            if not _valid_string_list(
                value,
                allow_empty=field
                in {
                    "required_scopes",
                    "required_credentials",
                    "filesystem_allowlist",
                    "process_allowlist",
                },
            ):
                errors.append(f"invalid_{field}")
        elif value in (None, ""):
            errors.append(f"missing_{field}")

    if manifest.get("substrate") not in SUBSTRATES:
        errors.append("invalid_substrate")
    if manifest.get("provenance_origin") not in PROVENANCE_ORIGINS:
        errors.append("invalid_provenance_origin")
    if manifest.get("source_risk") not in SOURCE_RISKS:
        errors.append("invalid_source_risk")
    if manifest.get("auth_mode") not in AUTH_MODES:
        errors.append("invalid_auth_mode")
    if manifest.get("side_effect_class") not in SIDE_EFFECT_CLASSES:
        errors.append("invalid_side_effect_class")
    if manifest.get("confirmation_policy") not in CONFIRMATION_POLICIES:
        errors.append("invalid_confirmation_policy")
    if manifest.get("cache_behavior") not in CACHE_BEHAVIORS:
        errors.append("invalid_cache_behavior")
    if not isinstance(manifest.get("dry_run_supported"), bool):
        errors.append("invalid_dry_run_supported")
    if not isinstance(manifest.get("cost_model"), dict) or not manifest.get("cost_model"):
        errors.append("invalid_cost_model")
    if not isinstance(manifest.get("rate_limit_model"), dict) or not manifest.get(
        "rate_limit_model"
    ):
        errors.append("invalid_rate_limit_model")
    if _parse_time(manifest.get("expires_at")) is None:
        errors.append("invalid_expires_at")

    if manifest.get("substrate") in NON_NATIVE_SUBSTRATES:
        if not manifest.get("sandbox_profile_class"):
            errors.append("missing_sandbox_profile_class")
        if not _valid_string_list(manifest.get("artifact_allowlist"), allow_empty=False):
            errors.append("invalid_artifact_allowlist")

    if manifest.get("side_effect_class") in {"write", "admin", "payment", "destructive"}:
        if manifest.get("confirmation_policy") not in {
            "required",
            "dry_run_then_confirm",
            "blocked",
        }:
            errors.append("high_risk_requires_confirmation_policy")

    if (
        manifest.get("source_risk") == "anti_bot_or_tos_sensitive"
        and manifest.get("confirmation_policy") != "blocked"
    ):
        errors.append("anti_bot_routes_must_be_blocked")

    policy = route_recommendation_policy(manifest)
    if policy["default_recommendable"] and manifest.get("promotion_state") in {
        "fixture_only",
        "experimental_non_default",
        "blocked",
        "deprecated",
    }:
        errors.append("promotion_state_not_default_executable")
    errors.extend(lint_public_claim_boundary(manifest))

    expected_digest = capability_manifest_digest(manifest)
    if manifest.get("manifest_digest") != expected_digest:
        errors.append("manifest_digest_mismatch")
    return sorted(set(errors))


def _with_digest(manifest: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(manifest)
    result["manifest_digest"] = capability_manifest_digest(result)
    return result


def _base_manifest(
    *,
    manifest_id: str,
    route_id: str,
    route_name: str,
    service_id: str,
    provider_id: str,
    vendor: str,
    capability_id: str,
    substrate: str,
    provenance_origin: str,
    source_risk: str,
    auth_mode: str,
    data_classes: list[str],
    side_effect_class: str,
    public_claim_boundary: str,
    network_allowlist: list[str] | None = None,
    filesystem_allowlist: list[str] | None = None,
    process_allowlist: list[str] | None = None,
    artifact_allowlist: list[str] | None = None,
    sandbox_profile_class: str | None = None,
    confirmation_policy: str = "none",
    dry_run_supported: bool = False,
    cache_behavior: str = "none",
    required_scopes: list[str] | None = None,
    required_credentials: list[str] | None = None,
    promotion_state: str = "beta_executable",
) -> dict[str, Any]:
    manifest = {
        "manifest_id": manifest_id,
        "manifest_version": "2026-05-19.1",
        "route_id": route_id,
        "route_name": route_name,
        "service_id": service_id,
        "provider_id": provider_id,
        "vendor": vendor,
        "capability_id": capability_id,
        "substrate": substrate,
        "provenance_origin": provenance_origin,
        "source_risk": source_risk,
        "auth_mode": auth_mode,
        "required_scopes": required_scopes or [],
        "data_classes": data_classes,
        "side_effect_class": side_effect_class,
        "required_credentials": required_credentials or [],
        "network_allowlist": network_allowlist or [],
        "filesystem_allowlist": filesystem_allowlist or [],
        "process_allowlist": process_allowlist or [],
        "artifact_allowlist": artifact_allowlist or [],
        "cost_model": {"unit": "call", "estimated_cost_usd": 0.003},
        "rate_limit_model": {"unit": "minute", "limit": 60, "enforced_by": "rhumb"},
        "dry_run_supported": dry_run_supported,
        "confirmation_policy": confirmation_policy,
        "cache_behavior": cache_behavior,
        "tests": [f"test_manifest_{route_id}"],
        "evidence_refs": [f"evidence:{route_id}"],
        "owner": "Pedro",
        "reviewer": "Pedro",
        "expires_at": "2026-08-17T00:00:00Z",
        "public_claim_boundary": public_claim_boundary,
        "promotion_state": promotion_state,
    }
    if sandbox_profile_class is not None:
        manifest["sandbox_profile_class"] = sandbox_profile_class
    return _with_digest(manifest)


def command_manifest_fixtures() -> list[dict[str, Any]]:
    """Representative PP-2 fixtures across managed and non-native substrates."""

    managed = [
        ("search.query", "brave-search", "brave-search-api", "web_search_query"),
        ("email.verify", "emailable", "emailable-api", "email_address"),
        ("crm.contact.lookup", "salesforce", "salesforce-api", "crm_contact"),
        ("support.ticket.create", "zendesk", "zendesk-api", "support_ticket"),
        ("warehouse.query", "snowflake", "snowflake-api", "warehouse_query"),
    ]
    fixtures: list[dict[str, Any]] = []
    for capability_id, service_id, provider_id, data_class in managed:
        safe_cap = capability_id.replace(".", "_")
        fixtures.append(
            _base_manifest(
                manifest_id=f"manifest_{safe_cap}_{provider_id.replace('-', '_')}_official_api_v1",
                route_id=f"route_{safe_cap}_{provider_id.replace('-', '_')}_official_api_v1",
                route_name=f"{capability_id} via {provider_id} official API",
                service_id=service_id,
                provider_id=provider_id,
                vendor=service_id,
                capability_id=capability_id,
                substrate="official_api",
                provenance_origin="rhumb_managed",
                source_risk="verified_low",
                auth_mode="rhumb_managed",
                data_classes=[data_class],
                side_effect_class="read" if capability_id != "support.ticket.create" else "write",
                required_credentials=[f"{provider_id}:api_key"],
                network_allowlist=[f"api.{service_id}.example.com"],
                confirmation_policy=(
                    "dry_run_then_confirm" if capability_id == "support.ticket.create" else "none"
                ),
                dry_run_supported=capability_id == "support.ticket.create",
                public_claim_boundary=f"Rhumb can represent the {capability_id} managed official API route when governed auth, budget, and policy allow it.",
            )
        )

    fixtures.extend(
        [
            _base_manifest(
                manifest_id="manifest_github_workflow_list_official_cli_v1",
                route_id="route_workflow_run_list_github_cli_v1",
                route_name="workflow_run.list via official GitHub CLI",
                service_id="github",
                provider_id="github-cli",
                vendor="GitHub",
                capability_id="workflow_run.list",
                substrate="official_cli",
                provenance_origin="vendor_official",
                source_risk="community_unverified",
                auth_mode="agent_vault",
                data_classes=["workflow_metadata"],
                side_effect_class="read",
                network_allowlist=["api.github.com"],
                process_allowlist=["gh"],
                artifact_allowlist=["gh@pinned-digest-placeholder"],
                sandbox_profile_class="cli_readonly_network_github",
                public_claim_boundary="Fixture-only route describing how a pinned official GitHub CLI could list workflow runs after non-native sandbox gates pass.",
                promotion_state="fixture_only",
            ),
            _base_manifest(
                manifest_id="manifest_filesystem_search_official_mcp_v1",
                route_id="route_file_search_official_mcp_v1",
                route_name="file.search via official MCP server fixture",
                service_id="filesystem",
                provider_id="filesystem-mcp",
                vendor="Model Context Protocol",
                capability_id="file.search",
                substrate="official_mcp",
                provenance_origin="vendor_official",
                source_risk="community_unverified",
                auth_mode="none",
                data_classes=["local_file_metadata"],
                side_effect_class="read",
                network_allowlist=["none"],
                filesystem_allowlist=["/tmp/rhumb-fixtures/read-only"],
                process_allowlist=["node"],
                artifact_allowlist=["mcp-filesystem@pinned-digest-placeholder"],
                sandbox_profile_class="mcp_readonly_filesystem_fixture",
                public_claim_boundary="Fixture-only route describing a pinned read-only MCP filesystem search path after sandbox and consent gates pass.",
                promotion_state="fixture_only",
            ),
            _base_manifest(
                manifest_id="manifest_stripe_customer_retrieve_sdk_code_v1",
                route_id="route_customer_retrieve_stripe_sdk_code_mode_v1",
                route_name="customer.retrieve via official SDK code-mode fixture",
                service_id="stripe",
                provider_id="stripe-sdk",
                vendor="Stripe",
                capability_id="customer.retrieve",
                substrate="sdk_code_mode",
                provenance_origin="vendor_official",
                source_risk="community_unverified",
                auth_mode="agent_vault",
                data_classes=["customer_profile"],
                side_effect_class="read",
                network_allowlist=["api.stripe.com"],
                process_allowlist=["python"],
                artifact_allowlist=["stripe-python@pinned-digest-placeholder"],
                sandbox_profile_class="sdk_code_readonly_network_stripe",
                public_claim_boundary="Fixture-only route describing a pinned official Stripe SDK read path after code-mode sandbox gates pass.",
                promotion_state="fixture_only",
            ),
            _base_manifest(
                manifest_id="manifest_generated_calendar_freebusy_fixture_v1",
                route_id="route_calendar_freebusy_generated_adapter_v1",
                route_name="calendar.freebusy via generated adapter fixture",
                service_id="google-calendar",
                provider_id="generated-calendar-adapter",
                vendor="Google Calendar",
                capability_id="calendar.freebusy",
                substrate="generated_adapter",
                provenance_origin="rhumb_generated",
                source_risk="community_unverified",
                auth_mode="agent_vault",
                data_classes=["calendar_availability"],
                side_effect_class="read",
                network_allowlist=["www.googleapis.com"],
                process_allowlist=["python"],
                artifact_allowlist=["generated-calendar-adapter@fixture-digest-placeholder"],
                sandbox_profile_class="generated_adapter_readonly_fixture",
                public_claim_boundary="Fixture-only generated adapter candidate; Rhumb must not describe it as approved by the vendor or production ready before evidence, sandbox, and review gates pass.",
                promotion_state="fixture_only",
            ),
        ]
    )
    return fixtures


def fixture_manifests_by_route_id() -> dict[str, dict[str, Any]]:
    return {manifest["route_id"]: manifest for manifest in command_manifest_fixtures()}
