"""Tests for the HubSpot CRM hosted proof script."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "hubspot_crm_read_dogfood.py"

spec = importlib.util.spec_from_file_location("hubspot_crm_read_dogfood", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
hubspot_crm_read_dogfood = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hubspot_crm_read_dogfood)


UNCONFIGURED_PREFLIGHT = {
    "configured": False,
    "available_for_execute": True,
    "resolve": {
        "status": 200,
        "json": {
            "data": {
                "providers": [
                    {
                        "service_slug": "hubspot",
                        "available_for_execute": True,
                        "configured": False,
                    }
                ]
            }
        },
    },
    "credential_modes": {
        "status": 200,
        "json": {
            "data": {
                "providers": [
                    {
                        "service_slug": "hubspot",
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

    monkeypatch.setattr(hubspot_crm_read_dogfood, "_request_json", fake_request_json)

    preflight = hubspot_crm_read_dogfood._run_preflight(root="https://api.rhumb.dev", timeout=5.0)

    assert preflight["configured"] is False
    assert preflight["available_for_execute"] is True
    assert [item["check"] for item in preflight["results"]] == [
        "crm_record_search_resolve_surface",
        "crm_record_search_credential_modes_surface",
        "crm_bundle_configured",
    ]
    assert preflight["results"][0]["ok"] is True
    assert preflight["results"][1]["ok"] is True
    assert preflight["results"][2]["ok"] is False
    assert preflight["results"][2]["error"] == "crm_bundle_unconfigured"


def test_main_preflight_only_writes_blocker_artifact_without_record_id(monkeypatch, tmp_path) -> None:
    artifact_path = tmp_path / "hubspot-preflight.json"
    monkeypatch.setattr(hubspot_crm_read_dogfood, "_run_preflight", lambda **_: UNCONFIGURED_PREFLIGHT)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "hubspot_crm_read_dogfood.py",
            "--preflight-only",
            "--json-out",
            str(artifact_path),
        ],
    )

    exit_code = hubspot_crm_read_dogfood.main()

    assert exit_code == 1
    artifact = json.loads(artifact_path.read_text())
    assert artifact["mode"] == "preflight_only"
    assert artifact["record_id"] is None
    assert artifact["preflight"]["configured"] is False
    assert artifact["results"][2]["error"] == "crm_bundle_unconfigured"


def test_main_requires_record_id_without_preflight(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["hubspot_crm_read_dogfood.py"])

    try:
        hubspot_crm_read_dogfood.main()
    except SystemExit as exc:
        assert exc.code == 2
    else:  # pragma: no cover
        raise AssertionError("Expected parser error when --record-id is omitted without --preflight-only")
