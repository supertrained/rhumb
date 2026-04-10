"""Tests for the crm_ref registry."""

from __future__ import annotations

import json

import pytest

from services.crm_connection_registry import (
    CrmRefError,
    SalesforceCrmBundle,
    effective_properties_for_object,
    ensure_properties_allowed,
    ensure_record_allowed,
    has_any_crm_bundle_configured,
    resolve_crm_bundle,
)


VALID_BUNDLE = {
    "provider": "hubspot",
    "auth_mode": "private_app_token",
    "private_app_token": "secret-token",
    "portal_id": "12345678",
    "allowed_object_types": ["Contacts", "Deals"],
    "allowed_properties_by_object": {
        "Contacts": ["email", "firstname", "lastname"],
        "Deals": ["dealname", "amount"],
    },
    "default_properties_by_object": {
        "Contacts": ["email", "firstname"],
    },
    "searchable_properties_by_object": {
        "Contacts": ["email"],
    },
    "sortable_properties_by_object": {
        "Contacts": ["firstname"],
    },
    "allowed_record_ids_by_object": {
        "Contacts": ["101", "202"],
    },
}

VALID_SALESFORCE_BUNDLE = {
    "provider": "salesforce",
    "auth_mode": "connected_app_refresh_token",
    "client_id": "client-123",
    "client_secret": "secret-123",
    "refresh_token": "refresh-123",
    "auth_base_url": "https://test.salesforce.com",
    "api_version": "v61.0",
    "allowed_object_types": ["Account"],
    "allowed_properties_by_object": {
        "Account": ["Name", "Industry", "CreatedDate", "LastModifiedDate"],
    },
    "default_properties_by_object": {
        "Account": ["Name", "Industry"],
    },
    "searchable_properties_by_object": {
        "Account": ["Name"],
    },
    "sortable_properties_by_object": {
        "Account": ["CreatedDate"],
    },
    "allowed_record_ids_by_object": {
        "Account": ["001ABC000000123XYZ"],
    },
}


def test_resolve_crm_bundle_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RHUMB_CRM_HS_MAIN", json.dumps(VALID_BUNDLE))

    bundle = resolve_crm_bundle("hs_main")

    assert bundle.provider == "hubspot"
    assert bundle.auth_mode == "private_app_token"
    assert bundle.portal_id == "12345678"
    assert bundle.allowed_object_types == ("contacts", "deals")
    assert bundle.allowed_properties_by_object["contacts"] == ("email", "firstname", "lastname")
    assert bundle.default_properties_by_object["contacts"] == ("email", "firstname")
    assert bundle.searchable_properties_by_object["contacts"] == ("email",)
    assert bundle.sortable_properties_by_object["contacts"] == ("firstname",)
    assert bundle.allowed_record_ids_by_object["contacts"] == ("101", "202")


def test_resolve_crm_bundle_requires_allowed_properties_for_every_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid = dict(VALID_BUNDLE)
    invalid["allowed_properties_by_object"] = {"contacts": ["email"]}
    monkeypatch.setenv("RHUMB_CRM_HS_MAIN", json.dumps(invalid))

    with pytest.raises(CrmRefError, match="missing entries for: deals"):
        resolve_crm_bundle("hs_main")


def test_resolve_salesforce_bundle_from_env_preserves_exact_api_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RHUMB_CRM_SF_MAIN", json.dumps(VALID_SALESFORCE_BUNDLE))

    bundle = resolve_crm_bundle("sf_main")

    assert isinstance(bundle, SalesforceCrmBundle)
    assert bundle.provider == "salesforce"
    assert bundle.auth_mode == "connected_app_refresh_token"
    assert bundle.auth_base_url == "https://test.salesforce.com"
    assert bundle.api_version == "v61.0"
    assert bundle.allowed_object_types == ("Account",)
    assert bundle.allowed_properties_by_object["Account"] == (
        "Name",
        "Industry",
        "CreatedDate",
        "LastModifiedDate",
    )


def test_salesforce_scope_helpers_enforce_exact_object_and_field_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RHUMB_CRM_SF_MAIN", json.dumps(VALID_SALESFORCE_BUNDLE))

    bundle = resolve_crm_bundle("sf_main")

    assert effective_properties_for_object(bundle, "Account", None) == ("Name", "Industry")

    with pytest.raises(CrmRefError, match="object_type 'account'"):
        effective_properties_for_object(bundle, "account", None)

    with pytest.raises(CrmRefError, match="property 'name'"):
        ensure_properties_allowed(bundle, "Account", ["name"])

    with pytest.raises(CrmRefError, match="record_id '001ABC000000999XYZ'"):
        ensure_record_allowed(bundle, "Account", "001ABC000000999XYZ")


def test_resolve_crm_bundle_rejects_default_properties_outside_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid = dict(VALID_BUNDLE)
    invalid["default_properties_by_object"] = {"contacts": ["email", "lifecyclestage"]}
    monkeypatch.setenv("RHUMB_CRM_HS_MAIN", json.dumps(invalid))

    with pytest.raises(CrmRefError, match="outside allowed_properties_by_object"):
        resolve_crm_bundle("hs_main")


def test_crm_scope_helpers_enforce_properties_and_record_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "RHUMB_CRM_HS_MAIN",
        json.dumps(
            {
                "provider": "hubspot",
                "auth_mode": "private_app_token",
                "private_app_token": "secret-token",
                "allowed_object_types": ["contacts"],
                "allowed_properties_by_object": {
                    "contacts": ["email", "firstname"],
                },
                "default_properties_by_object": {
                    "contacts": ["email"],
                },
                "allowed_record_ids_by_object": {
                    "contacts": ["101"],
                },
            }
        ),
    )

    bundle = resolve_crm_bundle("hs_main")

    assert effective_properties_for_object(bundle, "contacts", None) == ("email",)

    with pytest.raises(CrmRefError, match="property 'lastname'"):
        ensure_properties_allowed(bundle, "contacts", ["lastname"])

    with pytest.raises(CrmRefError, match="record_id '999'"):
        ensure_record_allowed(bundle, "contacts", "999")


def test_has_any_crm_bundle_configured_filters_invalid_or_wrong_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RHUMB_CRM_BAD", "not-json")
    monkeypatch.setenv("RHUMB_CRM_HS_MAIN", json.dumps(VALID_BUNDLE))
    monkeypatch.setenv("RHUMB_CRM_SF_MAIN", json.dumps(VALID_SALESFORCE_BUNDLE))

    assert has_any_crm_bundle_configured() is True
    assert has_any_crm_bundle_configured("hubspot") is True
    assert has_any_crm_bundle_configured("salesforce") is True
