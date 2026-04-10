#!/usr/bin/env python3
"""Live hosted proof bundle for the AUD-18 BigQuery warehouse read-first rail."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "packages" / "api"
VENV_PYTHON = API_DIR / ".venv" / "bin" / "python"
ARTIFACTS_DIR = ROOT / "artifacts"
DEFAULT_BASE_URL = "https://api.rhumb.dev"
DEFAULT_WAREHOUSE_REF = "bq_analytics_read"
DEFAULT_BAD_WAREHOUSE_REF = "bq_missing"
DEFAULT_TIMEOUT = 60.0
DEFAULT_MAX_ROWS = 10
DEFAULT_TIMEOUT_MS = 10000
DEFAULT_BYTES_BREACH_CAP = 1
_BIGQUERY_DIRECT_SCOPES = (
    "https://www.googleapis.com/auth/bigquery.readonly",
)


PayloadCheck = Callable[[Any], Tuple[bool, Optional[str]]]


def _ensure_runtime() -> None:
    if sys.version_info >= (3, 10):
        return
    if not VENV_PYTHON.exists():
        raise SystemExit(
            f"Python 3.10+ required and virtualenv interpreter missing at {VENV_PYTHON}"
        )
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), __file__, *sys.argv[1:]])


_ensure_runtime()

sys.path.insert(0, str(API_DIR))

from services.warehouse_connection_registry import WarehouseRefError, resolve_warehouse_bundle  # noqa: E402


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


def _request_form_json(
    *,
    url: str,
    payload: dict[str, str],
    timeout: float,
) -> dict[str, Any]:
    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
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


def _first_provider(payload: Any, *, service_slug: str) -> dict[str, Any] | None:
    data = _extract_data(payload)
    if not isinstance(data, dict):
        return None
    providers = data.get("providers")
    if not isinstance(providers, list):
        return None
    for provider in providers:
        if isinstance(provider, dict) and provider.get("service_slug") == service_slug:
            return provider
    return None


def _first_credential_mode(payload: Any, *, service_slug: str, mode_name: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    provider = _first_provider(payload, service_slug=service_slug)
    if not isinstance(provider, dict):
        return None, None
    modes = provider.get("modes")
    if not isinstance(modes, list):
        return provider, None
    for mode in modes:
        if isinstance(mode, dict) and mode.get("mode") == mode_name:
            return provider, mode
    return provider, None


def _run_preflight(*, root: str, timeout: float) -> dict[str, Any]:
    resolve = _request_json(
        method="GET",
        url=f"{root}/v1/capabilities/warehouse.query.read/resolve",
        headers={},
        payload=None,
        timeout=timeout,
    )
    credential_modes = _request_json(
        method="GET",
        url=f"{root}/v1/capabilities/warehouse.query.read/credential-modes",
        headers={},
        payload=None,
        timeout=timeout,
    )

    resolve_provider = _first_provider(resolve.get("json"), service_slug="bigquery")
    modes_provider, byok_mode = _first_credential_mode(
        credential_modes.get("json"),
        service_slug="bigquery",
        mode_name="byok",
    )

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
            "check": "warehouse_query_read_resolve_surface",
            "ok": resolve_ok,
            "status": resolve.get("status"),
            "error": None if resolve_ok else "warehouse_capability_unavailable",
            "payload_check": None if resolve_ok else "missing_bigquery_provider_or_execute_hint",
            "payload": resolve.get("json"),
        },
        {
            "check": "warehouse_query_read_credential_modes_surface",
            "ok": credential_modes_ok,
            "status": credential_modes.get("status"),
            "error": None if credential_modes_ok else "warehouse_credential_modes_unavailable",
            "payload_check": None if credential_modes_ok else "missing_bigquery_byok_mode",
            "payload": credential_modes.get("json"),
        },
        {
            "check": "warehouse_bundle_configured",
            "ok": configured,
            "status": 200 if resolve.get("status") == 200 and credential_modes.get("status") == 200 else None,
            "error": None if configured else "warehouse_bundle_unconfigured",
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


def _parse_params_json(raw: str | None) -> list[Any] | dict[str, Any] | None:
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    parsed = json.loads(text)
    if parsed is None:
        return None
    if not isinstance(parsed, (list, dict)):
        raise ValueError("--params-json must decode to a JSON array or object")
    return parsed


def _bundle_summary(bundle: Any) -> dict[str, Any]:
    return {
        "warehouse_ref": bundle.warehouse_ref,
        "provider": bundle.provider,
        "auth_mode": bundle.auth_mode,
        "billing_project_id": bundle.billing_project_id,
        "location": bundle.location,
        "allowed_dataset_refs": list(bundle.allowed_dataset_refs),
        "allowed_table_refs": list(bundle.allowed_table_refs),
        "max_bytes_billed": bundle.max_bytes_billed,
        "max_rows_returned": bundle.max_rows_returned,
        "max_result_bytes": bundle.max_result_bytes,
        "statement_timeout_ms": bundle.statement_timeout_ms,
        "require_partition_filter_for_table_refs": list(bundle.require_partition_filter_for_table_refs),
    }


def _load_local_bundle(warehouse_ref: str) -> tuple[Any | None, dict[str, Any] | None]:
    try:
        return resolve_warehouse_bundle(warehouse_ref), None
    except WarehouseRefError as exc:
        return None, {
            "check": "local_warehouse_bundle_available",
            "ok": False,
            "status": None,
            "error": "warehouse_bundle_unavailable_locally",
            "payload_check": str(exc),
            "payload": None,
        }


def _default_schema_dataset_refs(bundle: Any, requested: list[str]) -> list[str]:
    if requested:
        return requested
    return [bundle.allowed_dataset_refs[0]] if bundle.allowed_dataset_refs else []


def _default_schema_table_refs(bundle: Any, requested: list[str]) -> list[str]:
    if requested:
        return requested
    return [bundle.allowed_table_refs[0]] if bundle.allowed_table_refs else []


def _derive_denied_table_ref(bundle: Any, requested: str | None) -> str:
    if requested:
        return requested
    allowed = bundle.allowed_table_refs[0]
    prefix, _, suffix = allowed.rpartition(".")
    suffix = suffix or "table"
    return f"{prefix}.{suffix}__denied" if prefix else f"{suffix}__denied"


def _derive_not_read_only_query(table_ref: str) -> str:
    return f"DELETE FROM {table_ref} WHERE 1 = 1"


def _derive_script_query(table_ref: str) -> str:
    return f"SELECT user_id FROM {table_ref}; SELECT 1"


def _make_schema_success_check(
    *,
    warehouse_ref: str,
    location: str,
    dataset_refs: tuple[str, ...],
    table_refs: tuple[str, ...],
) -> PayloadCheck:
    def _check(payload: Any) -> tuple[bool, str | None]:
        data = _extract_data(payload)
        if not isinstance(data, dict):
            return False, "missing_data"
        if data.get("warehouse_ref") != warehouse_ref:
            return False, f"unexpected_warehouse_ref:{data.get('warehouse_ref')}"
        if data.get("provider_used") != "bigquery":
            return False, f"unexpected_provider:{data.get('provider_used')}"
        if data.get("location") != location:
            return False, f"unexpected_location:{data.get('location')}"
        datasets = data.get("datasets")
        if not isinstance(datasets, list) or not datasets:
            return False, "expected_non_empty_datasets"
        returned_datasets = {
            f"{item.get('project_id')}.{item.get('dataset_id')}"
            for item in datasets
            if isinstance(item, dict) and item.get("project_id") and item.get("dataset_id")
        }
        missing_datasets = [item for item in dataset_refs if item not in returned_datasets]
        if missing_datasets:
            return False, f"missing_dataset_refs:{','.join(missing_datasets)}"
        tables = data.get("tables")
        if not isinstance(tables, list) or not tables:
            return False, "expected_non_empty_tables"
        returned_tables = {
            item.get("table_ref")
            for item in tables
            if isinstance(item, dict) and isinstance(item.get("table_ref"), str)
        }
        missing_tables = [item for item in table_refs if item not in returned_tables]
        if missing_tables:
            return False, f"missing_table_refs:{','.join(missing_tables)}"
        return True, None

    return _check


def _make_query_success_check(*, warehouse_ref: str, location: str) -> PayloadCheck:
    def _check(payload: Any) -> tuple[bool, str | None]:
        data = _extract_data(payload)
        if not isinstance(data, dict):
            return False, "missing_data"
        if data.get("warehouse_ref") != warehouse_ref:
            return False, f"unexpected_warehouse_ref:{data.get('warehouse_ref')}"
        if data.get("provider_used") != "bigquery":
            return False, f"unexpected_provider:{data.get('provider_used')}"
        if data.get("location") != location:
            return False, f"unexpected_location:{data.get('location')}"
        summary = data.get("query_summary")
        if not isinstance(summary, dict):
            return False, "missing_query_summary"
        if summary.get("dry_run_performed") is not True:
            return False, "dry_run_not_recorded"
        tables = summary.get("tables_referenced")
        if not isinstance(tables, list) or len(tables) != 1:
            return False, "expected_exactly_one_table_reference"
        columns = data.get("columns")
        if not isinstance(columns, list) or not columns:
            return False, "expected_non_empty_columns"
        rows = data.get("rows")
        if not isinstance(rows, list):
            return False, "rows_missing"
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


def _base64url_bytes(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _sign_jwt(payload: bytes, *, private_key_pem: str) -> bytes:
    openssl_bin = shutil.which("openssl")
    if not openssl_bin:
        raise RuntimeError("openssl_missing")
    with tempfile.NamedTemporaryFile("w", delete=False) as key_file:
        key_file.write(private_key_pem)
        key_path = key_file.name
    try:
        result = subprocess.run(
            [openssl_bin, "dgst", "-sha256", "-sign", key_path],
            input=payload,
            capture_output=True,
            check=False,
        )
    finally:
        try:
            os.unlink(key_path)
        except OSError:
            pass
    if result.returncode != 0:
        raise RuntimeError((result.stderr or b"openssl sign failed").decode("utf-8", "ignore").strip())
    return result.stdout


def _service_account_access_token(service_account_info: dict[str, Any], *, timeout: float) -> str:
    client_email = str(service_account_info.get("client_email") or "").strip()
    private_key = str(service_account_info.get("private_key") or "").strip()
    token_uri = str(service_account_info.get("token_uri") or "https://oauth2.googleapis.com/token").strip()
    if not client_email or not private_key:
        raise RuntimeError("service_account_credentials_incomplete")

    issued_at = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    claim_set = {
        "iss": client_email,
        "scope": " ".join(_BIGQUERY_DIRECT_SCOPES),
        "aud": token_uri,
        "iat": issued_at,
        "exp": issued_at + 3600,
    }
    signing_input = (
        f"{_base64url_bytes(json.dumps(header, separators=(',', ':')).encode('utf-8'))}."
        f"{_base64url_bytes(json.dumps(claim_set, separators=(',', ':')).encode('utf-8'))}"
    )
    signature = _sign_jwt(signing_input.encode("utf-8"), private_key_pem=private_key)
    assertion = f"{signing_input}.{_base64url_bytes(signature)}"

    response = _request_form_json(
        url=token_uri,
        payload={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        },
        timeout=timeout,
    )
    token_payload = response.get("json")
    if response.get("status") != 200 or not isinstance(token_payload, dict):
        raise RuntimeError(f"token_exchange_failed:{response.get('status')}")
    access_token = str(token_payload.get("access_token") or "").strip()
    if not access_token:
        raise RuntimeError("access_token_missing")
    return access_token


def _authorized_user_access_token(authorized_user_info: dict[str, Any], *, timeout: float) -> str:
    refresh_token = str(authorized_user_info.get("refresh_token") or "").strip()
    client_id = str(authorized_user_info.get("client_id") or "").strip()
    client_secret = str(authorized_user_info.get("client_secret") or "").strip()
    token_uri = str(authorized_user_info.get("token_uri") or "https://oauth2.googleapis.com/token").strip()
    if not refresh_token or not client_id or not client_secret:
        raise RuntimeError("authorized_user_credentials_incomplete")

    response = _request_form_json(
        url=token_uri,
        payload={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=timeout,
    )
    token_payload = response.get("json")
    if response.get("status") != 200 or not isinstance(token_payload, dict):
        raise RuntimeError(f"authorized_user_refresh_failed:{response.get('status')}")
    access_token = str(token_payload.get("access_token") or "").strip()
    if not access_token:
        raise RuntimeError("authorized_user_access_token_missing")
    return access_token


def _impersonated_service_account_access_token(bundle: Any, *, timeout: float) -> str:
    authorized_user_info = getattr(bundle, "authorized_user_info", None)
    service_account_email = str(getattr(bundle, "service_account_email", None) or "").strip()
    if not isinstance(authorized_user_info, dict):
        raise RuntimeError("authorized_user_credentials_incomplete")
    if not service_account_email:
        raise RuntimeError("service_account_email_missing")

    source_access_token = _authorized_user_access_token(authorized_user_info, timeout=timeout)
    response = _google_request_json(
        method="POST",
        url=(
            "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/"
            f"{urllib.parse.quote(service_account_email, safe='')}:generateAccessToken"
        ),
        access_token=source_access_token,
        timeout=timeout,
        payload={"scope": list(_BIGQUERY_DIRECT_SCOPES)},
    )
    token_payload = response.get("json")
    if response.get("status") != 200 or not isinstance(token_payload, dict):
        raise RuntimeError(f"impersonated_token_exchange_failed:{response.get('status')}")
    access_token = str(token_payload.get("accessToken") or "").strip()
    if not access_token:
        raise RuntimeError("impersonated_access_token_missing")
    return access_token


def _access_token_for_bundle(bundle: Any, *, timeout: float) -> str:
    auth_mode = str(getattr(bundle, "auth_mode", "") or "").strip().lower()
    if auth_mode == "service_account_json":
        service_account_info = getattr(bundle, "service_account_info", None)
        if not isinstance(service_account_info, dict):
            raise RuntimeError("service_account_credentials_incomplete")
        return _service_account_access_token(service_account_info, timeout=timeout)
    if auth_mode == "service_account_impersonation":
        return _impersonated_service_account_access_token(bundle, timeout=timeout)
    raise RuntimeError(f"unsupported_auth_mode:{auth_mode or 'missing'}")


def _google_request_json(
    *,
    method: str,
    url: str,
    access_token: str,
    timeout: float,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {access_token}"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    return _request_json(method=method, url=url, headers=headers, payload=payload, timeout=timeout)


def _bigquery_scalar_type(value: Any) -> str:
    if isinstance(value, bool):
        return "BOOL"
    if isinstance(value, int) and not isinstance(value, bool):
        return "INT64"
    if isinstance(value, float):
        return "FLOAT64"
    if isinstance(value, str):
        return "STRING"
    raise ValueError("Unsupported query parameter type; use strings, numbers, booleans, or arrays of one scalar type")


def _validate_named_query_parameter_name(name: object) -> None:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(name)):
        raise ValueError("Named query parameters must use simple identifiers")


def _query_parameter_payload(name: str | None, value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        if not value:
            raise ValueError("Array query parameters must not be empty")
        element_type = _bigquery_scalar_type(value[0])
        array_values: list[dict[str, Any]] = []
        for item in value:
            if _bigquery_scalar_type(item) != element_type:
                raise ValueError("Array query parameters must contain values of one scalar type")
            array_values.append({"value": item})
        payload = {
            "parameterType": {
                "type": "ARRAY",
                "arrayType": {"type": element_type},
            },
            "parameterValue": {"arrayValues": array_values},
        }
    else:
        payload = {
            "parameterType": {"type": _bigquery_scalar_type(value)},
            "parameterValue": {"value": value},
        }
    if name is not None:
        payload["name"] = name
    return payload


def _direct_query_parameter_state(params: list[Any] | dict[str, Any] | None) -> tuple[str | None, list[dict[str, Any]] | None]:
    if params is None:
        return None, None
    if isinstance(params, list):
        return "POSITIONAL", [_query_parameter_payload(None, value) for value in params]
    if isinstance(params, dict):
        payloads: list[dict[str, Any]] = []
        for name, value in params.items():
            _validate_named_query_parameter_name(name)
            payloads.append(_query_parameter_payload(str(name), value))
        return "NAMED", payloads
    raise ValueError("params must be either a positional list or named object")


def _direct_query_request_body(
    *,
    query: str,
    params: list[Any] | dict[str, Any] | None,
    location: str,
    max_rows: int,
    timeout_ms: int,
    max_bytes_billed: int,
) -> dict[str, Any]:
    parameter_mode, query_parameters = _direct_query_parameter_state(params)
    payload: dict[str, Any] = {
        "query": query,
        "useLegacySql": False,
        "useQueryCache": False,
        "location": location,
        "maxResults": max_rows,
        "timeoutMs": timeout_ms,
        "maximumBytesBilled": str(max_bytes_billed),
    }
    if parameter_mode and query_parameters:
        payload["parameterMode"] = parameter_mode
        payload["queryParameters"] = query_parameters
    return payload


def _rest_mode(field: dict[str, Any]) -> str:
    mode = str(field.get("mode") or "NULLABLE").upper()
    return mode or "NULLABLE"


def _normalize_rest_value(value: Any, field: dict[str, Any]) -> Any:
    if value is None:
        return None
    mode = _rest_mode(field)
    if mode == "REPEATED":
        if not isinstance(value, list):
            return []
        repeated_field = dict(field)
        repeated_field["mode"] = "NULLABLE"
        normalized: list[Any] = []
        for item in value:
            if isinstance(item, dict):
                normalized.append(_normalize_rest_value(item.get("v"), repeated_field))
            else:
                normalized.append(_normalize_rest_value(item, repeated_field))
        return normalized

    field_type = str(field.get("type") or "STRING").upper()
    if field_type == "BOOL":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() == "true"
    if field_type == "INT64":
        try:
            return int(value)
        except Exception:
            return value
    if field_type == "FLOAT64":
        try:
            return float(value)
        except Exception:
            return value
    if field_type == "RECORD":
        nested_fields = field.get("fields") if isinstance(field.get("fields"), list) else []
        if isinstance(value, dict) and isinstance(value.get("f"), list):
            cells = value.get("f")
            return {
                str(nested.get("name") or f"field_{index}"): _normalize_rest_value(
                    cells[index].get("v") if index < len(cells) and isinstance(cells[index], dict) else None,
                    nested if isinstance(nested, dict) else {},
                )
                for index, nested in enumerate(nested_fields)
            }
        return value
    return value


def _rest_columns(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    columns: list[dict[str, Any]] = []
    for field in fields:
        if not isinstance(field, dict):
            continue
        columns.append(
            {
                "name": str(field.get("name") or "unknown"),
                "type": str(field.get("type") or "UNKNOWN"),
                "mode": _rest_mode(field),
                "nullable": _rest_mode(field) != "REQUIRED",
                "description": field.get("description"),
            }
        )
    return columns


def _rest_rows(fields: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        cells = row.get("f") if isinstance(row.get("f"), list) else []
        record: dict[str, Any] = {}
        for index, field in enumerate(fields):
            if not isinstance(field, dict):
                continue
            cell = cells[index] if index < len(cells) and isinstance(cells[index], dict) else {}
            record[str(field.get("name") or f"field_{index}")] = _normalize_rest_value(cell.get("v"), field)
        normalized_rows.append(record)
    return normalized_rows


def _run_direct_bigquery_query(
    *,
    bundle: Any,
    query: str,
    params: list[Any] | dict[str, Any] | None,
    max_rows: int,
    timeout_ms: int,
    max_bytes_billed: int,
    timeout: float,
) -> dict[str, Any]:
    access_token = _access_token_for_bundle(bundle, timeout=timeout)
    base = f"https://bigquery.googleapis.com/bigquery/v2/projects/{urllib.parse.quote(bundle.billing_project_id, safe='')}"
    execute = _google_request_json(
        method="POST",
        url=f"{base}/queries",
        access_token=access_token,
        timeout=timeout,
        payload=_direct_query_request_body(
            query=query,
            params=params,
            location=bundle.location,
            max_rows=max_rows,
            timeout_ms=timeout_ms,
            max_bytes_billed=max_bytes_billed,
        ),
    )
    if execute.get("status") != 200 or not isinstance(execute.get("json"), dict):
        raise RuntimeError(f"direct_query_failed:{execute.get('status')}")

    payload = execute["json"]
    deadline = time.time() + timeout
    while payload.get("jobComplete") is False:
        job_reference = payload.get("jobReference") if isinstance(payload.get("jobReference"), dict) else {}
        job_id = str(job_reference.get("jobId") or "").strip()
        if not job_id:
            raise RuntimeError("direct_query_job_incomplete_without_job_id")
        if time.time() >= deadline:
            raise RuntimeError("direct_query_timeout")
        poll_url = (
            f"{base}/queries/{urllib.parse.quote(job_id, safe='')}?"
            + urllib.parse.urlencode(
                {
                    "location": bundle.location,
                    "maxResults": max_rows,
                    "timeoutMs": max(timeout_ms, 1000),
                }
            )
        )
        poll = _google_request_json(
            method="GET",
            url=poll_url,
            access_token=access_token,
            timeout=min(timeout, max(timeout_ms / 1000.0, 1.0) + 5.0),
            payload=None,
        )
        if poll.get("status") != 200 or not isinstance(poll.get("json"), dict):
            raise RuntimeError(f"direct_query_poll_failed:{poll.get('status')}")
        payload = poll["json"]

    schema = payload.get("schema") if isinstance(payload.get("schema"), dict) else {}
    fields = schema.get("fields") if isinstance(schema.get("fields"), list) else []
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    return {
        "columns": _rest_columns(fields),
        "rows": _rest_rows(fields, rows),
        "row_count_returned": len(rows),
        "actual_bytes_billed": payload.get("totalBytesBilled"),
        "job_id": (payload.get("jobReference") or {}).get("jobId") if isinstance(payload.get("jobReference"), dict) else None,
        "location": bundle.location,
        "billing_project_id": bundle.billing_project_id,
    }


def _column_mode_from_hosted(column: dict[str, Any]) -> str:
    mode = column.get("mode")
    if isinstance(mode, str) and mode.strip():
        return mode.strip().upper()
    if column.get("nullable") is False:
        return "REQUIRED"
    return "NULLABLE"


def _canonical_columns(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    canonical: list[dict[str, Any]] = []
    for column in columns:
        if not isinstance(column, dict):
            continue
        canonical.append(
            {
                "name": str(column.get("name") or "unknown"),
                "type": str(column.get("type") or "UNKNOWN").upper(),
                "mode": _column_mode_from_hosted(column),
            }
        )
    return canonical


def _canonical_scalar(value: Any, field_type: str) -> Any:
    if value is None:
        return None
    normalized_type = str(field_type or "").strip().upper()
    if normalized_type == "BOOL":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() == "true"
    if normalized_type in {"INT64", "INTEGER"}:
        if isinstance(value, bool):
            return value
        try:
            return int(value)
        except Exception:
            return value
    if normalized_type in {"FLOAT64", "FLOAT", "NUMERIC", "BIGNUMERIC"}:
        try:
            return float(value)
        except Exception:
            return value
    return value


def _canonical_rows(rows: list[dict[str, Any]], columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        normalized.append(
            {
                column["name"]: _canonical_scalar(row.get(column["name"]), column["type"])
                for column in columns
            }
        )
    return normalized


def _compare_query_parity(hosted_payload: Any, direct_result: dict[str, Any]) -> tuple[bool, str | None]:
    hosted_data = _extract_data(hosted_payload)
    if not isinstance(hosted_data, dict):
        return False, "hosted_query_data_missing"

    hosted_columns_raw = hosted_data.get("columns")
    hosted_rows_raw = hosted_data.get("rows")
    direct_columns_raw = direct_result.get("columns")
    direct_rows_raw = direct_result.get("rows")
    if not isinstance(hosted_columns_raw, list) or not isinstance(hosted_rows_raw, list):
        return False, "hosted_query_shape_missing"
    if not isinstance(direct_columns_raw, list) or not isinstance(direct_rows_raw, list):
        return False, "direct_query_shape_missing"

    hosted_columns = _canonical_columns(hosted_columns_raw)
    direct_columns = _canonical_columns(direct_columns_raw)
    if hosted_columns != direct_columns:
        return False, "column_shape_mismatch"

    hosted_rows = _canonical_rows(hosted_rows_raw, hosted_columns)
    direct_rows = _canonical_rows(direct_rows_raw, direct_columns)
    if hosted_rows != direct_rows:
        return False, "row_shape_mismatch"

    return True, None


def _direct_parity_result(
    *,
    hosted_query_response: dict[str, Any],
    bundle: Any,
    query: str,
    params: list[Any] | dict[str, Any] | None,
    max_rows: int,
    timeout_ms: int,
    max_bytes_billed: int,
    timeout: float,
) -> dict[str, Any]:
    try:
        direct_payload = _run_direct_bigquery_query(
            bundle=bundle,
            query=query,
            params=params,
            max_rows=max_rows,
            timeout_ms=timeout_ms,
            max_bytes_billed=max_bytes_billed,
            timeout=timeout,
        )
    except Exception as exc:
        return {
            "check": "direct_bigquery_query_parity",
            "ok": False,
            "status": None,
            "error": "bigquery_direct_parity_failed",
            "payload_check": str(exc),
            "payload": None,
        }

    parity_ok, parity_note = _compare_query_parity(hosted_query_response.get("json"), direct_payload)
    return {
        "check": "direct_bigquery_query_parity",
        "ok": parity_ok,
        "status": 200 if parity_ok else 409,
        "error": None if parity_ok else "bigquery_direct_parity_mismatch",
        "payload_check": parity_note,
        "payload": direct_payload,
    }


def _write_artifact(*, args: argparse.Namespace, artifact: dict[str, Any], ok: bool, results: list[dict[str, Any]]) -> int:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = Path(args.json_out) if args.json_out else ARTIFACTS_DIR / f"aud18-bigquery-hosted-proof-{_now_slug()}.json"
    artifact_path.write_text(json.dumps(artifact, indent=2))
    print(str(artifact_path))
    print(
        json.dumps(
            {
                "ok": ok,
                "checks": [
                    {
                        "check": item["check"],
                        "status": item.get("status"),
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the hosted BigQuery warehouse read-first proof bundle")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--warehouse-ref", default=DEFAULT_WAREHOUSE_REF)
    parser.add_argument("--bad-warehouse-ref", default=DEFAULT_BAD_WAREHOUSE_REF)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--dataset-ref", action="append", default=[])
    parser.add_argument("--table-ref", action="append", default=[])
    parser.add_argument("--denied-table-ref")
    parser.add_argument("--missing-allowed-table-ref")
    parser.add_argument("--query")
    parser.add_argument("--params-json")
    parser.add_argument("--max-rows", type=int, default=DEFAULT_MAX_ROWS)
    parser.add_argument("--timeout-ms", type=int, default=DEFAULT_TIMEOUT_MS)
    parser.add_argument("--bytes-breach-cap", type=int, default=DEFAULT_BYTES_BREACH_CAP)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--api-key")
    parser.add_argument("--json-out")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.preflight_only and not args.query:
        parser.error("--query is required unless --preflight-only is used")

    try:
        params = _parse_params_json(args.params_json)
    except ValueError as exc:
        parser.error(str(exc))

    root = args.base_url.rstrip("/")
    preflight = _run_preflight(root=root, timeout=args.timeout)
    results: list[dict[str, Any]] = list(preflight["results"])

    bundle = None
    local_bundle_error = None
    if not args.preflight_only:
        bundle, local_bundle_error = _load_local_bundle(args.warehouse_ref)
        if local_bundle_error is not None:
            results.append(local_bundle_error)

    artifact: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": root,
        "warehouse_ref": args.warehouse_ref,
        "bad_warehouse_ref": args.bad_warehouse_ref,
        "query": args.query,
        "params": params,
        "api_key_hint": _mask(args.api_key or os.environ.get("RHUMB_API_KEY")),
        "preflight": {
            "configured": preflight["configured"],
            "available_for_execute": preflight["available_for_execute"],
            "resolve": preflight["resolve"],
            "credential_modes": preflight["credential_modes"],
        },
    }

    if args.preflight_only or not preflight["configured"]:
        ok = all(item["ok"] for item in results)
        artifact["ok"] = ok
        artifact["mode"] = "preflight_only" if args.preflight_only else "blocked_preflight"
        artifact["results"] = results
        return _write_artifact(args=args, artifact=artifact, ok=ok, results=results)

    if bundle is None:
        ok = False
        artifact["ok"] = ok
        artifact["mode"] = "blocked_local_bundle"
        artifact["results"] = results
        return _write_artifact(args=args, artifact=artifact, ok=ok, results=results)

    schema_dataset_refs = _default_schema_dataset_refs(bundle, args.dataset_ref)
    schema_table_refs = _default_schema_table_refs(bundle, args.table_ref)
    denied_table_ref = _derive_denied_table_ref(bundle, args.denied_table_ref)

    if args.missing_allowed_table_ref and args.missing_allowed_table_ref not in set(bundle.allowed_table_refs):
        parser.error("--missing-allowed-table-ref must already be allowlisted in the local RHUMB_WAREHOUSE_<REF> bundle")

    api_key = (args.api_key or os.environ.get("RHUMB_API_KEY") or "").strip()
    if not api_key:
        raise SystemExit("Pass --api-key or set RHUMB_API_KEY")

    headers = {
        "Content-Type": "application/json",
        "X-Rhumb-Key": api_key,
    }

    max_rows = min(args.max_rows, bundle.max_rows_returned)
    timeout_ms = min(args.timeout_ms, bundle.statement_timeout_ms)
    max_bytes_billed = bundle.max_bytes_billed

    checks: list[tuple[str, str, dict[str, Any], int, str | None, PayloadCheck | None, bool]] = [
        (
            "warehouse_schema_describe",
            f"{root}/v1/capabilities/warehouse.schema.describe/execute",
            {
                "warehouse_ref": args.warehouse_ref,
                "dataset_refs": schema_dataset_refs,
                "table_refs": schema_table_refs,
                "include_columns": True,
            },
            200,
            None,
            _make_schema_success_check(
                warehouse_ref=args.warehouse_ref,
                location=bundle.location,
                dataset_refs=tuple(schema_dataset_refs),
                table_refs=tuple(schema_table_refs),
            ),
            True,
        ),
        (
            "warehouse_query_read",
            f"{root}/v1/capabilities/warehouse.query.read/execute",
            {
                "warehouse_ref": args.warehouse_ref,
                "query": args.query,
                "params": params,
                "max_rows": max_rows,
                "timeout_ms": timeout_ms,
            },
            200,
            None,
            _make_query_success_check(warehouse_ref=args.warehouse_ref, location=bundle.location),
            True,
        ),
        (
            "bad_warehouse_ref_denial",
            f"{root}/v1/capabilities/warehouse.schema.describe/execute",
            {
                "warehouse_ref": args.bad_warehouse_ref,
                "dataset_refs": schema_dataset_refs,
                "table_refs": schema_table_refs,
                "include_columns": False,
            },
            400,
            "warehouse_ref_invalid",
            None,
            False,
        ),
        (
            "out_of_scope_table_denial",
            f"{root}/v1/capabilities/warehouse.schema.describe/execute",
            {
                "warehouse_ref": args.warehouse_ref,
                "table_refs": [denied_table_ref],
                "include_columns": False,
            },
            403,
            "warehouse_scope_denied",
            None,
            False,
        ),
        (
            "warehouse_query_not_read_only_denial",
            f"{root}/v1/capabilities/warehouse.query.read/execute",
            {
                "warehouse_ref": args.warehouse_ref,
                "query": _derive_not_read_only_query(schema_table_refs[0]),
            },
            422,
            "warehouse_query_not_read_only",
            None,
            False,
        ),
        (
            "warehouse_query_multi_statement_denial",
            f"{root}/v1/capabilities/warehouse.query.read/execute",
            {
                "warehouse_ref": args.warehouse_ref,
                "query": _derive_script_query(schema_table_refs[0]),
            },
            422,
            "warehouse_query_multi_statement_denied",
            None,
            False,
        ),
        (
            "warehouse_bytes_cap_denial",
            f"{root}/v1/capabilities/warehouse.query.read/execute",
            {
                "warehouse_ref": args.warehouse_ref,
                "query": args.query,
                "params": params,
                "max_rows": max_rows,
                "timeout_ms": timeout_ms,
                "max_bytes_billed": args.bytes_breach_cap,
            },
            422,
            "warehouse_bytes_limit_exceeded",
            None,
            False,
        ),
    ]

    if args.missing_allowed_table_ref:
        checks.append(
            (
                "warehouse_object_not_found_denial",
                f"{root}/v1/capabilities/warehouse.schema.describe/execute",
                {
                    "warehouse_ref": args.warehouse_ref,
                    "table_refs": [args.missing_allowed_table_ref],
                    "include_columns": False,
                },
                404,
                "warehouse_object_not_found",
                None,
                False,
            )
        )

    hosted_query_result: dict[str, Any] | None = None
    for name, url, payload, expected_status, expected_error, payload_check, fetch_receipt in checks:
        response = _request_json(
            method="POST",
            url=url,
            headers=headers,
            payload=payload,
            timeout=args.timeout,
        )
        result = _check_result(
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
        results.append(result)
        if name == "warehouse_query_read":
            hosted_query_result = response

    if hosted_query_result is not None:
        results.append(
            _direct_parity_result(
                hosted_query_response=hosted_query_result,
                bundle=bundle,
                query=args.query,
                params=params,
                max_rows=max_rows,
                timeout_ms=timeout_ms,
                max_bytes_billed=max_bytes_billed,
                timeout=args.timeout,
            )
        )

    ok = all(item["ok"] for item in results)
    artifact.update(
        {
            "ok": ok,
            "mode": "full",
            "schema_dataset_refs": schema_dataset_refs,
            "schema_table_refs": schema_table_refs,
            "denied_table_ref": denied_table_ref,
            "missing_allowed_table_ref": args.missing_allowed_table_ref,
            "max_rows": max_rows,
            "timeout_ms": timeout_ms,
            "bytes_breach_cap": args.bytes_breach_cap,
            "local_bundle": _bundle_summary(bundle),
            "results": results,
        }
    )
    return _write_artifact(args=args, artifact=artifact, ok=ok, results=results)


if __name__ == "__main__":
    raise SystemExit(main())
