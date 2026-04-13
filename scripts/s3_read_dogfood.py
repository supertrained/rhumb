#!/usr/bin/env python3
"""Live dogfood proof for the AUD-18 AWS S3 read-first rail.

This exercises the public Rhumb API end to end for the first S3 wedge:

1. object.list execute
2. object.head execute
3. object.get execute
4. denied non-allowlisted bucket
5. denied non-allowlisted prefix
6. denied oversized object fetch without a bounded range

The script is intentionally operator-facing. It records the raw hosted truth so we can
separate product regressions from missing config / proof-material issues.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "https://api.rhumb.dev"
DEFAULT_API_KEY_ENV = "RHUMB_DOGFOOD_API_KEY"
DEFAULT_API_KEY_ITEM = "Rhumb API Key - pedro-dogfood"
DEFAULT_API_KEY_VAULT = "OpenClaw Agents"
DEFAULT_TIMEOUT = 30.0
DEFAULT_STORAGE_REF = "st_docs"
DEFAULT_BUCKET = "docs-bucket"
DEFAULT_PREFIX = "reports/"
DEFAULT_KEY = "reports/daily.json"
DEFAULT_DENY_BUCKET = "forbidden-bucket"
DEFAULT_DENY_PREFIX = "private/"
DEFAULT_OVERSIZED_KEY = "reports/large.json"
DEFAULT_OVERSIZED_MAX_BYTES = 1024


@dataclass
class CheckSpec:
    name: str
    capability_id: str
    payload: dict[str, Any]
    expect_status: int | tuple[int, int]
    expect_error: str | None = None
    expect_message_contains: str | None = None


class FlowError(RuntimeError):
    def __init__(self, message: str, state: dict[str, Any]):
        super().__init__(message)
        self.state = json.loads(json.dumps(state, default=str))


def _mask_secret(value: str | None, *, head: int = 12, tail: int = 4) -> str | None:
    if value is None:
        return None
    if len(value) <= head + tail:
        return value
    return f"{value[:head]}…{value[-tail:]}"


def _load_api_key_from_sop(
    item_name: str = DEFAULT_API_KEY_ITEM,
    vault: str = DEFAULT_API_KEY_VAULT,
) -> str | None:
    try:
        result = subprocess.run(
            [
                "sop",
                "item",
                "get",
                item_name,
                "--vault",
                vault,
                "--fields",
                "credential",
                "--reveal",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    if result.returncode != 0:
        return None

    value = result.stdout.strip()
    return value or None


def _get_api_key(env_name: str) -> str:
    value = os.environ.get(env_name, "").strip()
    if value:
        return value

    value = _load_api_key_from_sop()
    if value:
        return value

    raise RuntimeError(
        f"Missing API key. Set {env_name} or store {DEFAULT_API_KEY_ITEM!r} in 1Password."
    )


def _http_json(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    body_bytes = None
    request_headers = {
        "Accept": "application/json",
        "User-Agent": "rhumb-s3-read-dogfood/0.1",
    }
    if headers:
        request_headers.update(headers)
    if payload is not None:
        body_bytes = json.dumps(payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")

    request = Request(url, data=body_bytes, headers=request_headers, method=method.upper())

    try:
        with urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8")
            status = response.getcode()
            response_headers = dict(response.headers.items())
    except HTTPError as exc:
        text = exc.read().decode("utf-8") if exc.fp else ""
        status = exc.code
        response_headers = dict(exc.headers.items()) if exc.headers else {}
    except URLError as exc:
        raise RuntimeError(f"Network error for {url}: {exc.reason}") from exc

    parsed: dict[str, Any] | list[Any] | None = None
    if text:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None

    return {
        "url": url,
        "status": status,
        "json": parsed,
        "text": text,
        "headers": response_headers,
    }


def _extract_error(payload: Any) -> str | None:
    if isinstance(payload, dict):
        value = payload.get("error")
        if isinstance(value, str) and value.strip():
            return value.strip()
        data = payload.get("data")
        if isinstance(data, dict):
            value = data.get("error")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _extract_message(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ("message", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        data = payload.get("data")
        if isinstance(data, dict):
            for key in ("message", "detail"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return None


def _extract_data(payload: Any) -> Any:
    if isinstance(payload, dict) and "data" in payload:
        return payload.get("data")
    return payload


def _status_matches(actual: int, expected: int | tuple[int, int]) -> bool:
    if isinstance(expected, tuple):
        lower, upper = expected
        return lower <= actual <= upper
    return actual == expected


def _receipt_id_from_execute(payload: Any) -> str | None:
    data = _extract_data(payload)
    if isinstance(data, dict):
        value = data.get("receipt_id")
        if isinstance(value, str) and value:
            return value
    return None


def _execute_check(
    *,
    root: str,
    headers: dict[str, str],
    timeout: float,
    check: CheckSpec,
) -> dict[str, Any]:
    response = _http_json(
        "POST",
        f"{root}/v1/capabilities/{check.capability_id}/execute",
        payload=check.payload,
        headers=headers,
        timeout=timeout,
    )
    payload = response.get("json")
    actual_status = int(response.get("status") or 0)
    actual_error = _extract_error(payload)
    actual_message = _extract_message(payload)

    ok = _status_matches(actual_status, check.expect_status)
    if check.expect_error is not None:
        ok = ok and actual_error == check.expect_error
    if check.expect_message_contains is not None:
        ok = ok and isinstance(actual_message, str) and check.expect_message_contains in actual_message

    receipt_id = _receipt_id_from_execute(payload)

    return {
        "name": check.name,
        "capability_id": check.capability_id,
        "ok": ok,
        "expected": {
            "status": check.expect_status,
            "error": check.expect_error,
            "message_contains": check.expect_message_contains,
        },
        "status": actual_status,
        "error": actual_error,
        "message": actual_message,
        "receipt_id": receipt_id,
        "response": payload if payload is not None else response.get("text"),
    }


def _fetch_receipt(
    *,
    root: str,
    headers: dict[str, str],
    timeout: float,
    receipt_id: str,
) -> dict[str, Any]:
    response = _http_json(
        "GET",
        f"{root}/v2/receipts/{receipt_id}",
        headers=headers,
        timeout=timeout,
    )
    payload = response.get("json")
    return {
        "status": response.get("status"),
        "ok": 200 <= int(response.get("status") or 0) < 300,
        "response": payload if payload is not None else response.get("text"),
    }


def _first_provider(payload: Any) -> dict[str, Any] | None:
    data = _extract_data(payload)
    if not isinstance(data, dict):
        return None
    providers = data.get("providers")
    if not isinstance(providers, list):
        return None
    for provider in providers:
        if isinstance(provider, dict) and provider.get("service_slug") == "aws-s3":
            return provider
    return None


def _first_credential_mode(payload: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    data = _extract_data(payload)
    if not isinstance(data, dict):
        return None, None
    providers = data.get("providers")
    if not isinstance(providers, list):
        return None, None
    for provider in providers:
        if not isinstance(provider, dict) or provider.get("service_slug") != "aws-s3":
            continue
        modes = provider.get("modes")
        if not isinstance(modes, list):
            return provider, None
        for mode in modes:
            if isinstance(mode, dict) and mode.get("mode") == "byok":
                return provider, mode
        return provider, None
    return None, None


def _resolve_handoff(payload: Any) -> dict[str, Any] | None:
    data = _extract_data(payload)
    if not isinstance(data, dict):
        return None
    recovery_hint = data.get("recovery_hint")
    raw_recovery = recovery_hint if isinstance(recovery_hint, dict) else {}
    candidates = (
        ("execute_hint", data.get("execute_hint")),
        ("alternate_execute_hint", raw_recovery.get("alternate_execute_hint")),
        ("setup_handoff", raw_recovery.get("setup_handoff")),
    )
    for source, candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        handoff = {
            "source": source,
            "reason": raw_recovery.get("reason") if isinstance(raw_recovery.get("reason"), str) else None,
            "resolve_url": raw_recovery.get("resolve_url") if isinstance(raw_recovery.get("resolve_url"), str) else None,
            "preferred_provider": candidate.get("preferred_provider") if isinstance(candidate.get("preferred_provider"), str) else None,
            "preferred_credential_mode": (
                candidate.get("preferred_credential_mode")
                if isinstance(candidate.get("preferred_credential_mode"), str)
                else None
            ),
            "selection_reason": candidate.get("selection_reason") if isinstance(candidate.get("selection_reason"), str) else None,
            "setup_hint": candidate.get("setup_hint") if isinstance(candidate.get("setup_hint"), str) else None,
            "setup_url": candidate.get("setup_url") if isinstance(candidate.get("setup_url"), str) else None,
            "credential_modes_url": (
                candidate.get("credential_modes_url")
                if isinstance(candidate.get("credential_modes_url"), str)
                else raw_recovery.get("credential_modes_url")
                if isinstance(raw_recovery.get("credential_modes_url"), str)
                else None
            ),
            "endpoint_pattern": candidate.get("endpoint_pattern") if isinstance(candidate.get("endpoint_pattern"), str) else None,
            "configured": candidate.get("configured") if isinstance(candidate.get("configured"), bool) else None,
        }
        return {key: value for key, value in handoff.items() if value is not None}
    return None


def _resolve_handoff_summary(handoff: dict[str, Any] | None) -> str | None:
    if not isinstance(handoff, dict) or not handoff:
        return None
    parts: list[str] = []
    if isinstance(handoff.get("source"), str):
        parts.append(f"source={handoff['source']}")
    if isinstance(handoff.get("preferred_provider"), str):
        parts.append(f"provider={handoff['preferred_provider']}")
    if isinstance(handoff.get("preferred_credential_mode"), str):
        parts.append(f"mode={handoff['preferred_credential_mode']}")
    if isinstance(handoff.get("endpoint_pattern"), str):
        parts.append(f"endpoint={handoff['endpoint_pattern']}")
    next_url = handoff.get("setup_url") or handoff.get("resolve_url") or handoff.get("credential_modes_url")
    if isinstance(next_url, str):
        parts.append(f"next_url={next_url}")
    if not parts:
        return None
    return "Resolve next step: " + ", ".join(parts)


def _run_preflight(*, root: str, timeout: float) -> dict[str, Any]:
    resolve = _http_json(
        "GET",
        f"{root}/v1/capabilities/object.list/resolve",
        timeout=timeout,
    )
    credential_modes = _http_json(
        "GET",
        f"{root}/v1/capabilities/object.list/credential-modes",
        timeout=timeout,
    )

    resolve_provider = _first_provider(resolve.get("json"))
    modes_provider, byok_mode = _first_credential_mode(credential_modes.get("json"))
    resolve_handoff = _resolve_handoff(resolve.get("json"))

    resolve_ok = (
        resolve.get("status") == 200
        and isinstance(resolve_provider, dict)
        and (
            resolve_provider.get("available_for_execute") is True
            or isinstance(resolve_handoff, dict)
        )
    )
    credential_modes_ok = (
        credential_modes.get("status") == 200
        and isinstance(modes_provider, dict)
        and isinstance(byok_mode, dict)
        and byok_mode.get("available") is True
    )

    resolve_configured = bool(resolve_provider.get("configured")) if isinstance(resolve_provider, dict) else False
    mode_configured = bool(byok_mode.get("configured")) if isinstance(byok_mode, dict) else False
    configured = resolve_configured and mode_configured

    results = [
        {
            "check": "object_list_resolve_surface",
            "ok": resolve_ok,
            "status": resolve.get("status"),
            "error": None if resolve_ok else "storage_capability_unavailable",
            "payload_check": None if resolve_ok else "missing_aws_s3_provider_or_resolve_handoff",
            "payload": {
                "provider": resolve_provider,
                "resolve_handoff": resolve_handoff,
                "response": resolve.get("json"),
            },
        },
        {
            "check": "object_list_credential_modes_surface",
            "ok": credential_modes_ok,
            "status": credential_modes.get("status"),
            "error": None if credential_modes_ok else "storage_credential_modes_unavailable",
            "payload_check": None if credential_modes_ok else "missing_aws_s3_byok_mode",
            "payload": credential_modes.get("json"),
        },
        {
            "check": "storage_bundle_configured",
            "ok": configured,
            "status": 200 if resolve.get("status") == 200 and credential_modes.get("status") == 200 else None,
            "error": None if configured else "storage_bundle_unconfigured",
            "payload_check": None if configured else "configured_false",
            "payload": {
                "resolve_configured": resolve_configured,
                "credential_mode_configured": mode_configured,
                "resolve_handoff": resolve_handoff,
            },
        },
    ]

    return {
        "configured": configured,
        "available_for_execute": bool(resolve_provider.get("available_for_execute")) if isinstance(resolve_provider, dict) else False,
        "resolve_handoff": resolve_handoff,
        "resolve": resolve,
        "credential_modes": credential_modes,
        "results": results,
    }


def _build_checks(args: argparse.Namespace) -> list[CheckSpec]:
    checks = [
        CheckSpec(
            name="list",
            capability_id="object.list",
            payload={
                "storage_ref": args.storage_ref,
                "bucket": args.bucket,
                "prefix": args.prefix,
                "max_keys": args.max_keys,
            },
            expect_status=(200, 299),
        ),
        CheckSpec(
            name="head",
            capability_id="object.head",
            payload={
                "storage_ref": args.storage_ref,
                "bucket": args.bucket,
                "key": args.key,
            },
            expect_status=(200, 299),
        ),
        CheckSpec(
            name="get",
            capability_id="object.get",
            payload={
                "storage_ref": args.storage_ref,
                "bucket": args.bucket,
                "key": args.key,
                "max_bytes": args.get_max_bytes,
            },
            expect_status=(200, 299),
        ),
        CheckSpec(
            name="deny_bucket",
            capability_id="object.list",
            payload={
                "storage_ref": args.storage_ref,
                "bucket": args.deny_bucket,
                "prefix": args.prefix,
                "max_keys": min(args.max_keys, 5),
            },
            expect_status=400,
            expect_error="storage_ref_invalid",
            expect_message_contains="not allowed to access bucket",
        ),
        CheckSpec(
            name="deny_prefix",
            capability_id="object.list",
            payload={
                "storage_ref": args.storage_ref,
                "bucket": args.bucket,
                "prefix": args.deny_prefix,
                "max_keys": min(args.max_keys, 5),
            },
            expect_status=400,
            expect_error="storage_ref_invalid",
            expect_message_contains="not allowed to access",
        ),
        CheckSpec(
            name="oversized_get",
            capability_id="object.get",
            payload={
                "storage_ref": args.storage_ref,
                "bucket": args.bucket,
                "key": args.oversized_key,
                "max_bytes": args.oversized_max_bytes,
            },
            expect_status=422,
            expect_error="s3_object_too_large",
            expect_message_contains="exceeds max_bytes",
        ),
    ]
    return checks


def _build_summary(state: dict[str, Any]) -> str:
    results = state.get("results") or []
    ok_count = sum(1 for item in results if item.get("ok"))
    total = len(results)

    by_name = {item.get("name") or item.get("check"): item for item in results}
    list_result = by_name.get("list") or {}
    head_result = by_name.get("head") or {}
    get_result = by_name.get("get") or {}
    deny_bucket = by_name.get("deny_bucket") or {}
    deny_prefix = by_name.get("deny_prefix") or {}
    oversized = by_name.get("oversized_get") or {}
    resolve_surface = by_name.get("object_list_resolve_surface") or {}
    modes_surface = by_name.get("object_list_credential_modes_surface") or {}
    bundle_state = by_name.get("storage_bundle_configured") or {}

    parts = [
        f"AUD-18 S3 dogfood {ok_count}/{total} checks green",
        f"resolve={resolve_surface.get('status', 'n/a')}:{resolve_surface.get('error') or 'ok'}",
        f"credential_modes={modes_surface.get('status', 'n/a')}:{modes_surface.get('error') or 'ok'}",
        f"configured={bundle_state.get('status', 'n/a')}:{bundle_state.get('error') or 'ok'}",
        f"list={list_result.get('status', 'n/a')}:{list_result.get('error') or 'ok'}",
        f"head={head_result.get('status', 'n/a')}:{head_result.get('error') or 'ok'}",
        f"get={get_result.get('status', 'n/a')}:{get_result.get('error') or 'ok'}",
        f"deny_bucket={deny_bucket.get('status', 'n/a')}:{deny_bucket.get('error') or 'ok'}",
        f"deny_prefix={deny_prefix.get('status', 'n/a')}:{deny_prefix.get('error') or 'ok'}",
        f"oversized={oversized.get('status', 'n/a')}:{oversized.get('error') or 'ok'}",
    ]

    blocking = [
        item for item in results
        if item.get("name") in {"list", "head", "get"} and item.get("error") == "storage_ref_invalid"
    ]
    if blocking or bundle_state.get("error") == "storage_bundle_unconfigured":
        parts.append("blocked_on=hosted_storage_ref_config")

    resolve_step = state.get("resolve_step")
    if isinstance(resolve_step, str):
        parts.append(f"resolve_step={resolve_step}")

    return "; ".join(parts)


def run_flow(args: argparse.Namespace) -> dict[str, Any]:
    root = args.base_url.rstrip("/")
    preflight = _run_preflight(root=root, timeout=args.timeout)

    state: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": root,
        "mode": "full_proof",
        "config": {
            "api_key_env": args.api_key_env,
            "api_key_preview": _mask_secret(os.environ.get(args.api_key_env)),
            "storage_ref": args.storage_ref,
            "bucket": args.bucket,
            "prefix": args.prefix,
            "key": args.key,
            "deny_bucket": args.deny_bucket,
            "deny_prefix": args.deny_prefix,
            "oversized_key": args.oversized_key,
            "oversized_max_bytes": args.oversized_max_bytes,
            "get_max_bytes": args.get_max_bytes,
        },
        "preflight": {
            "configured": preflight["configured"],
            "available_for_execute": preflight["available_for_execute"],
            "resolve_handoff": preflight["resolve_handoff"],
            "resolve": preflight["resolve"],
            "credential_modes": preflight["credential_modes"],
        },
        "results": list(preflight["results"]),
        "receipts": {},
    }

    if args.preflight_only or not preflight["configured"]:
        state["mode"] = "preflight_only" if args.preflight_only else "blocked_preflight"
        state["ok"] = all(bool(item.get("ok")) for item in state["results"])
        resolve_step = _resolve_handoff_summary(preflight.get("resolve_handoff")) if not state["ok"] else None
        if isinstance(resolve_step, str):
            state["resolve_step"] = resolve_step
        state["summary"] = _build_summary(state)
        return state

    api_key = _get_api_key(args.api_key_env)
    headers = {"X-Rhumb-Key": api_key}
    state["config"]["api_key_preview"] = _mask_secret(api_key)

    for check in _build_checks(args):
        result = _execute_check(root=root, headers=headers, timeout=args.timeout, check=check)
        state["results"].append(result)
        receipt_id = result.get("receipt_id")
        if receipt_id:
            state["receipts"][check.name] = _fetch_receipt(
                root=root,
                headers=headers,
                timeout=args.timeout,
                receipt_id=receipt_id,
            )

    state["ok"] = all(bool(item.get("ok")) for item in state["results"])
    state["summary"] = _build_summary(state)
    return state


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-key-env", default=DEFAULT_API_KEY_ENV)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--storage-ref", default=DEFAULT_STORAGE_REF)
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--key", default=DEFAULT_KEY)
    parser.add_argument("--max-keys", type=int, default=10)
    parser.add_argument("--get-max-bytes", type=int, default=262144)
    parser.add_argument("--deny-bucket", default=DEFAULT_DENY_BUCKET)
    parser.add_argument("--deny-prefix", default=DEFAULT_DENY_PREFIX)
    parser.add_argument("--oversized-key", default=DEFAULT_OVERSIZED_KEY)
    parser.add_argument("--oversized-max-bytes", type=int, default=DEFAULT_OVERSIZED_MAX_BYTES)
    parser.add_argument("--json-out")
    parser.add_argument("--summary-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    state = run_flow(args)

    if args.json_out:
        output_path = Path(args.json_out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    if args.summary_only:
        print(state["summary"])
    else:
        print(json.dumps(state, indent=2))

    return 0 if state.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
