"""Tests for the support proof-source audit helper."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "audit_support_proof_sources.py"

spec = importlib.util.spec_from_file_location("audit_support_proof_sources", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
support_proof_audit = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = support_proof_audit
spec.loader.exec_module(support_proof_audit)


def test_intercom_provider_declares_hosted_capability_id() -> None:
    provider = support_proof_audit.PROVIDERS["intercom"]

    assert provider.hosted_capability_id == "conversation.list"


def test_audit_hosted_surface_marks_intercom_live_when_capability_endpoints_are_live() -> None:
    provider = support_proof_audit.PROVIDERS["intercom"]

    responses = [
        (
            200,
            {
                "data": {
                    "providers": [
                        {
                            "service_slug": "intercom",
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
                            "service_slug": "intercom",
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
                            "service_slug": "intercom",
                            "any_configured": False,
                        }
                    ]
                }
            },
            None,
        ),
    ]

    with patch.object(support_proof_audit, "_fetch_json_url", side_effect=responses):
        hosted_surface = support_proof_audit.audit_hosted_surface(provider, "https://api.rhumb.dev")

    assert hosted_surface == {
        "ok": True,
        "supported": True,
        "capability_id": "conversation.list",
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
    provider = support_proof_audit.PROVIDERS["intercom"]

    responses = [
        (
            200,
            {
                "data": {
                    "providers": [
                        {
                            "service_slug": "intercom",
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
                            "service_slug": "zendesk",
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
                            "service_slug": "zendesk",
                            "any_configured": True,
                        }
                    ]
                }
            },
            None,
        ),
    ]

    with patch.object(support_proof_audit, "_fetch_json_url", side_effect=responses):
        hosted_surface = support_proof_audit.audit_hosted_surface(provider, "https://api.rhumb.dev")

    assert hosted_surface["live"] is False
    assert hosted_surface["resolve_provider_present"] is False
    assert hosted_surface["credential_modes_provider_present"] is False
    assert hosted_surface["resolve_configured"] is False
    assert hosted_surface["credential_modes_configured"] is False


def test_audit_hosted_surface_carries_resolve_handoff() -> None:
    provider = support_proof_audit.PROVIDERS["intercom"]

    responses = [
        (
            200,
            {
                "data": {
                    "providers": [
                        {
                            "service_slug": "intercom",
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
                            "service_slug": "intercom",
                            "configured": False,
                        }
                    ],
                    "recovery_hint": {
                        "reason": "no_execute_ready_providers",
                        "resolve_url": "/v1/capabilities/conversation.list/resolve",
                        "setup_handoff": {
                            "preferred_provider": "intercom",
                            "preferred_credential_mode": "byok",
                            "setup_url": "/v1/services/intercom/ceremony",
                            "credential_modes_url": "/v1/capabilities/conversation.list/credential-modes",
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
                            "service_slug": "intercom",
                            "any_configured": False,
                        }
                    ]
                }
            },
            None,
        ),
    ]

    with patch.object(support_proof_audit, "_fetch_json_url", side_effect=responses):
        hosted_surface = support_proof_audit.audit_hosted_surface(provider, "https://api.rhumb.dev")

    assert hosted_surface["resolve_handoff"] == {
        "source": "setup_handoff",
        "reason": "no_execute_ready_providers",
        "resolve_url": "/v1/capabilities/conversation.list/resolve",
        "preferred_provider": "intercom",
        "preferred_credential_mode": "byok",
        "setup_url": "/v1/services/intercom/ceremony",
        "credential_modes_url": "/v1/capabilities/conversation.list/credential-modes",
        "configured": False,
    }


def test_summarize_provider_marks_intercom_blocked_on_credentials_when_hosted_surface_is_live() -> None:
    provider = support_proof_audit.PROVIDERS["intercom"]

    summary = support_proof_audit.summarize_provider(
        provider,
        vault={"hit_count": 0, "bundle_ready_hit_count": 0},
        browser={"workspace_hosts": []},
        gmail={"hit_count": 2, "instances": ["example-workspace"]},
        hosted_surface={
            "supported": True,
            "live": True,
            "resolve_configured": False,
            "credential_modes_configured": False,
        },
    )

    assert summary["provider"] == "intercom"
    assert summary["hosted_surface_live"] is True
    assert summary["hosted_surface_configured"] is False
    assert summary["vault_bundle_ready_hit_count"] == 0
    assert summary["proof_material_ready"] is False
    assert summary["likely_blocked_on_credentials"] is True
    assert "Hosted support surface is live" in summary["assessment"]
    assert "no vault-backed support credential bundle was detected" in summary["assessment"]


def test_summarize_provider_includes_resolve_handoff_summary_when_available() -> None:
    provider = support_proof_audit.PROVIDERS["intercom"]

    summary = support_proof_audit.summarize_provider(
        provider,
        vault={"hit_count": 0, "bundle_ready_hit_count": 0},
        browser={"workspace_hosts": []},
        gmail={"hit_count": 0, "instances": []},
        hosted_surface={
            "supported": True,
            "live": True,
            "resolve_configured": False,
            "credential_modes_configured": False,
            "resolve_handoff": {
                "source": "setup_handoff",
                "preferred_provider": "intercom",
                "preferred_credential_mode": "byok",
                "setup_url": "/v1/services/intercom/ceremony",
                "resolve_url": "/v1/capabilities/conversation.list/resolve",
            },
        },
    )

    assert summary["resolve_step"] == (
        "Resolve next step: source=setup_handoff, provider=intercom, mode=byok, "
        "setup_url=/v1/services/intercom/ceremony, resolve_url=/v1/capabilities/conversation.list/resolve"
    )
    assert summary["resolve_handoff_summary"] == summary["resolve_step"]
    assert "Resolve next step: source=setup_handoff" in summary["assessment"]


def test_summarize_provider_keeps_intercom_blocked_when_only_login_item_exists() -> None:
    provider = support_proof_audit.PROVIDERS["intercom"]

    summary = support_proof_audit.summarize_provider(
        provider,
        vault={"hit_count": 1, "bundle_ready_hit_count": 0},
        browser={"workspace_hosts": []},
        gmail={"hit_count": 0, "instances": []},
        hosted_surface={
            "supported": True,
            "live": True,
            "resolve_configured": False,
            "credential_modes_configured": False,
        },
    )

    assert summary["vault_hit_count"] == 1
    assert summary["vault_bundle_ready_hit_count"] == 0
    assert summary["proof_material_ready"] is False
    assert summary["likely_blocked_on_credentials"] is True
    assert "candidate vault items now exist" in summary["assessment"]


def test_audit_vault_marks_login_only_intercom_item_as_not_bundle_ready() -> None:
    provider = support_proof_audit.PROVIDERS["intercom"]
    list_payload = [
        {
            "id": "item123",
            "title": "Intercom - Rhumb AUD-18 Admin Login",
            "category": "LOGIN",
            "urls": ["https://app.intercom.com"],
            "tags": [],
        }
    ]
    item_payload = {
        "id": "item123",
        "fields": [
            {"label": "username", "value": "team@getsupertrained.com"},
            {"label": "password", "value": "secret"},
        ],
        "urls": ["https://app.intercom.com"],
    }

    with patch.object(support_proof_audit, "_run_json", return_value=(list_payload, None)), patch.object(
        support_proof_audit, "_load_vault_item", return_value=(item_payload, None)
    ):
        result = support_proof_audit.audit_vault(provider, "OpenClaw Agents", 25)

    assert result["hit_count"] == 1
    assert result["bundle_ready_hit_count"] == 0
    assert result["hits"][0]["bundle_material_ready"] is False
    assert result["hits"][0]["missing_bundle_fields"] == [
        "region",
        "allowed_team_ids_or_allowed_admin_ids",
    ]


def test_main_creates_parent_dirs_for_json_out(tmp_path, monkeypatch) -> None:
    artifact_path = tmp_path / "nested" / "support-proof-source-audit.json"
    summary = {"provider": "intercom", "assessment": "ready"}

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "audit_support_proof_sources.py",
            "--provider",
            "intercom",
            "--json-out",
            str(artifact_path),
        ],
    )

    with patch.object(support_proof_audit, "audit_vault", return_value={"ok": True}), patch.object(
        support_proof_audit, "audit_browser_history", return_value={"ok": True}
    ), patch.object(support_proof_audit, "audit_gmail", return_value={"ok": True}), patch.object(
        support_proof_audit, "audit_hosted_surface", return_value={"ok": True}
    ), patch.object(support_proof_audit, "summarize_provider", return_value=summary):
        exit_code = support_proof_audit.main()

    assert exit_code == 0
    assert artifact_path.exists()
    payload = json.loads(artifact_path.read_text())
    assert payload["summary"] == [summary]
