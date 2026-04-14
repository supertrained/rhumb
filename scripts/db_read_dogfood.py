#!/usr/bin/env python3
"""Live dogfood proof for the AUD-18 DB read-first rail.

This exercises the public Rhumb API end to end for the first PostgreSQL /
Supabase direct-read wedge:

1. capability search / get / resolve / credential-modes surfaces
2. db.query.read execute
3. db.schema.describe execute
4. db.row.get execute
5. receipt fetches through /v2/receipts
6. explicit denied write + multi-statement proofs

Default target: the production connection_ref already configured on the API
service (`conn_rhumb_app_read`).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "https://api.rhumb.dev"
DEFAULT_API_KEY_ENV = "RHUMB_DOGFOOD_API_KEY"
DEFAULT_API_KEY_ITEM = "Rhumb API Key - pedro-dogfood"
DEFAULT_API_KEY_VAULT = "OpenClaw Agents"
DEFAULT_TIMEOUT = 30.0
DEFAULT_CONNECTION_REF = "conn_rhumb_app_read"
DEFAULT_QUERY = (
    "SELECT id, domain, action FROM capabilities "
    "WHERE id LIKE 'db.%' ORDER BY id LIMIT 3"
)
DEFAULT_SCHEMA = "public"
DEFAULT_TABLE = "capabilities"
DEFAULT_ROW_ID = "db.query.read"


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
        "User-Agent": "rhumb-db-read-dogfood/0.1",
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
        data = payload.get("data")
        if isinstance(data, dict):
            for key in ("detail", "error", "message"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    text = (response.get("text") or "").strip()
    return text or f"HTTP {response.get('status')}"


def _extract_data(payload: dict[str, Any] | None) -> Any:
    if isinstance(payload, dict) and "data" in payload:
        return payload.get("data")
    return payload


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


def _receipt_id_from_execute(payload: dict[str, Any]) -> str | None:
    value = payload.get("receipt_id")
    return value if isinstance(value, str) and value else None


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


def _preferred_resolve_handoff(state: dict[str, Any]) -> dict[str, Any] | None:
    capabilities = state.get("capabilities")
    if not isinstance(capabilities, dict):
        return None
    for capability_id in ("db.query.read", "db.schema.describe", "db.row.get"):
        candidate = (capabilities.get(capability_id) or {}).get("resolve_handoff")
        if isinstance(candidate, dict) and candidate:
            return candidate
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
    if isinstance(handoff.get("selection_reason"), str):
        parts.append(f"selection_reason={handoff['selection_reason']}")
    if isinstance(handoff.get("setup_url"), str):
        parts.append(f"setup_url={handoff['setup_url']}")
    if isinstance(handoff.get("resolve_url"), str):
        parts.append(f"resolve_url={handoff['resolve_url']}")
    if isinstance(handoff.get("credential_modes_url"), str):
        parts.append(f"credential_modes_url={handoff['credential_modes_url']}")
    if not parts:
        return None
    return "Resolve next step: " + ", ".join(parts)


def _resolve_step(state: dict[str, Any]) -> str | None:
    return _resolve_handoff_summary(_preferred_resolve_handoff(state))


def _attach_resolve_step(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("ok") is True:
        return payload
    resolve_step = _resolve_step(payload)
    if isinstance(resolve_step, str):
        payload["resolve_step"] = resolve_step
    return payload


def _failure_summary(message: str, state: dict[str, Any]) -> str:
    handoff_summary = _resolve_step(state)
    if not handoff_summary:
        return message
    return f"{message}; {handoff_summary}"


def _run_denial(
    *,
    root: str,
    headers: dict[str, str],
    connection_ref: str,
    query: str,
    timeout: float,
) -> dict[str, Any]:
    response = _http_json(
        "POST",
        f"{root}/v1/capabilities/db.query.read/execute",
        payload={"connection_ref": connection_ref, "query": query},
        headers=headers,
        timeout=timeout,
    )
    payload = response.get("json") if isinstance(response.get("json"), dict) else {}
    return {
        "status": response.get("status"),
        "error": payload.get("error"),
        "message": payload.get("message"),
        "execution_id": payload.get("execution_id"),
        "request_id": payload.get("request_id"),
    }


def _build_summary(state: dict[str, Any]) -> str:
    query = ((state.get("executions") or {}).get("db.query.read") or {}).get("data") or {}
    schema = ((state.get("executions") or {}).get("db.schema.describe") or {}).get("data") or {}
    row = ((state.get("executions") or {}).get("db.row.get") or {}).get("data") or {}
    denied = state.get("denied") or {}
    searches = state.get("searches") or {}

    search_top = []
    for label, payload in searches.items():
        top_id = payload.get("top_id") or "n/a"
        search_top.append(f"{label}={top_id}")

    return "; ".join(
        part
        for part in [
            "AUD-18 DB dogfood complete",
            f"provider={query.get('provider_used') or schema.get('provider_used') or row.get('provider_used') or 'n/a'}",
            f"query_receipt={query.get('receipt_id') or 'n/a'}",
            f"schema_receipt={schema.get('receipt_id') or 'n/a'}",
            f"row_receipt={row.get('receipt_id') or 'n/a'}",
            f"write_denial={((denied.get('write') or {}).get('error')) or 'n/a'}",
            f"multi_denial={((denied.get('multi') or {}).get('error')) or 'n/a'}",
            ", ".join(search_top) if search_top else None,
        ]
        if part
    )


def run_flow(args: argparse.Namespace) -> dict[str, Any]:
    root = args.base_url.rstrip("/")
    api_key = _get_api_key(args.api_key_env)
    headers = {"X-Rhumb-Key": api_key}
    json_headers = {**headers, "Content-Type": "application/json"}

    state: dict[str, Any] = {
        "config": {
            "base_url": root,
            "api_key_env": args.api_key_env,
            "api_key_preview": _mask_secret(api_key),
            "connection_ref": args.connection_ref,
            "schema": args.schema,
            "table": args.table,
            "row_id": args.row_id,
        }
    }

    searches: dict[str, Any] = {}
    for label, query in {
        "postgres_query": "postgres query",
        "database_schema": "database schema",
    }.items():
        response = _expect_success(
            f"capability search {label}",
            _http_json(
                "GET",
                f"{root}/v1/capabilities?search={quote(query)}&limit=5",
                headers=headers,
                timeout=args.timeout,
            ),
            state,
        )
        data = _extract_data(response.get("json")) or {}
        items = data.get("items") or []
        searches[label] = {
            "query": query,
            "top_id": items[0].get("id") if items else None,
            "top_ids": [item.get("id") for item in items[:5]],
        }
    state["searches"] = searches

    capabilities: dict[str, Any] = {}
    for capability_id in ("db.query.read", "db.schema.describe", "db.row.get"):
        get_resp = _expect_success(
            f"capability get {capability_id}",
            _http_json(
                "GET",
                f"{root}/v1/capabilities/{quote(capability_id, safe='')}",
                headers=headers,
                timeout=args.timeout,
            ),
            state,
        )
        resolve_resp = _expect_success(
            f"capability resolve {capability_id}",
            _http_json(
                "GET",
                f"{root}/v1/capabilities/{quote(capability_id, safe='')}/resolve",
                headers=headers,
                timeout=args.timeout,
            ),
            state,
        )
        modes_resp = _expect_success(
            f"capability modes {capability_id}",
            _http_json(
                "GET",
                f"{root}/v1/capabilities/{quote(capability_id, safe='')}/credential-modes",
                headers=headers,
                timeout=args.timeout,
            ),
            state,
        )
        capabilities[capability_id] = {
            "get": _extract_data(get_resp.get("json")),
            "resolve": _extract_data(resolve_resp.get("json")),
            "resolve_handoff": _resolve_handoff(resolve_resp.get("json")),
            "credential_modes": _extract_data(modes_resp.get("json")),
        }
    state["capabilities"] = capabilities

    execute_payloads = {
        "db.query.read": {
            "connection_ref": args.connection_ref,
            "query": args.query,
        },
        "db.schema.describe": {
            "connection_ref": args.connection_ref,
            "schemas": [args.schema],
            "tables": [args.table],
            "include_relationships": True,
        },
        "db.row.get": {
            "connection_ref": args.connection_ref,
            "schema": args.schema,
            "table": args.table,
            "filters": {"id": args.row_id},
            "columns": ["id", "domain", "action"],
            "limit": 1,
        },
    }

    executions: dict[str, Any] = {}
    for capability_id, payload in execute_payloads.items():
        execute_resp = _expect_success(
            f"execute {capability_id}",
            _http_json(
                "POST",
                f"{root}/v1/capabilities/{quote(capability_id, safe='')}/execute",
                payload=payload,
                headers=json_headers,
                timeout=args.timeout,
            ),
            state,
        )
        execute_data = _extract_data(execute_resp.get("json")) or {}
        receipt_id = _receipt_id_from_execute(execute_data)
        if not receipt_id:
            raise FlowError(f"{capability_id} returned no receipt_id", state)
        receipt_resp = _expect_success(
            f"receipt {capability_id}",
            _http_json(
                "GET",
                f"{root}/v2/receipts/{quote(receipt_id, safe='')}",
                headers=headers,
                timeout=args.timeout,
            ),
            state,
        )
        executions[capability_id] = {
            "request": payload,
            "data": execute_data,
            "receipt": _extract_data(receipt_resp.get("json")),
        }
    state["executions"] = executions

    state["denied"] = {
        "write": _run_denial(
            root=root,
            headers=json_headers,
            connection_ref=args.connection_ref,
            query=f"DELETE FROM {args.table} WHERE id = '{args.row_id}'",
            timeout=args.timeout,
        ),
        "multi": _run_denial(
            root=root,
            headers=json_headers,
            connection_ref=args.connection_ref,
            query=f"SELECT 1; DELETE FROM {args.table} WHERE id = '{args.row_id}'",
            timeout=args.timeout,
        ),
    }

    if state["denied"]["write"]["error"] != "db_query_not_read_only":
        raise FlowError("Write denial did not return db_query_not_read_only", state)
    if state["denied"]["multi"]["error"] != "db_query_multi_statement_denied":
        raise FlowError("Multi-statement denial did not return db_query_multi_statement_denied", state)

    state["ok"] = True
    state["summary"] = _build_summary(state)
    return state


def _print_human(payload: dict[str, Any]) -> None:
    print(payload.get("summary") or ("OK" if payload.get("ok") else "FAILED"))
    resolve_step = payload.get("resolve_step")
    if isinstance(resolve_step, str):
        print(resolve_step)
    print()

    for label, search in (payload.get("searches") or {}).items():
        print(f"Search {label}: {search.get('top_ids')}")

    capabilities = payload.get("capabilities") or {}
    executions = payload.get("executions") or {}
    for capability_id in ("db.query.read", "db.schema.describe", "db.row.get"):
        capability = capabilities.get(capability_id) or {}
        resolve_handoff = capability.get("resolve_handoff") or {}
        run = executions.get(capability_id) or {}
        data = run.get("data") or {}
        receipt = run.get("receipt") or {}
        print()
        print(capability_id)
        if resolve_handoff:
            print(f"- resolve_handoff: {json.dumps(resolve_handoff, sort_keys=True)}")
        print(f"- provider_used: {data.get('provider_used')}")
        print(f"- receipt_id: {data.get('receipt_id')}")
        print(f"- execution_id: {data.get('execution_id')}")
        print(f"- receipt_status: {receipt.get('status')}")
        print(f"- chain_sequence: {receipt.get('chain_sequence')}")

    denied = payload.get("denied") or {}
    print()
    print("Denied proofs")
    print(f"- write: {denied.get('write')}")
    print(f"- multi: {denied.get('multi')}")

    if payload.get("last_error_response"):
        print()
        print("Last error response")
        print(json.dumps(payload["last_error_response"], indent=2, sort_keys=True))


def _print_summary_only(payload: dict[str, Any]) -> None:
    print(payload.get("summary") or ("OK" if payload.get("ok") else "FAILED"))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-key-env", default=DEFAULT_API_KEY_ENV)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--connection-ref", default=DEFAULT_CONNECTION_REF)
    parser.add_argument("--schema", default=DEFAULT_SCHEMA)
    parser.add_argument("--table", default=DEFAULT_TABLE)
    parser.add_argument("--row-id", default=DEFAULT_ROW_ID)
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--summary-only", action="store_true")
    parser.add_argument("--json-out")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    try:
        payload = run_flow(args)
        exit_code = 0
    except FlowError as exc:
        payload = {"ok": False, "summary": _failure_summary(str(exc), exc.state), **exc.state}
        exit_code = 1
    except Exception as exc:  # pragma: no cover - defensive CLI fallback
        payload = {"ok": False, "summary": str(exc)}
        exit_code = 1

    payload = _attach_resolve_step(payload)

    if args.summary_only:
        _print_summary_only(payload)
    elif args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_human(payload)

    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
