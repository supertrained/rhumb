from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "launch_dashboard_snapshot.py"

spec = importlib.util.spec_from_file_location("launch_dashboard_snapshot", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
launch_dashboard_snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launch_dashboard_snapshot)


SAMPLE_PAYLOAD = {
    "data": {
        "readiness": {
            "status": "small_group_candidate",
            "headline": "Ready to bring the small-group recommendation to Tom.",
        },
        "launch_gates": {
            "small_group": {
                "status": "ready",
                "should_notify": True,
            },
            "public_launch": {
                "status": "blocked",
            },
        },
        "clicks": {
            "provider_clicks": 4,
            "provider_click_surfaces": [
                {"key": "service_page_hero", "count": 3},
                {"key": "service_page_sidebar", "count": 1},
            ],
            "service_page_cta_split": {
                "service_page_clicks": 4,
                "outside_service_page_clicks": 0,
                "hero": {"clicks": 3, "share": 0.75},
                "sidebar": {"clicks": 1, "share": 0.25},
                "legacy_service_page": {"clicks": 0, "share": 0.0},
                "other": {"clicks": 0, "share": 0.0},
            },
        },
        "funnel": {
            "stage_transitions": [
                {
                    "from_stage": "service_views",
                    "to_stage": "provider_clicks",
                    "from_count": 20,
                    "to_count": 4,
                    "conversion_rate": 0.2,
                }
            ]
        },
    },
    "error": None,
}


def test_extract_observation_summary_reads_launch_window_shape() -> None:
    summary = launch_dashboard_snapshot._extract_observation_summary(SAMPLE_PAYLOAD)

    assert summary == {
        "readiness_status": "small_group_candidate",
        "readiness_headline": "Ready to bring the small-group recommendation to Tom.",
        "small_group_gate_status": "ready",
        "small_group_should_notify": True,
        "public_launch_gate_status": "blocked",
        "provider_clicks": 4,
        "provider_click_surfaces": [
            {"key": "service_page_hero", "count": 3},
            {"key": "service_page_sidebar", "count": 1},
        ],
        "service_page_cta_split": {
            "service_page_clicks": 4,
            "outside_service_page_clicks": 0,
            "hero": {"clicks": 3, "share": 0.75},
            "sidebar": {"clicks": 1, "share": 0.25},
            "legacy_service_page": {"clicks": 0, "share": 0.0},
            "other": {"clicks": 0, "share": 0.0},
        },
        "service_views_to_provider_clicks": {
            "from_stage": "service_views",
            "to_stage": "provider_clicks",
            "from_count": 20,
            "to_count": 4,
            "conversion_rate": 0.2,
        },
    }


def test_main_writes_timestamped_and_latest_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    json_out = tmp_path / "dashboard.json"
    latest_out = tmp_path / "dashboard-latest.json"

    monkeypatch.setattr(
        launch_dashboard_snapshot,
        "_request_json",
        lambda **_: {"status": 200, "json": SAMPLE_PAYLOAD},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "launch_dashboard_snapshot.py",
            "--base-url",
            "https://api.rhumb.dev",
            "--window",
            "7d",
            "--admin-key",
            "secret",
            "--json-out",
            str(json_out),
            "--latest-out",
            str(latest_out),
        ],
    )

    assert launch_dashboard_snapshot.main() == 0
    stdout = capsys.readouterr().out
    assert "readiness=small_group_candidate" in stdout
    assert "small_group=ready" in stdout
    assert "provider_clicks=4" in stdout

    written = json.loads(json_out.read_text(encoding="utf-8"))
    latest = json.loads(latest_out.read_text(encoding="utf-8"))
    assert written["ok"] is True
    assert written["window"] == "7d"
    assert written["summary"]["small_group_gate_status"] == "ready"
    assert latest == written


def test_main_requires_admin_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RHUMB_ADMIN_SECRET", raising=False)
    monkeypatch.setattr(sys, "argv", ["launch_dashboard_snapshot.py"])

    with pytest.raises(SystemExit, match="Pass --admin-key or set RHUMB_ADMIN_SECRET"):
        launch_dashboard_snapshot.main()
