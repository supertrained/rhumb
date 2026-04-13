"""Capability registry routes — maps agent capabilities to services.

Agents think in capabilities ("send an email"), not services ("call SendGrid").
This module provides discovery, resolution, and bundle endpoints.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from routes._supabase import cached_query, supabase_fetch
from services.actions_connection_registry import has_any_actions_bundle_configured
from services.crm_connection_registry import has_any_crm_bundle_configured
from services.warehouse_connection_registry import has_any_warehouse_bundle_configured
from services.proxy_auth import AuthInjector
from services.service_slugs import normalize_proxy_slug
from services.deployment_connection_registry import has_any_deployment_bundle_configured
from services.support_connection_registry import has_any_support_bundle_configured


async def _capability_not_found(raw_request: Request, capability_id: str) -> JSONResponse:
    """Return a standardized 404 for missing capabilities."""
    request_id = getattr(raw_request.state, "request_id", None) or "unknown"
    search_url = f"/v1/capabilities?search={quote(capability_id)}"
    content: dict[str, Any] = {
        "error": "capability_not_found",
        "message": f"No capability found with id '{capability_id}'",
        "resolution": "Check available capabilities at GET /v1/capabilities or /v1/capabilities?search=...",
        "request_id": request_id,
        "search_url": search_url,
    }
    suggestions = await _suggested_capabilities(capability_id)
    if suggestions:
        content["suggested_capabilities"] = suggestions
    return JSONResponse(
        status_code=404,
        content=content,
    )

router = APIRouter()
_READ_CACHE_TTL_SECONDS = 60.0
_DEGRADED_DISCOVERY_ERROR = "Capability catalog temporarily unavailable; showing direct capability fallback where possible."


async def _cached_fetch(table: str, path: str, ttl: float = _READ_CACHE_TTL_SECONDS) -> Any | None:
    return await cached_query(table, lambda: supabase_fetch(path), cache_key=path, ttl=ttl)

_DB_DIRECT_PROVIDER_SLUG = "postgresql"
_DB_DIRECT_PROVIDER_NAME = "PostgreSQL"
_DB_DIRECT_PROVIDER_CATEGORY = "database"
_DB_DIRECT_CREDENTIAL_MODES = ["byok", "agent_vault"]
_WAREHOUSE_DIRECT_PROVIDER_SLUG = "bigquery"
_WAREHOUSE_DIRECT_PROVIDER_NAME = "BigQuery"
_WAREHOUSE_DIRECT_PROVIDER_CATEGORY = "warehouse"
_WAREHOUSE_DIRECT_CREDENTIAL_MODES = ["byok"]
_OBJECT_STORAGE_DIRECT_PROVIDER_SLUG = "aws-s3"
_OBJECT_STORAGE_DIRECT_PROVIDER_NAME = "AWS S3"
_OBJECT_STORAGE_DIRECT_PROVIDER_CATEGORY = "storage_object"
_OBJECT_STORAGE_DIRECT_CREDENTIAL_MODES = ["byok"]
_DEPLOYMENT_DIRECT_PROVIDER_SLUG = "vercel"
_DEPLOYMENT_DIRECT_PROVIDER_NAME = "Vercel"
_DEPLOYMENT_DIRECT_PROVIDER_CATEGORY = "deployment"
_DEPLOYMENT_DIRECT_CREDENTIAL_MODES = ["byok"]
_ACTIONS_DIRECT_PROVIDER_SLUG = "github"
_ACTIONS_DIRECT_PROVIDER_NAME = "GitHub"
_ACTIONS_DIRECT_PROVIDER_CATEGORY = "automation"
_ACTIONS_DIRECT_CREDENTIAL_MODES = ["byok"]
_CRM_HUBSPOT_DIRECT_PROVIDER_SLUG = "hubspot"
_CRM_HUBSPOT_DIRECT_PROVIDER_NAME = "HubSpot"
_CRM_SALESFORCE_DIRECT_PROVIDER_SLUG = "salesforce"
_CRM_SALESFORCE_DIRECT_PROVIDER_NAME = "Salesforce"
_CRM_DIRECT_PROVIDER_CATEGORY = "crm"
_CRM_DIRECT_CREDENTIAL_MODES = ["byok"]
_ZENDESK_SUPPORT_DIRECT_PROVIDER_SLUG = "zendesk"
_ZENDESK_SUPPORT_DIRECT_PROVIDER_NAME = "Zendesk"
_INTERCOM_SUPPORT_DIRECT_PROVIDER_SLUG = "intercom"
_INTERCOM_SUPPORT_DIRECT_PROVIDER_NAME = "Intercom"
_SUPPORT_DIRECT_PROVIDER_CATEGORY = "support"
_SUPPORT_DIRECT_CREDENTIAL_MODES = ["byok"]


def _effective_auth_method(service_slug: str, auth_method: str) -> str:
    """Prefer hardcoded provider auth defaults over stale capability metadata."""
    proxy_slug = normalize_proxy_slug(service_slug)
    default_method = AuthInjector.default_method_for(proxy_slug)
    return default_method.value if default_method is not None else auth_method


def _is_db_direct_capability(capability_id: str) -> bool:
    return capability_id in {
        "db.query.read",
        "db.schema.describe",
        "db.row.get",
    }


def _is_warehouse_direct_capability(capability_id: str) -> bool:
    return capability_id in {
        "warehouse.query.read",
        "warehouse.schema.describe",
    }


def _is_object_storage_direct_capability(capability_id: str) -> bool:
    return capability_id in {
        "object.list",
        "object.head",
        "object.get",
    }


def _is_deployment_direct_capability(capability_id: str) -> bool:
    return capability_id in {
        "deployment.list",
        "deployment.get",
    }


def _is_support_direct_capability(capability_id: str) -> bool:
    return capability_id in {
        "ticket.search",
        "ticket.get",
        "ticket.list_comments",
        "conversation.list",
        "conversation.get",
        "conversation.list_parts",
    }


def _is_actions_direct_capability(capability_id: str) -> bool:
    return capability_id in {
        "workflow_run.list",
        "workflow_run.get",
    }


def _is_crm_direct_capability(capability_id: str) -> bool:
    return capability_id in {
        "crm.object.describe",
        "crm.record.search",
        "crm.record.get",
    }


def _support_direct_provider_slug(capability_id: str) -> str:
    if capability_id.startswith("conversation."):
        return _INTERCOM_SUPPORT_DIRECT_PROVIDER_SLUG
    return _ZENDESK_SUPPORT_DIRECT_PROVIDER_SLUG


def _support_direct_provider_name(capability_id: str) -> str:
    if _support_direct_provider_slug(capability_id) == _INTERCOM_SUPPORT_DIRECT_PROVIDER_SLUG:
        return _INTERCOM_SUPPORT_DIRECT_PROVIDER_NAME
    return _ZENDESK_SUPPORT_DIRECT_PROVIDER_NAME


def _support_direct_recommendation_reason(capability_id: str) -> str:
    if capability_id.startswith("conversation."):
        return "Direct read-only Intercom execution via support_ref with explicit team/admin scope and customer-visible-by-default conversation parts."
    return "Direct read-only Zendesk execution via support_ref with explicit brand/group scope and public-comments-only default."


def _mapped_provider_setup_hint(service_slug: str, auth_method: str, mode: str) -> str | None:
    if mode == "byok":
        return (
            f"Set RHUMB_CREDENTIAL_{service_slug.upper().replace('-', '_')}_{auth_method.upper()} "
            f"environment variable or configure via proxy credentials"
        )
    if mode == "rhumb_managed":
        return "No setup needed — Rhumb manages the credential"
    if mode == "agent_vault":
        return (
            f"Complete the ceremony at GET /v1/services/{service_slug}/ceremony, "
            f"then pass token via X-Agent-Token header"
        )
    return None


def _support_direct_setup_hint_for_provider(provider_slug: str) -> str:
    if provider_slug == _INTERCOM_SUPPORT_DIRECT_PROVIDER_SLUG:
        return "Pass a support_ref that resolves to a RHUMB_SUPPORT_<REF> JSON bundle with provider=intercom, region, auth_mode=bearer_token, bearer_token, and explicit allowed_team_ids and/or allowed_admin_ids."
    return "Pass a support_ref that resolves to a RHUMB_SUPPORT_<REF> JSON bundle with provider=zendesk, subdomain, auth_mode, credentials, and explicit allowed_group_ids and/or allowed_brand_ids."


def _support_direct_setup_hint(capability_id: str) -> str:
    return _support_direct_setup_hint_for_provider(_support_direct_provider_slug(capability_id))


def _direct_provider_setup_hint(service_slug: str, auth_method: str, mode: str) -> str | None:
    if service_slug == _DB_DIRECT_PROVIDER_SLUG and auth_method == "connection_ref":
        if mode == "byok":
            return "Self-hosted/internal only: pass a connection_ref that resolves to a RHUMB_DB_<REF> environment variable at execution time. Hosted Rhumb should prefer agent_vault."
        if mode == "agent_vault":
            return "Hosted/default path: set credential_mode to 'agent_vault' and pass either a short-lived signed rhdbv1 DB vault token in X-Agent-Token or, as a compatibility bridge, a transient PostgreSQL DSN in X-Agent-Token. The raw DSN is never stored."
        return None

    if service_slug == _WAREHOUSE_DIRECT_PROVIDER_SLUG and auth_method == "warehouse_ref" and mode == "byok":
        return "Pass a warehouse_ref that resolves to a RHUMB_WAREHOUSE_<REF> JSON bundle with provider=bigquery, auth_mode set to either service_account_json or service_account_impersonation, the matching credential payload, billing_project_id, location, and explicit allowed_dataset_refs and allowed_table_refs."

    if service_slug == _OBJECT_STORAGE_DIRECT_PROVIDER_SLUG and auth_method == "storage_ref" and mode == "byok":
        return "Pass a storage_ref that resolves to a RHUMB_STORAGE_<REF> JSON bundle with provider=aws-s3, region, credentials, allowed_buckets, and optional allowed_prefixes."

    if service_slug == _DEPLOYMENT_DIRECT_PROVIDER_SLUG and auth_method == "deployment_ref" and mode == "byok":
        return "Pass a deployment_ref that resolves to a RHUMB_DEPLOYMENT_<REF> JSON bundle with provider=vercel, auth_mode=bearer_token, bearer_token, allowed_project_ids, and optional team_id/allowed_targets."

    if service_slug == _ACTIONS_DIRECT_PROVIDER_SLUG and auth_method == "actions_ref" and mode == "byok":
        return "Pass an actions_ref that resolves to a RHUMB_ACTIONS_<REF> JSON bundle with provider=github, auth_mode=bearer_token, bearer_token, and allowed_repositories."

    if auth_method == "crm_ref" and mode == "byok":
        if service_slug == _CRM_SALESFORCE_DIRECT_PROVIDER_SLUG:
            return "Pass a crm_ref that resolves to a RHUMB_CRM_<REF> JSON bundle with provider=salesforce, auth_mode=connected_app_refresh_token, client_id, client_secret, refresh_token, optional auth_base_url/api_version, allowed_object_types, allowed_properties_by_object, and optional default/searchable/sortable/allowed_record_ids maps."
        return "Pass a crm_ref that resolves to a RHUMB_CRM_<REF> JSON bundle with provider=hubspot, auth_mode=private_app_token, private_app_token, allowed_object_types, allowed_properties_by_object, and optional default/searchable/sortable/allowed_record_ids maps."

    if auth_method == "support_ref" and mode == "byok":
        return _support_direct_setup_hint_for_provider(service_slug)

    return None


def _provider_mode_setup_hint(service_slug: str, auth_method: str, mode: str) -> str | None:
    return _direct_provider_setup_hint(service_slug, auth_method, mode) or _mapped_provider_setup_hint(
        service_slug,
        auth_method,
        mode,
    )


def _db_direct_top_provider() -> dict[str, str | None]:
    return {
        "slug": _DB_DIRECT_PROVIDER_SLUG,
        "an_score": None,
        "tier_label": "Direct",
    }


def _warehouse_direct_top_provider() -> dict[str, str | None]:
    return {
        "slug": _WAREHOUSE_DIRECT_PROVIDER_SLUG,
        "an_score": None,
        "tier_label": "Direct",
    }


def _object_storage_direct_top_provider() -> dict[str, str | None]:
    return {
        "slug": _OBJECT_STORAGE_DIRECT_PROVIDER_SLUG,
        "an_score": None,
        "tier_label": "Direct",
    }


def _support_direct_top_provider(capability_id: str) -> dict[str, str | None]:
    return {
        "slug": _support_direct_provider_slug(capability_id),
        "an_score": None,
        "tier_label": "Direct",
    }


def _deployment_direct_top_provider() -> dict[str, str | None]:
    return {
        "slug": _DEPLOYMENT_DIRECT_PROVIDER_SLUG,
        "an_score": None,
        "tier_label": "Direct",
    }


def _actions_direct_top_provider() -> dict[str, str | None]:
    return {
        "slug": _ACTIONS_DIRECT_PROVIDER_SLUG,
        "an_score": None,
        "tier_label": "Direct",
    }


def _crm_direct_top_provider() -> dict[str, str | None]:
    preferred_slug = _crm_direct_provider_order()[0]
    return {
        "slug": preferred_slug,
        "an_score": None,
        "tier_label": "Direct",
    }


def _crm_direct_provider_order() -> list[str]:
    hubspot_configured = has_any_crm_bundle_configured("hubspot")
    salesforce_configured = has_any_crm_bundle_configured("salesforce")
    if salesforce_configured:
        return [_CRM_SALESFORCE_DIRECT_PROVIDER_SLUG, _CRM_HUBSPOT_DIRECT_PROVIDER_SLUG]
    if hubspot_configured:
        return [_CRM_HUBSPOT_DIRECT_PROVIDER_SLUG, _CRM_SALESFORCE_DIRECT_PROVIDER_SLUG]
    return [_CRM_HUBSPOT_DIRECT_PROVIDER_SLUG, _CRM_SALESFORCE_DIRECT_PROVIDER_SLUG]


def _crm_direct_provider_name(provider_slug: str) -> str:
    if provider_slug == _CRM_SALESFORCE_DIRECT_PROVIDER_SLUG:
        return _CRM_SALESFORCE_DIRECT_PROVIDER_NAME
    return _CRM_HUBSPOT_DIRECT_PROVIDER_NAME


def _db_direct_provider_details(capability_id: str) -> dict[str, object]:
    hosted_posture_suffix = (
        " Hosted Rhumb should use agent_vault; env-backed connection_ref setup is "
        "self-hosted/internal only."
    )
    notes = {
        "db.query.read": "Direct read-only PostgreSQL query execution via connection_ref with classifier, timeout, and result caps." + hosted_posture_suffix,
        "db.schema.describe": "Direct PostgreSQL schema inspection via connection_ref with bounded schema, table, and column scope." + hosted_posture_suffix,
        "db.row.get": "Direct PostgreSQL row lookup via connection_ref with exact-match filters and bounded result scope." + hosted_posture_suffix,
    }
    return {
        "service_slug": _DB_DIRECT_PROVIDER_SLUG,
        "service_name": _DB_DIRECT_PROVIDER_NAME,
        "category": _DB_DIRECT_PROVIDER_CATEGORY,
        "an_score": None,
        "tier": None,
        "tier_label": "Direct",
        "auth_method": "connection_ref",
        "endpoint_pattern": f"POST /v1/capabilities/{capability_id}/execute",
        "credential_modes": list(_DB_DIRECT_CREDENTIAL_MODES),
        "cost_per_call": None,
        "cost_currency": "USD",
        "free_tier_calls": None,
        "notes": notes.get(capability_id),
        "is_primary": True,
    }


def _warehouse_direct_provider_details(capability_id: str) -> dict[str, object]:
    notes = {
        "warehouse.query.read": "Direct read-only BigQuery query execution via warehouse_ref with dry-run enforcement, an explicit single-table allowlist, and bounded rows, bytes, and result size.",
        "warehouse.schema.describe": "Direct bounded BigQuery dataset and table schema inspection via warehouse_ref with explicit dataset/table allowlists and no SQL execution.",
    }
    return {
        "service_slug": _WAREHOUSE_DIRECT_PROVIDER_SLUG,
        "service_name": _WAREHOUSE_DIRECT_PROVIDER_NAME,
        "category": _WAREHOUSE_DIRECT_PROVIDER_CATEGORY,
        "an_score": None,
        "tier": None,
        "tier_label": "Direct",
        "auth_method": "warehouse_ref",
        "endpoint_pattern": f"POST /v1/capabilities/{capability_id}/execute",
        "credential_modes": list(_WAREHOUSE_DIRECT_CREDENTIAL_MODES),
        "cost_per_call": None,
        "cost_currency": "USD",
        "free_tier_calls": None,
        "notes": notes.get(capability_id),
        "is_primary": True,
    }


def _actions_direct_provider_details(capability_id: str) -> dict[str, object]:
    notes = {
        "workflow_run.list": "Direct read-only GitHub Actions workflow-run listing via actions_ref with explicit repository scope and bounded metadata only.",
        "workflow_run.get": "Direct read-only GitHub Actions workflow-run fetch via actions_ref with explicit repository scope and no logs or artifacts.",
    }
    return {
        "service_slug": _ACTIONS_DIRECT_PROVIDER_SLUG,
        "service_name": _ACTIONS_DIRECT_PROVIDER_NAME,
        "category": _ACTIONS_DIRECT_PROVIDER_CATEGORY,
        "an_score": None,
        "tier": None,
        "tier_label": "Direct",
        "auth_method": "actions_ref",
        "endpoint_pattern": f"POST /v1/capabilities/{capability_id}/execute",
        "credential_modes": list(_ACTIONS_DIRECT_CREDENTIAL_MODES),
        "cost_per_call": None,
        "cost_currency": "USD",
        "free_tier_calls": None,
        "notes": notes.get(capability_id),
        "is_primary": True,
    }


def _crm_direct_provider_details(capability_id: str) -> list[dict[str, object]]:
    return [
        _crm_direct_provider_detail(capability_id, provider_slug)
        for provider_slug in _crm_direct_provider_order()
    ]


def _crm_direct_provider_detail(capability_id: str, provider_slug: str) -> dict[str, object]:
    notes_by_provider = {
        _CRM_HUBSPOT_DIRECT_PROVIDER_SLUG: {
            "crm.object.describe": "Direct read-only HubSpot CRM object property describe via crm_ref with explicit object and property scope.",
            "crm.record.search": "Direct read-only HubSpot CRM record search via crm_ref with explicit object/property scope, a bounded simple filters list, and at most two sorts.",
            "crm.record.get": "Direct read-only HubSpot CRM record fetch via crm_ref with explicit object/property scope and optional exact record allowlists.",
        },
        _CRM_SALESFORCE_DIRECT_PROVIDER_SLUG: {
            "crm.object.describe": "Direct read-only Salesforce object describe via crm_ref with exact object and field allowlists.",
            "crm.record.search": "Direct read-only Salesforce record search via crm_ref with exact object/field scope, generated provider-side query clauses, and no caller-supplied SOQL or SOSL.",
            "crm.record.get": "Direct read-only Salesforce record fetch via crm_ref with exact object/field scope and optional exact record allowlists.",
        },
    }
    return {
        "service_slug": provider_slug,
        "service_name": _crm_direct_provider_name(provider_slug),
        "category": _CRM_DIRECT_PROVIDER_CATEGORY,
        "an_score": None,
        "tier": None,
        "tier_label": "Direct",
        "auth_method": "crm_ref",
        "endpoint_pattern": f"POST /v1/capabilities/{capability_id}/execute",
        "credential_modes": list(_CRM_DIRECT_CREDENTIAL_MODES),
        "cost_per_call": None,
        "cost_currency": "USD",
        "free_tier_calls": None,
        "notes": notes_by_provider[provider_slug].get(capability_id),
        "is_primary": provider_slug == _crm_direct_provider_order()[0],
    }


def _object_storage_direct_provider_details(capability_id: str) -> dict[str, object]:
    notes = {
        "object.list": "Direct read-only AWS S3 object listing via storage_ref with bucket/prefix allowlists and bounded pagination.",
        "object.head": "Direct AWS S3 object metadata fetch via storage_ref with bucket/prefix allowlists.",
        "object.get": "Direct bounded AWS S3 object fetch via storage_ref with bucket/prefix allowlists and byte caps.",
    }
    return {
        "service_slug": _OBJECT_STORAGE_DIRECT_PROVIDER_SLUG,
        "service_name": _OBJECT_STORAGE_DIRECT_PROVIDER_NAME,
        "category": _OBJECT_STORAGE_DIRECT_PROVIDER_CATEGORY,
        "an_score": None,
        "tier": None,
        "tier_label": "Direct",
        "auth_method": "storage_ref",
        "endpoint_pattern": f"POST /v1/capabilities/{capability_id}/execute",
        "credential_modes": list(_OBJECT_STORAGE_DIRECT_CREDENTIAL_MODES),
        "cost_per_call": None,
        "cost_currency": "USD",
        "free_tier_calls": None,
        "notes": notes.get(capability_id),
        "is_primary": True,
    }


def _deployment_direct_provider_details(capability_id: str) -> dict[str, object]:
    notes = {
        "deployment.list": "Direct read-only Vercel deployment listing via deployment_ref with explicit project scope and optional target bounds.",
        "deployment.get": "Direct read-only Vercel deployment fetch via deployment_ref with explicit project scope, optional target bounds, and bounded failure metadata.",
    }
    return {
        "service_slug": _DEPLOYMENT_DIRECT_PROVIDER_SLUG,
        "service_name": _DEPLOYMENT_DIRECT_PROVIDER_NAME,
        "category": _DEPLOYMENT_DIRECT_PROVIDER_CATEGORY,
        "an_score": None,
        "tier": None,
        "tier_label": "Direct",
        "auth_method": "deployment_ref",
        "endpoint_pattern": f"POST /v1/capabilities/{capability_id}/execute",
        "credential_modes": list(_DEPLOYMENT_DIRECT_CREDENTIAL_MODES),
        "cost_per_call": None,
        "cost_currency": "USD",
        "free_tier_calls": None,
        "notes": notes.get(capability_id),
        "is_primary": True,
    }


def _support_direct_provider_details(capability_id: str) -> dict[str, object]:
    notes = {
        "ticket.search": "Direct read-only Zendesk ticket search via support_ref with explicit brand/group scope and bounded results.",
        "ticket.get": "Direct read-only Zendesk ticket fetch via support_ref with scope enforcement and bounded plain-text fields.",
        "ticket.list_comments": "Direct read-only Zendesk ticket comment fetch via support_ref with public-comments-only default.",
        "conversation.list": "Direct read-only Intercom conversation listing via support_ref with explicit team/admin scope and bounded results.",
        "conversation.get": "Direct read-only Intercom conversation fetch via support_ref with scope enforcement and bounded plain-text source fields.",
        "conversation.list_parts": "Direct read-only Intercom conversation parts fetch via support_ref with customer-visible-by-default notes handling.",
    }
    return {
        "service_slug": _support_direct_provider_slug(capability_id),
        "service_name": _support_direct_provider_name(capability_id),
        "category": _SUPPORT_DIRECT_PROVIDER_CATEGORY,
        "an_score": None,
        "tier": None,
        "tier_label": "Direct",
        "auth_method": "support_ref",
        "endpoint_pattern": f"POST /v1/capabilities/{capability_id}/execute",
        "credential_modes": list(_SUPPORT_DIRECT_CREDENTIAL_MODES),
        "cost_per_call": None,
        "cost_currency": "USD",
        "free_tier_calls": None,
        "notes": notes.get(capability_id),
        "is_primary": True,
    }


def _db_direct_resolve_payload(capability_id: str) -> dict[str, object]:
    provider = {
        "service_slug": _DB_DIRECT_PROVIDER_SLUG,
        "service_name": _DB_DIRECT_PROVIDER_NAME,
        "an_score": None,
        "execution_score": None,
        "access_readiness_score": None,
        "tier": None,
        "tier_label": "Direct",
        "confidence": None,
        "cost_per_call": None,
        "cost_currency": "USD",
        "free_tier_calls": None,
        "credential_modes": list(_DB_DIRECT_CREDENTIAL_MODES),
        "auth_method": "connection_ref",
        "endpoint_pattern": f"POST /v1/capabilities/{capability_id}/execute",
        "recommendation": "available",
        "recommendation_reason": "Direct read-only PostgreSQL execution. Hosted Rhumb uses agent_vault; env-backed connection_ref is self-hosted/internal only.",
        "circuit_state": "n/a",
        "available_for_execute": True,
        "configured": False,
    }
    return {
        "capability": capability_id,
        "providers": [provider],
        "fallback_chain": [_DB_DIRECT_PROVIDER_SLUG],
        "related_bundles": [],
        "execute_hint": _with_execute_hint_fallbacks(
            _execute_hint_from_provider(capability_id, provider),
            [provider],
        ),
    }


def _warehouse_direct_resolve_payload(capability_id: str) -> dict[str, object]:
    configured = has_any_warehouse_bundle_configured("bigquery")
    provider = {
        "service_slug": _WAREHOUSE_DIRECT_PROVIDER_SLUG,
        "service_name": _WAREHOUSE_DIRECT_PROVIDER_NAME,
        "an_score": None,
        "execution_score": None,
        "access_readiness_score": None,
        "tier": None,
        "tier_label": "Direct",
        "confidence": None,
        "cost_per_call": None,
        "cost_currency": "USD",
        "free_tier_calls": None,
        "credential_modes": list(_WAREHOUSE_DIRECT_CREDENTIAL_MODES),
        "auth_method": "warehouse_ref",
        "endpoint_pattern": f"POST /v1/capabilities/{capability_id}/execute",
        "recommendation": "available",
        "recommendation_reason": "Direct read-only BigQuery execution via warehouse_ref with byok service-account JSON bundles, dry-run-before-run enforcement, and explicit dataset/table allowlists.",
        "circuit_state": "n/a",
        "available_for_execute": True,
        "configured": configured,
    }
    return {
        "capability": capability_id,
        "providers": [provider],
        "fallback_chain": [_WAREHOUSE_DIRECT_PROVIDER_SLUG],
        "related_bundles": [],
        "execute_hint": _with_execute_hint_fallbacks(
            _execute_hint_from_provider(capability_id, provider),
            [provider],
        ),
    }


def _object_storage_direct_resolve_payload(capability_id: str) -> dict[str, object]:
    provider = {
        "service_slug": _OBJECT_STORAGE_DIRECT_PROVIDER_SLUG,
        "service_name": _OBJECT_STORAGE_DIRECT_PROVIDER_NAME,
        "an_score": None,
        "execution_score": None,
        "access_readiness_score": None,
        "tier": None,
        "tier_label": "Direct",
        "confidence": None,
        "cost_per_call": None,
        "cost_currency": "USD",
        "free_tier_calls": None,
        "credential_modes": list(_OBJECT_STORAGE_DIRECT_CREDENTIAL_MODES),
        "auth_method": "storage_ref",
        "endpoint_pattern": f"POST /v1/capabilities/{capability_id}/execute",
        "recommendation": "available",
        "recommendation_reason": "Direct read-only AWS S3 execution via storage_ref with bucket/prefix allowlists and bounded byte limits.",
        "circuit_state": "n/a",
        "available_for_execute": True,
        "configured": False,
    }
    return {
        "capability": capability_id,
        "providers": [provider],
        "fallback_chain": [_OBJECT_STORAGE_DIRECT_PROVIDER_SLUG],
        "related_bundles": [],
        "execute_hint": _with_execute_hint_fallbacks(
            _execute_hint_from_provider(capability_id, provider),
            [provider],
        ),
    }


def _deployment_direct_resolve_payload(capability_id: str) -> dict[str, object]:
    configured = has_any_deployment_bundle_configured("vercel")
    provider = {
        "service_slug": _DEPLOYMENT_DIRECT_PROVIDER_SLUG,
        "service_name": _DEPLOYMENT_DIRECT_PROVIDER_NAME,
        "an_score": None,
        "execution_score": None,
        "access_readiness_score": None,
        "tier": None,
        "tier_label": "Direct",
        "confidence": None,
        "cost_per_call": None,
        "cost_currency": "USD",
        "free_tier_calls": None,
        "credential_modes": list(_DEPLOYMENT_DIRECT_CREDENTIAL_MODES),
        "auth_method": "deployment_ref",
        "endpoint_pattern": f"POST /v1/capabilities/{capability_id}/execute",
        "recommendation": "available",
        "recommendation_reason": "Direct read-only Vercel deployment visibility via deployment_ref with explicit project scope and optional target limits.",
        "circuit_state": "n/a",
        "available_for_execute": True,
        "configured": configured,
    }
    return {
        "capability": capability_id,
        "providers": [provider],
        "fallback_chain": [_DEPLOYMENT_DIRECT_PROVIDER_SLUG],
        "related_bundles": [],
        "execute_hint": _with_execute_hint_fallbacks(
            _execute_hint_from_provider(capability_id, provider),
            [provider],
        ),
    }


def _actions_direct_resolve_payload(capability_id: str) -> dict[str, object]:
    configured = has_any_actions_bundle_configured("github")
    provider = {
        "service_slug": _ACTIONS_DIRECT_PROVIDER_SLUG,
        "service_name": _ACTIONS_DIRECT_PROVIDER_NAME,
        "an_score": None,
        "execution_score": None,
        "access_readiness_score": None,
        "tier": None,
        "tier_label": "Direct",
        "confidence": None,
        "cost_per_call": None,
        "cost_currency": "USD",
        "free_tier_calls": None,
        "credential_modes": list(_ACTIONS_DIRECT_CREDENTIAL_MODES),
        "auth_method": "actions_ref",
        "endpoint_pattern": f"POST /v1/capabilities/{capability_id}/execute",
        "recommendation": "available",
        "recommendation_reason": "Direct read-only GitHub Actions workflow-run visibility via actions_ref with explicit repository scope and bounded metadata only.",
        "circuit_state": "n/a",
        "available_for_execute": True,
        "configured": configured,
    }
    return {
        "capability": capability_id,
        "providers": [provider],
        "fallback_chain": [_ACTIONS_DIRECT_PROVIDER_SLUG],
        "related_bundles": [],
        "execute_hint": _with_execute_hint_fallbacks(
            _execute_hint_from_provider(capability_id, provider),
            [provider],
        ),
    }


def _crm_direct_resolve_payload(capability_id: str) -> dict[str, object]:
    providers = []
    for provider_slug in _crm_direct_provider_order():
        providers.append({
            "service_slug": provider_slug,
            "service_name": _crm_direct_provider_name(provider_slug),
            "an_score": None,
            "execution_score": None,
            "access_readiness_score": None,
            "tier": None,
            "tier_label": "Direct",
            "confidence": None,
            "cost_per_call": None,
            "cost_currency": "USD",
            "free_tier_calls": None,
            "credential_modes": list(_CRM_DIRECT_CREDENTIAL_MODES),
            "auth_method": "crm_ref",
            "endpoint_pattern": f"POST /v1/capabilities/{capability_id}/execute",
            "recommendation": "available",
            "recommendation_reason": (
                "Direct read-only Salesforce CRM execution via crm_ref with exact object/field scope, generated bounded SOQL, and optional record allowlists."
                if provider_slug == _CRM_SALESFORCE_DIRECT_PROVIDER_SLUG
                else "Direct read-only HubSpot CRM execution via crm_ref with explicit object/property scope and optional record/search/sort allowlists."
            ),
            "circuit_state": "n/a",
            "available_for_execute": True,
            "configured": has_any_crm_bundle_configured(provider_slug),
        })
    preferred_provider = providers[0]
    return {
        "capability": capability_id,
        "providers": providers,
        "fallback_chain": [provider["service_slug"] for provider in providers],
        "related_bundles": [],
        "execute_hint": _with_execute_hint_fallbacks(
            _execute_hint_from_provider(capability_id, preferred_provider),
            providers,
        ),
    }


def _support_direct_resolve_payload(capability_id: str) -> dict[str, object]:
    provider_slug = _support_direct_provider_slug(capability_id)
    configured = has_any_support_bundle_configured(provider_slug)
    provider = {
        "service_slug": provider_slug,
        "service_name": _support_direct_provider_name(capability_id),
        "an_score": None,
        "execution_score": None,
        "access_readiness_score": None,
        "tier": None,
        "tier_label": "Direct",
        "confidence": None,
        "cost_per_call": None,
        "cost_currency": "USD",
        "free_tier_calls": None,
        "credential_modes": list(_SUPPORT_DIRECT_CREDENTIAL_MODES),
        "auth_method": "support_ref",
        "endpoint_pattern": f"POST /v1/capabilities/{capability_id}/execute",
        "recommendation": "available",
        "recommendation_reason": _support_direct_recommendation_reason(capability_id),
        "circuit_state": "n/a",
        "available_for_execute": True,
        "configured": configured,
    }
    return {
        "capability": capability_id,
        "providers": [provider],
        "fallback_chain": [provider_slug],
        "related_bundles": [],
        "execute_hint": _with_execute_hint_fallbacks(
            _execute_hint_from_provider(capability_id, provider),
            [provider],
        ),
    }


def _synthetic_direct_resolve_payload(capability_id: str) -> dict[str, object] | None:
    if _is_db_direct_capability(capability_id):
        return _db_direct_resolve_payload(capability_id)
    if _is_warehouse_direct_capability(capability_id):
        return _warehouse_direct_resolve_payload(capability_id)
    if _is_object_storage_direct_capability(capability_id):
        return _object_storage_direct_resolve_payload(capability_id)
    if _is_deployment_direct_capability(capability_id):
        return _deployment_direct_resolve_payload(capability_id)
    if _is_actions_direct_capability(capability_id):
        return _actions_direct_resolve_payload(capability_id)
    if _is_crm_direct_capability(capability_id):
        return _crm_direct_resolve_payload(capability_id)
    if _is_support_direct_capability(capability_id):
        return _support_direct_resolve_payload(capability_id)
    return None


def _capability_credential_modes_url(capability_id: str) -> str:
    return f"/v1/capabilities/{quote(capability_id)}/credential-modes"


def _provider_mode_setup_url(service_slug: str, mode: str) -> str | None:
    normalized_mode = _canonicalize_credential_mode(mode)
    if normalized_mode == "agent_vault":
        return f"/v1/services/{quote(service_slug)}/ceremony"
    return None


def _empty_resolve_payload(
    capability_id: str,
    *,
    requested_credential_mode: str | None = None,
    recovery_reason: str | None = None,
    recovery_items: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "capability": capability_id,
        "providers": [],
        "fallback_chain": [],
        "related_bundles": [],
        "execute_hint": None,
    }
    normalized_requested_mode = _canonicalize_credential_mode(requested_credential_mode)
    if recovery_reason and normalized_requested_mode:
        payload["recovery_hint"] = _credential_mode_filter_recovery_hint(
            capability_id,
            normalized_requested_mode,
            reason=recovery_reason,
            recovery_items=recovery_items,
        )
    return payload


def _canonicalize_credential_mode(credential_mode: str | None) -> str | None:
    normalized = str(credential_mode or "").strip().lower()
    if not normalized:
        return None
    if normalized == "byo":
        return "byok"
    return normalized


def _canonicalize_credential_modes(
    credential_modes: object,
    *,
    default: tuple[str, ...] = ("byok",),
) -> list[str]:
    raw_modes = credential_modes if isinstance(credential_modes, list) and credential_modes else list(default)
    normalized_modes: list[str] = []
    seen: set[str] = set()
    for mode in raw_modes:
        normalized = _canonicalize_credential_mode(str(mode))
        if normalized and normalized not in seen:
            normalized_modes.append(normalized)
            seen.add(normalized)
    if normalized_modes:
        return normalized_modes
    return list(default)


def _credential_mode_aliases(credential_mode: str | None) -> set[str]:
    normalized = _canonicalize_credential_mode(credential_mode)
    if not normalized:
        return set()
    aliases = {normalized}
    if normalized == "byok":
        aliases.update({"byo", "byok"})
    return aliases


def _recovery_supported_provider_slugs(items: list[dict[str, object]]) -> list[str]:
    provider_slugs: list[str] = []
    seen: set[str] = set()
    for item in items:
        provider_slug = str(item.get("service_slug") or "")
        if not provider_slug or provider_slug in seen:
            continue
        provider_slugs.append(provider_slug)
        seen.add(provider_slug)
    return provider_slugs


def _recovery_supported_credential_modes(items: list[dict[str, object]]) -> list[str]:
    discovered_modes: list[str] = []
    seen: set[str] = set()
    for item in items:
        for mode in _canonicalize_credential_modes(item.get("credential_modes")):
            if mode in seen:
                continue
            discovered_modes.append(mode)
            seen.add(mode)

    ordered_modes = [
        mode
        for mode in ("rhumb_managed", "agent_vault", "byok")
        if mode in seen
    ]
    ordered_modes.extend(mode for mode in discovered_modes if mode not in ordered_modes)
    return ordered_modes


def _credential_mode_filter_recovery_hint(
    capability_id: str,
    requested_credential_mode: str | None,
    *,
    reason: str,
    recovery_items: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    recovery_hint: dict[str, object] = {
        "reason": reason,
        "requested_credential_mode": _canonicalize_credential_mode(requested_credential_mode),
        "credential_modes_url": _capability_credential_modes_url(capability_id),
    }

    if recovery_items:
        provider_slugs = _recovery_supported_provider_slugs(recovery_items)
        if provider_slugs:
            recovery_hint["supported_provider_slugs"] = provider_slugs

        supported_modes = _recovery_supported_credential_modes(recovery_items)
        if supported_modes:
            recovery_hint["supported_credential_modes"] = supported_modes

    return recovery_hint


def _supports_requested_credential_mode(
    supported_modes: object,
    credential_mode: str | None,
) -> bool:
    requested_modes = _credential_mode_aliases(credential_mode)
    if not requested_modes:
        return True
    if not isinstance(supported_modes, list):
        return False
    normalized_supported = set()
    for mode in supported_modes:
        normalized_supported.update(_credential_mode_aliases(str(mode)))
    return bool(normalized_supported & requested_modes)


def _apply_direct_resolve_credential_mode_filter(
    capability_id: str,
    payload: dict[str, object],
    credential_mode: str | None,
) -> dict[str, object]:
    if not credential_mode:
        return payload

    providers = payload.get("providers")
    if not isinstance(providers, list):
        return payload

    filtered_providers = [
        provider
        for provider in providers
        if isinstance(provider, dict)
        and _supports_requested_credential_mode(provider.get("credential_modes"), credential_mode)
    ]

    filtered_payload = dict(payload)
    filtered_payload["providers"] = filtered_providers
    filtered_payload["fallback_chain"] = [
        str(provider.get("service_slug"))
        for provider in filtered_providers
        if provider.get("service_slug")
    ]

    execute_hint = payload.get("execute_hint")
    if not filtered_providers:
        filtered_payload["execute_hint"] = None
        filtered_payload["recovery_hint"] = _credential_mode_filter_recovery_hint(
            capability_id,
            credential_mode,
            reason="no_providers_match_credential_mode",
            recovery_items=[provider for provider in providers if isinstance(provider, dict)],
        )
        return filtered_payload

    filtered_payload.pop("recovery_hint", None)

    if isinstance(execute_hint, dict):
        preferred_slug = execute_hint.get("preferred_provider")
        preferred_provider = next(
            (
                provider
                for provider in filtered_providers
                if provider.get("service_slug") == preferred_slug
            ),
            filtered_providers[0],
        )
        filtered_payload["execute_hint"] = _with_execute_hint_fallbacks(
            _execute_hint_from_provider(
                capability_id,
                preferred_provider,
                requested_credential_mode=credential_mode,
            ),
            filtered_providers,
            selection_providers=[provider for provider in providers if isinstance(provider, dict)],
            requested_credential_mode=credential_mode,
        )

    return filtered_payload


def _has_proxy_credential_configured(service_slug: str, auth_method: str) -> bool:
    try:
        from services.proxy_credentials import get_credential_store
        store = get_credential_store()
        return store.get_credential(service_slug, auth_method) is not None
    except Exception:
        return False


def _mapped_provider_is_configured(
    credential_modes: object,
    *,
    byok_configured: bool,
    requested_credential_mode: str | None = None,
) -> bool:
    normalized_modes = _canonicalize_credential_modes(credential_modes)
    requested_mode = _canonicalize_credential_mode(requested_credential_mode)

    if requested_mode:
        if requested_mode not in normalized_modes:
            return False
        if requested_mode == "rhumb_managed":
            return True
        if requested_mode == "byok":
            return byok_configured
        return False

    if "rhumb_managed" in normalized_modes:
        return True
    if "byok" in normalized_modes:
        return byok_configured
    return False


def _provider_can_back_execute_hint(provider: dict[str, object]) -> bool:
    return bool(provider.get("available_for_execute") and provider.get("endpoint_pattern"))


def _preferred_credential_mode_for_execute_hint(
    credential_modes: object,
    *,
    requested_credential_mode: str | None = None,
) -> str | None:
    normalized_modes = _canonicalize_credential_modes(credential_modes)
    requested_mode = _canonicalize_credential_mode(requested_credential_mode)
    if requested_mode and requested_mode in normalized_modes:
        return requested_mode
    for mode in ("rhumb_managed", "agent_vault", "byok"):
        if mode in normalized_modes:
            return mode
    if normalized_modes:
        return normalized_modes[0]
    return None


def _execute_hint_from_provider(
    capability_id: str,
    provider: dict[str, object],
    *,
    requested_credential_mode: str | None = None,
) -> dict[str, object]:
    credential_modes = _canonicalize_credential_modes(provider.get("credential_modes", ["byok"]))
    auth_method = str(provider.get("auth_method") or "")
    configured = bool(provider.get("configured"))
    execute_hint = {
        "preferred_provider": provider["service_slug"],
        "endpoint_pattern": provider.get("endpoint_pattern"),
        "estimated_cost_usd": provider.get("cost_per_call"),
        "auth_method": auth_method,
        "credential_modes": credential_modes,
        "configured": configured,
        "credential_modes_url": _capability_credential_modes_url(capability_id),
    }
    preferred_credential_mode = _preferred_credential_mode_for_execute_hint(
        credential_modes,
        requested_credential_mode=requested_credential_mode,
    )
    if preferred_credential_mode is not None:
        execute_hint["preferred_credential_mode"] = preferred_credential_mode
        if not configured:
            setup_hint = _provider_mode_setup_hint(
                str(provider.get("service_slug") or ""),
                auth_method,
                preferred_credential_mode,
            )
            if setup_hint is not None:
                execute_hint["setup_hint"] = setup_hint
            setup_url = _provider_mode_setup_url(
                str(provider.get("service_slug") or ""),
                preferred_credential_mode,
            )
            if setup_url is not None:
                execute_hint["setup_url"] = setup_url
    return execute_hint


def _execute_ready_fallback_chain(providers: list[dict[str, object]]) -> list[str]:
    return [
        str(provider.get("service_slug"))
        for provider in providers
        if provider.get("service_slug")
        and provider.get("recommendation") in ("preferred", "available")
        and _provider_can_back_execute_hint(provider)
    ][:3]


def _execute_ready_recovery_hint(
    capability_id: str,
    providers: list[dict[str, object]],
    *,
    requested_credential_mode: str | None = None,
) -> dict[str, object] | None:
    if not providers or any(_provider_can_back_execute_hint(provider) for provider in providers):
        return None

    recovery_hint: dict[str, object] = {
        "reason": "no_execute_ready_providers",
        "credential_modes_url": _capability_credential_modes_url(capability_id),
    }

    normalized_requested_mode = _canonicalize_credential_mode(requested_credential_mode)
    if normalized_requested_mode:
        recovery_hint["requested_credential_mode"] = normalized_requested_mode

    supported_provider_slugs = _recovery_supported_provider_slugs(providers)
    if supported_provider_slugs:
        recovery_hint["supported_provider_slugs"] = supported_provider_slugs

    supported_credential_modes = _recovery_supported_credential_modes(providers)
    if supported_credential_modes:
        recovery_hint["supported_credential_modes"] = supported_credential_modes

    unavailable_provider_slugs = [
        str(provider.get("service_slug"))
        for provider in providers
        if provider.get("service_slug") and not provider.get("available_for_execute")
    ]
    if unavailable_provider_slugs:
        recovery_hint["unavailable_provider_slugs"] = unavailable_provider_slugs

    not_execute_ready_provider_slugs = [
        str(provider.get("service_slug"))
        for provider in providers
        if provider.get("service_slug") and not provider.get("endpoint_pattern")
    ]
    if not_execute_ready_provider_slugs:
        recovery_hint["not_execute_ready_provider_slugs"] = not_execute_ready_provider_slugs

    return recovery_hint


def _execute_hint_fallback_providers(
    providers: list[dict[str, object]],
    *,
    preferred_provider: str,
) -> list[str]:
    return [
        str(provider.get("service_slug"))
        for provider in providers
        if provider.get("service_slug")
        and provider.get("service_slug") != preferred_provider
        and _provider_can_back_execute_hint(provider)
    ][:3]


def _execute_hint_selection_metadata(
    execute_hint: dict[str, object],
    providers: list[dict[str, object]],
    *,
    selection_providers: list[dict[str, object]] | None = None,
    requested_credential_mode: str | None = None,
) -> dict[str, object]:
    preferred_provider = str(execute_hint.get("preferred_provider") or "")
    if not preferred_provider:
        return {}

    ranked_providers = [
        provider
        for provider in (selection_providers or providers)
        if isinstance(provider, dict) and provider.get("service_slug")
    ]
    if not ranked_providers:
        return {}

    selected_index = next(
        (
            index
            for index, provider in enumerate(ranked_providers)
            if provider.get("service_slug") == preferred_provider
        ),
        None,
    )
    if selected_index is None:
        return {}

    skipped_providers = ranked_providers[:selected_index]
    if not skipped_providers:
        return {"selection_reason": "highest_ranked_provider"}

    reason = "lower_ranked_provider_selected"
    skipped_unavailable_provider_slugs = [
        str(provider.get("service_slug"))
        for provider in skipped_providers
        if provider.get("service_slug") and not provider.get("available_for_execute")
    ]
    skipped_not_execute_ready_provider_slugs = [
        str(provider.get("service_slug"))
        for provider in skipped_providers
        if provider.get("service_slug") and not provider.get("endpoint_pattern")
    ]
    if requested_credential_mode and any(
        not _supports_requested_credential_mode(provider.get("credential_modes"), requested_credential_mode)
        for provider in skipped_providers
    ):
        reason = "higher_ranked_provider_filtered_by_credential_mode"
    elif skipped_unavailable_provider_slugs and skipped_not_execute_ready_provider_slugs:
        reason = "higher_ranked_provider_mixed_execute_blockers"
    elif skipped_unavailable_provider_slugs:
        reason = "higher_ranked_provider_unavailable"
    elif skipped_not_execute_ready_provider_slugs:
        reason = "higher_ranked_provider_not_execute_ready"
    elif bool(ranked_providers[selected_index].get("configured")):
        reason = "configured_provider_preferred"

    metadata = {
        "selection_reason": reason,
        "skipped_provider_slugs": [
            str(provider.get("service_slug"))
            for provider in skipped_providers
            if provider.get("service_slug")
        ],
    }
    if skipped_unavailable_provider_slugs:
        metadata["unavailable_provider_slugs"] = skipped_unavailable_provider_slugs
    if skipped_not_execute_ready_provider_slugs:
        metadata["not_execute_ready_provider_slugs"] = skipped_not_execute_ready_provider_slugs
    return metadata


def _with_execute_hint_fallbacks(
    execute_hint: dict[str, object] | None,
    providers: list[dict[str, object]],
    *,
    selection_providers: list[dict[str, object]] | None = None,
    requested_credential_mode: str | None = None,
) -> dict[str, object] | None:
    if not isinstance(execute_hint, dict):
        return execute_hint

    preferred_provider = str(execute_hint.get("preferred_provider") or "")
    if not preferred_provider:
        return execute_hint

    enriched_execute_hint = {
        **execute_hint,
        **_execute_hint_selection_metadata(
            execute_hint,
            providers,
            selection_providers=selection_providers,
            requested_credential_mode=requested_credential_mode,
        ),
    }

    fallback_providers = _execute_hint_fallback_providers(
        providers,
        preferred_provider=preferred_provider,
    )
    if not fallback_providers:
        return enriched_execute_hint

    return {
        **enriched_execute_hint,
        "fallback_providers": fallback_providers,
    }


def _pick_mapped_execute_hint(
    capability_id: str,
    providers: list[dict[str, object]],
    *,
    requested_credential_mode: str | None = None,
) -> dict[str, object] | None:
    configured_provider = next(
        (
            provider
            for provider in providers
            if provider.get("configured") and _provider_can_back_execute_hint(provider)
        ),
        None,
    )
    if configured_provider is not None:
        return _execute_hint_from_provider(
            capability_id,
            configured_provider,
            requested_credential_mode=requested_credential_mode,
        )

    fallback_provider = next(
        (provider for provider in providers if _provider_can_back_execute_hint(provider)),
        None,
    )
    if fallback_provider is not None:
        return _execute_hint_from_provider(
            capability_id,
            fallback_provider,
            requested_credential_mode=requested_credential_mode,
        )

    return None


def _db_direct_credential_modes(capability_id: str) -> dict[str, object]:
    return {
        "capability_id": capability_id,
        "providers": [
            {
                "service_slug": _DB_DIRECT_PROVIDER_SLUG,
                "auth_method": "connection_ref",
                "modes": [
                    {
                        "mode": "byok",
                        "available": True,
                        "configured": False,
                        "setup_hint": _provider_mode_setup_hint(_DB_DIRECT_PROVIDER_SLUG, "connection_ref", "byok"),
                    },
                    {
                        "mode": "agent_vault",
                        "available": True,
                        "configured": False,
                        "setup_hint": _provider_mode_setup_hint(_DB_DIRECT_PROVIDER_SLUG, "connection_ref", "agent_vault"),
                    }
                ],
                "any_configured": False,
            }
        ],
    }


def _warehouse_direct_credential_modes(capability_id: str) -> dict[str, object]:
    configured = has_any_warehouse_bundle_configured("bigquery")
    return {
        "capability_id": capability_id,
        "providers": [
            {
                "service_slug": _WAREHOUSE_DIRECT_PROVIDER_SLUG,
                "auth_method": "warehouse_ref",
                "modes": [
                    {
                        "mode": "byok",
                        "available": True,
                        "configured": configured,
                        "setup_hint": _provider_mode_setup_hint(_WAREHOUSE_DIRECT_PROVIDER_SLUG, "warehouse_ref", "byok"),
                    }
                ],
                "any_configured": configured,
            }
        ],
    }


def _object_storage_direct_credential_modes(capability_id: str) -> dict[str, object]:
    return {
        "capability_id": capability_id,
        "providers": [
            {
                "service_slug": _OBJECT_STORAGE_DIRECT_PROVIDER_SLUG,
                "auth_method": "storage_ref",
                "modes": [
                    {
                        "mode": "byok",
                        "available": True,
                        "configured": False,
                        "setup_hint": _provider_mode_setup_hint(_OBJECT_STORAGE_DIRECT_PROVIDER_SLUG, "storage_ref", "byok"),
                    }
                ],
                "any_configured": False,
            }
        ],
    }


def _deployment_direct_credential_modes(capability_id: str) -> dict[str, object]:
    configured = has_any_deployment_bundle_configured("vercel")
    return {
        "capability_id": capability_id,
        "providers": [
            {
                "service_slug": _DEPLOYMENT_DIRECT_PROVIDER_SLUG,
                "auth_method": "deployment_ref",
                "modes": [
                    {
                        "mode": "byok",
                        "available": True,
                        "configured": configured,
                        "setup_hint": _provider_mode_setup_hint(_DEPLOYMENT_DIRECT_PROVIDER_SLUG, "deployment_ref", "byok"),
                    }
                ],
                "any_configured": configured,
            }
        ],
    }


def _actions_direct_credential_modes(capability_id: str) -> dict[str, object]:
    configured = has_any_actions_bundle_configured("github")
    return {
        "capability_id": capability_id,
        "providers": [
            {
                "service_slug": _ACTIONS_DIRECT_PROVIDER_SLUG,
                "auth_method": "actions_ref",
                "modes": [
                    {
                        "mode": "byok",
                        "available": True,
                        "configured": configured,
                        "setup_hint": _provider_mode_setup_hint(_ACTIONS_DIRECT_PROVIDER_SLUG, "actions_ref", "byok"),
                    }
                ],
                "any_configured": configured,
            }
        ],
    }


def _crm_direct_credential_modes(capability_id: str) -> dict[str, object]:
    return {
        "capability_id": capability_id,
        "providers": [
            {
                "service_slug": provider_slug,
                "auth_method": "crm_ref",
                "modes": [
                    {
                        "mode": "byok",
                        "available": True,
                        "configured": has_any_crm_bundle_configured(provider_slug),
                        "setup_hint": _provider_mode_setup_hint(provider_slug, "crm_ref", "byok"),
                    }
                ],
                "any_configured": has_any_crm_bundle_configured(provider_slug),
            }
            for provider_slug in _crm_direct_provider_order()
        ],
    }


def _support_direct_credential_modes(capability_id: str) -> dict[str, object]:
    provider_slug = _support_direct_provider_slug(capability_id)
    configured = has_any_support_bundle_configured(provider_slug)
    return {
        "capability_id": capability_id,
        "providers": [
            {
                "service_slug": provider_slug,
                "auth_method": "support_ref",
                "modes": [
                    {
                        "mode": "byok",
                        "available": True,
                        "configured": configured,
                        "setup_hint": _provider_mode_setup_hint(provider_slug, "support_ref", "byok"),
                    }
                ],
                "any_configured": configured,
            }
        ],
    }


def _synthetic_capability_record(capability_id: str) -> dict[str, object] | None:

    db_records = {
        "db.query.read": {
            "id": "db.query.read",
            "domain": "database",
            "action": "query.read",
            "description": "Direct read-only PostgreSQL query execution with bounded rows, timeout, and result size.",
            "input_hint": "Provide connection_ref plus a read-only SQL query.",
            "outcome": "Returns read-only query results with provider attribution.",
        },
        "db.schema.describe": {
            "id": "db.schema.describe",
            "domain": "database",
            "action": "schema.describe",
            "description": "Direct PostgreSQL schema inspection with bounded schema, table, and column scope.",
            "input_hint": "Provide connection_ref and optional schemas/tables.",
            "outcome": "Returns tables, columns, and optional relationships.",
        },
        "db.row.get": {
            "id": "db.row.get",
            "domain": "database",
            "action": "row.get",
            "description": "Direct PostgreSQL row lookup with exact-match filters and bounded result scope.",
            "input_hint": "Provide connection_ref, table, and filters.",
            "outcome": "Returns bounded matching rows from the requested table.",
        },
    }
    warehouse_records = {
        "warehouse.query.read": {
            "id": "warehouse.query.read",
            "domain": "warehouse",
            "action": "query.read",
            "description": "Direct read-only BigQuery query execution with mandatory dry-run validation, explicit allowlists, and bounded rows, bytes, and result size.",
            "input_hint": "Provide warehouse_ref, a single-table read-only SELECT query, and optional params.",
            "outcome": "Returns bounded BigQuery query results with provider attribution and dry-run metadata.",
        },
        "warehouse.schema.describe": {
            "id": "warehouse.schema.describe",
            "domain": "warehouse",
            "action": "schema.describe",
            "description": "Direct BigQuery schema inspection with explicit dataset and table allowlists and bounded table and column scope.",
            "input_hint": "Provide warehouse_ref and optional dataset_refs or table_refs.",
            "outcome": "Returns bounded BigQuery table and column metadata for the allowlisted scope.",
        },
    }
    object_storage_records = {
        "object.list": {
            "id": "object.list",
            "domain": "storage",
            "action": "list",
            "description": "Direct read-only AWS S3 object listing with bucket and prefix allowlists.",
            "input_hint": "Provide storage_ref, bucket, and optional prefix.",
            "outcome": "Returns bounded object summaries for the allowed S3 location.",
        },
        "object.head": {
            "id": "object.head",
            "domain": "storage",
            "action": "head",
            "description": "Direct read-only AWS S3 object metadata fetch with bucket and prefix allowlists.",
            "input_hint": "Provide storage_ref, bucket, and key.",
            "outcome": "Returns object metadata like size, content type, and last modified timestamp.",
        },
        "object.get": {
            "id": "object.get",
            "domain": "storage",
            "action": "get",
            "description": "Direct read-only AWS S3 object fetch with bounded bytes and prefix allowlists.",
            "input_hint": "Provide storage_ref, bucket, key, and optional byte range.",
            "outcome": "Returns bounded object content as text or base64 with honest truncation state.",
        },
    }
    deployment_records = {
        "deployment.list": {
            "id": "deployment.list",
            "domain": "deployment",
            "action": "list",
            "description": "Direct read-only Vercel deployment listing with explicit project scope and optional target bounds.",
            "input_hint": "Provide deployment_ref and optional project, target, state, and time filters.",
            "outcome": "Returns bounded Vercel deployment summaries for the allowlisted scope.",
        },
        "deployment.get": {
            "id": "deployment.get",
            "domain": "deployment",
            "action": "get",
            "description": "Direct read-only Vercel deployment fetch with explicit project scope and bounded failure metadata.",
            "input_hint": "Provide deployment_ref and deployment_id.",
            "outcome": "Returns one allowed Vercel deployment with bounded alias and error details.",
        },
    }
    actions_records = {
        "workflow_run.list": {
            "id": "workflow_run.list",
            "domain": "workflow_run",
            "action": "list",
            "description": "Direct read-only GitHub Actions workflow-run listing with explicit repository scope and bounded metadata.",
            "input_hint": "Provide actions_ref, repository, and optional branch/status/event filters.",
            "outcome": "Returns bounded GitHub Actions workflow-run summaries for the allowlisted repository.",
        },
        "workflow_run.get": {
            "id": "workflow_run.get",
            "domain": "workflow_run",
            "action": "get",
            "description": "Direct read-only GitHub Actions workflow-run fetch with explicit repository scope and no logs or artifacts.",
            "input_hint": "Provide actions_ref, repository, and run_id.",
            "outcome": "Returns one allowed GitHub Actions workflow run with bounded metadata only.",
        },
    }
    crm_records = {
        "crm.object.describe": {
            "id": "crm.object.describe",
            "domain": "crm",
            "action": "object.describe",
            "description": "Direct read-only CRM object property describe with provider-scoped object and field allowlists.",
            "input_hint": "Provide crm_ref and object_type.",
            "outcome": "Returns the allowlisted CRM property metadata for the requested object.",
        },
        "crm.record.search": {
            "id": "crm.record.search",
            "domain": "crm",
            "action": "record.search",
            "description": "Direct read-only CRM record search with provider-scoped filters, exact allowlists, and bounded results.",
            "input_hint": "Provide crm_ref, object_type, and optional query, property_names, up to 5 filters, and up to 2 sorts.",
            "outcome": "Returns bounded CRM record summaries for the allowlisted scope.",
        },
        "crm.record.get": {
            "id": "crm.record.get",
            "domain": "crm",
            "action": "record.get",
            "description": "Direct read-only CRM record fetch with exact object/property scope and optional exact record allowlists.",
            "input_hint": "Provide crm_ref, object_type, and record_id.",
            "outcome": "Returns one allowed CRM record with bounded property values only.",
        },
    }
    support_records = {
        "ticket.search": {
            "id": "ticket.search",
            "domain": "support",
            "action": "search",
            "description": "Direct read-only Zendesk ticket search with explicit scope limits and bounded results.",
            "input_hint": "Provide support_ref, query, and optional limit/page_after.",
            "outcome": "Returns bounded Zendesk ticket summaries with honest provider attribution.",
        },
        "ticket.get": {
            "id": "ticket.get",
            "domain": "support",
            "action": "get",
            "description": "Direct read-only Zendesk ticket fetch with scope enforcement and bounded plain-text fields.",
            "input_hint": "Provide support_ref and ticket_id.",
            "outcome": "Returns one allowed Zendesk ticket with bounded description and custom field values.",
        },
        "ticket.list_comments": {
            "id": "ticket.list_comments",
            "domain": "support",
            "action": "list_comments",
            "description": "Direct read-only Zendesk ticket comment fetch with public-comments-only default.",
            "input_hint": "Provide support_ref, ticket_id, and optional include_internal/page_after.",
            "outcome": "Returns bounded Zendesk ticket comments with honest visibility rules.",
        },
        "conversation.list": {
            "id": "conversation.list",
            "domain": "support",
            "action": "list",
            "description": "Direct read-only Intercom conversation listing with explicit scope limits and bounded results.",
            "input_hint": "Provide support_ref and optional limit/page_after/state filters.",
            "outcome": "Returns bounded Intercom conversation summaries with honest provider attribution.",
        },
        "conversation.get": {
            "id": "conversation.get",
            "domain": "support",
            "action": "get",
            "description": "Direct read-only Intercom conversation fetch with scope enforcement and bounded source fields.",
            "input_hint": "Provide support_ref and conversation_id.",
            "outcome": "Returns one allowed Intercom conversation with bounded plain-text source content.",
        },
        "conversation.list_parts": {
            "id": "conversation.list_parts",
            "domain": "support",
            "action": "list_parts",
            "description": "Direct read-only Intercom conversation parts fetch with customer-visible-by-default note handling.",
            "input_hint": "Provide support_ref, conversation_id, and optional include_internal/page_after.",
            "outcome": "Returns bounded Intercom conversation parts with honest visibility rules.",
        },
    }
    return (
        db_records.get(capability_id)
        or warehouse_records.get(capability_id)
        or object_storage_records.get(capability_id)
        or deployment_records.get(capability_id)
        or actions_records.get(capability_id)
        or crm_records.get(capability_id)
        or support_records.get(capability_id)
    )


def _synthetic_capability_records() -> list[dict[str, object]]:
    return [
        record
        for capability_id in [
            "db.query.read",
            "db.schema.describe",
            "db.row.get",
            "warehouse.query.read",
            "warehouse.schema.describe",
            "object.list",
            "object.head",
            "object.get",
            "deployment.list",
            "deployment.get",
            "workflow_run.list",
            "workflow_run.get",
            "crm.object.describe",
            "crm.record.search",
            "crm.record.get",
            "ticket.search",
            "ticket.get",
            "ticket.list_comments",
            "conversation.list",
            "conversation.get",
            "conversation.list_parts",
        ]
        if (record := _synthetic_capability_record(capability_id)) is not None
    ]


_TOKEN_ALIASES: dict[str, set[str]] = {
    "audio": {"speech", "voice", "sound", "video"},
    "company": {"business", "organization", "org"},
    "crm": {"hubspot", "salesforce", "record", "records", "contact", "contacts", "deal", "deals", "company", "companies", "object", "objects", "account", "accounts"},
    "crawl": {"scrape", "extract", "website", "web"},
    "database": {"db", "postgres", "postgresql", "sql", "table", "schema", "query"},
    "db": {"database", "postgres", "postgresql", "sql", "schema", "table", "query"},
    "deployment": {"deploy", "deployments", "vercel", "preview", "production", "project"},
    "extract": {"scrape", "crawl", "parse", "website", "webpage", "url"},
    "find": {"search", "lookup", "discover", "query"},
    "generate": {"create", "make", "write"},
    "github": {"actions", "workflow", "run", "runs", "ci", "automation"},
    "hubspot": {"crm", "record", "records", "contact", "contacts", "deal", "deals", "company", "companies", "object", "objects"},
    "salesforce": {"crm", "record", "records", "contact", "contacts", "lead", "leads", "account", "accounts", "opportunity", "opportunities", "object", "objects"},
    "image": {"images", "photo", "picture", "visual", "graphic"},
    "linkedin": {"profile", "professional", "person", "contact", "lead"},
    "person": {"people", "profile", "contact", "lead", "professional"},
    "postgres": {"postgresql", "database", "db", "sql", "query", "schema"},
    "postgresql": {"postgres", "database", "db", "sql", "query", "schema"},
    "s3": {"bucket", "object", "storage", "file", "aws"},
    "scrape": {"extract", "crawl", "parse", "website", "webpage", "url"},
    "search": {"find", "lookup", "discover", "query"},
    "sql": {"query", "database", "db", "postgres", "postgresql", "schema", "table"},
    "speech": {"audio", "voice", "sound"},
    "support": {"ticket", "tickets", "helpdesk", "zendesk", "comment", "comments"},
    "ticket": {"tickets", "support", "zendesk", "comment", "comments", "helpdesk"},
    "transcribe": {"transcription", "captions", "subtitle", "audio", "speech", "voice"},
    "vercel": {"deploy", "deployment", "deployments", "preview", "production", "project"},
    "warehouse": {"bigquery", "bq", "sql", "analytics", "dataset", "datasets", "table", "tables", "query", "schema"},
    "bigquery": {"warehouse", "bq", "sql", "analytics", "dataset", "datasets", "table", "tables", "query", "schema"},
    "bq": {"warehouse", "bigquery", "sql", "analytics", "dataset", "datasets", "table", "tables", "query", "schema"},
    "workflow": {"workflow_run", "github", "actions", "run", "runs", "ci"},
    "workflow_run": {"workflow", "github", "actions", "run", "runs", "ci"},
    "website": {"web", "webpage", "page", "site", "url", "html"},
    "webpage": {"web", "website", "page", "site", "url", "html"},
    "zendesk": {"support", "ticket", "tickets", "comment", "comments", "helpdesk"},
}

_CAPABILITY_SEARCH_ALIASES: dict[str, tuple[str, ...]] = {
    "ai.generate_image": (
        "nano banana",
        "nano banana pro",
        "nano banana 2",
        "gemini 3 pro image",
        "gemini 3 1 flash image",
        "imagen 4",
    ),
}


def _normalize_intent_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


async def _provider_aliases_by_capability() -> dict[str, str]:
    mappings = await _cached_fetch(
        "capability_services",
        "capability_services?select=capability_id,service_slug",
    )
    if not mappings:
        return {}

    service_slugs = sorted(
        {
            str(mapping.get("service_slug") or "").strip()
            for mapping in mappings
            if str(mapping.get("service_slug") or "").strip()
        }
    )
    service_names_by_slug: dict[str, str] = {}
    if service_slugs:
        slug_filter = ",".join(f'"{slug}"' for slug in service_slugs)
        services = await _cached_fetch(
            "services",
            f"services?slug=in.({slug_filter})&select=slug,name",
        )
        if services:
            for service in services:
                slug = str(service.get("slug") or "").strip()
                name = str(service.get("name") or "").strip()
                if slug and name:
                    service_names_by_slug[slug] = name

    aliases_by_capability: dict[str, set[str]] = {}
    for mapping in mappings:
        capability_id = str(mapping.get("capability_id") or "").strip()
        service_slug = str(mapping.get("service_slug") or "").strip()
        if not capability_id or not service_slug:
            continue

        aliases = aliases_by_capability.setdefault(capability_id, set())
        aliases.add(service_slug)
        if service_name := service_names_by_slug.get(service_slug):
            aliases.add(service_name)

    return {
        capability_id: _normalize_intent_text(" ".join(sorted(aliases)))
        for capability_id, aliases in aliases_by_capability.items()
        if aliases
    }


async def _enrich_capabilities_with_provider_aliases(capabilities: list[dict]) -> list[dict]:
    if not capabilities:
        return capabilities

    aliases_by_capability = await _provider_aliases_by_capability()
    if not aliases_by_capability:
        return capabilities

    enriched: list[dict] = []
    for capability in capabilities:
        capability_id = str(capability.get("id") or "")
        provider_aliases = aliases_by_capability.get(capability_id)
        if not provider_aliases:
            enriched.append(capability)
            continue

        enriched_capability = dict(capability)
        enriched_capability["provider_aliases"] = provider_aliases
        enriched.append(enriched_capability)

    return enriched


def _term_variants(term: str) -> set[str]:
    variants = {term}
    if len(term) > 3 and term.endswith("s"):
        variants.add(term[:-1])
    elif len(term) > 3:
        variants.add(f"{term}s")
    return {variant for variant in variants if variant}


def _expanded_query_terms(term: str) -> set[str]:
    expanded = set()
    for variant in _term_variants(term):
        expanded.add(variant)
        expanded.update(_TOKEN_ALIASES.get(variant, set()))
    return {token for token in expanded if token}


def _capability_search_alias_blob(capability_id: str | None) -> str:
    if not capability_id:
        return ""
    aliases = _CAPABILITY_SEARCH_ALIASES.get(capability_id, ())
    return _normalize_intent_text(" ".join(aliases))


def _build_capability_search_blob(capability: dict) -> str:
    provider_aliases = capability.get("provider_aliases")
    if isinstance(provider_aliases, (list, tuple, set)):
        provider_alias_blob = _normalize_intent_text(
            " ".join(str(alias) for alias in provider_aliases if alias)
        )
    else:
        provider_alias_blob = _normalize_intent_text(str(provider_aliases or ""))

    parts = [
        capability.get("id"),
        capability.get("domain"),
        capability.get("action"),
        capability.get("description"),
        capability.get("input_hint"),
        capability.get("outcome"),
        _capability_search_alias_blob(str(capability.get("id") or "")),
        provider_alias_blob,
    ]
    return _normalize_intent_text(" ".join(part for part in parts if part))


def _score_capability_intent(query: str, capability: dict) -> int:
    normalized_query = _normalize_intent_text(query)
    if not normalized_query:
        return 0

    blob = _build_capability_search_blob(capability)
    if not blob:
        return 0

    tokens = normalized_query.split()
    blob_tokens = set(blob.split())
    capability_id = str(capability.get("id") or "")
    id_text = _normalize_intent_text(capability.get("id"))
    domain_text = _normalize_intent_text(capability.get("domain"))
    action_text = _normalize_intent_text(capability.get("action"))
    db_terms = {"db", "database", "postgres", "postgresql", "sql", "schema", "table"}
    warehouse_terms = {"warehouse", "bigquery", "bq", "sql", "analytics", "dataset", "table", "schema"}
    support_terms = {"support", "ticket", "tickets", "zendesk", "helpdesk", "comment", "comments"}
    actions_terms = {"github", "actions", "workflow", "workflow_run", "run", "runs", "ci"}
    crm_terms = {"crm", "hubspot", "salesforce", "record", "records", "contact", "contacts", "deal", "deals", "company", "companies", "lead", "leads", "account", "accounts", "object", "objects"}

    score = 0
    matched_groups = 0

    if any(token in db_terms for token in tokens) and (
        domain_text == "database"
        or any(term in blob_tokens for term in db_terms)
        or id_text.startswith("db ")
    ):
        score += 18

    if any(token in warehouse_terms for token in tokens) and (
        domain_text == "warehouse"
        or any(term in blob_tokens for term in warehouse_terms)
        or id_text.startswith("warehouse ")
    ):
        score += 18

    if any(token in support_terms for token in tokens) and (
        domain_text == "support"
        or any(term in blob_tokens for term in support_terms)
        or id_text.startswith("ticket ")
    ):
        score += 18

    if any(token in actions_terms for token in tokens) and (
        domain_text == "workflow run"
        or any(term in blob_tokens for term in actions_terms)
        or id_text.startswith("workflow run ")
    ):
        score += 18

    if any(token in crm_terms for token in tokens) and (
        domain_text == "crm"
        or any(term in blob_tokens for term in crm_terms)
        or id_text.startswith("crm ")
    ):
        score += 18

    if capability_id == "db.query.read":
        if any(token in {"db", "database", "postgres", "postgresql", "sql"} for token in tokens):
            score += 30
        if any(token in {"query", "read"} for token in tokens):
            score += 12
    elif capability_id == "warehouse.query.read":
        if any(token in {"warehouse", "bigquery", "bq", "sql", "analytics"} for token in tokens):
            score += 30
        if any(token in {"query", "read", "select"} for token in tokens):
            score += 12
    elif capability_id == "warehouse.schema.describe":
        if any(token in {"warehouse", "bigquery", "bq", "sql", "analytics"} for token in tokens):
            score += 30
        if any(token in {"schema", "describe", "dataset", "datasets", "table", "tables"} for token in tokens):
            score += 12
    elif capability_id == "db.schema.describe":
        if any(token in {"db", "database", "postgres", "postgresql", "sql"} for token in tokens) and any(
            token in {"schema", "table", "tables", "describe"} for token in tokens
        ):
            score += 30
    elif capability_id == "db.row.get":
        if any(token in {"db", "database", "postgres", "postgresql", "sql", "table"} for token in tokens) and any(
            token in {"row", "rows", "record", "lookup", "get"} for token in tokens
        ):
            score += 30
    elif capability_id == "ticket.search":
        if any(token in {"support", "ticket", "tickets", "zendesk", "helpdesk"} for token in tokens):
            score += 30
        if any(token in {"search", "find", "lookup", "query"} for token in tokens):
            score += 12
    elif capability_id == "ticket.get":
        if any(token in {"support", "ticket", "tickets", "zendesk", "helpdesk"} for token in tokens) and any(
            token in {"get", "fetch", "read", "lookup"} for token in tokens
        ):
            score += 30
    elif capability_id == "ticket.list_comments":
        if any(token in {"ticket", "tickets", "support", "zendesk"} for token in tokens) and any(
            token in {"comment", "comments", "reply", "replies", "notes"} for token in tokens
        ):
            score += 30
    elif capability_id == "workflow_run.list":
        if any(token in {"github", "actions", "workflow", "ci", "run", "runs"} for token in tokens):
            score += 30
        if any(token in {"list", "search", "recent"} for token in tokens):
            score += 12
    elif capability_id == "workflow_run.get":
        if any(token in {"github", "actions", "workflow", "ci", "run", "runs"} for token in tokens) and any(
            token in {"get", "fetch", "read", "lookup"} for token in tokens
        ):
            score += 30
    elif capability_id == "crm.object.describe":
        if any(token in {"crm", "hubspot", "salesforce", "object", "schema", "properties", "property"} for token in tokens):
            score += 30
        if any(token in {"describe", "inspect", "metadata"} for token in tokens):
            score += 12
    elif capability_id == "crm.record.search":
        if any(token in {"crm", "hubspot", "salesforce", "record", "records", "contact", "company", "deal", "lead", "account", "opportunity"} for token in tokens):
            score += 30
        if any(token in {"search", "find", "query", "list"} for token in tokens):
            score += 12
    elif capability_id == "crm.record.get":
        if any(token in {"crm", "hubspot", "salesforce", "record", "contact", "company", "deal", "lead", "account", "opportunity"} for token in tokens):
            score += 30
        if any(token in {"get", "fetch", "read", "lookup"} for token in tokens):
            score += 12

    if normalized_query in id_text:
        score += 40
    elif normalized_query in blob:
        score += 24

    for token in tokens:
        expansions = _expanded_query_terms(token)
        direct_hit = token in blob_tokens or f" {token} " in f" {blob} "
        alias_hits = [alias for alias in expansions if alias != token and (alias in blob_tokens or f" {alias} " in f" {blob} ")]

        if direct_hit:
            matched_groups += 1
            score += 12
            if token in id_text:
                score += 10
            if token == domain_text or token == action_text:
                score += 6
        elif alias_hits:
            matched_groups += 1
            score += 5
            if any(alias in id_text for alias in alias_hits):
                score += 4
            if any(alias in blob_tokens for alias in alias_hits):
                score += 8

    if tokens and matched_groups == len(tokens):
        score += 24
    elif len(tokens) > 1 and matched_groups >= len(tokens) - 1:
        score += 10

    if id_text.startswith(normalized_query):
        score += 12

    return score


def _rank_capability_suggestions(query: str, capabilities: list[dict], *, limit: int = 3) -> list[dict]:
    ranked: list[tuple[int, dict]] = []
    seen_ids: set[str] = set()

    for capability in capabilities:
        capability_id = str(capability.get("id") or "")
        if not capability_id or capability_id in seen_ids:
            continue
        score = _score_capability_intent(query, capability)
        if score <= 0:
            continue
        ranked.append((score, capability))
        seen_ids.add(capability_id)

    ranked.sort(
        key=lambda item: (
            -item[0],
            item[1].get("domain") or "",
            item[1].get("action") or "",
            item[1].get("id") or "",
        )
    )
    return [capability for _, capability in ranked[:limit]]


async def _suggested_capabilities(query: str, *, limit: int = 3) -> list[dict[str, str]]:
    normalized_query = _normalize_intent_text(query)
    if not normalized_query:
        return []

    path = "capabilities?select=id,domain,action,description,input_hint,outcome&order=domain.asc,action.asc"
    capabilities = await _cached_fetch("capabilities", path)
    if capabilities is None:
        capabilities = []

    existing_ids = {cap.get("id") for cap in capabilities}
    for synthetic in _synthetic_capability_records():
        if synthetic["id"] not in existing_ids:
            capabilities.append(dict(synthetic))

    capabilities = await _enrich_capabilities_with_provider_aliases(capabilities)

    suggestions = _rank_capability_suggestions(query, capabilities, limit=limit)
    return [
        {
            "id": str(suggestion.get("id") or ""),
            "description": str(suggestion.get("description") or ""),
        }
        for suggestion in suggestions
        if suggestion.get("id")
    ]


@router.get("/capabilities")
async def list_capabilities(
    domain: str | None = Query(default=None, description="Filter by domain (e.g. 'email', 'payment')"),
    search: str | None = Query(default=None, description="Search capabilities by text"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """List capabilities with optional domain filter and text search.

    Returns capabilities enriched with provider count and top provider info.
    """
    # Pull the lightweight capability registry and rank/filter in Python so
    # intent-style queries like "generate image" or "scrape website" can
    # match dotted/underscored IDs and related descriptions.
    path = "capabilities?select=id,domain,action,description,input_hint,outcome&order=domain.asc,action.asc"
    capabilities = await _cached_fetch("capabilities", path)
    degraded_error = None
    if capabilities is None:
        capabilities = []
        degraded_error = _DEGRADED_DISCOVERY_ERROR

    existing_ids = {cap.get("id") for cap in capabilities}
    for synthetic in _synthetic_capability_records():
        if synthetic["id"] not in existing_ids:
            capabilities.append(dict(synthetic))

    if domain:
        capabilities = [c for c in capabilities if c.get("domain") == domain]

    if search:
        capabilities = await _enrich_capabilities_with_provider_aliases(capabilities)
        ranked: list[tuple[int, dict]] = []
        for capability in capabilities:
            intent_score = _score_capability_intent(search, capability)
            if intent_score > 0:
                ranked.append((intent_score, capability))

        ranked.sort(
            key=lambda item: (
                -item[0],
                item[1].get("domain") or "",
                item[1].get("action") or "",
                item[1].get("id") or "",
            )
        )
        capabilities = [capability for _, capability in ranked]

    total = len(capabilities)
    page = capabilities[offset : offset + limit]

    if not page:
        return {
            "data": {"items": [], "total": total, "limit": limit, "offset": offset},
            "error": degraded_error,
        }

    # Get provider counts and top providers for this page
    cap_ids = [c["id"] for c in page]
    cap_filter = ",".join(f'"{cid}"' for cid in cap_ids)

    mappings = await _cached_fetch(
        "capability_services",
        f"capability_services?capability_id=in.({cap_filter})"
        f"&select=capability_id,service_slug"
    )

    # Get scores for provider ranking
    if mappings:
        service_slugs = list({m["service_slug"] for m in mappings})
        slug_filter = ",".join(f'"{s}"' for s in service_slugs)
        scores = await _cached_fetch(
            "scores",
            f"scores?service_slug=in.({slug_filter})"
            f"&select=service_slug,aggregate_recommendation_score,tier_label"
            f"&order=aggregate_recommendation_score.desc.nullslast"
        )
    else:
        scores = []

    # Index scores by slug (best per slug)
    scores_by_slug: dict[str, dict] = {}
    if scores:
        for sc in scores:
            slug = sc.get("service_slug")
            if slug and slug not in scores_by_slug:
                scores_by_slug[slug] = sc

    # Build provider stats per capability
    providers_by_cap: dict[str, list[str]] = {}
    if mappings:
        for m in mappings:
            cid = m["capability_id"]
            providers_by_cap.setdefault(cid, []).append(m["service_slug"])

    items = []
    for cap in page:
        cid = cap["id"]
        provider_slugs = providers_by_cap.get(cid, [])
        provider_count = len(provider_slugs)

        # Find top provider by AN score
        top_provider = None
        if _is_support_direct_capability(cid):
            provider_count = 1
            top_provider = _support_direct_top_provider(cid)
        elif provider_slugs:
            best_slug = None
            best_score = -1.0
            for slug in provider_slugs:
                sc = scores_by_slug.get(slug, {})
                agg = sc.get("aggregate_recommendation_score")
                if agg is not None and agg > best_score:
                    best_score = agg
                    best_slug = slug
            if best_slug:
                sc = scores_by_slug.get(best_slug, {})
                top_provider = {
                    "slug": best_slug,
                    "an_score": sc.get("aggregate_recommendation_score"),
                    "tier_label": sc.get("tier_label"),
                }
        elif _is_db_direct_capability(cid):
            provider_count = 1
            top_provider = _db_direct_top_provider()
        elif _is_warehouse_direct_capability(cid):
            provider_count = 1
            top_provider = _warehouse_direct_top_provider()
        elif _is_object_storage_direct_capability(cid):
            provider_count = 1
            top_provider = _object_storage_direct_top_provider()
        elif _is_deployment_direct_capability(cid):
            provider_count = 1
            top_provider = _deployment_direct_top_provider()
        elif _is_actions_direct_capability(cid):
            provider_count = 1
            top_provider = _actions_direct_top_provider()
        elif _is_crm_direct_capability(cid):
            provider_count = len(_crm_direct_provider_order())
            top_provider = _crm_direct_top_provider()

        items.append({
            "id": cid,
            "domain": cap.get("domain"),
            "action": cap.get("action"),
            "description": cap.get("description"),
            "input_hint": cap.get("input_hint"),
            "outcome": cap.get("outcome"),
            "provider_count": provider_count,
            "top_provider": top_provider,
        })

    return {
        "data": {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        },
        "error": degraded_error,
    }


@router.get("/capabilities/domains")
async def list_domains() -> dict:
    """List all capability domains with counts.

    Useful for building domain navigation / filtering UIs.
    """
    capabilities = await _cached_fetch(
        "capabilities",
        "capabilities?select=domain,id&order=domain.asc"
    )
    degraded_error = None
    if capabilities is None:
        capabilities = []
        degraded_error = _DEGRADED_DISCOVERY_ERROR

    existing_ids = {cap.get("id") for cap in capabilities}
    for synthetic in _synthetic_capability_records():
        if synthetic["id"] not in existing_ids:
            capabilities.append({"id": synthetic["id"], "domain": synthetic["domain"]})

    # Count capabilities per domain
    domain_counts: dict[str, int] = {}
    for cap in capabilities:
        d = cap.get("domain", "unknown")
        domain_counts[d] = domain_counts.get(d, 0) + 1

    domains = [
        {"domain": d, "capability_count": c}
        for d, c in sorted(domain_counts.items())
    ]

    return {"data": {"domains": domains}, "error": degraded_error}


@router.get("/capabilities/bundles")
async def list_bundles(
    search: str | None = Query(default=None, description="Search bundles by text"),
) -> dict:
    """List capability bundles (compound capabilities).

    Bundles represent pre-packaged capability chains that deliver more
    value together than individually (e.g., enrich + verify + validate).
    """
    path = (
        "capability_bundles?select=id,name,description,example,value_proposition"
        "&order=name.asc"
    )
    if search:
        encoded = quote(f"*{search}*")
        path += (
            f"&or=(id.ilike.{encoded},"
            f"name.ilike.{encoded},"
            f"description.ilike.{encoded})"
        )

    bundles = await _cached_fetch("capability_bundles", path)
    if bundles is None:
        return {"data": {"bundles": []}, "error": "Unable to load bundles."}

    if not bundles:
        return {"data": {"bundles": []}, "error": None}

    # Get bundle-capability mappings
    bundle_ids = [b["id"] for b in bundles]
    bid_filter = ",".join(f'"{bid}"' for bid in bundle_ids)
    mappings = await _cached_fetch(
        "bundle_capabilities",
        f"bundle_capabilities?bundle_id=in.({bid_filter})"
        f"&select=bundle_id,capability_id,sequence_order"
        f"&order=sequence_order.asc"
    )

    caps_by_bundle: dict[str, list[str]] = {}
    if mappings:
        for m in mappings:
            bid = m["bundle_id"]
            caps_by_bundle.setdefault(bid, []).append(m["capability_id"])

    items = []
    for bundle in bundles:
        bid = bundle["id"]
        items.append({
            "id": bid,
            "name": bundle.get("name"),
            "description": bundle.get("description"),
            "example": bundle.get("example"),
            "value_proposition": bundle.get("value_proposition"),
            "capabilities": caps_by_bundle.get(bid, []),
        })

    return {"data": {"bundles": items}, "error": None}


@router.get("/capabilities/rhumb-managed")
async def list_rhumb_managed() -> dict:
    """Public catalog of capabilities with zero-config managed execution.

    These capabilities use Rhumb's own credentials — agents don't need to
    configure anything. Just call execute with credential_mode=rhumb_managed.
    """
    from services.rhumb_managed import get_managed_executor
    executor = get_managed_executor()
    managed = await executor.list_managed()

    # Enrich with capability details
    if managed:
        cap_ids = list({m["capability_id"] for m in managed})
        cap_filter = ",".join(f'"{c}"' for c in cap_ids)
        caps = await _cached_fetch(
            "capabilities",
            f"capabilities?id=in.({cap_filter})"
            f"&select=id,domain,action,description"
        )
        caps_by_id = {c["id"]: c for c in (caps or [])}

        for m in managed:
            cap = caps_by_id.get(m["capability_id"], {})
            m["domain"] = cap.get("domain")
            m["action"] = cap.get("action")
            m["capability_description"] = cap.get("description")

    return {
        "data": {
            "managed_capabilities": managed,
            "count": len(managed),
        },
        "error": None,
    }


@router.get("/capabilities/{capability_id}")
async def get_capability(capability_id: str, raw_request: Request):
    """Get a single capability with full provider details."""
    caps = await _cached_fetch(
        "capabilities",
        f"capabilities?id=eq.{quote(capability_id)}"
        f"&select=id,domain,action,description,input_hint,outcome&limit=1"
    )
    if not caps:
        synthetic = _synthetic_capability_record(capability_id)
        if synthetic is None:
            return await _capability_not_found(raw_request, capability_id)
        cap = synthetic
    else:
        cap = caps[0]

    if _is_support_direct_capability(capability_id):
        return {
            "data": {
                **cap,
                "providers": [_support_direct_provider_details(capability_id)],
                "provider_count": 1,
            },
            "error": None,
        }
    if _is_warehouse_direct_capability(capability_id):
        return {
            "data": {
                **cap,
                "providers": [_warehouse_direct_provider_details(capability_id)],
                "provider_count": 1,
            },
            "error": None,
        }
    if _is_deployment_direct_capability(capability_id):
        return {
            "data": {
                **cap,
                "providers": [_deployment_direct_provider_details(capability_id)],
                "provider_count": 1,
            },
            "error": None,
        }
    if _is_actions_direct_capability(capability_id):
        return {
            "data": {
                **cap,
                "providers": [_actions_direct_provider_details(capability_id)],
                "provider_count": 1,
            },
            "error": None,
        }
    if _is_crm_direct_capability(capability_id):
        providers = _crm_direct_provider_details(capability_id)
        return {
            "data": {
                **cap,
                "providers": providers,
                "provider_count": len(providers),
            },
            "error": None,
        }

    # Get all service mappings for this capability
    mappings = await _cached_fetch(
        "capability_services",
        f"capability_services?capability_id=eq.{quote(capability_id)}"
        f"&select=service_slug,credential_modes,auth_method,endpoint_pattern,"
        f"cost_per_call,cost_currency,free_tier_calls,notes,is_primary"
    )

    providers = []
    if mappings:
        # Get scores + service names for all mapped services
        slugs = [m["service_slug"] for m in mappings]
        slug_filter = ",".join(f'"{s}"' for s in slugs)

        scores = await _cached_fetch(
            "scores",
            f"scores?service_slug=in.({slug_filter})"
            f"&select=service_slug,aggregate_recommendation_score,tier,tier_label"
            f"&order=aggregate_recommendation_score.desc.nullslast"
        )
        services = await _cached_fetch(
            "services",
            f"services?slug=in.({slug_filter})&select=slug,name,category"
        )

        scores_by_slug: dict[str, dict] = {}
        if scores:
            for sc in scores:
                slug = sc.get("service_slug")
                if slug and slug not in scores_by_slug:
                    scores_by_slug[slug] = sc

        names_by_slug: dict[str, str] = {}
        cats_by_slug: dict[str, str] = {}
        if services:
            for svc in services:
                names_by_slug[svc["slug"]] = svc.get("name", svc["slug"])
                cats_by_slug[svc["slug"]] = svc.get("category", "")

        for m in mappings:
            slug = m["service_slug"]
            sc = scores_by_slug.get(slug, {})
            auth_method = _effective_auth_method(slug, m.get("auth_method", "api_key"))
            providers.append({
                "service_slug": slug,
                "service_name": names_by_slug.get(slug, slug),
                "category": cats_by_slug.get(slug, ""),
                "an_score": sc.get("aggregate_recommendation_score"),
                "tier": sc.get("tier"),
                "tier_label": sc.get("tier_label"),
                "auth_method": auth_method,
                "endpoint_pattern": m.get("endpoint_pattern"),
                "credential_modes": _canonicalize_credential_modes(
                    m.get("credential_modes") or ["byok"]
                ),
                "cost_per_call": float(m["cost_per_call"]) if m.get("cost_per_call") is not None else None,
                "cost_currency": m.get("cost_currency", "USD"),
                "free_tier_calls": m.get("free_tier_calls"),
                "notes": m.get("notes"),
                "is_primary": m.get("is_primary", True),
            })

        # Sort providers by AN score descending (nulls last)
        providers.sort(key=lambda p: -(p.get("an_score") or 0))

    if not providers and _is_db_direct_capability(capability_id):
        providers = [_db_direct_provider_details(capability_id)]
    if not providers and _is_warehouse_direct_capability(capability_id):
        providers = [_warehouse_direct_provider_details(capability_id)]
    if not providers and _is_object_storage_direct_capability(capability_id):
        providers = [_object_storage_direct_provider_details(capability_id)]
    if not providers and _is_deployment_direct_capability(capability_id):
        providers = [_deployment_direct_provider_details(capability_id)]
    if not providers and _is_actions_direct_capability(capability_id):
        providers = [_actions_direct_provider_details(capability_id)]
    if not providers and _is_crm_direct_capability(capability_id):
        providers = _crm_direct_provider_details(capability_id)

    return {
        "data": {
            **cap,
            "providers": providers,
            "provider_count": len(providers),
        },
        "error": None,
    }


@router.get("/capabilities/{capability_id}/resolve")
async def resolve_capability(
    capability_id: str,
    raw_request: Request,
    credential_mode: str | None = Query(default=None, description="Filter by credential mode (byok, rhumb_managed, agent_vault; legacy byo accepted)"),
    x_rhumb_key: str | None = Header(default=None, alias="X-Rhumb-Key"),
) -> dict:
    """Resolve a capability to ranked providers with health-aware recommendations.

    This is the core agent-facing endpoint: "I need email.send — what should I use?"
    Returns providers ranked by AN score with cost, health, and recommendation data.
    Includes circuit breaker state and execute_hint for direct execution.
    """
    agent_id = x_rhumb_key or "anonymous"
    # Verify capability exists
    caps = await _cached_fetch(
        "capabilities",
        f"capabilities?id=eq.{quote(capability_id)}"
        f"&select=id,domain,action,description&limit=1"
    )
    if not caps and _synthetic_capability_record(capability_id) is None:
        return await _capability_not_found(raw_request, capability_id)

    synthetic_direct_payload = _synthetic_direct_resolve_payload(capability_id)
    if synthetic_direct_payload is not None:
        return {
            "data": _apply_direct_resolve_credential_mode_filter(
                capability_id,
                synthetic_direct_payload,
                credential_mode,
            ),
            "error": None,
        }

    # Get service mappings
    mapping_path = (
        f"capability_services?capability_id=eq.{quote(capability_id)}"
        f"&select=service_slug,credential_modes,auth_method,endpoint_pattern,"
        f"cost_per_call,cost_currency,free_tier_calls,notes"
    )

    all_mappings = await _cached_fetch("capability_services", mapping_path)
    if not all_mappings:
        return {
            "data": _empty_resolve_payload(capability_id),
            "error": None,
        }

    if credential_mode and not any(
        _supports_requested_credential_mode(mapping.get("credential_modes"), credential_mode)
        for mapping in all_mappings
    ):
        recovery_reason = "no_providers_match_credential_mode" if credential_mode and all_mappings else None

        recovery_items = all_mappings if recovery_reason else None
        # Keep recovery metadata ordered the same way we'd rank providers during normal resolve.
        # This avoids drift where `supported_provider_slugs` reflects raw mapping insertion order
        # instead of score-ranked provider order.
        if recovery_reason and isinstance(all_mappings, list):
            try:
                slugs = list(dict.fromkeys(
                    str(m.get("service_slug"))
                    for m in all_mappings
                    if isinstance(m, dict) and m.get("service_slug")
                ))
                if slugs:
                    slug_filter = ",".join(f'"{s}"' for s in slugs)
                    scores = await _cached_fetch(
                        "scores",
                        f"scores?service_slug=in.({slug_filter})"
                        f"&select=service_slug,aggregate_recommendation_score"
                        f"&order=aggregate_recommendation_score.desc.nullslast",
                    )
                    scores_by_slug: dict[str, float] = {}
                    if isinstance(scores, list):
                        for sc in scores:
                            if not isinstance(sc, dict):
                                continue
                            slug = sc.get("service_slug")
                            score = sc.get("aggregate_recommendation_score")
                            if isinstance(slug, str) and isinstance(score, (int, float)):
                                scores_by_slug[slug] = float(score)

                    indexed: list[tuple[bool, float, int, dict[str, object]]] = []
                    for idx, mapping in enumerate(all_mappings):
                        if not isinstance(mapping, dict):
                            continue
                        slug = str(mapping.get("service_slug") or "")
                        an_score = scores_by_slug.get(slug)
                        indexed.append(
                            (
                                an_score is None,
                                -(an_score or 0.0),
                                idx,
                                mapping,
                            )
                        )
                    indexed.sort(key=lambda item: (item[0], item[1], item[2]))
                    recovery_items = [item[3] for item in indexed]
            except Exception:
                recovery_items = all_mappings
        return {
            "data": _empty_resolve_payload(
                capability_id,
                requested_credential_mode=credential_mode,
                recovery_reason=recovery_reason,
                recovery_items=recovery_items,
            ),
            "error": None,
        }

    # Get scores for all mapped services
    slugs = list(dict.fromkeys(m["service_slug"] for m in all_mappings))
    slug_filter = ",".join(f'"{s}"' for s in slugs)

    scores = await _cached_fetch(
        "scores",
        f"scores?service_slug=in.({slug_filter})"
        f"&select=service_slug,aggregate_recommendation_score,execution_score,"
        f"access_readiness_score,tier,tier_label,confidence"
        f"&order=aggregate_recommendation_score.desc.nullslast"
    )

    services = await _cached_fetch(
        "services",
        f"services?slug=in.({slug_filter})&select=slug,name"
    )

    scores_by_slug: dict[str, dict] = {}
    if scores:
        for sc in scores:
            slug = sc.get("service_slug")
            if slug and slug not in scores_by_slug:
                scores_by_slug[slug] = sc

    names_by_slug: dict[str, str] = {}
    if services:
        for svc in services:
            names_by_slug[svc["slug"]] = svc.get("name", svc["slug"])

    # Build ranked provider list with recommendations
    all_providers = []
    for m in all_mappings:
        slug = m["service_slug"]
        sc = scores_by_slug.get(slug, {})
        an_score = sc.get("aggregate_recommendation_score")
        tier = sc.get("tier")
        auth_method = _effective_auth_method(slug, m.get("auth_method", "api_key"))
        credential_modes = _canonicalize_credential_modes(m.get("credential_modes") or ["byok"])

        # Determine recommendation
        recommendation = "available"
        reason = ""
        if an_score is not None and an_score >= 7.5:
            recommendation = "preferred"
            reason = f"High AN score ({an_score:.1f})"
        elif an_score is not None and an_score >= 6.0:
            recommendation = "available"
            reason = f"Solid AN score ({an_score:.1f})"
        elif an_score is not None:
            recommendation = "caution"
            reason = f"Lower AN score ({an_score:.1f}) — check failure modes"
        else:
            recommendation = "unscored"
            reason = "No AN score available yet"

        # Enhance reason with cost info
        cost = m.get("cost_per_call")
        free_tier = m.get("free_tier_calls")
        if free_tier and cost is None:
            reason += f", {free_tier:,} free calls/month"
        elif cost is not None:
            reason += f", ${cost}/call"
            if free_tier:
                reason += f" ({free_tier:,} free)"

        # Circuit breaker state (if proxy is initialized)
        circuit_state = "unknown"
        available_for_execute = True
        try:
            from routes.proxy import get_breaker_registry
            breaker = get_breaker_registry().get(slug, agent_id)
            circuit_state = breaker.state.value
            available_for_execute = breaker.allow_request()
        except Exception:
            pass  # proxy not initialized or breaker not available

        byok_configured = False
        if "byok" in credential_modes:
            byok_configured = _has_proxy_credential_configured(slug, auth_method)

        all_providers.append({
            "service_slug": slug,
            "service_name": names_by_slug.get(slug, slug),
            "an_score": an_score,
            "execution_score": sc.get("execution_score"),
            "access_readiness_score": sc.get("access_readiness_score"),
            "tier": tier,
            "tier_label": sc.get("tier_label"),
            "confidence": sc.get("confidence"),
            "cost_per_call": float(cost) if cost is not None else None,
            "cost_currency": m.get("cost_currency", "USD"),
            "free_tier_calls": free_tier,
            "credential_modes": credential_modes,
            "auth_method": auth_method,
            "endpoint_pattern": m.get("endpoint_pattern"),
            "recommendation": recommendation,
            "recommendation_reason": reason,
            "circuit_state": circuit_state,
            "available_for_execute": available_for_execute,
            "configured": _mapped_provider_is_configured(
                credential_modes,
                byok_configured=byok_configured,
                requested_credential_mode=credential_mode,
            ),
        })

    # Sort: preferred first, then by AN score descending
    rank_order = {"preferred": 0, "available": 1, "caution": 2, "unscored": 3}
    all_providers.sort(key=lambda p: (
        rank_order.get(p["recommendation"], 4),
        -(p.get("an_score") or 0),
    ))

    providers = all_providers
    if credential_mode:
        providers = [
            provider
            for provider in all_providers
            if _supports_requested_credential_mode(provider.get("credential_modes"), credential_mode)
        ]

    # Build fallback chain (top 3 preferred/available providers)
    fallback_chain = _execute_ready_fallback_chain(providers)

    # Check for relevant bundles
    bundle_rows = await _cached_fetch(
        "bundle_capabilities",
        f"bundle_capabilities?capability_id=eq.{quote(capability_id)}"
        f"&select=bundle_id"
    )
    bundle_ids = list({r["bundle_id"] for r in bundle_rows}) if bundle_rows else []

    execute_hint = _pick_mapped_execute_hint(
        capability_id,
        providers,
        requested_credential_mode=credential_mode,
    )
    execute_hint = _with_execute_hint_fallbacks(
        execute_hint,
        providers,
        selection_providers=all_providers,
        requested_credential_mode=credential_mode,
    )

    data = {
        "capability": capability_id,
        "providers": providers,
        "fallback_chain": fallback_chain,
        "related_bundles": bundle_ids,
        "execute_hint": execute_hint,
    }
    if execute_hint is None:
        recovery_hint = _execute_ready_recovery_hint(
            capability_id,
            providers,
            requested_credential_mode=credential_mode,
        )
        if recovery_hint is not None:
            data["recovery_hint"] = recovery_hint

    return {
        "data": data,
        "error": None,
    }


@router.get("/capabilities/{capability_id}/credential-modes")
async def get_credential_modes(
    capability_id: str,
    raw_request: Request,
    x_rhumb_key: str | None = Header(default=None, alias="X-Rhumb-Key"),
) -> dict:
    """Return credential mode availability for a capability, per provider.

    Shows which modes each provider supports AND which the agent currently
    has configured. Agents use this to decide which mode to use at execution time.
    """
    agent_id = x_rhumb_key or "anonymous"

    # Verify capability
    caps = await _cached_fetch(
        "capabilities",
        f"capabilities?id=eq.{quote(capability_id)}"
        f"&select=id,domain,action,description&limit=1"
    )
    if not caps and _synthetic_capability_record(capability_id) is None:
        return await _capability_not_found(raw_request, capability_id)
    if _is_support_direct_capability(capability_id):
        return {
            "data": _support_direct_credential_modes(capability_id),
            "error": None,
        }
    if _is_warehouse_direct_capability(capability_id):
        return {
            "data": _warehouse_direct_credential_modes(capability_id),
            "error": None,
        }
    if _is_deployment_direct_capability(capability_id):
        return {
            "data": _deployment_direct_credential_modes(capability_id),
            "error": None,
        }
    if _is_actions_direct_capability(capability_id):
        return {
            "data": _actions_direct_credential_modes(capability_id),
            "error": None,
        }
    if _is_crm_direct_capability(capability_id):
        return {
            "data": _crm_direct_credential_modes(capability_id),
            "error": None,
        }

    # Get provider mappings
    mappings = await _cached_fetch(
        "capability_services",
        f"capability_services?capability_id=eq.{quote(capability_id)}"
        f"&select=service_slug,credential_modes,auth_method"
    )
    if not mappings:
        if _is_db_direct_capability(capability_id):
            return {
                "data": _db_direct_credential_modes(capability_id),
                "error": None,
            }
        if _is_warehouse_direct_capability(capability_id):
            return {
                "data": _warehouse_direct_credential_modes(capability_id),
                "error": None,
            }
        if _is_object_storage_direct_capability(capability_id):
            return {
                "data": _object_storage_direct_credential_modes(capability_id),
                "error": None,
            }
        if _is_deployment_direct_capability(capability_id):
            return {
                "data": _deployment_direct_credential_modes(capability_id),
                "error": None,
            }
        if _is_actions_direct_capability(capability_id):
            return {
                "data": _actions_direct_credential_modes(capability_id),
                "error": None,
            }
        if _is_crm_direct_capability(capability_id):
            return {
                "data": _crm_direct_credential_modes(capability_id),
                "error": None,
            }
        return {
            "data": {"capability_id": capability_id, "providers": []},
            "error": None,
        }

    # Check BYO credential status per provider
    providers = []
    for m in mappings:
        slug = m["service_slug"]
        modes = _canonicalize_credential_modes(m.get("credential_modes") or ["byok"])
        auth_method = _effective_auth_method(slug, m.get("auth_method", "api_key"))

        byok_configured = False
        if "byok" in modes:
            byok_configured = _has_proxy_credential_configured(slug, auth_method)

        mode_details = []
        for mode in modes:
            detail = {"mode": mode, "available": True, "configured": False}
            if mode == "byok":
                detail["configured"] = byok_configured
                detail["setup_hint"] = _provider_mode_setup_hint(slug, auth_method, mode)
            elif mode == "rhumb_managed":
                detail["configured"] = True  # always available if listed
                detail["setup_hint"] = _provider_mode_setup_hint(slug, auth_method, mode)
            elif mode == "agent_vault":
                detail["configured"] = False  # needs per-request token
                detail["setup_hint"] = _provider_mode_setup_hint(slug, auth_method, mode)

            mode_details.append(detail)

        providers.append({
            "service_slug": slug,
            "auth_method": auth_method,
            "modes": mode_details,
            "any_configured": any(d["configured"] for d in mode_details),
        })

    return {
        "data": {
            "capability_id": capability_id,
            "providers": providers,
        },
        "error": None,
    }


# ── Ceremony routes (Mode 3 — Agent Vault) ──────────────────────

@router.get("/services/ceremonies")
async def list_ceremonies() -> dict:
    """List all available ceremony skills.

    Ceremonies are structured auth guides that teach agents how to
    obtain their own API credentials for a service.
    """
    from services.agent_vault import get_vault_validator
    validator = get_vault_validator()
    ceremonies = await validator.list_ceremonies()
    return {
        "data": {
            "ceremonies": ceremonies,
            "count": len(ceremonies),
        },
        "error": None,
    }


@router.get("/services/{service_slug}/ceremony")
async def get_ceremony(service_slug: str) -> dict:
    """Get the ceremony skill for a specific service.

    Returns step-by-step instructions for an agent to obtain
    its own API credentials, plus token format info for validation.
    """
    from services.agent_vault import get_vault_validator
    validator = get_vault_validator()
    ceremony = await validator.get_ceremony(service_slug)
    if ceremony is None:
        return {
            "data": None,
            "error": f"No ceremony available for service '{service_slug}'",
        }
    return {"data": ceremony, "error": None}


@router.get("/agent/credentials")
async def get_agent_credentials(
    x_rhumb_key: str | None = Header(default=None, alias="X-Rhumb-Key"),
) -> dict:
    """Return the agent's full credential status.

    Shows which services have BYOK credentials configured, which capabilities
    those credentials unlock, and which capabilities need credentials.

    Requires a valid API key — this endpoint exposes Rhumb's managed
    credential inventory and must not be accessible to unauthenticated callers.
    """
    if not x_rhumb_key:
        raise HTTPException(status_code=401, detail="X-Rhumb-Key header required")

    from schemas.agent_identity import get_agent_identity_store
    agent = await get_agent_identity_store().verify_api_key_with_agent(x_rhumb_key)
    if agent is None:
        raise HTTPException(status_code=401, detail="Invalid or expired Rhumb API key")

    agent_id = agent.agent_id

    # Get all capability-service mappings
    all_mappings = await _cached_fetch(
        "capability_services",
        "capability_services?select=capability_id,service_slug,credential_modes,auth_method"
        "&order=capability_id.asc"
    )
    if not all_mappings:
        return {
            "data": {
                "agent_id": agent_id,
                "configured_services": [],
                "unlocked_capabilities": [],
                "locked_capabilities": [],
            },
            "error": None,
        }

    # Check which services have credentials
    configured_services = set()
    try:
        from services.proxy_credentials import get_credential_store
        store = get_credential_store()

        seen_slugs = {m["service_slug"] for m in all_mappings}
        for slug in seen_slugs:
            # Try common auth method keys
            for key in ("api_key", "oauth_token", "api_token", "basic_auth"):
                if store.get_credential(slug, key) is not None:
                    configured_services.add(slug)
                    break
    except Exception:
        pass

    # Categorize capabilities
    unlocked = set()
    locked = set()

    for m in all_mappings:
        cap_id = m["capability_id"]
        slug = m["service_slug"]

        if slug in configured_services:
            unlocked.add(cap_id)
        else:
            # Only locked if no provider for this capability is configured
            if cap_id not in unlocked:
                locked.add(cap_id)

    # Remove from locked if also in unlocked (has at least one configured provider)
    locked -= unlocked

    return {
        "data": {
            "agent_id": agent_id,
            "configured_services": sorted(configured_services),
            "configured_count": len(configured_services),
            "unlocked_capabilities": sorted(unlocked),
            "unlocked_count": len(unlocked),
            "locked_capabilities": sorted(locked),
            "locked_count": len(locked),
            "total_capabilities": len(unlocked | locked),
        },
        "error": None,
    }
