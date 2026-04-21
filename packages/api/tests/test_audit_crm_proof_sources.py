"""Tests for the CRM proof-source audit helper."""

from __future__ import annotations

import importlib.util
import json
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


def test_salesforce_provider_declares_hosted_capability_id() -> None:
    provider = crm_proof_audit.PROVIDERS["salesforce"]

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
        "resolve_provider_present": True,
        "credential_modes_provider_present": True,
        "resolve_configured": False,
        "credential_modes_configured": False,
        "resolve_handoff": None,
        "errors": {
            "get": None,
            "resolve": None,
            "credential_modes": None,
        },
    }


def test_audit_hosted_surface_does_not_fall_back_to_another_provider() -> None:
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
                            "service_slug": "salesforce",
                            "configured": True,
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
                            "service_slug": "salesforce",
                            "modes": [
                                {
                                    "mode": "byok",
                                    "configured": True,
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

    assert hosted_surface["live"] is False
    assert hosted_surface["resolve_provider_present"] is False
    assert hosted_surface["credential_modes_provider_present"] is False
    assert hosted_surface["resolve_configured"] is False
    assert hosted_surface["credential_modes_configured"] is False


def test_audit_hosted_surface_carries_resolve_handoff() -> None:
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
                    ],
                    "recovery_hint": {
                        "reason": "no_execute_ready_providers",
                        "resolve_url": "/v1/capabilities/crm.record.search/resolve",
                        "setup_handoff": {
                            "preferred_provider": "hubspot",
                            "preferred_credential_mode": "byok",
                            "setup_url": "/v1/services/hubspot/ceremony",
                            "credential_modes_url": "/v1/capabilities/crm.record.search/credential-modes",
                            "configured": False,
                        },
                    },
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

    assert hosted_surface["resolve_handoff"] == {
        "source": "setup_handoff",
        "reason": "no_execute_ready_providers",
        "resolve_url": "/v1/capabilities/crm.record.search/resolve",
        "preferred_provider": "hubspot",
        "preferred_credential_mode": "byok",
        "setup_url": "/v1/services/hubspot/ceremony",
        "credential_modes_url": "/v1/capabilities/crm.record.search/credential-modes",
        "configured": False,
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


def test_summarize_provider_includes_resolve_handoff_summary_when_available() -> None:
    provider = crm_proof_audit.PROVIDERS["hubspot"]

    summary = crm_proof_audit.summarize_provider(
        provider,
        vault={"hit_count": 0, "bundle_ready_hit_count": 0},
        browser={"workspace_hosts": [], "portal_ids": []},
        browser_saved_logins={"hit_count": 0, "usernames": []},
        gmail={"hit_count": 0, "instances": [], "password_reset_hit_count": 0},
        hosted_surface={
            "supported": True,
            "live": True,
            "resolve_configured": False,
            "credential_modes_configured": False,
            "resolve_handoff": {
                "source": "setup_handoff",
                "preferred_provider": "hubspot",
                "preferred_credential_mode": "byok",
                "setup_url": "/v1/services/hubspot/ceremony",
                "resolve_url": "/v1/capabilities/crm.record.search/resolve",
            },
        },
    )

    assert summary["resolve_step"] == (
        "Resolve next step: source=setup_handoff, provider=hubspot, mode=byok, "
        "setup_url=/v1/services/hubspot/ceremony, resolve_url=/v1/capabilities/crm.record.search/resolve"
    )
    assert summary["resolve_handoff_summary"] == summary["resolve_step"]
    assert "Resolve next step: source=setup_handoff" in summary["assessment"]


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


def test_audit_vault_marks_salesforce_item_without_scope_fields_as_not_bundle_ready() -> None:
    provider = crm_proof_audit.PROVIDERS["salesforce"]
    list_payload = [
        {
            "id": "sf-item-123",
            "title": "Salesforce Connected App",
            "category": "API_CREDENTIAL",
            "urls": ["https://login.salesforce.com"],
            "tags": [],
        }
    ]
    item_payload = {
        "id": "sf-item-123",
        "fields": [
            {"label": "client_id", "value": "client-id"},
            {"label": "client_secret", "value": "client-secret"},
            {"label": "refresh_token", "value": "refresh-token"},
        ],
        "urls": ["https://login.salesforce.com"],
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


def test_audit_vault_marks_scoped_salesforce_item_as_bundle_ready() -> None:
    provider = crm_proof_audit.PROVIDERS["salesforce"]
    list_payload = [
        {
            "id": "sf-item-456",
            "title": "Salesforce CRM Read",
            "category": "API_CREDENTIAL",
            "urls": ["https://login.salesforce.com"],
            "tags": [],
        }
    ]
    item_payload = {
        "id": "sf-item-456",
        "fields": [
            {"label": "client_id", "value": "client-id"},
            {"label": "client_secret", "value": "client-secret"},
            {"label": "refresh_token", "value": "refresh-token"},
            {"label": "allowed_object_types", "value": "Account"},
            {"label": "allowed_properties_Account", "value": "Name, Website"},
        ],
        "urls": ["https://login.salesforce.com"],
    }

    with patch.object(crm_proof_audit, "_run_json", return_value=(list_payload, None)), patch.object(
        crm_proof_audit, "_load_vault_item", return_value=(item_payload, None)
    ):
        result = crm_proof_audit.audit_vault(provider, "OpenClaw Agents", 25)

    assert result["hit_count"] == 1
    assert result["bundle_ready_hit_count"] == 1
    assert result["hits"][0]["provider_signal"] is True
    assert result["hits"][0]["bundle_material_ready"] is True
    assert result["hits"][0]["missing_bundle_fields"] == []


def test_audit_vault_scan_all_items_finds_hidden_salesforce_bundle() -> None:
    provider = crm_proof_audit.PROVIDERS["salesforce"]
    list_payload = [
        {
            "id": "x-oauth-123",
            "title": "X API - pedrorhumb (OAuth 1.0a)",
            "category": "API_CREDENTIAL",
            "urls": [],
            "tags": [],
        },
        {
            "id": "generic-crm-456",
            "title": "CRM Read Bundle",
            "category": "API_CREDENTIAL",
            "urls": [],
            "tags": [],
        },
    ]
    detail_payloads = {
        "x-oauth-123": {
            "id": "x-oauth-123",
            "fields": [
                {"label": "consumer_key", "value": "x-client-id"},
                {"label": "consumer_secret", "value": "x-client-secret"},
            ],
            "urls": [],
        },
        "generic-crm-456": {
            "id": "generic-crm-456",
            "fields": [
                {"label": "client_id", "value": "client-id"},
                {"label": "client_secret", "value": "client-secret"},
                {"label": "refresh_token", "value": "refresh-token"},
                {"label": "allowed_object_types", "value": "Account"},
                {"label": "allowed_properties_Account", "value": "Name, Website"},
                {"label": "login_url", "value": "https://login.salesforce.com"},
            ],
            "urls": [],
        },
    }

    with patch.object(crm_proof_audit, "_run_json", return_value=(list_payload, None)), patch.object(
        crm_proof_audit,
        "_load_vault_item",
        side_effect=lambda item_id, vault: (detail_payloads[item_id], None),
    ):
        result = crm_proof_audit.audit_vault(provider, "OpenClaw Agents", 25, scan_all_items=True)

    assert result["items_scanned"] == 2
    assert result["scan_all_items"] is True
    assert result["hit_count"] == 1
    assert result["bundle_ready_hit_count"] == 1
    assert result["hits"][0]["title"] == "CRM Read Bundle"
    assert result["hits"][0]["provider_signal"] is True
    assert result["hits"][0]["bundle_material_ready"] is True


def test_audit_vault_scan_all_items_ignores_unrelated_oauth_items_without_salesforce_signal() -> None:
    provider = crm_proof_audit.PROVIDERS["salesforce"]
    list_payload = [
        {
            "id": "x-oauth-123",
            "title": "X API - pedrorhumb (OAuth 1.0a)",
            "category": "API_CREDENTIAL",
            "urls": [],
            "tags": [],
        }
    ]
    item_payload = {
        "id": "x-oauth-123",
        "fields": [
            {"label": "consumer_key", "value": "x-client-id"},
            {"label": "consumer_secret", "value": "x-client-secret"},
            {"label": "refresh_token", "value": "refresh-token"},
        ],
        "urls": [],
    }

    with patch.object(crm_proof_audit, "_run_json", return_value=(list_payload, None)), patch.object(
        crm_proof_audit, "_load_vault_item", return_value=(item_payload, None)
    ):
        result = crm_proof_audit.audit_vault(provider, "OpenClaw Agents", 25, scan_all_items=True)

    assert result["items_scanned"] == 1
    assert result["hit_count"] == 0
    assert result["bundle_ready_hit_count"] == 0
    assert result["hits"] == []


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


def test_summarize_provider_mentions_salesforce_connected_app_bundle_when_blocked() -> None:
    provider = crm_proof_audit.PROVIDERS["salesforce"]

    summary = crm_proof_audit.summarize_provider(
        provider,
        vault={"hit_count": 0, "bundle_ready_hit_count": 0},
        browser={"workspace_hosts": [], "portal_ids": []},
        browser_saved_logins={"hit_count": 0, "usernames": []},
        gmail={"hit_count": 0, "instances": [], "password_reset_hit_count": 0},
        hosted_surface={
            "supported": True,
            "live": True,
            "resolve_configured": False,
            "credential_modes_configured": False,
        },
    )

    assert summary["provider"] == "salesforce"
    assert summary["proof_material_ready"] is False
    assert summary["likely_blocked_on_credentials"] is True
    assert "no vault-backed scoped Salesforce bundle was detected" in summary["assessment"]
    assert "Connected App refresh-token bundle" in summary["assessment"]
    assert "no saved Salesforce login entry" in summary["assessment"]


def test_main_creates_parent_dirs_for_json_out(tmp_path, monkeypatch) -> None:
    artifact_path = tmp_path / "nested" / "crm-proof-source-audit.json"
    summary = {"provider": "hubspot", "assessment": "ready"}

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "audit_crm_proof_sources.py",
            "--provider",
            "hubspot",
            "--json-out",
            str(artifact_path),
        ],
    )

    with patch.object(crm_proof_audit, "audit_vault", return_value={"ok": True}), patch.object(
        crm_proof_audit, "audit_browser_history", return_value={"ok": True}
    ), patch.object(crm_proof_audit, "audit_browser_saved_logins", return_value={"ok": True}), patch.object(
        crm_proof_audit, "audit_gmail", return_value={"ok": True}
    ), patch.object(crm_proof_audit, "audit_hosted_surface", return_value={"ok": True}), patch.object(
        crm_proof_audit, "summarize_provider", return_value=summary
    ):
        exit_code = crm_proof_audit.main()

    assert exit_code == 0
    assert artifact_path.exists()
    payload = json.loads(artifact_path.read_text())
    assert payload["summary"] == [summary]
