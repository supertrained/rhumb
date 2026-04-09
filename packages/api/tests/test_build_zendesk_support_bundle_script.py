"""Tests for the Zendesk support bundle builder script."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "build_zendesk_support_bundle.py"

spec = importlib.util.spec_from_file_location("build_zendesk_support_bundle", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
build_zendesk_support_bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_zendesk_support_bundle)


def test_extract_sop_defaults_infers_api_token_mode_from_email_and_credential() -> None:
    defaults = build_zendesk_support_bundle._extract_sop_defaults(
        {
            "fields": [
                {"label": "username", "value": "ops@acme.com"},
                {"label": "credential", "value": "secret-token"},
                {"label": "allowed_group_ids", "value": "123, 456"},
                {"label": "allow_internal_comments", "value": "true"},
            ],
            "urls": [{"href": "https://acme-help.zendesk.com/agent/admin"}],
        }
    )

    assert defaults == {
        "subdomain": "acme-help",
        "auth_mode": "api_token",
        "email": "ops@acme.com",
        "api_token": "secret-token",
        "allowed_group_ids": [123, 456],
        "allow_internal_comments": True,
    }


def test_extract_sop_defaults_honors_bearer_token_fields_and_brand_ids() -> None:
    defaults = build_zendesk_support_bundle._extract_sop_defaults(
        {
            "fields": [
                {"label": "auth mode", "value": "bearer_token"},
                {"label": "subdomain", "value": "thrivemarket"},
                {"label": "access_token", "value": "bearer-secret"},
                {"label": "allowed_brand_id", "value": [77, "88"]},
            ],
            "urls": [],
        }
    )

    assert defaults == {
        "subdomain": "thrivemarket",
        "auth_mode": "bearer_token",
        "bearer_token": "bearer-secret",
        "allowed_brand_ids": [77, 88],
    }


def test_build_bundle_prefers_cli_overrides_over_item_defaults() -> None:
    args = build_zendesk_support_bundle.build_parser().parse_args(
        [
            "--subdomain",
            "override-subdomain",
            "--email",
            "override@acme.com",
            "--api-token",
            "override-token",
            "--allowed-group-id",
            "999",
        ]
    )

    bundle = build_zendesk_support_bundle._build_bundle(
        args,
        sourced={
            "subdomain": "sourced-subdomain",
            "auth_mode": "api_token",
            "email": "ops@acme.com",
            "api_token": "sourced-token",
            "allowed_group_ids": [123],
            "allow_internal_comments": True,
        },
    )

    assert bundle == {
        "provider": "zendesk",
        "subdomain": "override-subdomain",
        "auth_mode": "api_token",
        "allowed_group_ids": [999],
        "allowed_brand_ids": [],
        "allow_internal_comments": True,
        "email": "override@acme.com",
        "api_token": "override-token",
    }


def test_build_bundle_errors_when_subdomain_missing_without_sop_source() -> None:
    args = build_zendesk_support_bundle.build_parser().parse_args(
        [
            "--email",
            "ops@acme.com",
            "--api-token",
            "secret-token",
            "--allowed-group-id",
            "123",
        ]
    )

    try:
        build_zendesk_support_bundle._build_bundle(args, sourced={})
    except ValueError as exc:
        assert str(exc) == "--subdomain is required unless it can be inferred from --from-sop-item"
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError for missing subdomain")
