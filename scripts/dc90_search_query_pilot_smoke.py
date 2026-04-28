#!/usr/bin/env python3
"""Run the final DC90 trusted-user pilot `search.query` managed smoke.

This is the pre-invite readiness check from
`docs/DC90-RESOLVE-MANAGED-CAPABILITIES-PILOT-READINESS-2026-04-27.md`:
resolve, estimate, then one governed `search.query` execution through a funded
dogfood Rhumb key. It writes only a compact redacted artifact; no secrets are
persisted.
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
VAULT = "OpenClaw Agents"
RHUMB_KEY_ITEMS = (
    "Rhumb API Key - pedro-dogfood",
    "Rhumb API Key - atlas@supertrained.ai",
)
CAPABILITY_ID = "search.query"
PROVIDER = "brave-search-api"
QUERY = "best tools for agent web search"
MAX_RESULTS = 3


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
        "User-Agent": "rhumb-dc90-search-query-pilot-smoke/2026-04-28",
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
    except Exception as exc:  # pragma: no cover - diagnostic path for cron runs
        return 0, {"transport_error": type(exc).__name__, "message": str(exc)}

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
        # `/v1/capabilities` is intentionally open, so it cannot prove the key.
        # Billing balance requires a valid governed key and keeps this helper
        # from accidentally selecting an expired dogfood secret.
        status, _payload = request_json(
            "GET",
            rhumb_url("/v1/billing/balance"),
            headers=rhumb_headers(key),
            timeout=20,
        )
        if 200 <= status < 300:
            return title, key
    raise SystemExit("No working Rhumb dogfood governed key found in 1Password")


def _hash_obj(value: Any) -> str:
    rendered = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(rendered.encode()).hexdigest()[:16]


def _extract_results(upstream: Any) -> dict[str, Any]:
    """Keep compact search evidence without persisting the full response."""
    candidates: list[Any] = []
    if isinstance(upstream, dict):
        for key in ("results", "web", "items", "data"):
            value = upstream.get(key)
            if isinstance(value, list):
                candidates = value
                break
            if isinstance(value, dict):
                nested = value.get("results") or value.get("items")
                if isinstance(nested, list):
                    candidates = nested
                    break
    elif isinstance(upstream, list):
        candidates = upstream

    compact: list[dict[str, Any]] = []
    for item in candidates[:MAX_RESULTS]:
        if not isinstance(item, dict):
            compact.append({"type": type(item).__name__, "hash16": _hash_obj(item)})
            continue
        compact.append(
            {
                key: item.get(key)
                for key in ("title", "url", "link", "description")
                if isinstance(item.get(key), str)
            }
        )
    return {
        "result_count_observed": len(candidates),
        "top_results": compact,
        "upstream_hash16": _hash_obj(upstream),
    }


def compact_step(name: str, status: int, payload: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"name": name, "http_status": status}
    if not isinstance(payload, dict):
        out["payload_type"] = type(payload).__name__
        out["payload_hash16"] = hashlib.sha256(str(payload).encode()).hexdigest()[:16]
        return out

    out["top_level_keys"] = sorted(payload.keys())[:20]
    if payload.get("error") is not None:
        out["error"] = payload.get("error")
    for key in ("detail", "message", "resolution", "request_id"):
        if isinstance(payload.get(key), str):
            out[key] = payload[key]

    data = payload.get("data")
    if isinstance(data, dict):
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
            "estimated_cost_usd",
        ):
            if key in data:
                out[key] = data[key]
        upstream = data.get("upstream_response")
        if upstream is not None:
            out["upstream_evidence"] = _extract_results(upstream)
    return out


def main() -> int:
    global BASE_URL
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=BASE_URL)
    ap.add_argument("--out", default=None)
    ap.add_argument("--provider", default=PROVIDER)
    ap.add_argument("--query", default=QUERY)
    args = ap.parse_args()
    BASE_URL = args.base_url.rstrip("/")

    stamp = utc_stamp()
    out = args.out or f"artifacts/dc90-search-query-pilot-smoke-{stamp}.json"
    key_title, api_key = load_working_rhumb_key()
    cap = urllib.parse.quote(CAPABILITY_ID, safe="")
    provider = args.provider
    steps: list[dict[str, Any]] = []

    status, payload = request_json(
        "GET",
        rhumb_url(f"/v1/capabilities/{cap}/resolve?credential_mode=rhumb_managed"),
        headers=rhumb_headers(api_key),
        timeout=30,
    )
    steps.append(compact_step("resolve", status, payload))

    status, payload = request_json(
        "GET",
        rhumb_url(
            f"/v1/capabilities/{cap}/execute/estimate?provider={urllib.parse.quote(provider)}&credential_mode=rhumb_managed"
        ),
        headers=rhumb_headers(api_key),
        timeout=30,
    )
    estimate_step = compact_step("estimate", status, payload)
    steps.append(estimate_step)

    execute_ran = False
    if 200 <= status < 300:
        body = {
            "provider": provider,
            "credential_mode": "rhumb_managed",
            "interface": "dc90-search-query-pilot-smoke-20260428",
            "idempotency_key": f"dc90-search-query-pilot-{int(time.time() * 1000)}",
            "body": {
                "query": args.query,
                "max_results": MAX_RESULTS,
            },
        }
        status, payload = request_json(
            "POST",
            rhumb_url(f"/v1/capabilities/{cap}/execute"),
            headers=rhumb_headers(api_key),
            body=body,
            timeout=90,
        )
        execute_ran = True
        steps.append(compact_step("execute", status, payload))

    execute_step = steps[-1] if execute_ran else {}
    upstream_evidence = execute_step.get("upstream_evidence") if isinstance(execute_step, dict) else None
    result_count = upstream_evidence.get("result_count_observed") if isinstance(upstream_evidence, dict) else None
    passed = bool(
        execute_ran
        and execute_step.get("http_status") == 200
        and execute_step.get("credential_mode") == "rhumb_managed"
        and execute_step.get("upstream_status") == 200
        and execute_step.get("receipt_id")
        and isinstance(result_count, int)
        and result_count > 0
    )

    report = {
        "timestamp_utc": stamp,
        "base_url": BASE_URL,
        "secret_written": False,
        "rhumb_key_item": key_title,
        "fixture": {
            "capability_id": CAPABILITY_ID,
            "provider": provider,
            "safety_class": "green",
            "query": args.query,
            "max_results": MAX_RESULTS,
            "execute_ran": execute_ran,
            "passed": passed,
            "steps": steps,
        },
        "summary": {
            "passed": passed,
            "execute_ran": execute_ran,
            "provider_used": execute_step.get("provider_used"),
            "credential_mode": execute_step.get("credential_mode"),
            "receipt_id": execute_step.get("receipt_id"),
            "upstream_status": execute_step.get("upstream_status"),
            "result_count_observed": result_count,
            "upstream_hash16": upstream_evidence.get("upstream_hash16") if isinstance(upstream_evidence, dict) else None,
            "estimated_cost_usd": estimate_step.get("cost_estimate_usd") or estimate_step.get("estimated_cost_usd"),
        },
    }

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    print(json.dumps({"out": out, "summary": report["summary"]}, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
