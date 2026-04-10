from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "mint_salesforce_refresh_token.py"

spec = importlib.util.spec_from_file_location("mint_salesforce_refresh_token", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
mint_salesforce_refresh_token = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mint_salesforce_refresh_token)


def test_extract_sop_client_metadata_reads_expected_fields() -> None:
    metadata = mint_salesforce_refresh_token._extract_sop_client_metadata(
        {
            "fields": [
                {"label": "consumer_key", "value": "client-id"},
                {"label": "consumer_secret", "value": "sf-secret-42"},
                {"label": "login_url", "value": "https://test.salesforce.com"},
                {"label": "callback_url", "value": "http://127.0.0.1:1717/callback"},
                {"label": "connected_app_name", "value": "Rhumb CRM Proof"},
                {"label": "account", "value": "ops@example.com"},
            ]
        }
    )

    assert metadata == {
        "client_id": "client-id",
        "client_secret": "sf-secret-42",
        "auth_base_url": "https://test.salesforce.com",
        "redirect_uri": "http://127.0.0.1:1717/callback",
        "connected_app": "Rhumb CRM Proof",
        "account": "ops@example.com",
    }


def test_build_authorize_url_includes_expected_query_parameters() -> None:
    url = mint_salesforce_refresh_token._build_authorize_url(
        auth_base_url="https://login.salesforce.com",
        client_id="client-id",
        redirect_uri="http://127.0.0.1:1717/callback",
        scopes=["api", "refresh_token"],
        state="state-123",
    )

    assert url.startswith("https://login.salesforce.com/services/oauth2/authorize?")
    assert "client_id=client-id" in url
    assert "redirect_uri=http%3A%2F%2F127.0.0.1%3A1717%2Fcallback" in url
    assert "scope=api+refresh_token" in url
    assert "state=state-123" in url


def test_extract_code_from_manual_input_accepts_callback_url() -> None:
    result = mint_salesforce_refresh_token._extract_code_from_manual_input(
        "http://127.0.0.1:1717/callback?code=abc123&state=state-123"
    )

    assert result == {
        "code": "abc123",
        "state": "state-123",
        "error": None,
        "error_description": None,
    }


def test_summarize_token_payload_masks_sensitive_values() -> None:
    summary = mint_salesforce_refresh_token._summarize_token_payload(
        {
            "access_token": "access-token-placeholder",
            "refresh_token": "refresh-token-placeholder-value",
            "instance_url": "https://acme.my.salesforce.com",
            "id": "https://login.salesforce.com/id/org-placeholder/user-0001",
            "scope": "api refresh_token",
            "issued_at": "1712784000000",
            "signature": "sig",
            "token_type": "Bearer",
        }
    )

    assert summary == {
        "instance_url": "https://acme.my.salesforce.com",
        "id_url": "https://...0001",
        "issued_at": "1712784000000",
        "signature_present": True,
        "token_type": "Bearer",
        "scope": ["api", "refresh_token"],
        "access_token_present": True,
        "access_token_length": len("access-token-placeholder"),
        "refresh_token_present": True,
        "refresh_token_length": len("refresh-token-placeholder-value"),
    }


def test_build_bundle_command_hint_uses_safe_placeholders() -> None:
    args = mint_salesforce_refresh_token.build_parser().parse_args(
        [
            "--client-id",
            "real-client-id",
            "--client-secret",
            "real-client-secret",
            "--crm-ref",
            "sf_main",
            "--allow-object",
            "Account",
            "--allow-property",
            "Account:Name",
            "--default-property",
            "Account:Industry",
            "--token-json-out",
            "/tmp/salesforce-token.json",
        ]
    )

    command = mint_salesforce_refresh_token._build_bundle_command_hint(
        args,
        token_json_path=Path("/tmp/salesforce-token.json"),
    )

    assert command is not None
    assert "build_salesforce_crm_bundle.py" in command
    assert 'SALESFORCE_CLIENT_ID' in command
    assert 'SALESFORCE_CLIENT_SECRET' in command
    assert 'SALESFORCE_REFRESH_TOKEN' in command
    assert "real-client-secret" not in command
    assert "real-client-id" not in command
    assert "/tmp/salesforce-token.json" in command
    assert "--crm-ref sf_main" in command
    assert "--allow-object Account" in command


def test_build_proof_command_hint_chains_bundle_and_dogfood_steps() -> None:
    args = mint_salesforce_refresh_token.build_parser().parse_args(
        [
            "--client-id",
            "real-client-id",
            "--client-secret",
            "real-client-secret",
            "--crm-ref",
            "sf_main",
            "--allow-object",
            "Account",
            "--allow-property",
            "Account:Name",
            "--token-json-out",
            "/tmp/salesforce-token.json",
            "--record-id",
            "001ABC000000123XYZ",
            "--property-name",
            "Name",
        ]
    )

    command = mint_salesforce_refresh_token._build_proof_command_hint(
        args,
        token_json_path=Path("/tmp/salesforce-token.json"),
    )

    assert command is not None
    assert "build_salesforce_crm_bundle.py" in command
    assert "salesforce_crm_read_dogfood.py" in command
    assert "source /tmp/salesforce-token.bundle.env" in command
    assert "--record-id 001ABC000000123XYZ" in command
    assert "--property-name Name" in command


def test_build_plan_includes_safe_1password_summary() -> None:
    with patch.object(
        mint_salesforce_refresh_token,
        "_load_sop_item",
        return_value={
            "fields": [
                {"label": "consumer_key", "value": "client-id"},
                {"label": "consumer_secret", "value": "sf-secret-42"},
                {"label": "login_url", "value": "https://test.salesforce.com"},
                {"label": "callback_url", "value": "http://127.0.0.1:1717/callback"},
                {"label": "connected_app_name", "value": "Rhumb CRM Proof"},
                {"label": "account", "value": "ops@example.com"},
            ]
        },
    ):
        args = mint_salesforce_refresh_token.build_parser().parse_args(
            [
                "--from-sop-item",
                "Rhumb - Salesforce OAuth",
                "--dry-run",
                "--token-json-out",
                "/tmp/salesforce-token.json",
                "--crm-ref",
                "sf_main",
                "--allow-object",
                "Account",
                "--allow-property",
                "Account:Name",
                "--record-id",
                "001ABC000000123XYZ",
            ]
        )
        plan = mint_salesforce_refresh_token._build_plan(args)

    assert plan["mode"] == "dry_run"
    assert plan["oauth_client"] == {
        "source": "1password",
        "from_sop_item": "Rhumb - Salesforce OAuth",
        "vault": "OpenClaw Agents",
        "connected_app": "Rhumb CRM Proof",
        "account": "ops@example.com",
        "client_id_length": 9,
        "client_secret_length": 12,
        "auth_base_url": "https://test.salesforce.com",
        "redirect_uri": "http://127.0.0.1:1717/callback",
        "scope": ["api", "refresh_token"],
    }
    assert plan["token_json_out"] == "/tmp/salesforce-token.json"
    assert plan["bundle_command"] is not None
    assert plan["proof_command"] is not None
    assert "sf-secret-42" not in json.dumps(plan)
