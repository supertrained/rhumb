#!/usr/bin/env python3
"""Run the bounded DC90 E2B managed lifecycle smoke.

Creates exactly one short-lived E2B sandbox through Rhumb-managed execution,
checks its status once through Rhumb-managed execution, then deletes it directly
with the E2B API key in a cleanup path. Secrets are loaded from 1Password at
runtime and are never written to artifacts.
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
E2B_BASE_URL = "https://api.e2b.app"
VAULT = "OpenClaw Agents"
RHUMB_KEY_ITEMS = (
    "Rhumb API Key - pedro-dogfood",
    "Rhumb API Key - atlas@supertrained.ai",
)
E2B_KEY_ITEM = "E2B API Key"
CREATE_CAPABILITY_ID = "agent.spawn"
STATUS_CAPABILITY_ID = "agent.get_status"
INTERFACE = "dc90-e2b-lifecycle-smoke-20260428"
SANDBOX_TIMEOUT_SECONDS = 10
CLEANUP_VERIFY_DEADLINE_SECONDS = 75


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
        "User-Agent": "rhumb-dc90-e2b-lifecycle-smoke/2026-04-28",
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
    except Exception as exc:
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


def e2b_headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


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


def cap_path(capability_id: str) -> str:
    return urllib.parse.quote(capability_id, safe="")


def data_dict(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def upstream_dict(payload: Any) -> dict[str, Any]:
    upstream = data_dict(payload).get("upstream_response")
    return upstream if isinstance(upstream, dict) else {}


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
        upstream = upstream_dict(payload)
        if upstream:
            out["upstream_keys"] = sorted(upstream.keys())[:30]
            for key in (
                "sandboxID",
                "templateID",
                "alias",
                "state",
                "envdVersion",
                "cpuCount",
                "memoryMB",
            ):
                if key in upstream:
                    out[f"upstream_{key}"] = upstream[key]
    elif payload is not None:
        out["payload_type"] = type(payload).__name__
    return out


def run_lifecycle(rhumb_key: str, e2b_key: str, stamp: str) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    cleanup: list[dict[str, Any]] = []
    sandbox_id: str | None = None
    cleanup_verdict = "not_started"

    create_cap = cap_path(CREATE_CAPABILITY_ID)
    status_cap = cap_path(STATUS_CAPABILITY_ID)

    try:
        # Preflight both rails before creating anything.
        for cap, provider_name in ((create_cap, CREATE_CAPABILITY_ID), (status_cap, STATUS_CAPABILITY_ID)):
            status, payload = request_json(
                "GET",
                rhumb_url(f"/v1/capabilities/{cap}/resolve?credential_mode=rhumb_managed"),
                headers=rhumb_headers(rhumb_key),
                timeout=30,
            )
            steps.append(compact_step(f"{provider_name}:resolve", status, payload))

            status, payload = request_json(
                "GET",
                rhumb_url(f"/v1/capabilities/{cap}/execute/estimate?provider=e2b&credential_mode=rhumb_managed"),
                headers=rhumb_headers(rhumb_key),
                timeout=30,
            )
            steps.append(compact_step(f"{provider_name}:estimate", status, payload))
            if not (200 <= status < 300):
                return {
                    "capabilities": [CREATE_CAPABILITY_ID, STATUS_CAPABILITY_ID],
                    "provider": "e2b",
                    "sandbox_id": sandbox_id,
                    "passed": False,
                    "skipped_create": f"{provider_name}_estimate_not_200",
                    "steps": steps,
                    "cleanup": cleanup,
                }

        create_body = {
            "provider": "e2b",
            "credential_mode": "rhumb_managed",
            "interface": INTERFACE,
            "idempotency_key": f"dc90-e2b-agent-spawn-{stamp.lower()}",
            "body": {"templateID": "base", "timeout": SANDBOX_TIMEOUT_SECONDS},
        }
        status, payload = request_json(
            "POST",
            rhumb_url(f"/v1/capabilities/{create_cap}/execute"),
            headers=rhumb_headers(rhumb_key),
            body=create_body,
            timeout=90,
        )
        steps.append(compact_step("agent.spawn:execute", status, payload))
        sandbox_id = upstream_dict(payload).get("sandboxID")
        if not sandbox_id:
            return {
                "capabilities": [CREATE_CAPABILITY_ID, STATUS_CAPABILITY_ID],
                "provider": "e2b",
                "sandbox_id": sandbox_id,
                "passed": False,
                "skipped_status": "no_sandbox_id_returned",
                "steps": steps,
                "cleanup": cleanup,
            }

        status_body = {
            "provider": "e2b",
            "credential_mode": "rhumb_managed",
            "interface": INTERFACE,
            "idempotency_key": f"dc90-e2b-agent-get-status-{stamp.lower()}",
            "body": {"sandboxId": sandbox_id},
        }
        status, payload = request_json(
            "POST",
            rhumb_url(f"/v1/capabilities/{status_cap}/execute"),
            headers=rhumb_headers(rhumb_key),
            body=status_body,
            timeout=90,
        )
        steps.append(compact_step("agent.get_status:execute", status, payload))

    finally:
        if sandbox_id:
            status, payload = request_json(
                "DELETE",
                f"{E2B_BASE_URL}/sandboxes/{urllib.parse.quote(sandbox_id, safe='')}",
                headers=e2b_headers(e2b_key),
                timeout=60,
            )
            cleanup.append(compact_step("direct_delete", status, payload))
            time.sleep(1.0)
            status, payload = request_json(
                "GET",
                f"{E2B_BASE_URL}/sandboxes/{urllib.parse.quote(sandbox_id, safe='')}",
                headers=e2b_headers(e2b_key),
                timeout=60,
            )
            verify = compact_step("direct_cleanup_verify", status, payload)
            verify["expected_http_status"] = 404
            cleanup.append(verify)

            # The hosted managed credential is the authority for the created
            # sandbox.  The local direct key should delete it when scopes match;
            # if E2B returns the ambiguous 404/no-access response, wait for the
            # deliberately short TTL and verify through Rhumb-managed status
            # that the sandbox is gone before marking the fixture safe.
            deadline = time.time() + CLEANUP_VERIFY_DEADLINE_SECONDS
            attempt = 0
            while time.time() < deadline:
                attempt += 1
                time.sleep(3.0 if attempt == 1 else 5.0)
                managed_cleanup_body = {
                    "provider": "e2b",
                    "credential_mode": "rhumb_managed",
                    "interface": INTERFACE,
                    "idempotency_key": f"dc90-e2b-managed-cleanup-verify-{stamp.lower()}-{attempt}",
                    "body": {"sandboxId": sandbox_id},
                }
                status, payload = request_json(
                    "POST",
                    rhumb_url(f"/v1/capabilities/{status_cap}/execute"),
                    headers=rhumb_headers(rhumb_key),
                    body=managed_cleanup_body,
                    timeout=90,
                )
                managed_verify = compact_step(f"managed_cleanup_verify:{attempt}", status, payload)
                managed_verify["expected_upstream_status"] = 404
                cleanup.append(managed_verify)
                if managed_verify.get("upstream_status") == 404:
                    cleanup_verdict = "managed_status_gone"
                    break
            else:
                cleanup_verdict = "not_verified_gone"

    create_step = next((s for s in steps if s["name"] == "agent.spawn:execute"), {})
    status_step = next((s for s in steps if s["name"] == "agent.get_status:execute"), {})
    delete_step = next((s for s in cleanup if s["name"] == "direct_delete"), {})
    cleanup_verify = next((s for s in cleanup if s["name"] == "direct_cleanup_verify"), {})
    managed_cleanup_ok = any(s.get("upstream_status") == 404 for s in cleanup if str(s.get("name", "")).startswith("managed_cleanup_verify:"))
    direct_cleanup_ok = delete_step.get("http_status") in {200, 202, 204}
    if direct_cleanup_ok:
        cleanup_verdict = "direct_delete_accepted"
    passed = bool(
        create_step.get("http_status") == 200
        and create_step.get("upstream_status") == 201
        and create_step.get("receipt_id")
        and status_step.get("http_status") == 200
        and status_step.get("upstream_status") == 200
        and status_step.get("receipt_id")
        and (direct_cleanup_ok or managed_cleanup_ok)
        and cleanup_verify.get("http_status") in {400, 404}
    )
    return {
        "capabilities": [CREATE_CAPABILITY_ID, STATUS_CAPABILITY_ID],
        "provider": "e2b",
        "sandbox_id": sandbox_id,
        "sandbox_timeout_seconds": SANDBOX_TIMEOUT_SECONDS,
        "cleanup_verdict": cleanup_verdict,
        "passed": passed,
        "steps": steps,
        "cleanup": cleanup,
    }


def main() -> int:
    global BASE_URL
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=BASE_URL)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    BASE_URL = args.base_url.rstrip("/")

    stamp = utc_stamp()
    out = args.out or f"artifacts/dc90-e2b-lifecycle-smoke-{stamp}.json"
    key_title, rhumb_key = load_working_rhumb_key()
    e2b_key = sop_field(E2B_KEY_ITEM)
    if not e2b_key:
        raise SystemExit("E2B API Key credential was unreadable from 1Password")

    result = run_lifecycle(rhumb_key, e2b_key, stamp)
    report: dict[str, Any] = {
        "timestamp_utc": stamp,
        "base_url": BASE_URL,
        "secret_written": False,
        "rhumb_key_item": key_title,
        "fixtures": [result],
        "summary": {
            "fixture_count": 1,
            "passed_count": 1 if result.get("passed") else 0,
            "e2b_lifecycle_passed": result.get("passed"),
            "sandbox_id": result.get("sandbox_id"),
        },
    }

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write("\n")
    print(json.dumps({"out": out, "summary": report["summary"]}, indent=2, sort_keys=True))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
