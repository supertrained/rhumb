"""Tests for the Vercel deployment hosted proof script."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "vercel_deployment_read_dogfood.py"

spec = importlib.util.spec_from_file_location("vercel_deployment_read_dogfood", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
vercel_deployment_read_dogfood = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vercel_deployment_read_dogfood)


UNCONFIGURED_PREFLIGHT = {
    "configured": False,
    "available_for_execute": True,
    "resolve_handoff": {
        "source": "execute_hint",
        "preferred_provider": "vercel",
        "preferred_credential_mode": "byok",
        "selection_reason": "highest_ranked_provider",
        "setup_hint": "Set RHUMB_DEPLOYMENT_<REF> on the server",
        "credential_modes_url": "/v1/capabilities/deployment.list/credential-modes",
        "configured": False,
    },
    "resolve": {
        "status": 200,
        "json": {
            "data": {
                "providers": [
                    {
                        "service_slug": "vercel",
                        "available_for_execute": True,
                        "configured": False,
                    }
                ],
                "execute_hint": {
                    "preferred_provider": "vercel",
                    "preferred_credential_mode": "byok",
                    "selection_reason": "highest_ranked_provider",
                    "setup_hint": "Set RHUMB_DEPLOYMENT_<REF> on the server",
                    "credential_modes_url": "/v1/capabilities/deployment.list/credential-modes",
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
                        "service_slug": "vercel",
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
            "check": "deployment_list_resolve_surface",
            "ok": True,
            "status": 200,
            "error": None,
            "payload_check": None,
            "payload": {},
        },
        {
            "check": "deployment_list_credential_modes_surface",
            "ok": True,
            "status": 200,
            "error": None,
            "payload_check": None,
            "payload": {},
        },
        {
            "check": "deployment_bundle_configured",
            "ok": False,
            "status": 200,
            "error": "deployment_bundle_unconfigured",
            "payload_check": "configured_false",
            "payload": {
                "resolve_configured": False,
                "credential_mode_configured": False,
                "resolve_handoff": {
                    "source": "execute_hint",
                    "preferred_provider": "vercel",
                    "preferred_credential_mode": "byok",
                    "selection_reason": "highest_ranked_provider",
                    "setup_hint": "Set RHUMB_DEPLOYMENT_<REF> on the server",
                    "credential_modes_url": "/v1/capabilities/deployment.list/credential-modes",
                    "configured": False,
                },
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

    monkeypatch.setattr(vercel_deployment_read_dogfood, "_request_json", fake_request_json)

    preflight = vercel_deployment_read_dogfood._run_preflight(root="https://api.rhumb.dev", timeout=5.0)

    assert preflight["configured"] is False
    assert preflight["available_for_execute"] is True
    assert preflight["resolve_handoff"] == UNCONFIGURED_PREFLIGHT["resolve_handoff"]
    assert [item["check"] for item in preflight["results"]] == [
        "deployment_list_resolve_surface",
        "deployment_list_credential_modes_surface",
        "deployment_bundle_configured",
    ]
    assert preflight["results"][2]["error"] == "deployment_bundle_unconfigured"
    assert preflight["results"][2]["payload"]["resolve_handoff"] == UNCONFIGURED_PREFLIGHT["resolve_handoff"]


def test_main_preflight_only_prints_resolve_step_summary(monkeypatch, tmp_path, capsys) -> None:
    artifact_path = tmp_path / "vercel-preflight.json"
    monkeypatch.setattr(vercel_deployment_read_dogfood, "_run_preflight", lambda **_: UNCONFIGURED_PREFLIGHT)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "vercel_deployment_read_dogfood.py",
            "--preflight-only",
            "--json-out",
            str(artifact_path),
        ],
    )

    exit_code = vercel_deployment_read_dogfood.main()

    assert exit_code == 1
    artifact = json.loads(artifact_path.read_text())
    assert artifact["mode"] == "preflight_only"
    assert artifact["preflight"]["resolve_handoff"] == UNCONFIGURED_PREFLIGHT["resolve_handoff"]
    assert artifact["resolve_step"] == (
        "Resolve next step: source=execute_hint, provider=vercel, mode=byok, "
        "next_url=/v1/capabilities/deployment.list/credential-modes"
    )
    stdout_lines = capsys.readouterr().out.splitlines()
    assert stdout_lines[0] == str(artifact_path)
    summary = json.loads("\n".join(stdout_lines[1:]))
    assert summary["resolve_step"] == (
        "Resolve next step: source=execute_hint, provider=vercel, mode=byok, "
        "next_url=/v1/capabilities/deployment.list/credential-modes"
    )


def test_main_full_proof_keeps_preflight_resolve_surfaces_in_artifact(monkeypatch, tmp_path, capsys) -> None:
    artifact_path = tmp_path / "vercel-full.json"
    configured_preflight = json.loads(json.dumps(UNCONFIGURED_PREFLIGHT))
    configured_preflight["configured"] = True
    configured_preflight["resolve_handoff"] = None
    configured_preflight["resolve"]["json"]["data"]["providers"][0]["configured"] = True
    configured_preflight["resolve"]["json"]["data"]["execute_hint"]["configured"] = True
    configured_preflight["credential_modes"]["json"]["data"]["providers"][0]["modes"][0]["configured"] = True
    configured_preflight["results"][2] = {
        "check": "deployment_bundle_configured",
        "ok": True,
        "status": 200,
        "error": None,
        "payload_check": None,
        "payload": {
            "resolve_configured": True,
            "credential_mode_configured": True,
            "resolve_handoff": None,
        },
    }
    monkeypatch.setattr(vercel_deployment_read_dogfood, "_run_preflight", lambda **_: configured_preflight)

    responses = [
        {
            "status": 200,
            "json": {"data": {"deployments": [{"project_id": vercel_deployment_read_dogfood.DEFAULT_ALLOWED_PROJECT_ID, "target": vercel_deployment_read_dogfood.DEFAULT_ALLOWED_TARGET}]}}
        },
        {
            "status": 200,
            "json": {"data": {"deployment_id": vercel_deployment_read_dogfood.DEFAULT_ALLOWED_DEPLOYMENT_ID, "project_id": vercel_deployment_read_dogfood.DEFAULT_ALLOWED_PROJECT_ID, "target": vercel_deployment_read_dogfood.DEFAULT_ALLOWED_TARGET}}
        },
        {"status": 400, "json": {"error": "deployment_ref_invalid"}},
        {"status": 403, "json": {"error": "deployment_scope_denied"}},
        {"status": 403, "json": {"error": "deployment_target_scope_denied"}},
    ]

    def fake_request_json(**_: object) -> dict[str, object]:
        return responses.pop(0)

    monkeypatch.setattr(vercel_deployment_read_dogfood, "_request_json", fake_request_json)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "vercel_deployment_read_dogfood.py",
            "--api-key",
            "test-key",
            "--json-out",
            str(artifact_path),
        ],
    )

    exit_code = vercel_deployment_read_dogfood.main()

    assert exit_code == 0
    artifact = json.loads(artifact_path.read_text())
    assert artifact["mode"] == "full_proof"
    assert artifact["preflight"]["resolve"] == configured_preflight["resolve"]
    assert artifact["preflight"]["credential_modes"] == configured_preflight["credential_modes"]
    stdout_lines = capsys.readouterr().out.splitlines()
    assert stdout_lines[0] == str(artifact_path)
