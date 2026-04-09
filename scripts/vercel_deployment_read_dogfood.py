#!/usr/bin/env python3
"""Live hosted proof bundle for the AUD-18 Vercel deployment read-first rail."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = ROOT / "artifacts"
DEFAULT_BASE_URL = "https://api.rhumb.dev"
DEFAULT_DEPLOYMENT_REF = "dep_rhumb"
DEFAULT_BAD_DEPLOYMENT_REF = "dep_missing"
DEFAULT_ALLOWED_PROJECT_ID = "prj_xkjVLZiODE5z9WVa9mNyMnNroJBf"
DEFAULT_ALLOWED_DEPLOYMENT_ID = "dpl_XDnnZwuVtFCKtaqWxxRUNWLVBa63"
DEFAULT_DENIED_DEPLOYMENT_ID = "dpl_3evXfwPoNSewbLVThSTGhdPg92pV"
DEFAULT_ALLOWED_TARGET = "production"
DEFAULT_DENIED_TARGET = "preview"
DEFAULT_TIMEOUT = 60.0


PayloadCheck = Callable[[Any], Tuple[bool, Optional[str]]]


def _now_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _mask(value: str | None, head: int = 8, tail: int = 4) -> str | None:
    if not value:
        return None
    if len(value) <= head + tail:
        return value
    return f"{value[:head]}...{value[-tail:]}"


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


def _make_list_success_check(*, project_id: str, target: str) -> PayloadCheck:
    def _check(payload: Any) -> tuple[bool, str | None]:
        data = _extract_data(payload)
        if not isinstance(data, dict):
            return False, "missing_data"
        deployments = data.get("deployments")
        if not isinstance(deployments, list) or not deployments:
            return False, "expected_non_empty_deployments"
        first = deployments[0] if isinstance(deployments[0], dict) else None
        if not isinstance(first, dict):
            return False, "first_deployment_missing"
        if first.get("project_id") != project_id:
            return False, f"unexpected_project_id:{first.get('project_id')}"
        if first.get("target") != target:
            return False, f"unexpected_target:{first.get('target')}"
        return True, None

    return _check


def _make_get_success_check(*, deployment_id: str, project_id: str, target: str) -> PayloadCheck:
    def _check(payload: Any) -> tuple[bool, str | None]:
        data = _extract_data(payload)
        if not isinstance(data, dict):
            return False, "missing_data"
        if data.get("deployment_id") != deployment_id:
            return False, f"unexpected_deployment_id:{data.get('deployment_id')}"
        if data.get("project_id") != project_id:
            return False, f"unexpected_project_id:{data.get('project_id')}"
        if data.get("target") != target:
            return False, f"unexpected_target:{data.get('target')}"
        return True, None

    return _check


def _check_result(
    *,
    name: str,
    response: dict[str, Any],
    expected_status: int,
    expected_error: str | None = None,
    payload_check: PayloadCheck | None = None,
    fetch_receipt: bool,
    root: str,
    headers: dict[str, str],
    timeout: float,
) -> dict[str, Any]:
    payload = response.get("json")
    status = int(response.get("status") or 0)
    error = payload.get("error") if isinstance(payload, dict) else None
    payload_ok = True
    payload_note = None
    if payload_check is not None and status == expected_status and (expected_error is None or error == expected_error):
        payload_ok, payload_note = payload_check(payload)
    ok = status == expected_status and (expected_error is None or error == expected_error) and payload_ok
    result: dict[str, Any] = {
        "check": name,
        "ok": ok,
        "status": status,
        "error": error,
        "payload_check": payload_note,
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
    parser = argparse.ArgumentParser(description="Run the hosted Vercel deployment read-first proof bundle")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--deployment-ref", default=DEFAULT_DEPLOYMENT_REF)
    parser.add_argument("--bad-deployment-ref", default=DEFAULT_BAD_DEPLOYMENT_REF)
    parser.add_argument("--project-id", default=DEFAULT_ALLOWED_PROJECT_ID)
    parser.add_argument("--deployment-id", default=DEFAULT_ALLOWED_DEPLOYMENT_ID)
    parser.add_argument("--denied-deployment-id", default=DEFAULT_DENIED_DEPLOYMENT_ID)
    parser.add_argument("--allowed-target", default=DEFAULT_ALLOWED_TARGET)
    parser.add_argument("--denied-target", default=DEFAULT_DENIED_TARGET)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--api-key")
    parser.add_argument("--json-out")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    api_key = (args.api_key or os.environ.get("RHUMB_API_KEY") or "").strip()
    if not api_key:
        raise SystemExit("Pass --api-key or set RHUMB_API_KEY")

    root = args.base_url.rstrip("/")
    headers = {
        "Content-Type": "application/json",
        "X-Rhumb-Key": api_key,
    }

    checks = [
        (
            "deployment_list",
            f"{root}/v1/capabilities/deployment.list/execute",
            {
                "deployment_ref": args.deployment_ref,
                "project_id": args.project_id,
                "target": args.allowed_target,
                "limit": args.limit,
            },
            200,
            None,
            _make_list_success_check(project_id=args.project_id, target=args.allowed_target),
            True,
        ),
        (
            "deployment_get",
            f"{root}/v1/capabilities/deployment.get/execute",
            {
                "deployment_ref": args.deployment_ref,
                "deployment_id": args.deployment_id,
            },
            200,
            None,
            _make_get_success_check(
                deployment_id=args.deployment_id,
                project_id=args.project_id,
                target=args.allowed_target,
            ),
            True,
        ),
        (
            "bad_deployment_ref_denial",
            f"{root}/v1/capabilities/deployment.list/execute",
            {
                "deployment_ref": args.bad_deployment_ref,
                "project_id": args.project_id,
                "limit": 1,
            },
            400,
            "deployment_ref_invalid",
            None,
            False,
        ),
        (
            "out_of_scope_deployment_denial",
            f"{root}/v1/capabilities/deployment.get/execute",
            {
                "deployment_ref": args.deployment_ref,
                "deployment_id": args.denied_deployment_id,
            },
            403,
            "deployment_scope_denied",
            None,
            False,
        ),
        (
            "out_of_scope_target_denial",
            f"{root}/v1/capabilities/deployment.list/execute",
            {
                "deployment_ref": args.deployment_ref,
                "project_id": args.project_id,
                "target": args.denied_target,
                "limit": 1,
            },
            403,
            "deployment_target_scope_denied",
            None,
            False,
        ),
    ]

    results: list[dict[str, Any]] = []
    for name, url, payload, expected_status, expected_error, payload_check, fetch_receipt in checks:
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
                payload_check=payload_check,
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
        "deployment_ref": args.deployment_ref,
        "project_id": args.project_id,
        "deployment_id": args.deployment_id,
        "denied_deployment_id": args.denied_deployment_id,
        "allowed_target": args.allowed_target,
        "denied_target": args.denied_target,
        "api_key_hint": _mask(api_key),
        "results": results,
    }

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = Path(args.json_out) if args.json_out else ARTIFACTS_DIR / f"aud18-vercel-hosted-proof-{_now_slug()}.json"
    artifact_path.write_text(json.dumps(artifact, indent=2))
    print(str(artifact_path))
    print(json.dumps({"ok": ok, "checks": [{"check": item["check"], "status": item["status"], "error": item.get("error"), "payload_check": item.get("payload_check")} for item in results]}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
