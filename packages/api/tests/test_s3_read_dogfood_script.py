"""Tests for the AWS S3 hosted proof script."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "s3_read_dogfood.py"

spec = importlib.util.spec_from_file_location("s3_read_dogfood", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
s3_read_dogfood = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = s3_read_dogfood
spec.loader.exec_module(s3_read_dogfood)


UNCONFIGURED_PREFLIGHT = {
    "configured": False,
    "available_for_execute": True,
    "resolve_handoff": {
        "source": "execute_hint",
        "preferred_provider": "aws-s3",
        "preferred_credential_mode": "byok",
        "selection_reason": "highest_ranked_provider",
        "setup_hint": "Set RHUMB_STORAGE_<REF> on the server",
        "credential_modes_url": "/v1/capabilities/object.list/credential-modes",
        "configured": False,
    },
    "resolve": {
        "status": 200,
        "json": {
            "data": {
                "providers": [
                    {
                        "service_slug": "aws-s3",
                        "available_for_execute": True,
                        "configured": False,
                    }
                ],
                "execute_hint": {
                    "preferred_provider": "aws-s3",
                    "preferred_credential_mode": "byok",
                    "selection_reason": "highest_ranked_provider",
                    "setup_hint": "Set RHUMB_STORAGE_<REF> on the server",
                    "credential_modes_url": "/v1/capabilities/object.list/credential-modes",
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
                        "service_slug": "aws-s3",
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
            "check": "object_list_resolve_surface",
            "ok": True,
            "status": 200,
            "error": None,
            "payload_check": None,
            "payload": {},
        },
        {
            "check": "object_list_credential_modes_surface",
            "ok": True,
            "status": 200,
            "error": None,
            "payload_check": None,
            "payload": {},
        },
        {
            "check": "storage_bundle_configured",
            "ok": False,
            "status": 200,
            "error": "storage_bundle_unconfigured",
            "payload_check": "configured_false",
            "payload": {
                "resolve_configured": False,
                "credential_mode_configured": False,
                "resolve_handoff": {
                    "source": "execute_hint",
                    "preferred_provider": "aws-s3",
                    "preferred_credential_mode": "byok",
                    "selection_reason": "highest_ranked_provider",
                    "setup_hint": "Set RHUMB_STORAGE_<REF> on the server",
                    "credential_modes_url": "/v1/capabilities/object.list/credential-modes",
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

    def fake_http_json(*args, **kwargs):  # type: ignore[no-untyped-def]
        return responses.pop(0)

    monkeypatch.setattr(s3_read_dogfood, "_http_json", fake_http_json)

    preflight = s3_read_dogfood._run_preflight(root="https://api.rhumb.dev", timeout=5.0)

    assert preflight["configured"] is False
    assert preflight["available_for_execute"] is True
    assert preflight["resolve_handoff"] == UNCONFIGURED_PREFLIGHT["resolve_handoff"]
    assert [item["check"] for item in preflight["results"]] == [
        "object_list_resolve_surface",
        "object_list_credential_modes_surface",
        "storage_bundle_configured",
    ]
    assert preflight["results"][2]["error"] == "storage_bundle_unconfigured"
    assert preflight["results"][2]["payload"]["resolve_handoff"] == UNCONFIGURED_PREFLIGHT["resolve_handoff"]


def test_main_preflight_only_summary_includes_resolve_step(monkeypatch, capsys) -> None:
    monkeypatch.setattr(s3_read_dogfood, "_run_preflight", lambda **_: UNCONFIGURED_PREFLIGHT)

    exit_code = s3_read_dogfood.main(["--preflight-only", "--summary-only"])

    assert exit_code == 1
    summary = capsys.readouterr().out.strip()
    assert "blocked_on=hosted_storage_ref_config" in summary
    assert (
        "resolve_step=Resolve next step: source=execute_hint, provider=aws-s3, mode=byok, "
        "credential_modes_url=/v1/capabilities/object.list/credential-modes"
    ) in summary


def test_main_writes_json_artifact_to_nested_path(monkeypatch, tmp_path, capsys) -> None:
    artifact_path = tmp_path / "nested" / "s3-read.json"
    monkeypatch.setattr(
        s3_read_dogfood,
        "run_flow",
        lambda args: {
            "ok": True,
            "summary": "object.list ok",
            "resolve_step": "Resolve next step: source=execute_hint, provider=aws-s3, mode=byok",
        },
    )

    exit_code = s3_read_dogfood.main(["--summary-only", "--json-out", str(artifact_path)])

    assert exit_code == 0
    payload = json.loads(artifact_path.read_text())
    assert payload == {
        "ok": True,
        "summary": "object.list ok",
        "resolve_step": "Resolve next step: source=execute_hint, provider=aws-s3, mode=byok",
    }
    assert capsys.readouterr().out.strip() == "object.list ok"
