#!/usr/bin/env python3
"""Live dogfood proof for the AUD-18 Zendesk ticket read-first rail.

Runs a bounded hosted proof bundle against:
- ticket.search
- ticket.get
- ticket.list_comments
- invalid support_ref denial
- denied out-of-scope ticket denial
- internal-comments denial

Writes a timestamped artifact under rhumb/artifacts/.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = ROOT / "artifacts"
DEFAULT_API_KEY_ITEM = "Rhumb API Key - pedro-dogfood"
DEFAULT_BASE_URL = "https://api.rhumb.dev"
DEFAULT_SUPPORT_REF = "st_zd"
DEFAULT_BAD_SUPPORT_REF = "st_missing"
DEFAULT_SEARCH_QUERY = "sort_by:created_at order_by:desc"
DEFAULT_TIMEOUT = 60.0


def _now_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _mask(value: str | None, head: int = 8, tail: int = 4) -> str | None:
    if not value:
        return None
    if len(value) <= head + tail:
        return value
    return f"{value[:head]}...{value[-tail:]}"


def _load_api_key_from_sop(item_name: str) -> str:
    result = subprocess.run(
        [
            "sop",
            "item",
            "get",
            item_name,
            "--vault",
            "OpenClaw Agents",
            "--fields",
            "credential",
            "--reveal",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _get_api_key(args: argparse.Namespace) -> str:
    if args.api_key:
        return args.api_key
    if os.environ.get("RHUMB_API_KEY"):
        return os.environ["RHUMB_API_KEY"].strip()
    return _load_api_key_from_sop(args.api_key_item)


def _request_json(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any] | None,
    timeout: float,
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
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


def _receipt_id_from_execute(payload: Any) -> str | None:
    data = _extract_data(payload)
    if not isinstance(data, dict):
        return None
    receipt_id = data.get("receipt_id")
    return receipt_id if isinstance(receipt_id, str) else None


def _fetch_receipt(*, root: str, headers: dict[str, str], timeout: float, receipt_id: str) -> dict[str, Any]:
    url = f"{root}/v1/receipts/{urllib.parse.quote(receipt_id)}"
    return _request_json(method="GET", url=url, headers=headers, payload=None, timeout=timeout)


def _check_result(
    *,
    name: str,
    response: dict[str, Any],
    expected_status: int,
    expected_error: str | None = None,
    fetch_receipt: bool,
    root: str,
    headers: dict[str, str],
    timeout: float,
) -> dict[str, Any]:
    payload = response.get("json")
    status = int(response.get("status") or 0)
    error = payload.get("error") if isinstance(payload, dict) else None
    ok = status == expected_status and (expected_error is None or error == expected_error)
    result: dict[str, Any] = {
        "check": name,
        "ok": ok,
        "status": status,
        "error": error,
        "payload": payload,
    }
    if fetch_receipt and isinstance(payload, dict):
        receipt_id = _receipt_id_from_execute(payload)
        if receipt_id:
            receipt = _fetch_receipt(root=root, headers=headers, timeout=timeout, receipt_id=receipt_id)
            result["receipt_id"] = receipt_id
            result["receipt_status"] = receipt.get("status")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the hosted Zendesk read-first dogfood proof bundle")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--support-ref", default=DEFAULT_SUPPORT_REF)
    parser.add_argument("--bad-support-ref", default=DEFAULT_BAD_SUPPORT_REF)
    parser.add_argument("--search-query", default=DEFAULT_SEARCH_QUERY)
    parser.add_argument("--ticket-id", type=int, default=1)
    parser.add_argument("--comments-ticket-id", type=int)
    parser.add_argument("--denied-ticket-id", type=int)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--api-key")
    parser.add_argument("--api-key-item", default=DEFAULT_API_KEY_ITEM)
    parser.add_argument("--json-out")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    api_key = _get_api_key(args)
    root = args.base_url.rstrip("/")
    headers = {
        "Content-Type": "application/json",
        "X-Rhumb-Key": api_key,
    }

    comments_ticket_id = args.comments_ticket_id or args.ticket_id
    checks = [
        (
            "ticket_search",
            f"{root}/v1/capabilities/ticket.search/execute",
            {"support_ref": args.support_ref, "query": args.search_query, "limit": 5},
            200,
            None,
            True,
        ),
        (
            "ticket_get",
            f"{root}/v1/capabilities/ticket.get/execute",
            {"support_ref": args.support_ref, "ticket_id": args.ticket_id},
            200,
            None,
            True,
        ),
        (
            "ticket_list_comments",
            f"{root}/v1/capabilities/ticket.list_comments/execute",
            {"support_ref": args.support_ref, "ticket_id": comments_ticket_id, "limit": 5},
            200,
            None,
            True,
        ),
        (
            "bad_support_ref_denial",
            f"{root}/v1/capabilities/ticket.search/execute",
            {"support_ref": args.bad_support_ref, "query": args.search_query, "limit": 5},
            400,
            "support_ref_invalid",
            False,
        ),
        (
            "internal_comment_denial",
            f"{root}/v1/capabilities/ticket.list_comments/execute",
            {
                "support_ref": args.support_ref,
                "ticket_id": comments_ticket_id,
                "limit": 5,
                "include_internal": True,
            },
            403,
            "support_internal_comments_denied",
            False,
        ),
    ]
    results: list[dict[str, Any]] = []
    if args.denied_ticket_id is None:
        results.append(
            {
                "check": "denied_ticket_scope",
                "ok": False,
                "status": 0,
                "error": "denied_ticket_id_required",
                "payload": {
                    "message": "Pass --denied-ticket-id with a real out-of-scope Zendesk ticket id to prove scope denial honestly."
                },
            }
        )
    else:
        checks.append(
            (
                "denied_ticket_scope",
                f"{root}/v1/capabilities/ticket.get/execute",
                {"support_ref": args.support_ref, "ticket_id": args.denied_ticket_id},
                403,
                "support_ticket_scope_denied",
                False,
            )
        )
    for name, url, payload, expected_status, expected_error, fetch_receipt in checks:
        response = _request_json(
            method="POST",
            url=url,
            headers=headers,
            payload=payload,
            timeout=args.timeout,
        )
        results.append(
            _check_result(
                name=name,
                response=response,
                expected_status=expected_status,
                expected_error=expected_error,
                fetch_receipt=fetch_receipt,
                root=root,
                headers=headers,
                timeout=args.timeout,
            )
        )

    ok = all(item["ok"] for item in results)
    artifact = {
        "ok": ok,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": root,
        "support_ref": args.support_ref,
        "api_key_hint": _mask(api_key),
        "results": results,
    }

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = Path(args.json_out) if args.json_out else ARTIFACTS_DIR / f"aud18-zendesk-hosted-proof-{_now_slug()}.json"
    artifact_path.write_text(json.dumps(artifact, indent=2))
    print(str(artifact_path))
    print(json.dumps({"ok": ok, "checks": [{"check": item["check"], "status": item["status"], "error": item.get("error")} for item in results]}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
