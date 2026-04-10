"""Tests for the CRM proof-source audit helper."""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "audit_crm_proof_sources.py"

spec = importlib.util.spec_from_file_location("audit_crm_proof_sources", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
crm_proof_audit = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = crm_proof_audit
spec.loader.exec_module(crm_proof_audit)


def test_hubspot_provider_declares_hosted_capability_id() -> None:
    provider = crm_proof_audit.PROVIDERS["hubspot"]

    assert provider.hosted_capability_id == "crm.record.search"


def test_audit_hosted_surface_marks_hubspot_live_when_capability_endpoints_are_live() -> None:
    provider = crm_proof_audit.PROVIDERS["hubspot"]

    responses = [
        (
            200,
            {
                "data": {
                    "providers": [
                        {
                            "service_slug": "hubspot",
                        }
                    ]
                }
            },
            None,
        ),
        (
            200,
            {
                "data": {
                    "providers": [
                        {
                            "service_slug": "hubspot",
                            "configured": False,
                        }
                    ]
                }
            },
            None,
        ),
        (
            200,
            {
                "data": {
                    "providers": [
                        {
                            "service_slug": "hubspot",
                            "modes": [
                                {
                                    "mode": "byok",
                                    "configured": False,
                                }
                            ],
                        }
                    ]
                }
            },
            None,
        ),
    ]

    with patch.object(crm_proof_audit, "_fetch_json_url", side_effect=responses):
        hosted_surface = crm_proof_audit.audit_hosted_surface(provider, "https://api.rhumb.dev")

    assert hosted_surface == {
        "ok": True,
        "supported": True,
        "capability_id": "crm.record.search",
        "get_status": 200,
        "resolve_status": 200,
        "credential_modes_status": 200,
        "live": True,
        "resolve_configured": False,
        "credential_modes_configured": False,
        "errors": {
            "get": None,
            "resolve": None,
            "credential_modes": None,
        },
    }


def test_summarize_provider_mentions_password_reset_path_when_mail_exists() -> None:
    provider = crm_proof_audit.PROVIDERS["hubspot"]

    summary = crm_proof_audit.summarize_provider(
        provider,
        vault={"hit_count": 0, "bundle_ready_hit_count": 0},
        browser={"workspace_hosts": [], "portal_ids": ["49739435"]},
        browser_saved_logins={"hit_count": 0, "usernames": []},
        gmail={"hit_count": 2, "instances": [], "password_reset_hit_count": 1},
        hosted_surface={
            "supported": True,
            "live": True,
            "resolve_configured": False,
            "credential_modes_configured": False,
        },
    )

    assert summary["provider"] == "hubspot"
    assert summary["hosted_surface_live"] is True
    assert summary["hosted_surface_configured"] is False
    assert summary["password_reset_hit_count"] == 1
    assert summary["browser_saved_login_hit_count"] == 0
    assert summary["proof_material_ready"] is False
    assert summary["likely_blocked_on_credentials"] is True
    assert "password-reset mail is reaching the known mailbox" in summary["assessment"]
    assert "no saved HubSpot login entry" in summary["assessment"]


def test_audit_vault_marks_login_only_hubspot_item_as_not_bundle_ready() -> None:
    provider = crm_proof_audit.PROVIDERS["hubspot"]
    list_payload = [
        {
            "id": "item123",
            "title": "HubSpot - Supertrained Login",
            "category": "LOGIN",
            "urls": ["https://app.hubspot.com"],
            "tags": [],
        }
    ]
    item_payload = {
        "id": "item123",
        "fields": [
            {"label": "username", "value": "tommeredith@supertrained.ai"},
            {"label": "password", "value": "secret"},
        ],
        "urls": ["https://app.hubspot.com"],
    }

    with patch.object(crm_proof_audit, "_run_json", return_value=(list_payload, None)), patch.object(
        crm_proof_audit, "_load_vault_item", return_value=(item_payload, None)
    ):
        result = crm_proof_audit.audit_vault(provider, "OpenClaw Agents", 25)

    assert result["hit_count"] == 1
    assert result["bundle_ready_hit_count"] == 0
    assert result["hits"][0]["bundle_material_ready"] is False
    assert result["hits"][0]["missing_bundle_fields"] == [
        "allowed_object_types",
        "allowed_properties_by_object",
    ]


def test_audit_browser_saved_logins_reports_matching_hubspot_entries(tmp_path: Path) -> None:
    provider = crm_proof_audit.PROVIDERS["hubspot"]
    login_db = tmp_path / "Login Data"
    conn = sqlite3.connect(login_db)
    try:
        conn.execute(
            "CREATE TABLE logins (origin_url TEXT, action_url TEXT, username_value TEXT, date_created INTEGER)"
        )
        conn.execute(
            "INSERT INTO logins VALUES (?, ?, ?, ?)",
            ("https://app.hubspot.com/login", "", "tommeredith@supertrained.ai", 123456),
        )
        conn.execute(
            "INSERT INTO logins VALUES (?, ?, ?, ?)",
            ("https://x.com/i/flow/login", "", "tommeredith@supertrained.ai", 123455),
        )
        conn.commit()
    finally:
        conn.close()

    result = crm_proof_audit.audit_browser_saved_logins(provider, login_db, 25)

    assert result["ok"] is True
    assert result["hit_count"] == 1
    assert result["hosts"] == ["app.hubspot.com"]
    assert result["usernames"] == ["tommeredith@supertrained.ai"]
    assert result["hits"][0]["host"] == "app.hubspot.com"
