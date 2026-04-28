#!/usr/bin/env python3
"""Run a bounded DC90 Firecrawl managed scrape.screenshot smoke.

The fixture screenshots https://example.com exactly once through Rhumb-managed
Firecrawl. Secrets are loaded from 1Password at runtime and are never written to
artifacts. The artifact stores only compact response shape, receipt, upstream
status, and hashed screenshot evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

BASE_URL = "https://api.rhumb.dev"
DEFAULT_TARGET_URL = "https://example.com"
VAULT = "OpenClaw Agents"
RHUMB_KEY_ITEMS = (
    "Rhumb API Key - pedro-dogfood",
    "Rhumb API Key - atlas@supertrained.ai",
)
CAPABILITY_ID = "scrape.screenshot"
PROVIDER = "firecrawl"
INTERFACE = "dc90-firecrawl-screenshot-smoke-20260428"


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sop_field(title: str, field: str = "credential") -> str | None:
    cp = subprocess.run(
        ["sop", "item", "get", title, "--vault", VAULT, "--fields", field, "--reveal"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=25,
        check=False,
    )
    if cp.returncode != 0:
        return None
    value = (cp.stdout or "").replace("\r", "").replace("\n", "").strip()
    return value or None


def request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: Any | None = None,
    timeout: float = 60.0,
) -> tuple[int, Any]:
    data = None
    merged_headers = {
        "Accept": "application/json",
        "User-Agent": "rhumb-dc90-firecrawl-screenshot-smoke/2026-04-28",
    }
    if headers:
        merged_headers.update(headers)
    if body is not None:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        merged_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=merged_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = int(getattr(resp, "status", 0) or 0)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = int(exc.code)
    except Exception as exc:  # pragma: no cover - network-only failure path
        return 0, {"transport_error": type(exc).__name__, "message": str(exc)}

    if not raw:
        return status, None
    try:
        return status, json.loads(raw.decode("utf-8"))
    except Exception:
        return status, {
            "non_json_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }


def rhumb_url(path: str) -> str:
    return f"{BASE_URL.rstrip('/')}{path}"


def rhumb_headers(api_key: str) -> dict[str, str]:
    return {"X-Rhumb-Key": api_key, "x-api-key": api_key}


def load_working_rhumb_key() -> tuple[str, str]:
    for title in RHUMB_KEY_ITEMS:
        key = sop_field(title)
        if not key:
            continue
        status, _ = request_json(
            "GET",
            rhumb_url("/v1/billing/balance"),
            headers=rhumb_headers(key),
            timeout=20,
        )
        if 200 <= status < 300:
            return title, key
    raise SystemExit("No working Rhumb dogfood governed key found in 1Password")


def data_dict(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def upstream_payload(payload: Any) -> Any:
    return data_dict(payload).get("upstream_response")


def find_screenshot_values(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in {"screenshot", "screenshoturl", "screenshot_url", "image", "imageurl", "image_url"} and isinstance(child, str) and child.strip():
                found.append(child.strip())
            else:
                found.extend(find_screenshot_values(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(find_screenshot_values(child))
    return found


def screenshot_evidence(value: Any) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for screenshot in find_screenshot_values(value):
        kind = "url" if screenshot.startswith(("http://", "https://")) else "data_or_inline"
        evidence.append(
            {
                "kind": kind,
                "length": len(screenshot),
                "sha256_16": hashlib.sha256(screenshot.encode("utf-8", errors="ignore")).hexdigest()[:16],
                "prefix": screenshot[:32],
            }
        )
    return evidence


def compact_step(name: str, status: int, payload: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"name": name, "http_status": status}
    if isinstance(payload, dict):
        out["top_level_keys"] = sorted(payload.keys())[:20]
        if payload.get("error") is not None:
            out["error"] = payload.get("error")
        for key in ("detail", "message", "resolution", "request_id"):
            if isinstance(payload.get(key), str):
                out[key] = payload[key]
        data = data_dict(payload)
        if data:
            out["data_keys"] = sorted(data.keys())[:30]
            for key in (
                "capability_id",
                "provider",
                "credential_mode",
                "provider_used",
                "receipt_id",
                "execution_id",
                "cost_estimate_usd",
                "budget_remaining_usd",
                "latency_ms",
                "upstream_status",
            ):
                if key in data:
                    out[key] = data[key]
        upstream = upstream_payload(payload)
        if isinstance(upstream, dict):
            out["upstream_keys"] = sorted(upstream.keys())[:30]
            nested_data = upstream.get("data") if isinstance(upstream.get("data"), dict) else None
            if nested_data:
                out["upstream_data_keys"] = sorted(nested_data.keys())[:30]
                title = nested_data.get("metadata", {}).get("title") if isinstance(nested_data.get("metadata"), dict) else None
                if isinstance(title, str):
                    out["page_title"] = title[:120]
            evidence = screenshot_evidence(upstream)
            if evidence:
                out["screenshot_evidence"] = evidence[:3]
        elif upstream is not None:
            out["upstream_summary"] = {
                "type": type(upstream).__name__,
                "sha256_16": hashlib.sha256(str(upstream).encode()).hexdigest()[:16],
            }
    elif payload is not None:
        out["payload_type"] = type(payload).__name__
    return out


def run_smoke(api_key: str, stamp: str, target_url: str) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    cap = urllib.parse.quote(CAPABILITY_ID, safe="")

    status, payload = request_json(
        "GET",
        rhumb_url(f"/v1/capabilities/{cap}/resolve?credential_mode=rhumb_managed"),
        headers=rhumb_headers(api_key),
        timeout=30,
    )
    steps.append(compact_step("resolve", status, payload))

    status, payload = request_json(
        "GET",
        rhumb_url(f"/v1/capabilities/{cap}/execute/estimate?provider={PROVIDER}&credential_mode=rhumb_managed"),
        headers=rhumb_headers(api_key),
        timeout=30,
    )
    steps.append(compact_step("estimate", status, payload))
    if not (200 <= status < 300):
        return {
            "capability_id": CAPABILITY_ID,
            "provider": PROVIDER,
            "target_url": target_url,
            "passed": False,
            "skipped_execute": "estimate_not_200",
            "steps": steps,
        }

    execute_body = {
        "provider": PROVIDER,
        "credential_mode": "rhumb_managed",
        "interface": INTERFACE,
        "idempotency_key": f"dc90-firecrawl-screenshot-{stamp.lower()}-{int(time.time() * 1000)}",
        "body": {
            "url": target_url,
            "formats": ["screenshot"],
            "onlyMainContent": True,
            "waitFor": 1000,
        },
    }
    status, payload = request_json(
        "POST",
        rhumb_url(f"/v1/capabilities/{cap}/execute"),
        headers=rhumb_headers(api_key),
        body=execute_body,
        timeout=120,
    )
    steps.append(compact_step("execute", status, payload))

    data = data_dict(payload)
    upstream = upstream_payload(payload)
    evidence = screenshot_evidence(upstream)
    passed = bool(
        status == 200
        and data.get("provider_used") == PROVIDER
        and data.get("receipt_id")
        and data.get("upstream_status") == 200
        and evidence
    )
    return {
        "capability_id": CAPABILITY_ID,
        "provider": PROVIDER,
        "target_url": target_url,
        "screenshot_evidence": evidence[:3],
        "passed": passed,
        "steps": steps,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run bounded DC90 Firecrawl scrape.screenshot managed smoke.")
    parser.add_argument("--target-url", default=DEFAULT_TARGET_URL, help="Public static page to screenshot")
    parser.add_argument("--output-dir", default="artifacts", help="Artifact directory (default: artifacts)")
    args = parser.parse_args()

    stamp = utc_stamp()
    key_title, api_key = load_working_rhumb_key()
    result = run_smoke(api_key, stamp, args.target_url)
    execute_step = next((step for step in result["steps"] if step.get("name") == "execute"), {})
    artifact = {
        "stamp": stamp,
        "base_url": BASE_URL,
        "rhumb_key_title": key_title,
        "secrets_redacted": True,
        "result": result,
        "summary": {
            "passed": result["passed"],
            "capability_id": CAPABILITY_ID,
            "provider": PROVIDER,
            "receipt_id": execute_step.get("receipt_id"),
            "upstream_status": execute_step.get("upstream_status"),
            "target_url": args.target_url,
            "screenshot_evidence": result.get("screenshot_evidence"),
        },
    }

    os.makedirs(args.output_dir, exist_ok=True)
    path = os.path.join(args.output_dir, f"dc90-firecrawl-screenshot-smoke-{stamp}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(artifact, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({"artifact": path, "summary": artifact["summary"]}, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
