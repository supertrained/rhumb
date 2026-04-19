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
DEFAULT_SEARCH_QUERY = "status:open"
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


def _first_provider(payload: Any) -> dict[str, Any] | None:
    data = _extract_data(payload)
    if not isinstance(data, dict):
        return None
    providers = data.get("providers")
    if not isinstance(providers, list):
        return None
    for provider in providers:
        if isinstance(provider, dict) and provider.get("service_slug") == "zendesk":
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
        if not isinstance(provider, dict) or provider.get("service_slug") != "zendesk":
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
    if isinstance(handoff.get("setup_url"), str):
        parts.append(f"setup_url={handoff['setup_url']}")
    if isinstance(handoff.get("resolve_url"), str):
        parts.append(f"resolve_url={handoff['resolve_url']}")
    if isinstance(handoff.get("credential_modes_url"), str):
        parts.append(f"credential_modes_url={handoff['credential_modes_url']}")
    if not parts:
        return None
    return "Resolve next step: " + ", ".join(parts)


def _run_preflight(*, root: str, timeout: float) -> dict[str, Any]:
    resolve = _request_json(
        method="GET",
        url=f"{root}/v1/capabilities/ticket.search/resolve",
        headers={},
        payload=None,
        timeout=timeout,
    )
    credential_modes = _request_json(
        method="GET",
        url=f"{root}/v1/capabilities/ticket.search/credential-modes",
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
            "check": "ticket_search_resolve_surface",
            "ok": resolve_ok,
            "status": resolve.get("status"),
            "error": None if resolve_ok else "support_capability_unavailable",
            "payload_check": None if resolve_ok else "missing_zendesk_provider_or_resolve_handoff",
            "payload": {
                "provider": resolve_provider,
                "resolve_handoff": resolve_handoff,
                "response": resolve.get("json"),
            },
        },
        {
            "check": "ticket_search_credential_modes_surface",
            "ok": credential_modes_ok,
            "status": credential_modes.get("status"),
            "error": None if credential_modes_ok else "support_credential_modes_unavailable",
            "payload_check": None if credential_modes_ok else "missing_zendesk_byok_mode",
            "payload": credential_modes.get("json"),
        },
        {
            "check": "support_bundle_configured",
            "ok": configured,
            "status": 200 if resolve.get("status") == 200 and credential_modes.get("status") == 200 else None,
            "error": None if configured else "support_bundle_unconfigured",
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


def _write_artifact(
    *,
    artifact: dict[str, Any],
    artifact_path: Path,
    ok: bool,
    results: list[dict[str, Any]],
    resolve_step: str | None,
) -> int:
    artifact_path.write_text(json.dumps(artifact, indent=2))
    print(str(artifact_path))
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
    print(json.dumps(summary, indent=2))
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the hosted Zendesk read-first dogfood proof bundle")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--support-ref", default=DEFAULT_SUPPORT_REF)
    parser.add_argument("--bad-support-ref", default=DEFAULT_BAD_SUPPORT_REF)
    parser.add_argument("--preflight-only", action="store_true")
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
    root = args.base_url.rstrip("/")
    preflight = _run_preflight(root=root, timeout=args.timeout)
    results: list[dict[str, Any]] = list(preflight["results"])

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = Path(args.json_out) if args.json_out else ARTIFACTS_DIR / f"aud18-zendesk-hosted-proof-{_now_slug()}.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)

    if args.preflight_only or not preflight["configured"]:
        ok = all(item["ok"] for item in results)
        resolve_step = _resolve_handoff_summary(preflight.get("resolve_handoff")) if not ok else None
        artifact = {
            "ok": ok,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "preflight_only" if args.preflight_only else "blocked_preflight",
            "base_url": root,
            "support_ref": args.support_ref,
            "bad_support_ref": args.bad_support_ref,
            "search_query": args.search_query,
            "ticket_id": args.ticket_id,
            "comments_ticket_id": args.comments_ticket_id or args.ticket_id,
            "denied_ticket_id": args.denied_ticket_id,
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
        if isinstance(resolve_step, str):
            artifact["resolve_step"] = resolve_step
        return _write_artifact(
            artifact=artifact,
            artifact_path=artifact_path,
            ok=ok,
            results=results,
            resolve_step=resolve_step,
        )

    api_key = _get_api_key(args)
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
        "mode": "full_proof",
        "base_url": root,
        "support_ref": args.support_ref,
        "api_key_hint": _mask(api_key),
        "preflight": {
            "configured": preflight["configured"],
            "available_for_execute": preflight["available_for_execute"],
            "resolve_handoff": preflight["resolve_handoff"],
            "resolve": preflight["resolve"],
            "credential_modes": preflight["credential_modes"],
        },
        "results": results,
    }
    return _write_artifact(
        artifact=artifact,
        artifact_path=artifact_path,
        ok=ok,
        results=results,
        resolve_step=None,
    )


if __name__ == "__main__":
    raise SystemExit(main())
