#!/usr/bin/env python3
"""Live hosted proof bundle for the AUD-18 GitHub Actions workflow-run read-first rail."""

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
DEFAULT_ACTIONS_REF = "gh_cli"
DEFAULT_BAD_ACTIONS_REF = "gh_missing"
DEFAULT_ALLOWED_REPOSITORY = "cli/cli"
DEFAULT_DENIED_REPOSITORY = "vercel/next.js"
DEFAULT_RUN_ID = 24204222943
DEFAULT_NOT_FOUND_RUN_ID = 99999999999
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


def _first_provider(payload: Any) -> dict[str, Any] | None:
    data = _extract_data(payload)
    if not isinstance(data, dict):
        return None
    providers = data.get("providers")
    if not isinstance(providers, list):
        return None
    for provider in providers:
        if isinstance(provider, dict) and provider.get("service_slug") == "github":
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
        if not isinstance(provider, dict) or provider.get("service_slug") != "github":
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
    resolve = _request_json(
        method="GET",
        url=f"{root}/v1/capabilities/workflow_run.list/resolve",
        headers={},
        payload=None,
        timeout=timeout,
    )
    credential_modes = _request_json(
        method="GET",
        url=f"{root}/v1/capabilities/workflow_run.list/credential-modes",
        headers={},
        payload=None,
        timeout=timeout,
    )

    resolve_provider = _first_provider(resolve.get("json"))
    modes_provider, byok_mode = _first_credential_mode(credential_modes.get("json"))
    resolve_handoff = _resolve_handoff(resolve.get("json"))

    resolve_ok = (
        resolve.get("status") == 200
        and isinstance(resolve_provider, dict)
        and (resolve_provider.get("available_for_execute") is True or isinstance(resolve_handoff, dict))
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
            "check": "workflow_run_list_resolve_surface",
            "ok": resolve_ok,
            "status": resolve.get("status"),
            "error": None if resolve_ok else "actions_capability_unavailable",
            "payload_check": None if resolve_ok else "missing_github_provider_or_resolve_handoff",
            "payload": {
                "provider": resolve_provider,
                "resolve_handoff": resolve_handoff,
                "response": resolve.get("json"),
            },
        },
        {
            "check": "workflow_run_list_credential_modes_surface",
            "ok": credential_modes_ok,
            "status": credential_modes.get("status"),
            "error": None if credential_modes_ok else "actions_credential_modes_unavailable",
            "payload_check": None if credential_modes_ok else "missing_github_byok_mode",
            "payload": credential_modes.get("json"),
        },
        {
            "check": "actions_bundle_configured",
            "ok": configured,
            "status": 200 if resolve.get("status") == 200 and credential_modes.get("status") == 200 else None,
            "error": None if configured else "actions_bundle_unconfigured",
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


def _make_list_success_check(*, repository: str) -> PayloadCheck:
    def _check(payload: Any) -> tuple[bool, str | None]:
        data = _extract_data(payload)
        if not isinstance(data, dict):
            return False, "missing_data"
        runs = data.get("workflow_runs")
        if not isinstance(runs, list) or not runs:
            return False, "expected_non_empty_workflow_runs"
        first = runs[0] if isinstance(runs[0], dict) else None
        if not isinstance(first, dict):
            return False, "first_workflow_run_missing"
        if first.get("repository") != repository:
            return False, f"unexpected_repository:{first.get('repository')}"
        if not isinstance(first.get("run_id"), int):
            return False, "first_run_id_missing"
        return True, None

    return _check


def _make_get_success_check(*, repository: str, run_id: int) -> PayloadCheck:
    def _check(payload: Any) -> tuple[bool, str | None]:
        data = _extract_data(payload)
        if not isinstance(data, dict):
            return False, "missing_data"
        if data.get("repository") != repository:
            return False, f"unexpected_repository:{data.get('repository')}"
        if data.get("run_id") != run_id:
            return False, f"unexpected_run_id:{data.get('run_id')}"
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
    parser = argparse.ArgumentParser(description="Run the hosted GitHub Actions workflow-run read-first proof bundle")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--actions-ref", default=DEFAULT_ACTIONS_REF)
    parser.add_argument("--bad-actions-ref", default=DEFAULT_BAD_ACTIONS_REF)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--repository", default=DEFAULT_ALLOWED_REPOSITORY)
    parser.add_argument("--denied-repository", default=DEFAULT_DENIED_REPOSITORY)
    parser.add_argument("--run-id", type=int, default=DEFAULT_RUN_ID)
    parser.add_argument("--not-found-run-id", type=int, default=DEFAULT_NOT_FOUND_RUN_ID)
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--api-key")
    parser.add_argument("--json-out")
    return parser


def _write_artifact(*, args: argparse.Namespace, artifact: dict[str, Any], ok: bool, results: list[dict[str, Any]]) -> int:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = Path(args.json_out) if args.json_out else ARTIFACTS_DIR / f"aud18-github-actions-hosted-proof-{_now_slug()}.json"
    artifact_path.write_text(json.dumps(artifact, indent=2))
    preflight = artifact.get("preflight") if isinstance(artifact.get("preflight"), dict) else {}
    resolve_step = _resolve_handoff_summary(preflight.get("resolve_handoff")) if not ok else None
    summary = {
        "ok": ok,
        "checks": [
            {
                "check": item["check"],
                "status": item["status"],
                "error": item.get("error"),
                "payload_check": item.get("payload_check"),
            }
            for item in results
        ],
    }
    if isinstance(resolve_step, str):
        summary["resolve_step"] = resolve_step
    print(str(artifact_path))
    print(json.dumps(summary, indent=2))
    return 0 if ok else 1


def main() -> int:
    args = build_parser().parse_args()
    root = args.base_url.rstrip("/")
    preflight = _run_preflight(root=root, timeout=args.timeout)
    results: list[dict[str, Any]] = list(preflight["results"])

    if args.preflight_only or not preflight["configured"]:
        ok = all(item["ok"] for item in results)
        artifact = {
            "ok": ok,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "preflight_only" if args.preflight_only else "blocked_preflight",
            "base_url": root,
            "actions_ref": args.actions_ref,
            "bad_actions_ref": args.bad_actions_ref,
            "repository": args.repository,
            "denied_repository": args.denied_repository,
            "run_id": args.run_id,
            "not_found_run_id": args.not_found_run_id,
            "api_key_hint": _mask(args.api_key or os.environ.get("RHUMB_API_KEY")),
            "preflight": {
                "configured": preflight["configured"],
                "available_for_execute": preflight["available_for_execute"],
                "resolve_handoff": preflight["resolve_handoff"],
                "resolve": preflight["resolve"],
                "credential_modes": preflight["credential_modes"],
            },
            "results": results,
        }
        resolve_step = _resolve_handoff_summary(preflight.get("resolve_handoff")) if not ok else None
        if isinstance(resolve_step, str):
            artifact["resolve_step"] = resolve_step
        return _write_artifact(args=args, artifact=artifact, ok=ok, results=results)

    api_key = (args.api_key or os.environ.get("RHUMB_API_KEY") or "").strip()
    if not api_key:
        raise SystemExit("Pass --api-key or set RHUMB_API_KEY")

    headers = {
        "Content-Type": "application/json",
        "X-Rhumb-Key": api_key,
    }

    checks = [
        (
            "workflow_run_list",
            f"{root}/v1/capabilities/workflow_run.list/execute",
            {
                "actions_ref": args.actions_ref,
                "repository": args.repository,
                "limit": args.limit,
            },
            200,
            None,
            _make_list_success_check(repository=args.repository),
            True,
        ),
        (
            "workflow_run_get",
            f"{root}/v1/capabilities/workflow_run.get/execute",
            {
                "actions_ref": args.actions_ref,
                "repository": args.repository,
                "run_id": args.run_id,
            },
            200,
            None,
            _make_get_success_check(repository=args.repository, run_id=args.run_id),
            True,
        ),
        (
            "bad_actions_ref_denial",
            f"{root}/v1/capabilities/workflow_run.list/execute",
            {
                "actions_ref": args.bad_actions_ref,
                "repository": args.repository,
                "limit": 1,
            },
            400,
            "actions_ref_invalid",
            None,
            False,
        ),
        (
            "out_of_scope_repository_denial",
            f"{root}/v1/capabilities/workflow_run.list/execute",
            {
                "actions_ref": args.actions_ref,
                "repository": args.denied_repository,
                "limit": 1,
            },
            403,
            "workflow_run_scope_denied",
            None,
            False,
        ),
        (
            "workflow_run_not_found_denial",
            f"{root}/v1/capabilities/workflow_run.get/execute",
            {
                "actions_ref": args.actions_ref,
                "repository": args.repository,
                "run_id": args.not_found_run_id,
            },
            404,
            "workflow_run_not_found",
            None,
            False,
        ),
    ]

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
        "mode": "full_proof",
        "base_url": root,
        "actions_ref": args.actions_ref,
        "bad_actions_ref": args.bad_actions_ref,
        "repository": args.repository,
        "denied_repository": args.denied_repository,
        "run_id": args.run_id,
        "not_found_run_id": args.not_found_run_id,
        "api_key_hint": _mask(api_key),
        "preflight": {
            "configured": preflight["configured"],
            "available_for_execute": preflight["available_for_execute"],
            "resolve_handoff": preflight["resolve_handoff"],
        },
        "results": results,
    }
    return _write_artifact(args=args, artifact=artifact, ok=ok, results=results)


if __name__ == "__main__":
    raise SystemExit(main())
