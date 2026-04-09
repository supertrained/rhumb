#!/usr/bin/env python3
"""Live hosted proof bundle for the AUD-18 HubSpot CRM read-first rail."""

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
DEFAULT_CRM_REF = "hs_contacts_read"
DEFAULT_BAD_CRM_REF = "hs_missing"
DEFAULT_OBJECT_TYPE = "contacts"
DEFAULT_DENIED_OBJECT_TYPE = "deals"
DEFAULT_DENIED_PROPERTY = "notes_last_updated"
DEFAULT_NOT_FOUND_RECORD_ID = "999999999999999"
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
        if isinstance(provider, dict) and provider.get("service_slug") == "hubspot":
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
        if not isinstance(provider, dict) or provider.get("service_slug") != "hubspot":
            continue
        modes = provider.get("modes")
        if not isinstance(modes, list):
            return provider, None
        for mode in modes:
            if isinstance(mode, dict) and mode.get("mode") == "byok":
                return provider, mode
        return provider, None
    return None, None


def _run_preflight(*, root: str, timeout: float) -> dict[str, Any]:
    resolve = _request_json(
        method="GET",
        url=f"{root}/v1/capabilities/crm.record.search/resolve",
        headers={},
        payload=None,
        timeout=timeout,
    )
    credential_modes = _request_json(
        method="GET",
        url=f"{root}/v1/capabilities/crm.record.search/credential-modes",
        headers={},
        payload=None,
        timeout=timeout,
    )

    resolve_provider = _first_provider(resolve.get("json"))
    modes_provider, byok_mode = _first_credential_mode(credential_modes.get("json"))

    resolve_ok = (
        resolve.get("status") == 200
        and isinstance(resolve_provider, dict)
        and resolve_provider.get("available_for_execute") is True
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
            "check": "crm_record_search_resolve_surface",
            "ok": resolve_ok,
            "status": resolve.get("status"),
            "error": None if resolve_ok else "crm_capability_unavailable",
            "payload_check": None if resolve_ok else "missing_hubspot_provider_or_execute_hint",
            "payload": resolve.get("json"),
        },
        {
            "check": "crm_record_search_credential_modes_surface",
            "ok": credential_modes_ok,
            "status": credential_modes.get("status"),
            "error": None if credential_modes_ok else "crm_credential_modes_unavailable",
            "payload_check": None if credential_modes_ok else "missing_hubspot_byok_mode",
            "payload": credential_modes.get("json"),
        },
        {
            "check": "crm_bundle_configured",
            "ok": configured,
            "status": 200 if resolve.get("status") == 200 and credential_modes.get("status") == 200 else None,
            "error": None if configured else "crm_bundle_unconfigured",
            "payload_check": None if configured else "configured_false",
            "payload": {
                "resolve_configured": resolve_configured,
                "credential_mode_configured": mode_configured,
            },
        },
    ]

    return {
        "configured": configured,
        "available_for_execute": bool(resolve_provider.get("available_for_execute")) if isinstance(resolve_provider, dict) else False,
        "resolve": resolve,
        "credential_modes": credential_modes,
        "results": results,
    }


def _make_describe_success_check(*, crm_ref: str, object_type: str, property_names: tuple[str, ...]) -> PayloadCheck:
    def _check(payload: Any) -> tuple[bool, str | None]:
        data = _extract_data(payload)
        if not isinstance(data, dict):
            return False, "missing_data"
        if data.get("crm_ref") != crm_ref:
            return False, f"unexpected_crm_ref:{data.get('crm_ref')}"
        if data.get("object_type") != object_type:
            return False, f"unexpected_object_type:{data.get('object_type')}"
        if data.get("provider_used") != "hubspot":
            return False, f"unexpected_provider:{data.get('provider_used')}"
        properties = data.get("properties")
        if not isinstance(properties, list) or not properties:
            return False, "expected_non_empty_properties"
        returned_names = {
            item.get("name")
            for item in properties
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        missing = [name for name in property_names if name not in returned_names]
        if missing:
            return False, f"missing_property_descriptors:{','.join(missing)}"
        return True, None

    return _check


def _make_search_success_check(
    *,
    crm_ref: str,
    object_type: str,
    expect_record_id: str | None,
    property_names: tuple[str, ...],
) -> PayloadCheck:
    def _check(payload: Any) -> tuple[bool, str | None]:
        data = _extract_data(payload)
        if not isinstance(data, dict):
            return False, "missing_data"
        if data.get("crm_ref") != crm_ref:
            return False, f"unexpected_crm_ref:{data.get('crm_ref')}"
        if data.get("object_type") != object_type:
            return False, f"unexpected_object_type:{data.get('object_type')}"
        if data.get("provider_used") != "hubspot":
            return False, f"unexpected_provider:{data.get('provider_used')}"
        records = data.get("records")
        if not isinstance(records, list) or not records:
            return False, "expected_non_empty_records"

        target_record: dict[str, Any] | None = None
        if expect_record_id:
            for item in records:
                if isinstance(item, dict) and item.get("record_id") == expect_record_id:
                    target_record = item
                    break
            if target_record is None:
                return False, f"expected_record_id_missing:{expect_record_id}"
        else:
            first = records[0]
            if isinstance(first, dict):
                target_record = first
        if not isinstance(target_record, dict):
            return False, "target_record_missing"

        properties = target_record.get("properties")
        if not isinstance(properties, dict) or not properties:
            return False, "target_record_properties_missing"
        missing = [name for name in property_names if name not in properties]
        if missing:
            return False, f"missing_record_properties:{','.join(missing)}"
        return True, None

    return _check


def _make_get_success_check(
    *,
    crm_ref: str,
    object_type: str,
    record_id: str,
    property_names: tuple[str, ...],
) -> PayloadCheck:
    def _check(payload: Any) -> tuple[bool, str | None]:
        data = _extract_data(payload)
        if not isinstance(data, dict):
            return False, "missing_data"
        if data.get("crm_ref") != crm_ref:
            return False, f"unexpected_crm_ref:{data.get('crm_ref')}"
        if data.get("object_type") != object_type:
            return False, f"unexpected_object_type:{data.get('object_type')}"
        if data.get("record_id") != record_id:
            return False, f"unexpected_record_id:{data.get('record_id')}"
        if data.get("provider_used") != "hubspot":
            return False, f"unexpected_provider:{data.get('provider_used')}"
        properties = data.get("properties")
        if not isinstance(properties, dict) or not properties:
            return False, "expected_non_empty_properties"
        missing = [name for name in property_names if name not in properties]
        if missing:
            return False, f"missing_record_properties:{','.join(missing)}"
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
    parser = argparse.ArgumentParser(description="Run the hosted HubSpot CRM read-first proof bundle")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--crm-ref", default=DEFAULT_CRM_REF)
    parser.add_argument("--bad-crm-ref", default=DEFAULT_BAD_CRM_REF)
    parser.add_argument("--object-type", default=DEFAULT_OBJECT_TYPE)
    parser.add_argument("--denied-object-type", default=DEFAULT_DENIED_OBJECT_TYPE)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--record-id")
    parser.add_argument("--denied-record-id")
    parser.add_argument("--not-found-record-id", default=DEFAULT_NOT_FOUND_RECORD_ID)
    parser.add_argument("--property-name", action="append", default=[])
    parser.add_argument("--denied-property", default=DEFAULT_DENIED_PROPERTY)
    parser.add_argument("--query")
    parser.add_argument("--search-filter-property")
    parser.add_argument("--search-filter-value")
    parser.add_argument("--search-filter-operator", default="EQ")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--api-key")
    parser.add_argument("--json-out")
    return parser


def _write_artifact(*, args: argparse.Namespace, artifact: dict[str, Any], ok: bool, results: list[dict[str, Any]]) -> int:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = Path(args.json_out) if args.json_out else ARTIFACTS_DIR / f"aud18-hubspot-crm-hosted-proof-{_now_slug()}.json"
    artifact_path.write_text(json.dumps(artifact, indent=2))
    print(str(artifact_path))
    print(
        json.dumps(
            {
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
            },
            indent=2,
        )
    )
    return 0 if ok else 1


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.preflight_only and not args.record_id:
        parser.error("--record-id is required unless --preflight-only is used")

    if bool(args.search_filter_property) != bool(args.search_filter_value):
        parser.error("--search-filter-property and --search-filter-value must be passed together")

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
            "crm_ref": args.crm_ref,
            "bad_crm_ref": args.bad_crm_ref,
            "object_type": args.object_type,
            "denied_object_type": args.denied_object_type,
            "record_id": args.record_id,
            "denied_record_id": args.denied_record_id,
            "not_found_record_id": args.not_found_record_id,
            "property_names": list(dict.fromkeys([item.strip().lower() for item in args.property_name if item.strip()])),
            "denied_property": args.denied_property,
            "query": args.query,
            "search_filter": {
                "property": args.search_filter_property,
                "operator": args.search_filter_operator if args.search_filter_property else None,
                "value": args.search_filter_value,
            },
            "api_key_hint": _mask(args.api_key or os.environ.get("RHUMB_API_KEY")),
            "preflight": {
                "configured": preflight["configured"],
                "available_for_execute": preflight["available_for_execute"],
                "resolve": preflight["resolve"],
                "credential_modes": preflight["credential_modes"],
            },
            "results": results,
        }
        return _write_artifact(args=args, artifact=artifact, ok=ok, results=results)

    api_key = (args.api_key or os.environ.get("RHUMB_API_KEY") or "").strip()
    if not api_key:
        raise SystemExit("Pass --api-key or set RHUMB_API_KEY")

    headers = {
        "Content-Type": "application/json",
        "X-Rhumb-Key": api_key,
    }
    property_names = tuple(dict.fromkeys([item.strip().lower() for item in args.property_name if item.strip()]))

    describe_payload: dict[str, Any] = {
        "crm_ref": args.crm_ref,
        "object_type": args.object_type,
    }
    search_payload: dict[str, Any] = {
        "crm_ref": args.crm_ref,
        "object_type": args.object_type,
        "limit": args.limit,
    }
    if property_names:
        search_payload["property_names"] = list(property_names)
    if args.query:
        search_payload["query"] = args.query
    if args.search_filter_property:
        search_payload["filters"] = [
            {
                "property": args.search_filter_property.strip().lower(),
                "operator": args.search_filter_operator.strip().upper(),
                "value": args.search_filter_value,
            }
        ]

    get_payload: dict[str, Any] = {
        "crm_ref": args.crm_ref,
        "object_type": args.object_type,
        "record_id": args.record_id,
    }
    if property_names:
        get_payload["property_names"] = list(property_names)

    checks: list[tuple[str, str, dict[str, Any], int, str | None, PayloadCheck | None, bool]] = [
        (
            "crm_object_describe",
            f"{root}/v1/capabilities/crm.object.describe/execute",
            describe_payload,
            200,
            None,
            _make_describe_success_check(
                crm_ref=args.crm_ref,
                object_type=args.object_type,
                property_names=property_names,
            ),
            True,
        ),
        (
            "crm_record_search",
            f"{root}/v1/capabilities/crm.record.search/execute",
            search_payload,
            200,
            None,
            _make_search_success_check(
                crm_ref=args.crm_ref,
                object_type=args.object_type,
                expect_record_id=args.record_id,
                property_names=property_names,
            ),
            True,
        ),
        (
            "crm_record_get",
            f"{root}/v1/capabilities/crm.record.get/execute",
            get_payload,
            200,
            None,
            _make_get_success_check(
                crm_ref=args.crm_ref,
                object_type=args.object_type,
                record_id=args.record_id,
                property_names=property_names,
            ),
            True,
        ),
        (
            "bad_crm_ref_denial",
            f"{root}/v1/capabilities/crm.object.describe/execute",
            {
                "crm_ref": args.bad_crm_ref,
                "object_type": args.object_type,
            },
            400,
            "crm_ref_invalid",
            None,
            False,
        ),
        (
            "out_of_scope_object_type_denial",
            f"{root}/v1/capabilities/crm.object.describe/execute",
            {
                "crm_ref": args.crm_ref,
                "object_type": args.denied_object_type,
            },
            403,
            "crm_object_scope_denied",
            None,
            False,
        ),
        (
            "out_of_scope_property_denial",
            f"{root}/v1/capabilities/crm.record.get/execute",
            {
                "crm_ref": args.crm_ref,
                "object_type": args.object_type,
                "record_id": args.record_id,
                "property_names": [args.denied_property.strip().lower()],
            },
            403,
            "crm_property_scope_denied",
            None,
            False,
        ),
        (
            "crm_record_not_found_denial",
            f"{root}/v1/capabilities/crm.record.get/execute",
            {
                "crm_ref": args.crm_ref,
                "object_type": args.object_type,
                "record_id": args.not_found_record_id,
            },
            404,
            "crm_record_not_found",
            None,
            False,
        ),
    ]

    if args.denied_record_id:
        checks.append(
            (
                "out_of_scope_record_denial",
                f"{root}/v1/capabilities/crm.record.get/execute",
                {
                    "crm_ref": args.crm_ref,
                    "object_type": args.object_type,
                    "record_id": args.denied_record_id,
                },
                403,
                "crm_record_scope_denied",
                None,
                False,
            )
        )

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
        "crm_ref": args.crm_ref,
        "bad_crm_ref": args.bad_crm_ref,
        "object_type": args.object_type,
        "denied_object_type": args.denied_object_type,
        "record_id": args.record_id,
        "denied_record_id": args.denied_record_id,
        "not_found_record_id": args.not_found_record_id,
        "property_names": list(property_names),
        "denied_property": args.denied_property,
        "query": args.query,
        "search_filter": {
            "property": args.search_filter_property,
            "operator": args.search_filter_operator if args.search_filter_property else None,
            "value": args.search_filter_value,
        },
        "api_key_hint": _mask(api_key),
        "results": results,
    }

    artifact["mode"] = "full"
    artifact["preflight"] = {
        "configured": preflight["configured"],
        "available_for_execute": preflight["available_for_execute"],
        "resolve": preflight["resolve"],
        "credential_modes": preflight["credential_modes"],
    }
    return _write_artifact(args=args, artifact=artifact, ok=ok, results=results)


if __name__ == "__main__":
    raise SystemExit(main())
