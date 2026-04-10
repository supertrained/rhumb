from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "mint_google_authorized_user_adc.py"

spec = importlib.util.spec_from_file_location("mint_google_authorized_user_adc", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
mint_google_authorized_user_adc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mint_google_authorized_user_adc)


def test_extract_sop_client_metadata_reads_expected_fields() -> None:
    metadata = mint_google_authorized_user_adc._extract_sop_client_metadata(
        {
            "fields": [
                {"label": "client_id", "value": "client-id.apps.googleusercontent.com"},
                {"label": "client_secret", "value": "client-secret"},
                {"label": "project_id", "value": "rhumb-490802"},
                {"label": "account", "value": "team@getsupertrained.com"},
            ]
        }
    )

    assert metadata == {
        "client_id": "client-id.apps.googleusercontent.com",
        "client_secret": "client-secret",
        "project_id": "rhumb-490802",
        "account": "team@getsupertrained.com",
    }


def test_build_client_id_file_payload_defaults_to_installed_client() -> None:
    payload = mint_google_authorized_user_adc._build_client_id_file_payload(
        "client-id", "client-secret"
    )

    assert payload == {
        "installed": {
            "client_id": "client-id",
            "client_secret": "client-secret",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def test_build_login_command_includes_scopes_and_quota_disable(tmp_path) -> None:
    command = mint_google_authorized_user_adc._build_login_command(
        gcloud_path=tmp_path / "gcloud",
        client_id_file=tmp_path / "client.json",
        scopes=[
            "https://www.googleapis.com/auth/cloud-platform",
            "https://www.googleapis.com/auth/bigquery",
        ],
        disable_quota_project=True,
        no_browser=False,
    )

    assert command == [
        str(tmp_path / "gcloud"),
        "auth",
        "application-default",
        "login",
        f"--client-id-file={tmp_path / 'client.json'}",
        "--scopes=https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/bigquery",
        "--disable-quota-project",
    ]


def test_resolve_gcloud_path_prefers_home_sdk_fallback(tmp_path) -> None:
    fallback = tmp_path / "google-cloud-sdk" / "bin" / "gcloud"
    fallback.parent.mkdir(parents=True)
    fallback.write_text("#!/bin/sh\n", encoding="utf-8")

    with patch.object(mint_google_authorized_user_adc, "DEFAULT_GCLOUD_FALLBACK", fallback), patch.object(
        mint_google_authorized_user_adc.shutil, "which", return_value=None
    ):
        path = mint_google_authorized_user_adc._resolve_gcloud_path()

    assert path == fallback


def test_summarize_adc_file_reports_matching_authorized_user(tmp_path) -> None:
    adc_path = tmp_path / "application_default_credentials.json"
    adc_path.write_text(
        json.dumps(
            {
                "type": "authorized_user",
                "client_id": "client-id.apps.googleusercontent.com",
                "client_secret": "client-secret",
                "refresh_token": "refresh-token",
                "quota_project_id": "rhumb-490802",
            }
        ),
        encoding="utf-8",
    )

    summary = mint_google_authorized_user_adc._summarize_adc_file(
        adc_path,
        expected_client_id="client-id.apps.googleusercontent.com",
    )

    assert summary == {
        "path": str(adc_path),
        "type": "authorized_user",
        "client_id_matches": True,
        "client_id_length": 36,
        "refresh_token_present": True,
        "refresh_token_length": 13,
        "quota_project_id": "rhumb-490802",
    }


def test_build_bundle_command_hint_requires_bounded_bigquery_fields() -> None:
    args = mint_google_authorized_user_adc.build_parser().parse_args(
        [
            "--warehouse-ref",
            "bq_analytics_read",
            "--service-account-email",
            "svc@rhumb-490802.iam.gserviceaccount.com",
            "--billing-project-id",
            "rhumb-490802",
            "--location",
            "US",
            "--allowed-dataset-ref",
            "rhumb-490802.analytics_sandbox",
            "--allowed-table-ref",
            "rhumb-490802.analytics_sandbox.orders",
        ]
    )

    command = mint_google_authorized_user_adc._build_bundle_command_hint(
        args,
        Path("/tmp/application_default_credentials.json"),
    )

    assert command is not None
    assert "build_bigquery_warehouse_bundle.py" in command
    assert "--authorized-user-json-file /tmp/application_default_credentials.json" in command
    assert "--warehouse-ref bq_analytics_read" in command


def test_build_proof_command_hint_chains_bundle_builder_and_dogfood_runner() -> None:
    args = mint_google_authorized_user_adc.build_parser().parse_args(
        [
            "--warehouse-ref",
            "bq_analytics_read",
            "--service-account-email",
            "svc@rhumb-490802.iam.gserviceaccount.com",
            "--billing-project-id",
            "rhumb-490802",
            "--location",
            "US",
            "--allowed-dataset-ref",
            "rhumb-490802.analytics_sandbox",
            "--allowed-table-ref",
            "rhumb-490802.analytics_sandbox.orders",
        ]
    )

    command = mint_google_authorized_user_adc._build_proof_command_hint(
        args,
        Path("/tmp/application_default_credentials.json"),
    )

    assert command is not None
    assert 'export RHUMB_WAREHOUSE_BQ_ANALYTICS_READ="$(' in command
    assert "build_bigquery_warehouse_bundle.py" in command
    assert "--format env-value" in command
    assert "bigquery_warehouse_read_dogfood.py" in command
    assert "--base-url https://api.rhumb.dev" in command
    assert "SELECT * FROM `rhumb-490802.analytics_sandbox.orders` LIMIT 5" in command


def test_build_plan_includes_safe_gcloud_summary(tmp_path) -> None:
    fallback = tmp_path / "google-cloud-sdk" / "bin" / "gcloud"
    fallback.parent.mkdir(parents=True)
    fallback.write_text("#!/bin/sh\n", encoding="utf-8")

    with (
        patch.object(mint_google_authorized_user_adc, "DEFAULT_GCLOUD_FALLBACK", fallback),
        patch.object(
            mint_google_authorized_user_adc, "_load_sop_item", return_value={
                "fields": [
                    {"label": "client_id", "value": "client-id.apps.googleusercontent.com"},
                    {"label": "client_secret", "value": "client-secret"},
                    {"label": "project_id", "value": "rhumb-490802"},
                    {"label": "account", "value": "team@getsupertrained.com"},
                ]
            }
        ),
        patch.object(mint_google_authorized_user_adc.shutil, "which", return_value=None),
    ):
        args = mint_google_authorized_user_adc.build_parser().parse_args(
            [
                "--dry-run",
                "--warehouse-ref",
                "bq_analytics_read",
                "--service-account-email",
                "svc@rhumb-490802.iam.gserviceaccount.com",
                "--billing-project-id",
                "rhumb-490802",
                "--location",
                "US",
                "--allowed-dataset-ref",
                "rhumb-490802.analytics_sandbox",
                "--allowed-table-ref",
                "rhumb-490802.analytics_sandbox.orders",
            ]
        )
        plan = mint_google_authorized_user_adc._build_plan(args)

    assert plan["mode"] == "dry_run"
    assert plan["oauth_client"]["client_id_length"] == 36
    assert plan["oauth_client"]["client_secret_length"] == 13
    assert plan["gcloud"]["path"] == str(fallback)
    assert "application-default login" in plan["gcloud"]["command"]
    assert plan["bundle_command"] is not None
    assert plan["proof_command"] is not None
    assert "build_bigquery_warehouse_bundle.py" in plan["proof_command"]
    assert "bigquery_warehouse_read_dogfood.py" in plan["proof_command"]
