"""Tests for the Intercom support bundle builder script."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "build_intercom_support_bundle.py"

spec = importlib.util.spec_from_file_location("build_intercom_support_bundle", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
build_intercom_support_bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_intercom_support_bundle)


def test_extract_sop_defaults_reads_region_token_and_scope_fields() -> None:
    defaults = build_intercom_support_bundle._extract_sop_defaults(
        {
            "fields": [
                {"label": "region", "value": "EU"},
                {"label": "credential", "value": "intercom-secret"},
                {"label": "allowed_team_ids", "value": "123, 456"},
                {"label": "allowed_admin_id", "value": [77, "88"]},
                {"label": "allowed_conversation_ids", "value": ["conv_1", 215473840934085]},
                {"label": "allow_internal_notes", "value": "true"},
            ]
        }
    )

    assert defaults == {
        "region": "eu",
        "bearer_token": "intercom-secret",
        "allowed_team_ids": [123, 456],
        "allowed_admin_ids": [77, 88],
        "allowed_conversation_ids": ["conv_1", "215473840934085"],
        "allow_internal_notes": True,
    }


def test_build_bundle_prefers_cli_overrides_over_item_defaults() -> None:
    args = build_intercom_support_bundle.build_parser().parse_args(
        [
            "--support-ref",
            "st_ic",
            "--region",
            "au",
            "--bearer-token",
            "override-token",
            "--allowed-team-id",
            "999",
        ]
    )

    bundle = build_intercom_support_bundle._build_bundle(
        args,
        sourced={
            "region": "us",
            "bearer_token": "sourced-token",
            "allowed_team_ids": [123],
            "allowed_admin_ids": [77],
            "allowed_conversation_ids": ["conv_1"],
            "allow_internal_notes": True,
        },
    )

    assert bundle == {
        "provider": "intercom",
        "region": "au",
        "auth_mode": "bearer_token",
        "bearer_token": "override-token",
        "allowed_team_ids": [999],
        "allowed_admin_ids": [77],
        "allowed_conversation_ids": ["conv_1"],
        "allow_internal_notes": True,
    }


def test_build_bundle_allows_conversation_only_scope() -> None:
    args = build_intercom_support_bundle.build_parser().parse_args(
        [
            "--support-ref",
            "st_ic",
            "--region",
            "us",
            "--bearer-token",
            "secret-token",
            "--allowed-conversation-id",
            "215473840934085",
        ]
    )

    bundle = build_intercom_support_bundle._build_bundle(args, sourced={})

    assert bundle == {
        "provider": "intercom",
        "region": "us",
        "auth_mode": "bearer_token",
        "bearer_token": "secret-token",
        "allowed_team_ids": [],
        "allowed_admin_ids": [],
        "allowed_conversation_ids": ["215473840934085"],
        "allow_internal_notes": False,
    }


def test_build_bundle_errors_when_region_missing_without_sop_source() -> None:
    args = build_intercom_support_bundle.build_parser().parse_args(
        [
            "--support-ref",
            "st_ic",
            "--bearer-token",
            "secret-token",
            "--allowed-team-id",
            "123",
        ]
    )

    try:
        build_intercom_support_bundle._build_bundle(args, sourced={})
    except ValueError as exc:
        assert str(exc) == (
            "--region is required unless it can be inferred from --from-sop-item, and must be us, eu, or au"
        )
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError for missing region")
