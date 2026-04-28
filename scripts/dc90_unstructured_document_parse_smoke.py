#!/usr/bin/env python3
"""Run a bounded DC90 Unstructured managed document-parse smoke.

Uses one tiny synthetic text fixture, encoded in the JSON body so the hosted
Rhumb managed executor can translate it to the provider multipart request. The
fixture contains no customer data. Secrets are loaded from 1Password at runtime
and are never written to artifacts.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
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
CAPABILITY_ID = "document.parse"
PROVIDER = "unstructured"
INTERFACE = "dc90-unstructured-document-parse-smoke-20260428"
FIXTURE_TOKEN = "dc90-unstructured-parse-ok"
FIXTURE_BYTES = (
    b"Rhumb DC90 managed fixture. This synthetic document should parse as "
    + FIXTURE_TOKEN.encode("utf-8")
    + b".\n"
)


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
        "User-Agent": "rhumb-dc90-unstructured-document-parse-smoke/2026-04-28",
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
    except Exception as exc:  # pragma: no cover - exercised only on network errors
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


def collect_text(value: Any) -> list[str]:
    texts: list[str] = []
    if isinstance(value, str):
        texts.append(value)
    elif isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in {"text", "content", "message"} and isinstance(child, str):
                texts.append(child)
            elif isinstance(child, (dict, list)):
                texts.extend(collect_text(child))
    elif isinstance(value, list):
        for child in value:
            texts.extend(collect_text(child))
    return texts


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
        if isinstance(upstream, list):
            out["upstream_type"] = "list"
            out["upstream_len"] = len(upstream)
            element_types = []
            text_snippets = []
            for item in upstream[:5]:
                if isinstance(item, dict):
                    if item.get("type") is not None:
                        element_types.append(str(item.get("type")))
                    if isinstance(item.get("text"), str):
                        text_snippets.append(item["text"][:120])
            if element_types:
                out["upstream_element_types"] = element_types
            if text_snippets:
                out["upstream_text_snippets"] = text_snippets
        elif isinstance(upstream, dict):
            out["upstream_type"] = "dict"
            out["upstream_keys"] = sorted(upstream.keys())[:30]
        elif upstream is not None:
            out["upstream_summary"] = {
                "type": type(upstream).__name__,
                "sha256_16": hashlib.sha256(str(upstream).encode()).hexdigest()[:16],
            }
    elif payload is not None:
        out["payload_type"] = type(payload).__name__
    return out


def run_smoke(api_key: str, stamp: str) -> dict[str, Any]:
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
            "fixture": "synthetic_text_file",
            "passed": False,
            "skipped_execute": "estimate_not_200",
            "steps": steps,
        }

    execute_body = {
        "provider": PROVIDER,
        "credential_mode": "rhumb_managed",
        "interface": INTERFACE,
        "idempotency_key": f"dc90-unstructured-document-parse-{stamp.lower()}-{int(time.time() * 1000)}",
        "body": {
            "files": {
                "filename": "dc90-unstructured-smoke.txt",
                "content_base64": base64.b64encode(FIXTURE_BYTES).decode("ascii"),
                "content_type": "text/plain",
            },
            "strategy": "fast",
            "languages": ["eng"],
        },
    }
    status, payload = request_json(
        "POST",
        rhumb_url(f"/v1/capabilities/{cap}/execute"),
        headers=rhumb_headers(api_key),
        body=execute_body,
        timeout=90,
    )
    steps.append(compact_step("execute", status, payload))

    data = data_dict(payload)
    texts = collect_text(upstream_payload(payload))
    passed = bool(
        status == 200
        and data.get("provider_used") == PROVIDER
        and data.get("receipt_id")
        and any(FIXTURE_TOKEN in text for text in texts)
    )
    return {
        "capability_id": CAPABILITY_ID,
        "provider": PROVIDER,
        "fixture": {
            "filename": "dc90-unstructured-smoke.txt",
            "content_type": "text/plain",
            "bytes": len(FIXTURE_BYTES),
            "sha256": hashlib.sha256(FIXTURE_BYTES).hexdigest(),
            "token": FIXTURE_TOKEN,
        },
        "passed": passed,
        "text_match": any(FIXTURE_TOKEN in text for text in texts),
        "parsed_text_snippets": [text[:160] for text in texts[:5]],
        "steps": steps,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run bounded DC90 Unstructured document.parse managed smoke.")
    parser.add_argument("--output-dir", default="artifacts", help="Artifact directory (default: artifacts)")
    args = parser.parse_args()

    stamp = utc_stamp()
    key_title, api_key = load_working_rhumb_key()
    result = run_smoke(api_key, stamp)
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
            "receipt_id": next((step.get("receipt_id") for step in result["steps"] if step.get("name") == "execute"), None),
            "upstream_status": next((step.get("upstream_status") for step in result["steps"] if step.get("name") == "execute"), None),
            "text_match": result.get("text_match"),
        },
    }

    import os

    os.makedirs(args.output_dir, exist_ok=True)
    path = os.path.join(args.output_dir, f"dc90-unstructured-document-parse-smoke-{stamp}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(artifact, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({"artifact": path, "summary": artifact["summary"]}, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
