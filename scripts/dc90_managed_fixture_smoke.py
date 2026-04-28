#!/usr/bin/env python3
"""Run bounded DC90 managed-capability fixture smokes.

This helper is intentionally narrow: it rechecks Emailable managed visibility and,
when still blocked, proves the next amber fixture by writing one disposable object
into the Rhumb-owned Algolia smoke index, reading it back directly, and deleting
it in a finally-style cleanup path. Secrets are loaded at runtime from 1Password
via `sop` and are never written to artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
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
ALGOLIA_KEY_ITEM = "Tester - Algolia"
ALGOLIA_APP_ID = "80LYFTF37Y"
ALGOLIA_INDEX = "rhumb_test"


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        "User-Agent": "rhumb-dc90-managed-fixture-smoke/2026-04-28",
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
        status, payload = request_json(
            "GET",
            rhumb_url("/v1/capabilities?limit=1"),
            headers=rhumb_headers(key),
            timeout=20,
        )
        if 200 <= status < 300:
            return title, key
        # The capabilities endpoint has been stable as a lightweight key probe,
        # but tolerate product-shape drift by trying billing balance too.
        status, payload = request_json(
            "GET",
            rhumb_url("/v1/billing/balance"),
            headers=rhumb_headers(key),
            timeout=20,
        )
        if 200 <= status < 300:
            return title, key
    raise SystemExit("No working Rhumb dogfood governed key found in 1Password")


def compact_step(name: str, status: int, payload: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"name": name, "http_status": status}
    if isinstance(payload, dict):
        out["top_level_keys"] = sorted(payload.keys())[:20]
        data = payload.get("data")
        error = payload.get("error")
        if error is not None:
            out["error"] = error
        for key in ("detail", "message", "resolution", "request_id"):
            if isinstance(payload.get(key), str):
                out[key] = payload[key]
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
            ):
                if key in data:
                    out[key] = data[key]
            upstream = data.get("upstream_response")
            if isinstance(upstream, dict):
                out["upstream_keys"] = sorted(upstream.keys())[:30]
                for key in ("objectID", "taskID", "updatedAt", "deletedAt", "nbHits"):
                    if key in upstream:
                        out[f"upstream_{key}"] = upstream[key]
                if "hits" in upstream and isinstance(upstream["hits"], list):
                    out["upstream_hits_len"] = len(upstream["hits"])
            elif upstream is not None:
                out["upstream_summary"] = {
                    "type": type(upstream).__name__,
                    "sha256_16": hashlib.sha256(str(upstream).encode()).hexdigest()[:16],
                }
        elif isinstance(data, list):
            out["data_len"] = len(data)
    else:
        out["payload_type"] = type(payload).__name__
    return out


def resolve_mentions_provider(payload: Any, provider: str) -> bool:
    """Return True when a Resolve response exposes provider as managed-capable.

    The DC90 smoke should not burn an estimate/auth call for Emailable while the
    hosted Resolve response still has no Emailable managed provider. The exact
    shape has evolved, so accept either fallback_chain entries or provider-list
    identifiers/slugs/names.
    """
    if not isinstance(payload, dict):
        return False
    data = payload.get("data")
    if not isinstance(data, dict):
        return False

    needle = provider.strip().lower()
    if not needle:
        return False

    for value in data.get("fallback_chain") or []:
        if isinstance(value, str) and value.strip().lower() == needle:
            return True

    for item in data.get("providers") or []:
        if not isinstance(item, dict):
            continue
        identifiers = (
            item.get("provider"),
            item.get("provider_id"),
            item.get("id"),
            item.get("slug"),
            item.get("service_id"),
            item.get("service"),
            item.get("name"),
        )
        if any(isinstance(value, str) and value.strip().lower() == needle for value in identifiers):
            return True
    return False


def recheck_emailable(api_key: str) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    cap = urllib.parse.quote("email.verify", safe="")
    resolve_path = f"/v1/capabilities/{cap}/resolve?credential_mode=rhumb_managed"
    status, payload = request_json("GET", rhumb_url(resolve_path), headers=rhumb_headers(api_key), timeout=30)
    steps.append(compact_step("resolve", status, payload))

    if not (200 <= status < 300):
        return {
            "capability_id": "email.verify",
            "provider": "emailable",
            "fixture": "pilot-fixture@example.com",
            "execute_ran": False,
            "passed": False,
            "skipped_estimate": "resolve_not_200",
            "skipped_execute": "resolve_not_200",
            "steps": steps,
        }

    if not resolve_mentions_provider(payload, "emailable"):
        return {
            "capability_id": "email.verify",
            "provider": "emailable",
            "fixture": "pilot-fixture@example.com",
            "execute_ran": False,
            "passed": False,
            "skipped_estimate": "resolve_missing_managed_provider",
            "skipped_execute": "resolve_missing_managed_provider",
            "steps": steps,
        }

    estimate_path = f"/v1/capabilities/{cap}/execute/estimate?provider=emailable&credential_mode=rhumb_managed"
    status, payload = request_json("GET", rhumb_url(estimate_path), headers=rhumb_headers(api_key), timeout=30)
    steps.append(compact_step("estimate", status, payload))

    execute_ran = False
    if 200 <= status < 300:
        body = {
            "provider": "emailable",
            "credential_mode": "rhumb_managed",
            "interface": "dc90-managed-fixture-smoke-20260428",
            "idempotency_key": f"dc90-emailable-email-verify-{int(time.time() * 1000)}",
            "body": {"email": "pilot-fixture@example.com"},
        }
        status, payload = request_json(
            "POST",
            rhumb_url(f"/v1/capabilities/{cap}/execute"),
            headers=rhumb_headers(api_key),
            body=body,
            timeout=60,
        )
        execute_ran = True
        steps.append(compact_step("execute", status, payload))

    passed = bool(execute_ran and steps[-1].get("http_status") == 200 and steps[-1].get("receipt_id"))
    return {
        "capability_id": "email.verify",
        "provider": "emailable",
        "fixture": "pilot-fixture@example.com",
        "execute_ran": execute_ran,
        "passed": passed,
        "steps": steps,
    }


def algolia_headers(api_key: str) -> dict[str, str]:
    return {
        "X-Algolia-Application-Id": ALGOLIA_APP_ID,
        "X-Algolia-API-Key": api_key,
    }


def algolia_url(path: str) -> str:
    return f"https://{ALGOLIA_APP_ID}-dsn.algolia.net{path}"


def algolia_direct_url(path: str) -> str:
    return f"https://{ALGOLIA_APP_ID}.algolia.net{path}"


def run_algolia_search_index(api_key: str, algolia_key: str, object_id: str) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    cleanup: list[dict[str, Any]] = []
    cap = urllib.parse.quote("search.index", safe="")
    fixture_object = {
        "index": ALGOLIA_INDEX,
        "objectID": object_id,
        "name": "Rhumb DC90 disposable search.index smoke",
        "category": "dc90-smoke",
        "description": "Temporary object created by Rhumb DC90 managed fixture smoke; safe to delete.",
        "created_by": "dc90_managed_fixture_smoke.py",
        "created_at": iso_now(),
    }
    try:
        status, payload = request_json(
            "GET",
            rhumb_url(f"/v1/capabilities/{cap}/resolve?credential_mode=rhumb_managed"),
            headers=rhumb_headers(api_key),
            timeout=30,
        )
        steps.append(compact_step("resolve", status, payload))

        status, payload = request_json(
            "GET",
            rhumb_url(f"/v1/capabilities/{cap}/execute/estimate?provider=algolia&credential_mode=rhumb_managed"),
            headers=rhumb_headers(api_key),
            timeout=30,
        )
        steps.append(compact_step("estimate", status, payload))
        if not (200 <= status < 300):
            return {
                "capability_id": "search.index",
                "provider": "algolia",
                "object_id": object_id,
                "index": ALGOLIA_INDEX,
                "passed": False,
                "skipped_execute": "estimate_not_200",
                "steps": steps,
                "cleanup": cleanup,
            }

        body = {
            "provider": "algolia",
            "credential_mode": "rhumb_managed",
            "interface": "dc90-managed-fixture-smoke-20260428",
            "idempotency_key": f"dc90-algolia-search-index-{object_id}",
            "body": fixture_object,
        }
        status, payload = request_json(
            "POST",
            rhumb_url(f"/v1/capabilities/{cap}/execute"),
            headers=rhumb_headers(api_key),
            body=body,
            timeout=60,
        )
        steps.append(compact_step("execute", status, payload))

        # Read back through Algolia directly to prove the write landed, without
        # charging another Rhumb execution. Keep the response compact/redacted.
        status, payload = request_json(
            "GET",
            algolia_url(f"/1/indexes/{urllib.parse.quote(ALGOLIA_INDEX, safe='')}/{urllib.parse.quote(object_id, safe='')}"),
            headers=algolia_headers(algolia_key),
            timeout=30,
        )
        readback = compact_step("direct_readback", status, payload)
        if isinstance(payload, dict):
            readback["objectID"] = payload.get("objectID")
            readback["object_name"] = payload.get("name")
            readback["category"] = payload.get("category")
        steps.append(readback)

    finally:
        status, payload = request_json(
            "DELETE",
            algolia_direct_url(f"/1/indexes/{urllib.parse.quote(ALGOLIA_INDEX, safe='')}/{urllib.parse.quote(object_id, safe='')}"),
            headers=algolia_headers(algolia_key),
            timeout=30,
        )
        cleanup.append(compact_step("direct_delete", status, payload))
        # Algolia deletes are task-based; give the index a moment, then verify
        # the object is no longer readable. A 404 is the desired cleanup state.
        time.sleep(1.5)
        status, payload = request_json(
            "GET",
            algolia_url(f"/1/indexes/{urllib.parse.quote(ALGOLIA_INDEX, safe='')}/{urllib.parse.quote(object_id, safe='')}"),
            headers=algolia_headers(algolia_key),
            timeout=30,
        )
        verify = compact_step("direct_cleanup_verify", status, payload)
        verify["expected_http_status"] = 404
        cleanup.append(verify)

    execute_step = next((s for s in steps if s["name"] == "execute"), {})
    readback_step = next((s for s in steps if s["name"] == "direct_readback"), {})
    cleanup_verify = next((s for s in cleanup if s["name"] == "direct_cleanup_verify"), {})
    passed = bool(
        execute_step.get("http_status") == 200
        and execute_step.get("receipt_id")
        and readback_step.get("http_status") == 200
        and readback_step.get("objectID") == object_id
        and cleanup_verify.get("http_status") == 404
    )
    return {
        "capability_id": "search.index",
        "provider": "algolia",
        "object_id": object_id,
        "index": ALGOLIA_INDEX,
        "passed": passed,
        "steps": steps,
        "cleanup": cleanup,
    }


def main() -> int:
    global BASE_URL
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=BASE_URL)
    ap.add_argument("--out", default=None)
    ap.add_argument("--skip-algolia", action="store_true", help="Only recheck Emailable")
    args = ap.parse_args()
    BASE_URL = args.base_url.rstrip("/")

    stamp = utc_stamp()
    out = args.out or f"artifacts/dc90-managed-fixture-smoke-{stamp}.json"
    key_title, rhumb_key = load_working_rhumb_key()
    algolia_key = None if args.skip_algolia else sop_field(ALGOLIA_KEY_ITEM)
    if not args.skip_algolia and not algolia_key:
        raise SystemExit("Algolia smoke requested but Tester - Algolia credential was unreadable")

    object_id = f"dc90-smoke-{stamp.lower()}"
    report: dict[str, Any] = {
        "timestamp_utc": stamp,
        "base_url": BASE_URL,
        "secret_written": False,
        "rhumb_key_item": key_title,
        "fixtures": [],
        "summary": {},
    }

    emailable = recheck_emailable(rhumb_key)
    report["fixtures"].append(emailable)

    if not args.skip_algolia:
        algolia_result = run_algolia_search_index(rhumb_key, str(algolia_key), object_id)
        report["fixtures"].append(algolia_result)

    report["summary"] = {
        "fixture_count": len(report["fixtures"]),
        "passed_count": sum(1 for item in report["fixtures"] if item.get("passed")),
        "emailable_passed": emailable.get("passed"),
        "emailable_execute_ran": emailable.get("execute_ran"),
        "algolia_search_index_passed": next(
            (item.get("passed") for item in report["fixtures"] if item.get("capability_id") == "search.index"),
            None,
        ),
    }

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    print(json.dumps({"out": out, "summary": report["summary"]}, indent=2, sort_keys=True))
    return 0 if report["summary"].get("algolia_search_index_passed") or args.skip_algolia else 1


if __name__ == "__main__":
    raise SystemExit(main())
