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
  python3 scripts/resolve_v2_dogfood.py --profile beacon --json
  python3 scripts/resolve_v2_dogfood.py --all-profiles --json-out /tmp/resolve-v2-dogfood-fleet.json
  python3 scripts/resolve_v2_dogfood.py --policy-provider-preference brave-search
  python3 scripts/resolve_v2_dogfood.py --skip-layer1 --json-out /tmp/resolve-v2-dogfood.json

Fallback secret path:
- If `RHUMB_DOGFOOD_API_KEY` is absent, the script will try to load
  `Rhumb API Key - pedro-dogfood` from the `OpenClaw Agents` 1Password vault
  via `sop`.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "https://api.rhumb.dev"
DEFAULT_API_KEY_ENV = "RHUMB_DOGFOOD_API_KEY"
DEFAULT_ADMIN_KEY_ENV = "RHUMB_ADMIN_SECRET"
DEFAULT_ADMIN_KEY_ENV_FALLBACKS = ("RHUMB_ADMIN_KEY",)
DEFAULT_API_KEY_ITEM = "Rhumb API Key - pedro-dogfood"
DEFAULT_ADMIN_KEY_ITEM = "Rhumb Admin Secret (Railway)"
DEFAULT_API_KEY_VAULT = "OpenClaw Agents"
DEFAULT_BOOTSTRAP_ORG_ID = "org_aud3_verifier"
DEFAULT_BOOTSTRAP_AGENT_NAME = "Pedro AUD-3 Verifier"
DEFAULT_TIMEOUT = 30.0
DEFAULT_CAPABILITY = "search.query"
DEFAULT_PROVIDER = "brave-search"
DEFAULT_CREDENTIAL_MODE = "rhumb_managed"
DEFAULT_PARAMETERS = {
    "query": "best AI agent observability tools",
    "numResults": 3,
}
DEFAULT_PARAMETERS_JSON = json.dumps(DEFAULT_PARAMETERS)
DEFAULT_INTERFACE = "dogfood"
DEFAULT_MAX_READ_LIMIT = 10
DEFAULT_PROFILE = "pedro"
DEFAULT_FLEET_STATUS_PROFILES = ("keel", "helm", "beacon")
DEFAULT_FLEET_STATUS_MAX_AGE_MINUTES = 18 * 60
ADMIN_BOOTSTRAP_LIST_RETRY_DELAYS = (0.5, 1.0, 2.0, 4.0)
ADMIN_BOOTSTRAP_TRANSIENT_STATUSES = {500, 502, 503, 504}

PROFILE_PRESETS: dict[str, dict[str, Any]] = {
    "pedro": {
        "description": "Operator search smoke path for Resolve v2.",
        "capability": "search.query",
        "provider": "brave-search",
        "credential_mode": "rhumb_managed",
        "interface": "dogfood-pedro",
        "parameters": {
            "query": "best AI agent observability tools",
            "numResults": 3,
        },
    },
    "keel": {
        "description": "Evidence/reviewops search smoke path with Keel-tagged telemetry.",
        "capability": "search.query",
        "provider": "brave-search",
        "credential_mode": "rhumb_managed",
        "interface": "dogfood-keel",
        "parameters": {
            "query": "runtime-backed API review evidence best practices",
            "numResults": 3,
        },
    },
    "helm": {
        "description": "Access/proxy search smoke path with Helm-tagged telemetry.",
        "capability": "search.query",
        "provider": "brave-search",
        "credential_mode": "rhumb_managed",
        "interface": "dogfood-helm",
        "parameters": {
            "query": "API proxy auth budget telemetry patterns",
            "numResults": 3,
        },
    },
    "beacon": {
        "description": "GTM/distribution search smoke path with Beacon-tagged telemetry.",
        "capability": "search.query",
        "provider": "brave-search",
        "credential_mode": "rhumb_managed",
        "interface": "dogfood-beacon",
        "parameters": {
            "query": "best MCP server distribution channels for developers",
            "numResults": 3,
        },
    },
}


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
    """Fallback to the dedicated Pedro dogfood credential in 1Password.

    This keeps scheduled/heartbeat dogfood runs honest even when the runtime
    shell did not inherit `RHUMB_DOGFOOD_API_KEY`.
    """
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


def _load_admin_key_from_sop(
    item_name: str = DEFAULT_ADMIN_KEY_ITEM,
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
        f"Missing API key. Set the {env_name} environment variable or store "
        f"{DEFAULT_API_KEY_ITEM!r} in 1Password."
    )


def _get_admin_key(env_name: str) -> str:
    value = os.environ.get(env_name, "").strip()
    if value:
        return value

    for fallback_env in DEFAULT_ADMIN_KEY_ENV_FALLBACKS:
        value = os.environ.get(fallback_env, "").strip()
        if value:
            return value

    value = _load_admin_key_from_sop()
    if value:
        return value

    env_names = ", ".join([env_name, *DEFAULT_ADMIN_KEY_ENV_FALLBACKS])
    raise RuntimeError(
        "Missing admin key. Set one of "
        f"{env_names} or store {DEFAULT_ADMIN_KEY_ITEM!r} in 1Password."
    )


def _is_transient_admin_bootstrap_failure(response: dict[str, Any]) -> bool:
    status = int(response.get("status") or 0)
    if status in ADMIN_BOOTSTRAP_TRANSIENT_STATUSES:
        return True

    detail = _extract_error_detail(response).lower()
    return any(
        marker in detail
        for marker in (
            "unexpected error occurred",
            "timeout",
            "timed out",
            "temporarily unavailable",
            "connection",
            "transport",
        )
    )


def _list_agents_via_admin_with_retry(
    *,
    root: str,
    org_id: str,
    headers: dict[str, str],
    timeout: float,
) -> tuple[dict[str, Any], int]:
    url = (
        f"{root}/v1/admin/agents?organization_id={quote(org_id, safe='')}&status=active"
    )
    delays = list(ADMIN_BOOTSTRAP_LIST_RETRY_DELAYS)
    attempts = len(delays) + 1

    for attempt in range(1, attempts + 1):
        try:
            response = _http_json(
                "GET",
                url,
                headers=headers,
                timeout=timeout,
            )
        except RuntimeError:
            if attempt >= attempts:
                raise
            time.sleep(delays[attempt - 1])
            continue

        agents = response.get("json")
        if response.get("status") == 200 and isinstance(agents, list):
            return response, attempt

        if attempt >= attempts or not _is_transient_admin_bootstrap_failure(response):
            return response, attempt

        time.sleep(delays[attempt - 1])

    raise RuntimeError("Admin agent list retry loop exited unexpectedly")


def provision_api_key_via_admin(
    args: argparse.Namespace,
    *,
    provider: str,
) -> tuple[str, dict[str, Any]]:
    """Create or rotate a verifier-agent API key through the admin API."""
    root = args.base_url.rstrip("/")
    admin_key = _get_admin_key(args.admin_key_env)
    org_id = args.bootstrap_org_id
    agent_name = args.bootstrap_agent_name
    service = args.bootstrap_service or provider
    headers = {"X-Rhumb-Admin-Key": admin_key}

    list_resp, list_attempts = _list_agents_via_admin_with_retry(
        root=root,
        org_id=org_id,
        headers=headers,
        timeout=args.timeout,
    )
    agents = list_resp.get("json")
    if list_resp.get("status") != 200 or not isinstance(agents, list):
        detail = _extract_error_detail(list_resp)
        raise RuntimeError(
            f"Admin agent list failed ({list_resp.get('status')}): {detail}"
        )

    existing_agent = next(
        (item for item in agents if item.get("name") == agent_name),
        None,
    )
    metadata: dict[str, Any] = {
        "organization_id": org_id,
        "agent_name": agent_name,
        "service": service,
        "list_attempts": list_attempts,
    }

    if existing_agent is None:
        create_resp = _http_json(
            "POST",
            f"{root}/v1/admin/agents",
            payload={
                "name": agent_name,
                "organization_id": org_id,
                "rate_limit_qpm": 100,
                "description": "Resolve v2 dogfood verifier agent",
                "tags": ["dogfood", "verifier"],
            },
            headers=headers,
            timeout=args.timeout,
        )
        create_payload = create_resp.get("json") or {}
        agent_id = create_payload.get("agent_id")
        api_key = create_payload.get("api_key")
        if create_resp.get("status") != 200 or not agent_id or not api_key:
            detail = _extract_error_detail(create_resp)
            raise RuntimeError(
                f"Admin agent create failed ({create_resp.get('status')}): {detail}"
            )
        metadata.update({"mode": "created", "agent_id": agent_id})
    else:
        agent_id = existing_agent.get("agent_id")
        rotate_resp = _http_json(
            "POST",
            f"{root}/v1/admin/agents/{quote(agent_id, safe='')}/rotate-key",
            payload={},
            headers=headers,
            timeout=args.timeout,
        )
        rotate_payload = rotate_resp.get("json") or {}
        api_key = rotate_payload.get("new_api_key")
        if rotate_resp.get("status") != 200 or not api_key:
            detail = _extract_error_detail(rotate_resp)
            raise RuntimeError(
                f"Admin agent rotate failed ({rotate_resp.get('status')}): {detail}"
            )
        metadata.update({"mode": "rotated", "agent_id": agent_id})

    if service:
        grant_resp = _http_json(
            "POST",
            f"{root}/v1/admin/agents/{quote(agent_id, safe='')}/grant-access",
            payload={"service": service},
            headers=headers,
            timeout=args.timeout,
        )
        if grant_resp.get("status") not in {200, 409}:
            detail = _extract_error_detail(grant_resp)
            raise RuntimeError(
                f"Admin agent grant-access failed ({grant_resp.get('status')}): {detail}"
            )
        metadata["service_access"] = "already_granted" if grant_resp.get("status") == 409 else "granted"

    return api_key, metadata


def _json_or_default(raw: str, fallback: dict[str, Any]) -> dict[str, Any]:
    if not raw.strip():
        return dict(fallback)
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object")
    return parsed


def _profile_names_csv() -> str:
    return ", ".join(sorted(PROFILE_PRESETS))


def _get_profile(profile_name: str) -> dict[str, Any]:
    profile = PROFILE_PRESETS.get(profile_name)
    if profile is None:
        raise ValueError(
            f"Unknown dogfood profile {profile_name!r}. Available: {_profile_names_csv()}"
        )
    return profile


def _apply_profile_defaults(args: argparse.Namespace, profile_name: str) -> argparse.Namespace:
    profile = _get_profile(profile_name)
    resolved = argparse.Namespace(**vars(args))
    resolved.profile = profile_name

    if resolved.capability == DEFAULT_CAPABILITY:
        resolved.capability = profile.get("capability", resolved.capability)
    if resolved.provider == DEFAULT_PROVIDER:
        resolved.provider = profile.get("provider", resolved.provider)
    if resolved.credential_mode == DEFAULT_CREDENTIAL_MODE:
        resolved.credential_mode = profile.get("credential_mode", resolved.credential_mode)
    if resolved.interface == DEFAULT_INTERFACE:
        resolved.interface = profile.get("interface", resolved.interface)
    if resolved.parameters_json == DEFAULT_PARAMETERS_JSON:
        resolved.parameters_json = json.dumps(profile.get("parameters", DEFAULT_PARAMETERS))

    return resolved


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


def _build_batch_summary(results: dict[str, dict[str, Any]]) -> str:
    total = len(results)
    ok_count = sum(1 for payload in results.values() if payload.get("ok"))
    parts = [f"Resolve v2 dogfood batch complete; ok_profiles={ok_count}/{total}"]

    for profile_name, payload in results.items():
        status = "ok" if payload.get("ok") else "failed"
        config = payload.get("config") or {}
        provider = config.get("provider") or "n/a"
        interface = config.get("interface") or "n/a"
        parts.append(f"{profile_name}={status} provider={provider} interface={interface}")

    return "; ".join(parts)


def _artifact_root() -> Path:
    return Path(__file__).resolve().parents[1] / "artifacts"


def _default_fleet_status_profiles() -> list[str]:
    return list(DEFAULT_FLEET_STATUS_PROFILES)


def _resolve_fleet_status_profiles(args: argparse.Namespace) -> list[str]:
    requested = args.fleet_status_profiles
    if requested:
        candidates = [item.strip() for item in requested.split(",") if item.strip()]
    else:
        candidates = _default_fleet_status_profiles()

    seen: set[str] = set()
    ordered: list[str] = []
    for profile_name in candidates:
        _get_profile(profile_name)
        if profile_name not in seen:
            seen.add(profile_name)
            ordered.append(profile_name)
    return ordered


def _artifact_path_for_profile(profile_name: str) -> Path:
    return _artifact_root() / f"resolve-v2-dogfood-{profile_name}-admin-latest.json"


def _isoformat_utc(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _round_age_minutes(age_seconds: float | None) -> float | None:
    if age_seconds is None:
        return None
    return round(age_seconds / 60.0, 1)


def _build_fleet_status_entry(
    profile_name: str,
    artifact_path: Path,
    *,
    now_ts: float,
    max_age_minutes: float,
) -> dict[str, Any]:
    artifact_root = _artifact_root().parent
    relative_artifact_path = (
        str(artifact_path.relative_to(artifact_root))
        if artifact_path.is_absolute() and artifact_path.is_relative_to(artifact_root)
        else str(artifact_path)
    )
    base: dict[str, Any] = {
        "profile": profile_name,
        "artifact_path": relative_artifact_path,
        "max_age_minutes": max_age_minutes,
    }

    if not artifact_path.exists():
        return {
            **base,
            "ok": False,
            "artifact_ok": False,
            "fresh": False,
            "blocker": "latest artifact missing",
        }

    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            **base,
            "ok": False,
            "artifact_ok": False,
            "fresh": False,
            "blocker": f"artifact unreadable: {exc}",
        }

    started_at_raw = payload.get("started_at")
    started_at = float(started_at_raw) if started_at_raw is not None else None
    age_seconds = max(now_ts - started_at, 0.0) if started_at is not None else None
    age_minutes = _round_age_minutes(age_seconds)
    fresh = age_minutes is not None and age_minutes <= max_age_minutes

    config = payload.get("config") or {}
    layer2_data = ((payload.get("layer2") or {}).get("execute") or {}).get("data") or {}
    layer1_data = ((payload.get("layer1") or {}).get("execute") or {}).get("data") or {}
    billing_summary = ((payload.get("billing") or {}).get("summary") or {}).get("data") or {}
    audit_status = ((payload.get("audit") or {}).get("status") or {}).get("data") or {}
    receipt_chain = payload.get("receipt_chain") or {}
    artifact_ok = bool(payload.get("ok"))
    chain_intact = bool(receipt_chain.get("chain_intact"))

    blocker_parts: list[str] = []
    if not artifact_ok:
        blocker_parts.append("artifact marked failed")
    if not fresh:
        blocker_parts.append("artifact stale")
    if not chain_intact:
        blocker_parts.append("receipt chain not intact")

    return {
        **base,
        "ok": artifact_ok and fresh and chain_intact,
        "artifact_ok": artifact_ok,
        "fresh": fresh,
        "started_at": started_at_raw,
        "started_at_iso": _isoformat_utc(started_at) if started_at is not None else None,
        "age_minutes": age_minutes,
        "provider": config.get("provider"),
        "interface": config.get("interface"),
        "summary": payload.get("summary"),
        "billing_events": billing_summary.get("events_count"),
        "audit_events": audit_status.get("total_events"),
        "chain_intact": chain_intact,
        "receipt_chain_verified": receipt_chain.get("verified"),
        "receipt_chain_checked": receipt_chain.get("total_checked"),
        "layer2_execution_id": extract_execution_id(layer2_data),
        "layer2_receipt_id": extract_receipt_id(layer2_data),
        "layer1_execution_id": extract_execution_id(layer1_data),
        "layer1_receipt_id": extract_receipt_id(layer1_data),
        "blocker": "; ".join(blocker_parts) if blocker_parts else None,
    }


def _build_fleet_status_summary(results: dict[str, dict[str, Any]], max_age_minutes: float) -> str:
    total = len(results)
    ok_count = sum(1 for payload in results.values() if payload.get("ok"))
    parts = [
        "Resolve v2 dogfood fleet status complete"
        f"; ok_profiles={ok_count}/{total}"
        f"; freshness_window_minutes={max_age_minutes}"
    ]

    for profile_name, payload in results.items():
        status = "ok" if payload.get("ok") else "failed"
        provider = payload.get("provider") or "n/a"
        age_minutes = payload.get("age_minutes")
        age_part = f" age_min={age_minutes}" if age_minutes is not None else " age_min=n/a"
        parts.append(f"{profile_name}={status} provider={provider}{age_part}")

    return "; ".join(parts)


def run_fleet_status(args: argparse.Namespace, profile_names: list[str]) -> dict[str, Any]:
    now_ts = time.time()
    results = {
        profile_name: _build_fleet_status_entry(
            profile_name,
            _artifact_path_for_profile(profile_name),
            now_ts=now_ts,
            max_age_minutes=args.fleet_status_max_age_minutes,
        )
        for profile_name in profile_names
    }

    return {
        "ok": all(payload.get("ok") for payload in results.values()),
        "mode": "fleet_status",
        "profiles": results,
        "profile_count": len(results),
        "checked_at": _isoformat_utc(now_ts),
        "max_artifact_age_minutes": args.fleet_status_max_age_minutes,
        "summary": _build_fleet_status_summary(results, args.fleet_status_max_age_minutes),
    }


def run_batch(args: argparse.Namespace, profile_names: list[str]) -> dict[str, Any]:
    results: dict[str, dict[str, Any]] = {}

    for profile_name in profile_names:
        run_args = _apply_profile_defaults(args, profile_name)
        try:
            payload = run_flow(run_args)
        except FlowError as exc:
            payload = {
                "ok": False,
                "summary": str(exc),
                **exc.state,
            }
        except Exception as exc:  # pragma: no cover - defensive CLI fallback
            payload = {
                "ok": False,
                "summary": str(exc),
                "config": {
                    "profile": profile_name,
                    "provider": run_args.provider,
                    "interface": run_args.interface,
                    "capability": run_args.capability,
                },
            }
        results[profile_name] = payload

    return {
        "ok": all(payload.get("ok") for payload in results.values()),
        "mode": "batch",
        "profiles": results,
        "profile_count": len(results),
        "summary": _build_batch_summary(results),
    }


def run_flow(args: argparse.Namespace) -> dict[str, Any]:
    root = args.base_url.rstrip("/")
    v2_root = f"{root}/v2"
    bootstrap = None
    if args.bootstrap_via_admin:
        api_key, bootstrap = provision_api_key_via_admin(args, provider=args.provider)
    else:
        api_key = _get_api_key(args.api_key_env)
    parameters = _json_or_default(args.parameters_json, DEFAULT_PARAMETERS)
    headers = {"X-Rhumb-Key": api_key}

    state: dict[str, Any] = {
        "config": {
            "profile": getattr(args, "profile", None),
            "base_url": root,
            "v2_root": v2_root,
            "api_key_env": args.api_key_env,
            "api_key_preview": _mask_secret(api_key),
            "bootstrap": bootstrap,
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
    if payload.get("mode") == "batch":
        print(payload.get("summary") or ("OK" if payload.get("ok") else "FAILED"))
        print()
        for profile_name, profile_payload in (payload.get("profiles") or {}).items():
            status = "OK" if profile_payload.get("ok") else "FAILED"
            print(f"{profile_name}: {status} — {profile_payload.get('summary')}")
        return

    if payload.get("mode") == "fleet_status":
        print(payload.get("summary") or ("OK" if payload.get("ok") else "FAILED"))
        print()
        for profile_name, profile_payload in (payload.get("profiles") or {}).items():
            status = "OK" if profile_payload.get("ok") else "FAILED"
            age_minutes = profile_payload.get("age_minutes")
            age_part = f"age_min={age_minutes}" if age_minutes is not None else "age_min=n/a"
            provider = profile_payload.get("provider") or "n/a"
            print(
                f"{profile_name}: {status} — provider={provider} {age_part} "
                f"artifact={profile_payload.get('artifact_path')}"
            )
            if profile_payload.get("blocker"):
                print(f"  blocker: {profile_payload.get('blocker')}")
        return

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
    parser.add_argument(
        "--profile",
        help=f"Apply a named dogfood profile default set ({_profile_names_csv()})",
    )
    parser.add_argument(
        "--batch-profiles",
        help=f"Run multiple named dogfood profiles, comma-separated ({_profile_names_csv()})",
    )
    parser.add_argument(
        "--all-profiles",
        action="store_true",
        help="Run all built-in dogfood profiles in sequence",
    )
    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="Print available built-in dogfood profiles and exit",
    )
    parser.add_argument(
        "--fleet-status",
        action="store_true",
        help="Read the latest per-profile dogfood artifacts and summarize fleet health without hitting live APIs",
    )
    parser.add_argument(
        "--fleet-status-profiles",
        help=(
            "Profiles to audit from latest artifacts, comma-separated "
            f"(default: {', '.join(DEFAULT_FLEET_STATUS_PROFILES)})"
        ),
    )
    parser.add_argument(
        "--fleet-status-max-age-minutes",
        type=float,
        default=DEFAULT_FLEET_STATUS_MAX_AGE_MINUTES,
        help="Maximum artifact age in minutes for --fleet-status mode before a lane is marked stale",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Rhumb API root URL (without /v2)")
    parser.add_argument(
        "--api-key-env",
        default=DEFAULT_API_KEY_ENV,
        help="Environment variable containing a real Rhumb API key",
    )
    parser.add_argument(
        "--bootstrap-via-admin",
        action="store_true",
        help="Create or rotate a verifier agent key through the admin API instead of reading a local API key",
    )
    parser.add_argument(
        "--admin-key-env",
        default=DEFAULT_ADMIN_KEY_ENV,
        help=(
            "Primary environment variable containing the Rhumb admin key for "
            "--bootstrap-via-admin (falls back to RHUMB_ADMIN_KEY or 1Password item "
            f"{DEFAULT_ADMIN_KEY_ITEM!r})"
        ),
    )
    parser.add_argument(
        "--bootstrap-org-id",
        default=DEFAULT_BOOTSTRAP_ORG_ID,
        help="Organization id to use for verifier-agent bootstrap",
    )
    parser.add_argument(
        "--bootstrap-agent-name",
        default=DEFAULT_BOOTSTRAP_AGENT_NAME,
        help="Agent name to create or rotate for verifier bootstrap",
    )
    parser.add_argument(
        "--bootstrap-service",
        help="Optional service slug to grant during verifier bootstrap (defaults to --provider)",
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
        default=DEFAULT_PARAMETERS_JSON,
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

    if args.list_profiles:
        for profile_name in sorted(PROFILE_PRESETS):
            profile = PROFILE_PRESETS[profile_name]
            print(
                f"{profile_name}: {profile.get('description', '')} "
                f"[capability={profile.get('capability')} provider={profile.get('provider')} interface={profile.get('interface')}]"
            )
        return 0

    if args.fleet_status:
        payload = run_fleet_status(args, _resolve_fleet_status_profiles(args))
        exit_code = 0 if payload.get("ok") else 1
    else:
        batch_profiles: list[str] = []
        if args.all_profiles:
            batch_profiles.extend(sorted(PROFILE_PRESETS))
        if args.batch_profiles:
            batch_profiles.extend(
                [item.strip() for item in args.batch_profiles.split(",") if item.strip()]
            )

        if batch_profiles:
            seen: set[str] = set()
            ordered_profiles: list[str] = []
            for profile_name in batch_profiles:
                _get_profile(profile_name)
                if profile_name not in seen:
                    seen.add(profile_name)
                    ordered_profiles.append(profile_name)
            payload = run_batch(args, ordered_profiles)
            exit_code = 0 if payload.get("ok") else 1
        else:
            if args.profile:
                _get_profile(args.profile)
                args = _apply_profile_defaults(args, args.profile)
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
