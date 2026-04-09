"""Tests for the crm_ref registry."""

from __future__ import annotations

import json

import pytest

from services.crm_connection_registry import (
    CrmRefError,
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

    assert has_any_crm_bundle_configured() is True
    assert has_any_crm_bundle_configured("hubspot") is True
    assert has_any_crm_bundle_configured("salesforce") is False
