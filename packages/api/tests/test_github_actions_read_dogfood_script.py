"""Tests for the GitHub Actions hosted proof script."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "github_actions_read_dogfood.py"

spec = importlib.util.spec_from_file_location("github_actions_read_dogfood", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
github_actions_read_dogfood = importlib.util.module_from_spec(spec)
spec.loader.exec_module(github_actions_read_dogfood)


UNCONFIGURED_PREFLIGHT = {
    "configured": False,
    "available_for_execute": True,
    "resolve_handoff": {
        "source": "execute_hint",
        "preferred_provider": "github",
        "preferred_credential_mode": "byok",
        "selection_reason": "highest_ranked_provider",
        "setup_hint": "Set RHUMB_ACTIONS_<REF> on the server",
        "credential_modes_url": "/v1/capabilities/workflow_run.list/credential-modes",
        "configured": False,
    },
    "resolve": {
        "status": 200,
        "json": {
            "data": {
                "providers": [
                    {
                        "service_slug": "github",
                        "available_for_execute": True,
                        "configured": False,
                    }
                ],
                "execute_hint": {
                    "preferred_provider": "github",
                    "preferred_credential_mode": "byok",
                    "selection_reason": "highest_ranked_provider",
                    "setup_hint": "Set RHUMB_ACTIONS_<REF> on the server",
                    "credential_modes_url": "/v1/capabilities/workflow_run.list/credential-modes",
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
                        "service_slug": "github",
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
            "check": "workflow_run_list_resolve_surface",
            "ok": True,
            "status": 200,
            "error": None,
            "payload_check": None,
            "payload": {},
        },
        {
            "check": "workflow_run_list_credential_modes_surface",
            "ok": True,
            "status": 200,
            "error": None,
            "payload_check": None,
            "payload": {},
        },
        {
            "check": "actions_bundle_configured",
            "ok": False,
            "status": 200,
            "error": "actions_bundle_unconfigured",
            "payload_check": "configured_false",
            "payload": {
                "resolve_configured": False,
                "credential_mode_configured": False,
                "resolve_handoff": {
                    "source": "execute_hint",
                    "preferred_provider": "github",
                    "preferred_credential_mode": "byok",
                    "selection_reason": "highest_ranked_provider",
                    "setup_hint": "Set RHUMB_ACTIONS_<REF> on the server",
                    "credential_modes_url": "/v1/capabilities/workflow_run.list/credential-modes",
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

    monkeypatch.setattr(github_actions_read_dogfood, "_request_json", fake_request_json)

    preflight = github_actions_read_dogfood._run_preflight(root="https://api.rhumb.dev", timeout=5.0)

    assert preflight["configured"] is False
    assert preflight["available_for_execute"] is True
    assert preflight["resolve_handoff"] == UNCONFIGURED_PREFLIGHT["resolve_handoff"]
    assert [item["check"] for item in preflight["results"]] == [
        "workflow_run_list_resolve_surface",
        "workflow_run_list_credential_modes_surface",
        "actions_bundle_configured",
    ]
    assert preflight["results"][2]["error"] == "actions_bundle_unconfigured"
    assert preflight["results"][2]["payload"]["resolve_handoff"] == UNCONFIGURED_PREFLIGHT["resolve_handoff"]


def test_main_preflight_only_prints_resolve_step_summary(monkeypatch, tmp_path, capsys) -> None:
    artifact_path = tmp_path / "github-actions-preflight.json"
    monkeypatch.setattr(github_actions_read_dogfood, "_run_preflight", lambda **_: UNCONFIGURED_PREFLIGHT)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "github_actions_read_dogfood.py",
            "--preflight-only",
            "--json-out",
            str(artifact_path),
        ],
    )

    exit_code = github_actions_read_dogfood.main()

    assert exit_code == 1
    artifact = json.loads(artifact_path.read_text())
    assert artifact["mode"] == "preflight_only"
    assert artifact["preflight"]["resolve_handoff"] == UNCONFIGURED_PREFLIGHT["resolve_handoff"]
    stdout_lines = capsys.readouterr().out.splitlines()
    assert stdout_lines[0] == str(artifact_path)
    summary = json.loads("\n".join(stdout_lines[1:]))
    assert summary["resolve_step"] == (
        "Resolve next step: source=execute_hint, provider=github, mode=byok, "
        "next_url=/v1/capabilities/workflow_run.list/credential-modes"
    )
