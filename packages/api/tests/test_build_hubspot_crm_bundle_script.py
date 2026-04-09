"""Tests for the HubSpot CRM bundle builder script."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "build_hubspot_crm_bundle.py"

spec = importlib.util.spec_from_file_location("build_hubspot_crm_bundle", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
build_hubspot_crm_bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_hubspot_crm_bundle)


def test_extract_sop_defaults_reads_token_scope_and_record_fields() -> None:
    defaults = build_hubspot_crm_bundle._extract_sop_defaults(
        {
            "fields": [
                {"label": "portal_id", "value": "123456"},
                {"label": "credential", "value": "hubspot-secret"},
                {"label": "allowed_object_types", "value": "Contacts, Deals"},
                {"label": "allowed_properties_contacts", "value": "firstname, lastname"},
                {"label": "default_properties_contacts", "value": ["email"]},
                {"label": "searchable_properties_contacts", "value": "email"},
                {"label": "sortable_properties_contacts", "value": "createdate"},
                {"label": "allowed_record_ids_contacts", "value": [123, "456"]},
            ]
        }
    )

    assert defaults == {
        "portal_id": "123456",
        "private_app_token": "hubspot-secret",
        "allowed_object_types": ["contacts", "deals"],
        "allowed_properties_by_object": {"contacts": ["firstname", "lastname"]},
        "default_properties_by_object": {"contacts": ["email"]},
        "searchable_properties_by_object": {"contacts": ["email"]},
        "sortable_properties_by_object": {"contacts": ["createdate"]},
        "allowed_record_ids_by_object": {"contacts": ["123", "456"]},
    }


def test_build_bundle_prefers_cli_scope_over_sourced_defaults() -> None:
    args = build_hubspot_crm_bundle.build_parser().parse_args(
        [
            "--portal-id",
            "654321",
            "--private-app-token",
            "override-token",
            "--allow-object",
            "contacts",
            "--allow-property",
            "contacts:firstname",
            "--default-property",
            "contacts:email",
        ]
    )

    bundle = build_hubspot_crm_bundle._build_bundle(
        args,
        sourced={
            "portal_id": "111111",
            "private_app_token": "sourced-token",
            "allowed_object_types": ["deals"],
            "allowed_properties_by_object": {"deals": ["dealname"]},
        },
    )

    assert bundle == {
        "provider": "hubspot",
        "portal_id": "654321",
        "auth_mode": "private_app_token",
        "private_app_token": "override-token",
        "allowed_object_types": ["contacts"],
        "allowed_properties_by_object": {"contacts": ["firstname"]},
        "default_properties_by_object": {"contacts": ["email"]},
    }


def test_build_bundle_requires_allowed_properties_for_every_object() -> None:
    args = build_hubspot_crm_bundle.build_parser().parse_args(
        [
            "--private-app-token",
            "hubspot-secret",
            "--allow-object",
            "contacts",
        ]
    )

    try:
        build_hubspot_crm_bundle._build_bundle(args, sourced={})
    except ValueError as exc:
        assert str(exc) == (
            "Every allowlisted object_type needs allowed properties; missing allowed properties for: contacts"
        )
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError for missing allowed properties")
