#!/usr/bin/env python3
"""Fetch and snapshot the internal launch dashboard for WU-T10 observation."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = ROOT / "artifacts"
DEFAULT_BASE_URL = "https://api.rhumb.dev"
DEFAULT_WINDOW = "7d"
DEFAULT_TIMEOUT = 30.0
SUPPORTED_WINDOWS = ("24h", "7d", "launch")


def _now_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _request_json(*, url: str, headers: dict[str, str], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return {
                "status": response.status,
                "json": json.loads(body) if body else None,
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return {"status": exc.code, "json": parsed}


def _extract_data(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    return data if isinstance(data, dict) else None


def _find_transition(
    transitions: Any,
    *,
    from_stage: str,
    to_stage: str,
) -> dict[str, Any] | None:
    if not isinstance(transitions, list):
        return None
    for row in transitions:
        if not isinstance(row, dict):
            continue
        if row.get("from_stage") == from_stage and row.get("to_stage") == to_stage:
            return row
    return None


def _extract_observation_summary(payload: Any) -> dict[str, Any]:
    data = _extract_data(payload) or {}
    readiness = data.get("readiness") if isinstance(data.get("readiness"), dict) else {}
    launch_gates = data.get("launch_gates") if isinstance(data.get("launch_gates"), dict) else {}
    clicks = data.get("clicks") if isinstance(data.get("clicks"), dict) else {}
    funnel = data.get("funnel") if isinstance(data.get("funnel"), dict) else {}

    small_group = launch_gates.get("small_group") if isinstance(launch_gates.get("small_group"), dict) else {}
    public_launch = launch_gates.get("public_launch") if isinstance(launch_gates.get("public_launch"), dict) else {}
    service_to_provider = _find_transition(
        funnel.get("stage_transitions"),
        from_stage="service_views",
        to_stage="provider_clicks",
    )

    return {
        "readiness_status": readiness.get("status"),
        "readiness_headline": readiness.get("headline"),
        "small_group_gate_status": small_group.get("status"),
        "small_group_should_notify": small_group.get("should_notify"),
        "public_launch_gate_status": public_launch.get("status"),
        "provider_clicks": clicks.get("provider_clicks"),
        "provider_click_surfaces": clicks.get("provider_click_surfaces"),
        "service_page_cta_split": clicks.get("service_page_cta_split"),
        "service_views_to_provider_clicks": service_to_provider,
    }


def _default_output_path(window: str) -> Path:
    return ARTIFACTS_DIR / f"wu-t10-launch-dashboard-{window}-{_now_slug()}.json"


def _default_latest_path(window: str) -> Path:
    return ARTIFACTS_DIR / f"wu-t10-launch-dashboard-{window}-latest.json"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--window", default=DEFAULT_WINDOW, choices=SUPPORTED_WINDOWS)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--admin-key")
    parser.add_argument("--json-out")
    parser.add_argument("--latest-out")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    admin_key = (args.admin_key or os.environ.get("RHUMB_ADMIN_SECRET") or "").strip()
    if not admin_key:
        raise SystemExit("Pass --admin-key or set RHUMB_ADMIN_SECRET")

    root = args.base_url.rstrip("/")
    url = f"{root}/v1/admin/launch/dashboard?window={urllib.parse.quote(args.window)}"
    response = _request_json(
        url=url,
        headers={"X-Rhumb-Admin-Key": admin_key},
        timeout=args.timeout,
    )
    payload = response.get("json")
    status = int(response.get("status") or 0)
    summary = _extract_observation_summary(payload)
    ok = status == 200 and isinstance(payload, dict) and payload.get("error") is None

    artifact = {
        "ok": ok,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "base_url": root,
        "window": args.window,
        "status": status,
        "summary": summary,
        "payload": payload,
    }

    json_out = Path(args.json_out) if args.json_out else _default_output_path(args.window)
    latest_out = Path(args.latest_out) if args.latest_out else _default_latest_path(args.window)
    _write_json(json_out, artifact)
    _write_json(latest_out, artifact)

    transition = summary.get("service_views_to_provider_clicks")
    conversion = None
    if isinstance(transition, dict):
        conversion = transition.get("conversion_rate")

    print(
        "launch_dashboard_snapshot"
        f" readiness={summary.get('readiness_status')}"
        f" small_group={summary.get('small_group_gate_status')}"
        f" public_launch={summary.get('public_launch_gate_status')}"
        f" provider_clicks={summary.get('provider_clicks')}"
        f" service_to_provider_conversion={conversion}"
        f" json={json_out}"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
