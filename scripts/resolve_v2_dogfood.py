#!/usr/bin/env python3
"""Repeatable live dogfood harness for the Resolve v2 surface.

This script exercises the honest post-build operator loop for Rhumb's v2 API:

1. Health + capability catalog read
2. Optional account-policy smoke test
3. Layer 2 capability estimate + execute
4. Layer 2 receipt + explanation fetch
5. Layer 1 provider detail + exact-provider execute
6. Layer 1 receipt fetch
7. Billing / trust / audit reads
8. Receipt-chain verification

Honest boundary:
- This is an operator dogfood harness, not a unit test.
- It expects a real Rhumb API key in an environment variable.
- It does not publish anything externally or mutate product state unless
  policy-smoke flags are supplied.
- When policy write flags are used, prefer a dedicated internal dogfood org.

Examples:
  export RHUMB_DOGFOOD_API_KEY=rhumb_...
  python3 scripts/resolve_v2_dogfood.py --json
  python3 scripts/resolve_v2_dogfood.py --policy-provider-preference brave-search-api
  python3 scripts/resolve_v2_dogfood.py --skip-layer1 --json-out /tmp/resolve-v2-dogfood.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from typing import Any
from urllib.parse import quote
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "https://api.rhumb.dev"
DEFAULT_API_KEY_ENV = "RHUMB_DOGFOOD_API_KEY"
DEFAULT_TIMEOUT = 30.0
DEFAULT_CAPABILITY = "search.query"
DEFAULT_PROVIDER = "brave-search-api"
DEFAULT_CREDENTIAL_MODE = "rhumb_managed"
DEFAULT_PARAMETERS = {
    "query": "best AI agent observability tools",
    "numResults": 3,
}
DEFAULT_INTERFACE = "dogfood"
DEFAULT_MAX_READ_LIMIT = 10


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


def _get_api_key(env_name: str) -> str:
    value = os.environ.get(env_name, "").strip()
    if not value:
        raise RuntimeError(f"Missing API key. Set the {env_name} environment variable.")
    return value


def _json_or_default(raw: str, fallback: dict[str, Any]) -> dict[str, Any]:
    if not raw.strip():
        return dict(fallback)
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object")
    return parsed


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
        "User-Agent": "rhumb-resolve-v2-dogfood/0.1",
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


def _extract_error_detail(response: dict[str, Any]) -> str:
    payload = response.get("json")
    if isinstance(payload, dict):
        for key in ("detail", "error", "message"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        error = payload.get("error")
        if isinstance(error, dict):
            for key in ("message", "detail", "code"):
                value = error.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        data = payload.get("data")
        if isinstance(data, dict):
            for key in ("detail", "error", "message"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    text = (response.get("text") or "").strip()
    return text or f"HTTP {response.get('status')}"


def _expect_success(label: str, response: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    if 200 <= int(response.get("status") or 0) < 300:
        return response
    detail = _extract_error_detail(response)
    state["last_error_response"] = {
        "label": label,
        "status": response.get("status"),
        "detail": detail,
        "url": response.get("url"),
    }
    raise FlowError(f"{label} failed: {detail}", state)


def _extract_data(payload: dict[str, Any] | None) -> Any:
    if isinstance(payload, dict) and "data" in payload:
        return payload.get("data")
    return payload


def build_l2_execute_payload(
    *,
    parameters: dict[str, Any],
    provider: str,
    credential_mode: str,
    interface: str,
    max_cost_usd: float | None,
    provider_preference: list[str] | None,
) -> dict[str, Any]:
    policy: dict[str, Any] = {}
    if max_cost_usd is not None:
        policy["max_cost_usd"] = max_cost_usd
    if provider_preference:
        policy["provider_preference"] = provider_preference

    payload: dict[str, Any] = {
        "parameters": parameters,
        "credential_mode": credential_mode,
        "interface": interface,
    }
    if policy:
        payload["policy"] = policy
    if provider and not provider_preference:
        payload["policy"] = {
            **payload.get("policy", {}),
            "provider_preference": [provider],
        }
    return payload


def build_l1_execute_payload(
    *,
    capability: str,
    parameters: dict[str, Any],
    credential_mode: str,
    interface: str,
    max_cost_usd: float | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "capability": capability,
        "parameters": parameters,
        "credential_mode": credential_mode,
        "interface": interface,
        "idempotency_key": f"dogfood-{uuid.uuid4().hex}",
    }
    if max_cost_usd is not None:
        payload["policy"] = {"max_cost_usd": max_cost_usd}
    return payload


def extract_receipt_id(data: dict[str, Any] | None) -> str | None:
    if not isinstance(data, dict):
        return None
    for key in ("receipt_id",):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    rhumb = data.get("_rhumb")
    if isinstance(rhumb, dict):
        value = rhumb.get("receipt_id")
        if isinstance(value, str) and value:
            return value
    rhumb_v2 = data.get("_rhumb_v2")
    if isinstance(rhumb_v2, dict):
        value = rhumb_v2.get("receipt_id")
        if isinstance(value, str) and value:
            return value
    return None


def extract_execution_id(data: dict[str, Any] | None) -> str | None:
    if not isinstance(data, dict):
        return None
    value = data.get("execution_id")
    return value if isinstance(value, str) and value else None


def extract_explanation_id(data: dict[str, Any] | None) -> str | None:
    if not isinstance(data, dict):
        return None
    rhumb_v2 = data.get("_rhumb_v2")
    if isinstance(rhumb_v2, dict):
        value = rhumb_v2.get("explanation_id")
        if isinstance(value, str) and value:
            return value
    return None


def _build_summary(state: dict[str, Any]) -> str:
    parts = ["Resolve v2 dogfood complete"]

    l2 = ((state.get("layer2") or {}).get("execute") or {}).get("data")
    l2_receipt = ((state.get("layer2") or {}).get("receipt") or {}).get("receipt_id")
    if isinstance(l2, dict):
        parts.append(
            "L2 "
            f"{state.get('config', {}).get('capability')}"
            f" via {l2.get('provider_used') or state.get('config', {}).get('provider')}"
            f" exec={extract_execution_id(l2) or 'n/a'}"
            f" receipt={l2_receipt or extract_receipt_id(l2) or 'n/a'}"
        )

    l1 = ((state.get("layer1") or {}).get("execute") or {}).get("data")
    l1_receipt = ((state.get("layer1") or {}).get("receipt") or {}).get("receipt_id")
    if isinstance(l1, dict):
        parts.append(
            "L1 "
            f"provider={state.get('config', {}).get('provider')}"
            f" exec={extract_execution_id(l1) or 'n/a'}"
            f" receipt={l1_receipt or extract_receipt_id(l1) or 'n/a'}"
        )

    billing = ((state.get("billing") or {}).get("summary") or {}).get("data") or {}
    if isinstance(billing, dict):
        parts.append(f"billing_events={billing.get('events_count', 'n/a')}")

    audit = ((state.get("audit") or {}).get("status") or {}).get("data") or {}
    if isinstance(audit, dict):
        parts.append(f"audit_events={audit.get('total_events', 'n/a')}")

    return "; ".join(parts)


def run_flow(args: argparse.Namespace) -> dict[str, Any]:
    root = args.base_url.rstrip("/")
    v2_root = f"{root}/v2"
    api_key = _get_api_key(args.api_key_env)
    parameters = _json_or_default(args.parameters_json, DEFAULT_PARAMETERS)
    headers = {"X-Rhumb-Key": api_key}

    state: dict[str, Any] = {
        "config": {
            "base_url": root,
            "v2_root": v2_root,
            "api_key_env": args.api_key_env,
            "api_key_preview": _mask_secret(api_key),
            "capability": args.capability,
            "provider": args.provider,
            "credential_mode": args.credential_mode,
            "interface": args.interface,
            "skip_layer1": args.skip_layer1,
            "policy_provider_preference": args.policy_provider_preference,
            "policy_max_cost_usd": args.policy_max_cost_usd,
        },
        "started_at": int(time.time()),
    }

    health_resp = _expect_success(
        "v2 health",
        _http_json("GET", f"{v2_root}/health", timeout=args.timeout),
        state,
    )
    state["health"] = _extract_data(health_resp.get("json"))

    capabilities_resp = _expect_success(
        "v2 capabilities",
        _http_json(
            "GET",
            f"{v2_root}/capabilities?limit={args.read_limit}",
            headers=headers,
            timeout=args.timeout,
        ),
        state,
    )
    state["capabilities"] = _extract_data(capabilities_resp.get("json"))

    policy_state: dict[str, Any] = {}
    current_policy_resp = _expect_success(
        "v2 policy get",
        _http_json("GET", f"{v2_root}/policy", headers=headers, timeout=args.timeout),
        state,
    )
    policy_state["before"] = _extract_data(current_policy_resp.get("json"))

    if args.policy_provider_preference or args.policy_max_cost_usd is not None:
        policy_payload: dict[str, Any] = {}
        if args.policy_provider_preference:
            policy_payload["provider_preference"] = [args.policy_provider_preference]
        if args.policy_max_cost_usd is not None:
            policy_payload["max_cost_usd"] = args.policy_max_cost_usd
        policy_put_resp = _expect_success(
            "v2 policy put",
            _http_json(
                "PUT",
                f"{v2_root}/policy",
                payload=policy_payload,
                headers=headers,
                timeout=args.timeout,
            ),
            state,
        )
        policy_state["written"] = policy_payload
        policy_state["after_put"] = _extract_data(policy_put_resp.get("json"))

        confirmed_policy_resp = _expect_success(
            "v2 policy confirm",
            _http_json("GET", f"{v2_root}/policy", headers=headers, timeout=args.timeout),
            state,
        )
        policy_state["after_confirm"] = _extract_data(confirmed_policy_resp.get("json"))

    state["policy"] = policy_state

    estimate_resp = _expect_success(
        "v2 layer2 estimate",
        _http_json(
            "GET",
            (
                f"{v2_root}/capabilities/{quote(args.capability, safe='')}/execute/estimate"
                f"?provider={quote(args.provider, safe='')}"
                f"&credential_mode={quote(args.credential_mode, safe='')}"
            ),
            headers=headers,
            timeout=args.timeout,
        ),
        state,
    )
    state["layer2"] = {
        "estimate": {
            "data": _extract_data(estimate_resp.get("json")),
            "headers": estimate_resp.get("headers"),
        }
    }

    l2_payload = build_l2_execute_payload(
        parameters=parameters,
        provider=args.provider,
        credential_mode=args.credential_mode,
        interface=args.interface,
        max_cost_usd=args.max_cost_usd,
        provider_preference=[args.provider] if args.force_provider_preference else None,
    )
    l2_execute_resp = _expect_success(
        "v2 layer2 execute",
        _http_json(
            "POST",
            f"{v2_root}/capabilities/{quote(args.capability, safe='')}/execute",
            payload=l2_payload,
            headers=headers,
            timeout=args.timeout,
        ),
        state,
    )
    l2_data = _extract_data(l2_execute_resp.get("json"))
    state["layer2"]["execute"] = {
        "request": l2_payload,
        "data": l2_data,
        "headers": l2_execute_resp.get("headers"),
    }

    l2_receipt_id = extract_receipt_id(l2_data)
    if not l2_receipt_id:
        raise FlowError("v2 layer2 execute returned no receipt_id", state)

    l2_receipt_resp = _expect_success(
        "v2 layer2 receipt",
        _http_json("GET", f"{v2_root}/receipts/{quote(l2_receipt_id, safe='')}", headers=headers, timeout=args.timeout),
        state,
    )
    state["layer2"]["receipt"] = _extract_data(l2_receipt_resp.get("json"))

    l2_explanation_resp = _expect_success(
        "v2 layer2 explanation",
        _http_json(
            "GET",
            f"{v2_root}/receipts/{quote(l2_receipt_id, safe='')}/explanation",
            headers=headers,
            timeout=args.timeout,
        ),
        state,
    )
    state["layer2"]["explanation"] = _extract_data(l2_explanation_resp.get("json"))

    if not args.skip_layer1:
        provider_resp = _expect_success(
            "v2 provider detail",
            _http_json(
                "GET",
                f"{v2_root}/providers/{quote(args.provider, safe='')}",
                headers=headers,
                timeout=args.timeout,
            ),
            state,
        )
        l1_payload = build_l1_execute_payload(
            capability=args.capability,
            parameters=parameters,
            credential_mode=args.credential_mode,
            interface=args.interface,
            max_cost_usd=args.max_cost_usd,
        )
        l1_execute_resp = _expect_success(
            "v2 layer1 execute",
            _http_json(
                "POST",
                f"{v2_root}/providers/{quote(args.provider, safe='')}/execute",
                payload=l1_payload,
                headers=headers,
                timeout=args.timeout,
            ),
            state,
        )
        l1_data = _extract_data(l1_execute_resp.get("json"))
        state["layer1"] = {
            "provider": _extract_data(provider_resp.get("json")),
            "execute": {
                "request": l1_payload,
                "data": l1_data,
                "headers": l1_execute_resp.get("headers"),
            },
        }

        l1_receipt_id = extract_receipt_id(l1_data)
        if not l1_receipt_id:
            raise FlowError("v2 layer1 execute returned no receipt_id", state)

        l1_receipt_resp = _expect_success(
            "v2 layer1 receipt",
            _http_json("GET", f"{v2_root}/receipts/{quote(l1_receipt_id, safe='')}", headers=headers, timeout=args.timeout),
            state,
        )
        state["layer1"]["receipt"] = _extract_data(l1_receipt_resp.get("json"))

    billing_summary_resp = _expect_success(
        "v2 billing summary",
        _http_json("GET", f"{v2_root}/billing/summary", headers=headers, timeout=args.timeout),
        state,
    )
    billing_events_resp = _expect_success(
        "v2 billing events",
        _http_json(
            "GET",
            f"{v2_root}/billing/events?limit={args.read_limit}",
            headers=headers,
            timeout=args.timeout,
        ),
        state,
    )
    billing_stream_resp = _expect_success(
        "v2 billing stream status",
        _http_json("GET", f"{v2_root}/billing/stream/status", timeout=args.timeout),
        state,
    )
    state["billing"] = {
        "summary": {"data": _extract_data(billing_summary_resp.get("json"))},
        "events": {"data": _extract_data(billing_events_resp.get("json"))},
        "stream_status": {"data": _extract_data(billing_stream_resp.get("json"))},
    }

    trust_summary_resp = _expect_success(
        "v2 trust summary",
        _http_json("GET", f"{v2_root}/trust/summary", headers=headers, timeout=args.timeout),
        state,
    )
    trust_providers_resp = _expect_success(
        "v2 trust providers",
        _http_json(
            "GET",
            f"{v2_root}/trust/providers?limit={args.read_limit}",
            headers=headers,
            timeout=args.timeout,
        ),
        state,
    )
    state["trust"] = {
        "summary": {"data": _extract_data(trust_summary_resp.get("json"))},
        "providers": {"data": _extract_data(trust_providers_resp.get("json"))},
    }

    audit_status_resp = _expect_success(
        "v2 audit status",
        _http_json("GET", f"{v2_root}/audit/status", headers=headers, timeout=args.timeout),
        state,
    )
    audit_events_resp = _expect_success(
        "v2 audit events",
        _http_json(
            "GET",
            f"{v2_root}/audit/events?limit={args.read_limit}",
            headers=headers,
            timeout=args.timeout,
        ),
        state,
    )
    state["audit"] = {
        "status": {"data": _extract_data(audit_status_resp.get("json"))},
        "events": {"data": _extract_data(audit_events_resp.get("json"))},
    }

    if args.audit_export:
        audit_export_resp = _expect_success(
            "v2 audit export",
            _http_json(
                "POST",
                f"{v2_root}/audit/export?format=json",
                headers=headers,
                timeout=args.timeout,
            ),
            state,
        )
        state["audit"]["export"] = {"data": _extract_data(audit_export_resp.get("json"))}

    receipt_chain_resp = _expect_success(
        "v2 receipt chain verify",
        _http_json(
            "GET",
            f"{v2_root}/receipts/chain/verify?limit={max(20, args.read_limit)}",
            headers=headers,
            timeout=args.timeout,
        ),
        state,
    )
    state["receipt_chain"] = _extract_data(receipt_chain_resp.get("json"))

    state["ok"] = True
    state["summary"] = _build_summary(state)
    return state


def _print_human(payload: dict[str, Any]) -> None:
    print(payload.get("summary") or ("OK" if payload.get("ok") else "FAILED"))
    print()

    config = payload.get("config") or {}
    print("Config")
    print(f"- base_url: {config.get('base_url')}")
    print(f"- capability: {config.get('capability')}")
    print(f"- provider: {config.get('provider')}")
    print(f"- credential_mode: {config.get('credential_mode')}")
    print(f"- api_key: {config.get('api_key_preview')}")

    health = payload.get("health") or {}
    if health:
        print()
        print("Health")
        print(f"- status: {health.get('status')}")
        print(f"- version: {health.get('version')}")
        print(f"- layer: {health.get('layer')}")

    layer2 = payload.get("layer2") or {}
    if layer2:
        execute_data = (layer2.get("execute") or {}).get("data") or {}
        print()
        print("Layer 2")
        print(f"- provider_used: {execute_data.get('provider_used')}")
        print(f"- execution_id: {extract_execution_id(execute_data)}")
        print(f"- receipt_id: {extract_receipt_id(execute_data)}")
        print(f"- explanation_id: {extract_explanation_id(execute_data)}")

    layer1 = payload.get("layer1") or {}
    if layer1:
        execute_data = (layer1.get("execute") or {}).get("data") or {}
        print()
        print("Layer 1")
        print(f"- provider_used: {execute_data.get('provider_used')}")
        print(f"- execution_id: {extract_execution_id(execute_data)}")
        print(f"- receipt_id: {extract_receipt_id(execute_data)}")

    billing = ((payload.get("billing") or {}).get("summary") or {}).get("data") or {}
    if billing:
        print()
        print("Billing")
        print(f"- total_charged_usd: {billing.get('total_charged_usd')}")
        print(f"- execution_count: {billing.get('execution_count')}")
        print(f"- events_count: {billing.get('events_count')}")

    audit = ((payload.get("audit") or {}).get("status") or {}).get("data") or {}
    if audit:
        print()
        print("Audit")
        print(f"- total_events: {audit.get('total_events')}")
        print(f"- chain_verified: {audit.get('chain_verified')}")
        print(f"- latest_sequence: {audit.get('latest_sequence')}")

    if payload.get("last_error_response"):
        err = payload["last_error_response"]
        print()
        print("Last error response")
        print(f"- label: {err.get('label')}")
        print(f"- status: {err.get('status')}")
        print(f"- detail: {err.get('detail')}")
        print(f"- url: {err.get('url')}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Rhumb API root URL (without /v2)")
    parser.add_argument(
        "--api-key-env",
        default=DEFAULT_API_KEY_ENV,
        help="Environment variable containing a real Rhumb API key",
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="HTTP timeout in seconds")
    parser.add_argument("--capability", default=DEFAULT_CAPABILITY, help="Capability ID for L1/L2 execute")
    parser.add_argument("--provider", default=DEFAULT_PROVIDER, help="Provider slug for estimate and L1 execute")
    parser.add_argument(
        "--credential-mode",
        default=DEFAULT_CREDENTIAL_MODE,
        help="Credential mode for both execute paths",
    )
    parser.add_argument(
        "--parameters-json",
        default=json.dumps(DEFAULT_PARAMETERS),
        help="JSON object for execute parameters",
    )
    parser.add_argument("--interface", default=DEFAULT_INTERFACE, help="Interface label for analytics")
    parser.add_argument(
        "--max-cost-usd",
        type=float,
        default=0.05,
        help="Per-call max_cost_usd ceiling for L1 and L2 execute",
    )
    parser.add_argument(
        "--force-provider-preference",
        action="store_true",
        help="Send provider_preference=[provider] on the Layer 2 execute call",
    )
    parser.add_argument(
        "--policy-provider-preference",
        help="Optional durable org policy smoke test: write provider_preference=[value] before executing",
    )
    parser.add_argument(
        "--policy-max-cost-usd",
        type=float,
        help="Optional durable org policy smoke test: write max_cost_usd before executing",
    )
    parser.add_argument("--skip-layer1", action="store_true", help="Skip exact-provider Layer 1 execute")
    parser.add_argument("--audit-export", action="store_true", help="Also hit POST /v2/audit/export?format=json")
    parser.add_argument("--read-limit", type=int, default=DEFAULT_MAX_READ_LIMIT, help="Limit for read endpoints")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument("--json-out", help="Write the result payload to a file")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        payload = run_flow(args)
        exit_code = 0
    except FlowError as exc:
        payload = {
            "ok": False,
            "summary": str(exc),
            **exc.state,
        }
        exit_code = 1
    except Exception as exc:  # pragma: no cover - defensive CLI fallback
        payload = {
            "ok": False,
            "summary": str(exc),
        }
        exit_code = 1

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_human(payload)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
