"""Tests for the Salesforce CRM bundle builder script."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "build_salesforce_crm_bundle.py"

spec = importlib.util.spec_from_file_location("build_salesforce_crm_bundle", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
build_salesforce_crm_bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_salesforce_crm_bundle)


def test_extract_sop_defaults_reads_connected_app_scope_and_record_fields() -> None:
    defaults = build_salesforce_crm_bundle._extract_sop_defaults(
        {
            "fields": [
                {"label": "client_id", "value": "client-123"},
                {"label": "client_secret", "value": "secret-123"},
                {"label": "refresh_token", "value": "refresh-123"},
                {"label": "auth_base_url", "value": "https://test.salesforce.com"},
                {"label": "api_version", "value": "61.0"},
                {"label": "allowed_object_types", "value": "Account, Contact"},
                {
                    "label": "allowed_properties_by_object",
                    "value": '{"Account":["Name","Industry"],"Contact":["FirstName","LastName"]}',
                },
                {
                    "label": "default_properties_by_object",
                    "value": '{"Account":["Name"]}',
                },
                {
                    "label": "searchable_properties_by_object",
                    "value": '{"Account":["Name"]}',
                },
                {
                    "label": "sortable_properties_by_object",
                    "value": '{"Account":["CreatedDate"]}',
                },
                {
                    "label": "allowed_record_ids_by_object",
                    "value": '{"Account":["001ABC000000123XYZ"]}',
                },
            ]
        }
    )

    assert defaults == {
        "client_id": "client-123",
        "client_secret": "secret-123",
        "refresh_token": "refresh-123",
        "auth_base_url": "https://test.salesforce.com",
        "api_version": "61.0",
        "allowed_object_types": ["Account", "Contact"],
        "allowed_properties_by_object": {
            "Account": ["Name", "Industry"],
            "Contact": ["FirstName", "LastName"],
        },
        "default_properties_by_object": {"Account": ["Name"]},
        "searchable_properties_by_object": {"Account": ["Name"]},
        "sortable_properties_by_object": {"Account": ["CreatedDate"]},
        "allowed_record_ids_by_object": {"Account": ["001ABC000000123XYZ"]},
    }


def test_build_bundle_prefers_cli_scope_over_sourced_defaults() -> None:
    args = build_salesforce_crm_bundle.build_parser().parse_args(
        [
            "--client-id",
            "override-client",
            "--client-secret",
            "override-secret",
            "--refresh-token",
            "override-refresh",
            "--auth-base-url",
            "https://test.salesforce.com",
            "--api-version",
            "v61.0",
            "--allow-object",
            "Account",
            "--allow-property",
            "Account:Name",
            "--default-property",
            "Account:Industry",
        ]
    )

    bundle = build_salesforce_crm_bundle._build_bundle(
        args,
        sourced={
            "client_id": "sourced-client",
            "client_secret": "sourced-secret",
            "refresh_token": "sourced-refresh",
            "allowed_object_types": ["Contact"],
            "allowed_properties_by_object": {"Contact": ["FirstName"]},
        },
    )

    assert bundle == {
        "provider": "salesforce",
        "auth_mode": "connected_app_refresh_token",
        "client_id": "override-client",
        "client_secret": "override-secret",
        "refresh_token": "override-refresh",
        "auth_base_url": "https://test.salesforce.com",
        "api_version": "v61.0",
        "allowed_object_types": ["Account"],
        "allowed_properties_by_object": {"Account": ["Name"]},
        "default_properties_by_object": {"Account": ["Industry"]},
    }


def test_build_bundle_requires_allowed_properties_for_every_object() -> None:
    args = build_salesforce_crm_bundle.build_parser().parse_args(
        [
            "--client-id",
            "client-123",
            "--client-secret",
            "secret-123",
            "--refresh-token",
            "refresh-123",
            "--allow-object",
            "Account",
        ]
    )

    try:
        build_salesforce_crm_bundle._build_bundle(args, sourced={})
    except ValueError as exc:
        assert str(exc) == (
            "Every allowlisted object_type needs allowed properties; missing allowed properties for: Account"
        )
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError for missing allowed properties")
