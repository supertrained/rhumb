#!/usr/bin/env python3
"""Mint a bounded Salesforce Connected App refresh token for the AUD-18 CRM rail.

This helper is intentionally operator-facing and avoids printing secret values by
default. It can:
- source Salesforce Connected App metadata from a 1Password item via `sop`
- build a safe dry-run plan with the authorize URL and follow-on command hints
- run a localhost callback flow or accept a pasted callback URL / auth code
- exchange the authorization code for Salesforce token JSON
- optionally write the raw token payload to a file for later bundle assembly
- print safe follow-on hints for `build_salesforce_crm_bundle.py` and
  `salesforce_crm_read_dogfood.py` when enough bounded CRM scope is supplied
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

DEFAULT_VAULT = "OpenClaw Agents"
DEFAULT_AUTH_BASE_URL = "https://login.salesforce.com"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:1717/callback"
DEFAULT_TIMEOUT = 180.0
DEFAULT_SCOPE = ("api", "refresh_token")
DEFAULT_PROOF_BASE_URL = "https://api.rhumb.dev"
DEFAULT_CRM_REF = "sf_main"
DEFAULT_BAD_CRM_REF = "sf_missing"
DEFAULT_OBJECT_TYPE = "Account"
DEFAULT_DENIED_OBJECT_TYPE = "Contact"
DEFAULT_DENIED_PROPERTY = "OwnerId"
DEFAULT_NOT_FOUND_RECORD_ID = "001000000000000AAA"
ROOT = Path(__file__).resolve().parents[1]


def _now_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _normalize_key(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _normalize_object_type(value: object) -> str:
    text = str(value or "").strip()
    return text


def _normalize_property_name(value: object) -> str:
    text = str(value or "").strip()
    return text


def _normalize_record_id(value: object) -> str:
    text = str(value or "").strip()
    return text


def _parse_string_list(values: list[str] | None) -> list[str]:
    output: list[str] = []
    for raw in values or []:
        for part in str(raw or "").replace(",", " ").split():
            text = part.strip()
            if text:
                output.append(text)
    return _dedupe(output)


def _parse_scoped_cli_values(
    values: list[str] | None,
    *,
    value_normalizer,
) -> list[tuple[str, str]]:
    scoped: list[tuple[str, str]] = []
    for raw in values or []:
        text = str(raw or "").strip()
        if not text:
            continue
        object_type, sep, raw_value = text.partition(":")
        if not sep:
            raise ValueError(f"Scoped value must look like object_type:value, got {raw!r}")
        normalized_object = _normalize_object_type(object_type)
        normalized_value = value_normalizer(raw_value)
        if not normalized_object or not normalized_value:
            raise ValueError(f"Scoped value must include both object_type and value, got {raw!r}")
        pair = (normalized_object, normalized_value)
        if pair not in scoped:
            scoped.append(pair)
    return scoped


def _field_value_map(item: dict[str, Any]) -> dict[str, object]:
    mapped: dict[str, object] = {}
    for field in item.get("fields") or []:
        if not isinstance(field, dict):
            continue
        value = field.get("value")
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        for key_name in ("label", "id", "name", "purpose"):
            key = _normalize_key(field.get(key_name))
            if key and key not in mapped:
                mapped[key] = value
    return mapped


def _first_string(values: dict[str, object], aliases: tuple[str, ...]) -> str | None:
    for alias in aliases:
        key = _normalize_key(alias)
        value = values.get(key)
        text = str(value or "").strip()
        if text:
            return text
    return None


def _load_sop_item(item_name: str, *, vault: str) -> dict[str, Any]:
    result = subprocess.run(
        ["sop", "item", "get", item_name, "--vault", vault, "--format", "json"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        error = (result.stderr or result.stdout or "sop item get failed").strip()
        raise ValueError(f"Unable to load 1Password item {item_name!r} from vault {vault!r}: {error}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"1Password item {item_name!r} did not return valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"1Password item {item_name!r} returned an unexpected payload")
    return payload


def _extract_sop_client_metadata(item: dict[str, Any]) -> dict[str, str | None]:
    values = _field_value_map(item)
    return {
        "client_id": _first_string(values, ("client_id", "consumer_key", "connected_app_client_id")),
        "client_secret": _first_string(
            values,
            ("client_secret", "consumer_secret", "connected_app_client_secret", "secret"),
        ),
        "auth_base_url": _first_string(values, ("auth_base_url", "login_url", "base_url")),
        "redirect_uri": _first_string(values, ("redirect_uri", "callback_url")),
        "connected_app": _first_string(values, ("connected_app", "connected_app_name", "app_name")),
        "account": _first_string(values, ("account", "username", "email")),
    }


def _resolve_oauth_client(args: argparse.Namespace) -> dict[str, Any]:
    sourced: dict[str, str | None] = {}
    if args.from_sop_item:
        sourced = _extract_sop_client_metadata(_load_sop_item(args.from_sop_item, vault=args.vault))

    client_id = str(args.client_id or sourced.get("client_id") or "").strip()
    client_secret = str(args.client_secret or sourced.get("client_secret") or "").strip()
    auth_base_url = _normalize_auth_base_url(args.auth_base_url or sourced.get("auth_base_url"))
    redirect_uri = _normalize_redirect_uri(args.redirect_uri or sourced.get("redirect_uri"))
    if not client_id:
        raise ValueError("--client-id is required unless it can be sourced from --from-sop-item")
    if not client_secret:
        raise ValueError("--client-secret is required unless it can be sourced from --from-sop-item")

    return {
        "source": "1password" if args.from_sop_item else "cli",
        "from_sop_item": args.from_sop_item,
        "vault": args.vault if args.from_sop_item else None,
        "connected_app": sourced.get("connected_app"),
        "account": sourced.get("account"),
        "client_id": client_id,
        "client_secret": client_secret,
        "auth_base_url": auth_base_url,
        "redirect_uri": redirect_uri,
    }


def _normalize_auth_base_url(value: str | None) -> str:
    text = str(value or "").strip() or DEFAULT_AUTH_BASE_URL
    parsed = urllib.parse.urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Invalid auth base URL: {text!r}")
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _normalize_redirect_uri(value: str | None) -> str:
    text = str(value or "").strip() or DEFAULT_REDIRECT_URI
    parsed = urllib.parse.urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Invalid redirect URI: {text!r}")
    path = parsed.path or "/"
    cleaned = parsed._replace(path=path, params="", query="", fragment="")
    return urllib.parse.urlunparse(cleaned)


def _normalize_scopes(values: list[str] | None) -> list[str]:
    scopes = _parse_string_list(values)
    return scopes or list(DEFAULT_SCOPE)


def _mask(value: str | None, head: int = 8, tail: int = 4) -> str | None:
    if not value:
        return None
    if len(value) <= head + tail:
        return value
    return f"{value[:head]}...{value[-tail:]}"


def _build_authorize_url(
    *,
    auth_base_url: str,
    client_id: str,
    redirect_uri: str,
    scopes: list[str],
    state: str,
) -> str:
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
        }
    )
    return f"{auth_base_url}/services/oauth2/authorize?{query}"


def _extract_code_from_manual_input(text: str) -> dict[str, str | None]:
    raw = text.strip()
    if not raw:
        raise ValueError("Expected a pasted callback URL or raw authorization code")
    if "://" not in raw:
        return {"code": raw, "state": None, "error": None, "error_description": None}
    parsed = urllib.parse.urlparse(raw)
    query = urllib.parse.parse_qs(parsed.query)
    return {
        "code": (query.get("code") or [None])[0],
        "state": (query.get("state") or [None])[0],
        "error": (query.get("error") or [None])[0],
        "error_description": (query.get("error_description") or [None])[0],
    }


def _wait_for_local_callback(*, redirect_uri: str, timeout: float) -> dict[str, str | None]:
    parsed = urllib.parse.urlparse(redirect_uri)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    expected_path = parsed.path or "/"

    class CallbackHandler(BaseHTTPRequestHandler):
        server_version = "RhumbSalesforceOAuth/1.0"
        auth_response: dict[str, str | None] | None = None

        def do_GET(self) -> None:  # noqa: N802
            request_path = urllib.parse.urlparse(self.path).path or "/"
            if request_path != expected_path:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Not found")
                return
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            self.__class__.auth_response = {
                "code": (query.get("code") or [None])[0],
                "state": (query.get("state") or [None])[0],
                "error": (query.get("error") or [None])[0],
                "error_description": (query.get("error_description") or [None])[0],
            }
            ok = self.__class__.auth_response.get("code") and not self.__class__.auth_response.get("error")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            body = (
                "<html><body><h1>Salesforce authorization received</h1>"
                "<p>You can return to the terminal.</p></body></html>"
                if ok
                else "<html><body><h1>Salesforce authorization failed</h1>"
                "<p>Return to the terminal for details.</p></body></html>"
            )
            self.wfile.write(body.encode("utf-8"))

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

    deadline = time.time() + timeout
    with HTTPServer((host, port), CallbackHandler) as server:
        server.timeout = min(0.5, max(timeout, 0.5))
        while time.time() < deadline:
            if CallbackHandler.auth_response is not None:
                return CallbackHandler.auth_response
            server.handle_request()
    raise TimeoutError(f"Timed out waiting for Salesforce callback on {redirect_uri}")


def _obtain_authorization_response(*, authorize_url: str, redirect_uri: str, args: argparse.Namespace) -> dict[str, str | None]:
    if args.auth_code:
        return {"code": args.auth_code.strip(), "state": None, "error": None, "error_description": None}

    print(authorize_url)
    sys.stdout.flush()
    if not args.no_browser:
        webbrowser.open(authorize_url)

    if args.manual_code:
        pasted = input("Paste the full callback URL or raw authorization code: ")
        return _extract_code_from_manual_input(pasted)

    parsed = urllib.parse.urlparse(redirect_uri)
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        pasted = input("Paste the full callback URL or raw authorization code: ")
        return _extract_code_from_manual_input(pasted)

    return _wait_for_local_callback(redirect_uri=redirect_uri, timeout=args.timeout)


def _exchange_code_for_tokens(
    *,
    auth_base_url: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code: str,
    timeout: float,
) -> dict[str, Any]:
    payload = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{auth_base_url}/services/oauth2/token",
        data=payload,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            data = json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        error = parsed.get("error_description") or parsed.get("error") or raw or str(exc)
        raise RuntimeError(f"Salesforce token exchange failed with status {exc.code}: {error}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Salesforce token exchange failed: {exc}") from exc

    if not isinstance(data, dict):
        raise RuntimeError("Salesforce token response was not a JSON object")
    refresh_token = str(data.get("refresh_token") or "").strip()
    if not refresh_token:
        raise RuntimeError(
            "Salesforce token response did not include refresh_token. Check Connected App scopes and refresh-token policy."
        )
    return data


def _summarize_token_payload(payload: dict[str, Any]) -> dict[str, Any]:
    access_token = str(payload.get("access_token") or "")
    refresh_token = str(payload.get("refresh_token") or "")
    scope_raw = str(payload.get("scope") or "")
    scopes = [part for part in scope_raw.split() if part]
    return {
        "instance_url": str(payload.get("instance_url") or "") or None,
        "id_url": _mask(str(payload.get("id") or "") or None),
        "issued_at": str(payload.get("issued_at") or "") or None,
        "signature_present": bool(str(payload.get("signature") or "").strip()),
        "token_type": str(payload.get("token_type") or "") or None,
        "scope": scopes,
        "access_token_present": bool(access_token),
        "access_token_length": len(access_token),
        "refresh_token_present": bool(refresh_token),
        "refresh_token_length": len(refresh_token),
    }


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _bundle_scope_args(args: argparse.Namespace, *, auth_base_url: str | None = None) -> list[str]:
    command: list[str] = []
    if args.crm_ref:
        command.extend(["--crm-ref", args.crm_ref])
    selected_auth_base_url = auth_base_url or args.auth_base_url or DEFAULT_AUTH_BASE_URL
    if selected_auth_base_url:
        command.extend(["--auth-base-url", selected_auth_base_url])
    if args.api_version:
        command.extend(["--api-version", args.api_version])
    for value in args.allow_object:
        command.extend(["--allow-object", value])
    for value in args.allow_property:
        command.extend(["--allow-property", value])
    for value in args.default_property:
        command.extend(["--default-property", value])
    for value in args.searchable_property:
        command.extend(["--searchable-property", value])
    for value in args.sortable_property:
        command.extend(["--sortable-property", value])
    for value in args.allowed_record_id:
        command.extend(["--allowed-record-id", value])
    return command


def _build_bundle_command_hint(args: argparse.Namespace, *, token_json_path: Path | None) -> str | None:
    if token_json_path is None:
        return None
    if not args.crm_ref or not args.allow_object or not args.allow_property:
        return None

    oauth_client = _resolve_oauth_client(args)
    bundle_shell_path = Path(args.bundle_shell_out or token_json_path.with_suffix(".bundle.env"))
    refresh_reader = "\n".join(
        [
            "$(python3 - <<'PY'",
            "import json",
            "from pathlib import Path",
            f"print(json.loads(Path({str(token_json_path)!r}).read_text(encoding='utf-8'))['refresh_token'])",
            "PY",
            ")",
        ]
    )
    dollar = chr(36)
    client_id_ref = f'"{dollar}SALESFORCE_CLIENT_ID"'
    client_secret_ref = f'"{dollar}SALESFORCE_CLIENT_SECRET"'
    refresh_token_ref = f'"{dollar}SALESFORCE_REFRESH_TOKEN"'
    builder_parts = [
        "python3",
        shlex.quote(str(ROOT / "scripts" / "build_salesforce_crm_bundle.py")),
        f"--client-id {client_id_ref}",
        f"--client-secret {client_secret_ref}",
        f"--refresh-token {refresh_token_ref}",
    ]
    scoped_args = _bundle_scope_args(args, auth_base_url=str(oauth_client["auth_base_url"]))
    for index in range(0, len(scoped_args), 2):
        flag = scoped_args[index]
        value = scoped_args[index + 1]
        builder_parts.append(f"{flag} {shlex.quote(value)}")
    builder_parts.append("--shell")
    builder = " ".join(builder_parts)
    lines = [
        "# Set SALESFORCE_CLIENT_ID and SALESFORCE_CLIENT_SECRET before running this.",
    ]
    if args.from_sop_item:
        lines.append(f"# You can source those from 1Password item: {args.from_sop_item}")
    lines.append(f"export SALESFORCE_REFRESH_TOKEN={refresh_reader}")
    lines.append(f"{builder} > {shlex.quote(str(bundle_shell_path))}")
    lines.append("unset SALESFORCE_REFRESH_TOKEN")
    return "\n".join(lines)


def _build_proof_command_hint(args: argparse.Namespace, *, token_json_path: Path | None) -> str | None:
    bundle_command = _build_bundle_command_hint(args, token_json_path=token_json_path)
    if bundle_command is None or not args.record_id:
        return None
    bundle_shell_path = Path(args.bundle_shell_out or token_json_path.with_suffix('.bundle.env'))
    command = ["python3", str(ROOT / "scripts" / "salesforce_crm_read_dogfood.py")]
    command.extend(["--base-url", args.base_url])
    command.extend(["--crm-ref", args.crm_ref])
    command.extend(["--bad-crm-ref", args.bad_crm_ref])
    command.extend(["--object-type", args.object_type])
    command.extend(["--denied-object-type", args.denied_object_type])
    command.extend(["--record-id", args.record_id])
    command.extend(["--not-found-record-id", args.not_found_record_id])
    command.extend(["--denied-property", args.denied_property])
    if args.denied_record_id:
        command.extend(["--denied-record-id", args.denied_record_id])
    for value in args.property_name:
        command.extend(["--property-name", value])
    if args.query:
        command.extend(["--query", args.query])
    if args.search_filter_property and args.search_filter_value:
        command.extend(["--search-filter-property", args.search_filter_property])
        command.extend(["--search-filter-value", args.search_filter_value])
        command.extend(["--search-filter-operator", args.search_filter_operator])
    if args.limit != 5:
        command.extend(["--limit", str(args.limit)])
    if args.timeout != DEFAULT_TIMEOUT:
        command.extend(["--timeout", str(args.timeout)])
    proof = shlex.join(command)
    return "\n".join(
        [
            bundle_command,
            f"set -a && source {shlex.quote(str(bundle_shell_path))} && set +a && {proof}",
        ]
    )


def _build_plan(args: argparse.Namespace) -> dict[str, Any]:
    oauth_client = _resolve_oauth_client(args)
    scopes = _normalize_scopes(args.scope)
    state = str(args.state or secrets.token_urlsafe(18)).strip()

    if args.search_filter_property and not args.search_filter_value:
        raise ValueError("--search-filter-value is required when --search-filter-property is passed")
    if args.search_filter_value and not args.search_filter_property:
        raise ValueError("--search-filter-property is required when --search-filter-value is passed")
    _parse_scoped_cli_values(args.allow_property, value_normalizer=_normalize_property_name)
    _parse_scoped_cli_values(args.default_property, value_normalizer=_normalize_property_name)
    _parse_scoped_cli_values(args.searchable_property, value_normalizer=_normalize_property_name)
    _parse_scoped_cli_values(args.sortable_property, value_normalizer=_normalize_property_name)
    _parse_scoped_cli_values(args.allowed_record_id, value_normalizer=_normalize_record_id)

    token_json_path = Path(args.token_json_out).expanduser() if args.token_json_out else None
    authorize_url = _build_authorize_url(
        auth_base_url=str(oauth_client["auth_base_url"]),
        client_id=str(oauth_client["client_id"]),
        redirect_uri=str(oauth_client["redirect_uri"]),
        scopes=scopes,
        state=state,
    )
    return {
        "mode": "dry_run" if args.dry_run else "mint",
        "authorize_url": authorize_url,
        "state": state,
        "oauth_client": {
            "source": oauth_client["source"],
            "from_sop_item": oauth_client["from_sop_item"],
            "vault": oauth_client["vault"],
            "connected_app": oauth_client["connected_app"],
            "account": oauth_client["account"],
            "client_id_length": len(str(oauth_client["client_id"])),
            "client_secret_length": len(str(oauth_client["client_secret"])),
            "auth_base_url": oauth_client["auth_base_url"],
            "redirect_uri": oauth_client["redirect_uri"],
            "scope": scopes,
        },
        "listener": {
            "mode": "manual" if args.manual_code or args.auth_code else "localhost",
            "timeout_seconds": args.timeout,
        },
        "token_json_out": str(token_json_path) if token_json_path else None,
        "bundle_command": _build_bundle_command_hint(args, token_json_path=token_json_path),
        "proof_command": _build_proof_command_hint(args, token_json_path=token_json_path),
    }


def _render_result(payload: dict[str, Any], *, as_json: bool) -> str:
    if as_json:
        return json.dumps(payload, indent=2, sort_keys=True)
    lines = [
        f"mode: {payload.get('mode')}",
        f"authorize_url: {payload.get('authorize_url')}",
    ]
    oauth = payload.get("oauth_client") or {}
    if isinstance(oauth, dict):
        lines.append(f"auth_base_url: {oauth.get('auth_base_url')}")
        lines.append(f"redirect_uri: {oauth.get('redirect_uri')}")
        lines.append(f"scope: {' '.join(oauth.get('scope') or [])}")
    token_summary = payload.get("token_summary")
    if isinstance(token_summary, dict):
        lines.append(f"instance_url: {token_summary.get('instance_url')}")
        lines.append(
            f"refresh_token_present: {token_summary.get('refresh_token_present')} (len={token_summary.get('refresh_token_length')})"
        )
    if payload.get("token_json_out"):
        lines.append(f"token_json_out: {payload['token_json_out']}")
    if payload.get("bundle_command"):
        lines.extend(["bundle_command:", str(payload["bundle_command"])])
    if payload.get("proof_command"):
        lines.extend(["proof_command:", str(payload["proof_command"])])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mint a Salesforce Connected App refresh token for the AUD-18 CRM proof rail"
    )
    parser.add_argument("--client-id")
    parser.add_argument("--client-secret")
    parser.add_argument("--auth-base-url")
    parser.add_argument("--redirect-uri")
    parser.add_argument("--scope", action="append", default=[])
    parser.add_argument("--state")
    parser.add_argument("--from-sop-item")
    parser.add_argument("--vault", default=DEFAULT_VAULT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--auth-code")
    parser.add_argument("--manual-code", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--token-json-out")
    parser.add_argument("--bundle-shell-out")

    parser.add_argument("--crm-ref", default=DEFAULT_CRM_REF)
    parser.add_argument("--bad-crm-ref", default=DEFAULT_BAD_CRM_REF)
    parser.add_argument("--api-version")
    parser.add_argument("--allow-object", action="append", default=[])
    parser.add_argument("--allow-property", action="append", default=[])
    parser.add_argument("--default-property", action="append", default=[])
    parser.add_argument("--searchable-property", action="append", default=[])
    parser.add_argument("--sortable-property", action="append", default=[])
    parser.add_argument("--allowed-record-id", action="append", default=[])

    parser.add_argument("--base-url", default=DEFAULT_PROOF_BASE_URL)
    parser.add_argument("--object-type", default=DEFAULT_OBJECT_TYPE)
    parser.add_argument("--denied-object-type", default=DEFAULT_DENIED_OBJECT_TYPE)
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
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        plan = _build_plan(args)
    except ValueError as exc:
        parser.error(str(exc))

    if args.dry_run:
        print(_render_result(plan, as_json=args.json))
        return 0

    auth_response = _obtain_authorization_response(
        authorize_url=str(plan["authorize_url"]),
        redirect_uri=str(plan["oauth_client"]["redirect_uri"]),
        args=args,
    )
    error = auth_response.get("error")
    if error:
        description = auth_response.get("error_description") or error
        raise SystemExit(f"Salesforce authorization failed: {description}")
    code = str(auth_response.get("code") or "").strip()
    if not code:
        raise SystemExit("Salesforce callback did not include an authorization code")

    expected_state = str(plan["state"])
    returned_state = str(auth_response.get("state") or "").strip() or None
    if returned_state and returned_state != expected_state:
        raise SystemExit("Salesforce callback state mismatch")

    oauth_client = _resolve_oauth_client(args)
    token_payload = _exchange_code_for_tokens(
        auth_base_url=str(oauth_client["auth_base_url"]),
        client_id=str(oauth_client["client_id"]),
        client_secret=str(oauth_client["client_secret"]),
        redirect_uri=str(oauth_client["redirect_uri"]),
        code=code,
        timeout=args.timeout,
    )

    token_json_path = Path(args.token_json_out).expanduser() if args.token_json_out else None
    if token_json_path is not None:
        _write_json_file(token_json_path, token_payload)

    result = dict(plan)
    result["mode"] = "minted"
    result["token_json_out"] = str(token_json_path) if token_json_path else None
    result["token_summary"] = _summarize_token_payload(token_payload)
    result["bundle_command"] = _build_bundle_command_hint(args, token_json_path=token_json_path)
    result["proof_command"] = _build_proof_command_hint(args, token_json_path=token_json_path)
    print(_render_result(result, as_json=args.json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
