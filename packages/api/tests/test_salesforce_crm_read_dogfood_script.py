"""Tests for the Salesforce CRM hosted proof script."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "salesforce_crm_read_dogfood.py"

spec = importlib.util.spec_from_file_location("salesforce_crm_read_dogfood", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
salesforce_crm_read_dogfood = importlib.util.module_from_spec(spec)
spec.loader.exec_module(salesforce_crm_read_dogfood)


UNCONFIGURED_PREFLIGHT = {
    "configured": False,
    "available_for_execute": True,
    "resolve_handoff": {
        "source": "execute_hint",
        "preferred_provider": "salesforce",
        "preferred_credential_mode": "byok",
        "selection_reason": "highest_ranked_provider",
        "setup_hint": "Set RHUMB_CRM_<REF> on the server",
        "credential_modes_url": "/v1/capabilities/crm.record.search/credential-modes",
        "configured": False,
    },
    "resolve": {
        "status": 200,
        "json": {
            "data": {
                "providers": [
                    {
                        "service_slug": "salesforce",
                        "available_for_execute": True,
                        "configured": False,
                    }
                ],
                "execute_hint": {
                    "preferred_provider": "salesforce",
                    "preferred_credential_mode": "byok",
                    "selection_reason": "highest_ranked_provider",
                    "setup_hint": "Set RHUMB_CRM_<REF> on the server",
                    "credential_modes_url": "/v1/capabilities/crm.record.search/credential-modes",
                    "configured": False,
                },
            }
        },
    },
    "credential_modes": {
        "status": 200,
        "json": {
            "data": {
                "providers": [
                    {
                        "service_slug": "salesforce",
                        "modes": [
                            {
                                "mode": "byok",
                                "available": True,
                                "configured": False,
                            }
                        ],
                    }
                ]
            }
        },
    },
    "results": [
        {
            "check": "crm_record_search_resolve_surface",
            "ok": True,
            "status": 200,
            "error": None,
            "payload_check": None,
            "payload": {},
        },
        {
            "check": "crm_record_search_credential_modes_surface",
            "ok": True,
            "status": 200,
            "error": None,
            "payload_check": None,
            "payload": {},
        },
        {
            "check": "crm_bundle_configured",
            "ok": False,
            "status": 200,
            "error": "crm_bundle_unconfigured",
            "payload_check": "configured_false",
            "payload": {
                "resolve_configured": False,
                "credential_mode_configured": False,
            },
        },
    ],
}


def test_run_preflight_reports_unconfigured_bundle_when_surfaces_are_live(monkeypatch) -> None:
    responses = [
        UNCONFIGURED_PREFLIGHT["resolve"],
        UNCONFIGURED_PREFLIGHT["credential_modes"],
    ]

    def fake_request_json(**_: object) -> dict[str, object]:
        return responses.pop(0)

    monkeypatch.setattr(salesforce_crm_read_dogfood, "_request_json", fake_request_json)

    preflight = salesforce_crm_read_dogfood._run_preflight(root="https://api.rhumb.dev", timeout=5.0)

    assert preflight["configured"] is False
    assert preflight["available_for_execute"] is True
    assert preflight["resolve_handoff"] == UNCONFIGURED_PREFLIGHT["resolve_handoff"]
    assert [item["check"] for item in preflight["results"]] == [
        "crm_record_search_resolve_surface",
        "crm_record_search_credential_modes_surface",
        "crm_bundle_configured",
    ]
    assert preflight["results"][0]["ok"] is True
    assert preflight["results"][1]["ok"] is True
    assert preflight["results"][2]["ok"] is False
    assert preflight["results"][2]["error"] == "crm_bundle_unconfigured"
    assert preflight["results"][2]["payload"]["resolve_handoff"] == UNCONFIGURED_PREFLIGHT["resolve_handoff"]


def test_run_preflight_accepts_execute_handoff_when_provider_not_execute_ready(monkeypatch) -> None:
    resolve_response = json.loads(json.dumps(UNCONFIGURED_PREFLIGHT["resolve"]))
    resolve_response["json"]["data"]["providers"][0]["available_for_execute"] = False
    responses = [
        resolve_response,
        UNCONFIGURED_PREFLIGHT["credential_modes"],
    ]

    def fake_request_json(**_: object) -> dict[str, object]:
        return responses.pop(0)

    monkeypatch.setattr(salesforce_crm_read_dogfood, "_request_json", fake_request_json)

    preflight = salesforce_crm_read_dogfood._run_preflight(root="https://api.rhumb.dev", timeout=5.0)

    assert preflight["available_for_execute"] is False
    assert preflight["resolve_handoff"] == UNCONFIGURED_PREFLIGHT["resolve_handoff"]
    assert preflight["results"][0]["ok"] is True
    assert preflight["results"][0]["payload_check"] is None


def test_main_preflight_only_writes_blocker_artifact_without_record_id(monkeypatch, tmp_path) -> None:
    artifact_path = tmp_path / "salesforce-preflight.json"
    monkeypatch.setattr(salesforce_crm_read_dogfood, "_run_preflight", lambda **_: UNCONFIGURED_PREFLIGHT)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "salesforce_crm_read_dogfood.py",
            "--preflight-only",
            "--json-out",
            str(artifact_path),
        ],
    )

    exit_code = salesforce_crm_read_dogfood.main()

    assert exit_code == 1
    artifact = json.loads(artifact_path.read_text())
    assert artifact["mode"] == "preflight_only"
    assert artifact["record_id"] is None
    assert artifact["preflight"]["configured"] is False
    assert artifact["preflight"]["resolve_handoff"] == UNCONFIGURED_PREFLIGHT["resolve_handoff"]
    assert artifact["results"][2]["error"] == "crm_bundle_unconfigured"


def test_main_requires_record_id_without_preflight(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["salesforce_crm_read_dogfood.py"])

    try:
        salesforce_crm_read_dogfood.main()
    except SystemExit as exc:
        assert exc.code == 2
    else:  # pragma: no cover
        raise AssertionError("Expected parser error when --record-id is omitted without --preflight-only")
