from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "audit_warehouse_proof_sources.py"

spec = importlib.util.spec_from_file_location("audit_warehouse_proof_sources", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
warehouse_audit = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = warehouse_audit
spec.loader.exec_module(warehouse_audit)


def test_bigquery_bundle_material_accepts_embedded_bundle_note() -> None:
    ready, missing, details = warehouse_audit._bigquery_bundle_material(
        {
            "notesPlain": """
            {
              "provider": "bigquery",
              "auth_mode": "service_account_json",
              "service_account_json": {
                "type": "service_account",
                "project_id": "rhumb-sandbox",
                "client_email": "rhumb-bq-read@rhumb-sandbox.iam.gserviceaccount.com",
                "private_key": "-----BEGIN PRIVATE KEY-----\\nabc\\n-----END PRIVATE KEY-----\\n"
              },
              "billing_project_id": "rhumb-sandbox",
              "location": "US",
              "allowed_dataset_refs": ["rhumb-sandbox.analytics"],
              "allowed_table_refs": ["rhumb-sandbox.analytics.orders_view"]
            }
            """,
            "fields": [],
        }
    )

    assert ready is True
    assert missing == []
    assert details["has_service_account_json"] is True
    assert details["has_embedded_bundle_json"] is True
    assert details["project_ids"] == ["rhumb-sandbox"]
    assert details["candidate_accounts"] == ["rhumb-bq-read@rhumb-sandbox.iam.gserviceaccount.com"]


def test_bigquery_bundle_material_accepts_split_field_impersonation_material() -> None:
    ready, missing, details = warehouse_audit._bigquery_bundle_material(
        {
            "notesPlain": "",
            "fields": [
                {"label": "client_id", "value": "client-id.apps.googleusercontent.com"},
                {"label": "client_secret", "value": "secret"},
                {"label": "credential", "value": "refresh-token"},
                {"label": "project_id", "value": "rhumb-490802"},
                {"label": "account", "value": "team@getsupertrained.com"},
                {"label": "service_account_email", "value": "rhumb-bq-proof-read@rhumb-490802.iam.gserviceaccount.com"},
                {"label": "location", "value": "US"},
                {"label": "allowed_dataset_refs", "value": "rhumb-490802.analytics_sandbox"},
                {"label": "allowed_table_refs", "value": "rhumb-490802.analytics_sandbox.orders"},
            ],
        }
    )

    assert ready is True
    assert missing == []
    assert details["auth_mode"] == "service_account_impersonation"
    assert details["has_authorized_user_json"] is True
    assert details["service_account_email"] == "rhumb-bq-proof-read@rhumb-490802.iam.gserviceaccount.com"
    assert details["project_ids"] == ["rhumb-490802"]
    assert details["candidate_accounts"] == [
        "rhumb-bq-proof-read@rhumb-490802.iam.gserviceaccount.com",
        "team@getsupertrained.com",
    ]


def test_bigquery_bundle_material_flags_google_oauth_hint_without_bundle() -> None:
    ready, missing, details = warehouse_audit._bigquery_bundle_material(
        {
            "notesPlain": "",
            "fields": [
                {"label": "notesPlain", "value": 'GCP project: Rhumb (rhumb-490802). Created 2026-03-19.'},
                {"label": "client_id", "value": "client-id.apps.googleusercontent.com"},
                {"label": "client_secret", "value": "secret"},
                {"label": "project_id", "value": "rhumb-490802"},
                {"label": "account", "value": "team@getsupertrained.com"},
            ],
        }
    )

    assert ready is False
    assert missing == [
        "authorized_user_json",
        "service_account_email",
        "location",
        "allowed_dataset_refs",
        "allowed_table_refs",
    ]
    assert details["auth_mode"] == "service_account_impersonation"
    assert details["has_google_oauth_material"] is True
    assert details["project_ids"] == ["rhumb-490802"]
    assert details["candidate_accounts"] == ["team@getsupertrained.com"]


def test_redact_url_for_artifact_keeps_project_and_drops_google_tokens() -> None:
    redacted = warehouse_audit._redact_url_for_artifact(
        "https://console.cloud.google.com/apis/credentials?rapt=secret-token&rart=other-secret&project=rhumb-490802&supportedpurview=project"
    )

    assert redacted == "https://console.cloud.google.com/apis/credentials?project=rhumb-490802&supportedpurview=project"


def test_summarize_provider_mentions_candidate_projects_and_accounts() -> None:
    provider = warehouse_audit.PROVIDERS["bigquery"]
    summary = warehouse_audit.summarize_provider(
        provider,
        vault={
            "hit_count": 2,
            "bundle_ready_hit_count": 0,
            "project_ids": ["rhumb-490802"],
            "candidate_accounts": ["team@getsupertrained.com"],
        },
        browser={
            "workspace_hosts": [],
            "project_ids": ["rhumb-sandbox"],
        },
        browser_saved_logins={
            "hit_count": 1,
            "usernames": ["team@getsupertrained.com"],
        },
        gmail={
            "hit_count": 0,
            "project_ids": [],
            "candidate_accounts": [],
        },
        hosted_surface={
            "supported": True,
            "live": True,
            "configured": False,
        },
        local_tooling={
            "gcloud_installed": False,
        },
        local_service_account_files={
            "hit_count": 1,
            "candidate_project_hit_count": 0,
            "project_ids": ["snowthere"],
        },
    )

    assert summary["proof_material_ready"] is False
    assert summary["likely_blocked_on_credentials"] is True
    assert "rhumb-490802" in summary["assessment"]
    assert "rhumb-sandbox" in summary["assessment"]
    assert "team@getsupertrained.com" in summary["assessment"]
    assert "Local file scan found service-account JSON" in summary["assessment"]
    assert "gcloud" in summary["assessment"]


def test_audit_local_service_account_files_distinguishes_candidate_project_hits(tmp_path: Path) -> None:
    matching = tmp_path / "rhumb-service-account.json"
    matching.write_text(
        json.dumps(
            {
                "type": "service_account",
                "project_id": "rhumb-490802",
                "private_key_id": "abc123",
                "private_key": "-----BEGIN PRIVATE KEY-----\\nabc\\n-----END PRIVATE KEY-----\\n",
            }
        )
    )
    unrelated = tmp_path / "snowthere-service-account.json"
    unrelated.write_text(
        json.dumps(
            {
                "type": "service_account",
                "project_id": "snowthere",
                "private_key_id": "def456",
                "private_key": "-----BEGIN PRIVATE KEY-----\\ndef\\n-----END PRIVATE KEY-----\\n",
            }
        )
    )
    not_service_account = tmp_path / "other.json"
    not_service_account.write_text(json.dumps({"hello": "world"}))

    result = warehouse_audit.audit_local_service_account_files([tmp_path], ["rhumb-490802"], max_hits=10)

    assert result["scanned_file_count"] == 3
    assert result["hit_count"] == 2
    assert result["candidate_project_hit_count"] == 1
    assert result["unrelated_service_account_hit_count"] == 1
    assert set(result["project_ids"]) == {"rhumb-490802", "snowthere"}
    assert any(hit["candidate_project_match"] is True for hit in result["hits"])
    assert any(hit["candidate_project_match"] is False for hit in result["hits"])
