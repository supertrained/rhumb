"""Tests for the BigQuery warehouse hosted proof script."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "bigquery_warehouse_read_dogfood.py"

spec = importlib.util.spec_from_file_location("bigquery_warehouse_read_dogfood", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
bigquery_warehouse_read_dogfood = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bigquery_warehouse_read_dogfood)


UNCONFIGURED_PREFLIGHT = {
    "configured": False,
    "available_for_execute": True,
    "resolve": {
        "status": 200,
        "json": {
            "data": {
                "providers": [
                    {
                        "service_slug": "bigquery",
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
                        "service_slug": "bigquery",
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
            "check": "warehouse_query_read_resolve_surface",
            "ok": True,
            "status": 200,
            "error": None,
            "payload_check": None,
            "payload": {},
        },
        {
            "check": "warehouse_query_read_credential_modes_surface",
            "ok": True,
            "status": 200,
            "error": None,
            "payload_check": None,
            "payload": {},
        },
        {
            "check": "warehouse_bundle_configured",
            "ok": False,
            "status": 200,
            "error": "warehouse_bundle_unconfigured",
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

    monkeypatch.setattr(bigquery_warehouse_read_dogfood, "_request_json", fake_request_json)

    preflight = bigquery_warehouse_read_dogfood._run_preflight(root="https://api.rhumb.dev", timeout=5.0)

    assert preflight["configured"] is False
    assert preflight["available_for_execute"] is True
    assert [item["check"] for item in preflight["results"]] == [
        "warehouse_query_read_resolve_surface",
        "warehouse_query_read_credential_modes_surface",
        "warehouse_bundle_configured",
    ]
    assert preflight["results"][2]["error"] == "warehouse_bundle_unconfigured"


def test_main_preflight_only_writes_blocker_artifact_without_query(monkeypatch, tmp_path) -> None:
    artifact_path = tmp_path / "warehouse-preflight.json"
    monkeypatch.setattr(bigquery_warehouse_read_dogfood, "_run_preflight", lambda **_: UNCONFIGURED_PREFLIGHT)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bigquery_warehouse_read_dogfood.py",
            "--preflight-only",
            "--json-out",
            str(artifact_path),
        ],
    )

    exit_code = bigquery_warehouse_read_dogfood.main()

    assert exit_code == 1
    artifact = json.loads(artifact_path.read_text())
    assert artifact["mode"] == "preflight_only"
    assert artifact["query"] is None
    assert artifact["preflight"]["configured"] is False
    assert artifact["results"][2]["error"] == "warehouse_bundle_unconfigured"


def test_main_requires_query_without_preflight(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["bigquery_warehouse_read_dogfood.py"])

    with pytest.raises(SystemExit) as excinfo:
        bigquery_warehouse_read_dogfood.main()

    assert excinfo.value.code == 2


def test_direct_query_parameter_state_supports_named_and_positional_params() -> None:
    mode, payload = bigquery_warehouse_read_dogfood._direct_query_parameter_state(
        {"user_id": 42, "flags": ["a", "b"]}
    )

    assert mode == "NAMED"
    assert payload == [
        {
            "name": "user_id",
            "parameterType": {"type": "INT64"},
            "parameterValue": {"value": 42},
        },
        {
            "name": "flags",
            "parameterType": {"type": "ARRAY", "arrayType": {"type": "STRING"}},
            "parameterValue": {"arrayValues": [{"value": "a"}, {"value": "b"}]},
        },
    ]

    positional_mode, positional_payload = bigquery_warehouse_read_dogfood._direct_query_parameter_state([True, 7])
    assert positional_mode == "POSITIONAL"
    assert positional_payload == [
        {
            "parameterType": {"type": "BOOL"},
            "parameterValue": {"value": True},
        },
        {
            "parameterType": {"type": "INT64"},
            "parameterValue": {"value": 7},
        },
    ]


def test_compare_query_parity_normalizes_bigquery_rest_scalars() -> None:
    hosted_payload = {
        "data": {
            "columns": [
                {"name": "user_id", "type": "INT64", "mode": "NULLABLE"},
                {"name": "active", "type": "BOOL", "mode": "NULLABLE"},
            ],
            "rows": [
                {"user_id": 42, "active": True},
            ],
        }
    }
    direct_payload = {
        "columns": [
            {"name": "user_id", "type": "INT64", "mode": "NULLABLE"},
            {"name": "active", "type": "BOOL", "mode": "NULLABLE"},
        ],
        "rows": [
            {"user_id": "42", "active": "true"},
        ],
    }

    ok, note = bigquery_warehouse_read_dogfood._compare_query_parity(hosted_payload, direct_payload)

    assert ok is True
    assert note is None
