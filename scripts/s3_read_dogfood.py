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

    by_name = {item.get("name"): item for item in results}
    list_result = by_name.get("list") or {}
    head_result = by_name.get("head") or {}
    get_result = by_name.get("get") or {}
    deny_bucket = by_name.get("deny_bucket") or {}
    deny_prefix = by_name.get("deny_prefix") or {}
    oversized = by_name.get("oversized_get") or {}

    parts = [
        f"AUD-18 S3 dogfood {ok_count}/{total} checks green",
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
    if blocking:
        parts.append("blocked_on=hosted_storage_ref_config")

    return "; ".join(parts)


def run_flow(args: argparse.Namespace) -> dict[str, Any]:
    root = args.base_url.rstrip("/")
    api_key = _get_api_key(args.api_key_env)
    headers = {"X-Rhumb-Key": api_key}

    state: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": root,
        "config": {
            "api_key_env": args.api_key_env,
            "api_key_preview": _mask_secret(api_key),
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
        "results": [],
        "receipts": {},
    }

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
