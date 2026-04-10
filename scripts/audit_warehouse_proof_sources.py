#!/usr/bin/env python3
"""Audit local proof-source signals for AUD-18 warehouse rails like BigQuery.

This is an operator helper for the credential-sourcing phase of the BigQuery
warehouse read-first wedge. It converts a repeated manual hunt into a
repeatable artifact by scanning:
- 1Password item metadata/details via `sop`
- the rhumb browser profile History DB
- the rhumb browser profile Login Data DB
- Gmail metadata via `gog`
- hosted Rhumb warehouse capability surfaces

It is intentionally conservative: browser/mail traces can prove project or
account history, but only vault-backed service-account or embedded warehouse
bundle material counts as proof-material-ready.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = ROOT / "artifacts"
DEFAULT_HISTORY_DB = Path("/Volumes/tomme 4TB/.openclaw/browser/rhumb/user-data/Default/History")
DEFAULT_LOGIN_DATA_DB = Path("/Volumes/tomme 4TB/.openclaw/browser/rhumb/user-data/Default/Login Data")
DEFAULT_VAULT = "OpenClaw Agents"
DEFAULT_LOCAL_FILE_SCAN_ROOTS = [
    Path("/Users/tom/Downloads"),
    Path("/Users/tom/Desktop"),
    Path("/Users/tom/Documents"),
    Path("/Users/tom/.config"),
    Path("/Volumes/tomme 4TB/.openclaw"),
]
LOCAL_FILE_SCAN_MAX_BYTES = 2_000_000
LOCAL_FILE_SCAN_SKIP_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "browser",
}
DEFAULT_GMAIL_ACCOUNTS = [
    "tommeredith@supertrained.ai",
    "tmeredith@simplaphi.com",
    "tom.d.meredith@gmail.com",
]
DEFAULT_API_BASE = "https://api.rhumb.dev"


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    vault_tokens: tuple[str, ...]
    gmail_query: str
    gmail_terms: tuple[str, ...]
    browser_like_terms: tuple[str, ...]
    login_like_terms: tuple[str, ...]
    generic_public_hosts: tuple[str, ...]
    hosted_capability_ids: tuple[str, ...]


PROVIDERS: dict[str, ProviderConfig] = {
    "bigquery": ProviderConfig(
        name="bigquery",
        vault_tokens=(
            "bigquery",
            "warehouse",
            "gcp",
            "google cloud",
            "service account",
            "analytics",
            "google oauth",
        ),
        gmail_query='("Google Cloud" OR BigQuery OR "service account" OR "Cloud Billing" OR from:(googlecloud-noreply@google.com) OR from:(googlecloudplatform-noreply@google.com))',
        gmail_terms=(
            "google cloud",
            "bigquery",
            "service account",
            "cloud billing",
            "billing account",
            "iam",
            "project",
        ),
        browser_like_terms=(
            "console.cloud.google.com",
            "bigquery",
            "cloud.google.com",
            "iam-admin",
            "serviceaccounts",
        ),
        login_like_terms=(
            "accounts.google.com",
            "console.cloud.google.com",
            "cloud.google.com",
            "bigquery",
        ),
        generic_public_hosts=(
            "cloud.google.com",
            "console.cloud.google.com",
            "accounts.google.com",
            "developers.google.com",
            "bigquery.cloud.google.com",
        ),
        hosted_capability_ids=("warehouse.query.read", "warehouse.schema.describe"),
    ),
}


def _now_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _run(cmd: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def _run_json(cmd: list[str]) -> tuple[Any | None, str | None]:
    code, stdout, stderr = _run(cmd)
    if code != 0:
        return None, (stderr or stdout or f"command failed with exit code {code}").strip()
    try:
        return json.loads(stdout or "null"), None
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON output: {exc}"


def _fetch_json_url(url: str) -> tuple[int | None, Any | None, str | None]:
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            status = response.status
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return None, None, str(exc)

    try:
        payload = json.loads(body or "null")
    except json.JSONDecodeError as exc:
        return status, None, f"invalid JSON response from {url}: {exc}"
    return status, payload, None


def _host_from_url(url: str) -> str | None:
    match = re.match(r"https?://([^/]+)", url, re.I)
    if not match:
        return None
    return match.group(1).lower()


def _dedupe_strings(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def _normalize_key(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


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
        for key_name in ("id", "label", "name", "purpose"):
            key = _normalize_key(field.get(key_name))
            if key and key not in mapped:
                mapped[key] = value
    return mapped


def _first_value(values: dict[str, object], aliases: tuple[str, ...]) -> object | None:
    for alias in aliases:
        key = _normalize_key(alias)
        if key in values:
            return values[key]
    return None


def _first_string(values: dict[str, object], aliases: tuple[str, ...]) -> str | None:
    value = _first_value(values, aliases)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_json_object(value: object, *, label: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None:
        raise ValueError(f"{label} is required")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} is required")
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must decode to a JSON object")
    return parsed


def _parse_string_list(value: object) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return _dedupe_strings([str(item).strip() for item in value if str(item).strip()])
    if isinstance(value, tuple):
        return _dedupe_strings([str(item).strip() for item in value if str(item).strip()])
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return _dedupe_strings([str(item).strip() for item in parsed if str(item).strip()])
    return _dedupe_strings([part.strip() for part in re.split(r"[\s,]+", text) if part.strip()])


def _extract_embedded_bundle(item: dict[str, Any], values: dict[str, object]) -> dict[str, Any]:
    candidates: list[object] = []
    notes = item.get("notesPlain")
    if isinstance(notes, str) and notes.strip():
        candidates.append(notes)
    direct = _first_value(
        values,
        (
            "warehouse_bundle_json",
            "warehouse_bundle",
            "bundle_json",
            "bundle",
        ),
    )
    if direct is not None:
        candidates.append(direct)

    for candidate in candidates:
        try:
            parsed = _parse_json_object(candidate, label="warehouse bundle")
        except (ValueError, json.JSONDecodeError):
            continue
        if str(parsed.get("provider") or "").strip().lower() == "bigquery":
            return parsed
    return {}


def _extract_service_account_json(
    item: dict[str, Any],
    values: dict[str, object],
    embedded_bundle: dict[str, Any],
) -> dict[str, Any] | None:
    candidates: list[object] = [
        _first_value(
            values,
            (
                "service_account_json",
                "google_service_account_json",
                "service_account_key_json",
                "gcp_service_account_json",
                "credentials_json",
                "keyfile_json",
            ),
        ),
        embedded_bundle.get("service_account_json"),
        item.get("notesPlain"),
    ]

    for candidate in candidates:
        if candidate is None:
            continue
        try:
            parsed = _parse_json_object(candidate, label="service account JSON")
        except (ValueError, json.JSONDecodeError):
            continue
        if str(parsed.get("type") or "").strip().lower() == "service_account":
            return parsed
    return None



def _extract_authorized_user_json(
    item: dict[str, Any],
    values: dict[str, object],
    embedded_bundle: dict[str, Any],
) -> dict[str, Any] | None:
    candidates: list[object] = [
        _first_value(
            values,
            (
                "authorized_user_json",
                "google_authorized_user_json",
                "oauth_authorized_user_json",
                "oauth_credentials_json",
            ),
        ),
        embedded_bundle.get("authorized_user_json"),
        item.get("notesPlain"),
    ]

    for candidate in candidates:
        if candidate is None:
            continue
        try:
            parsed = _parse_json_object(candidate, label="authorized user JSON")
        except (ValueError, json.JSONDecodeError):
            continue
        if str(parsed.get("type") or "").strip().lower() == "authorized_user":
            return parsed

    client_id = _first_string(values, ("client_id",))
    client_secret = _first_string(values, ("client_secret",))
    refresh_token = _first_string(
        values,
        (
            "refresh_token",
            "oauth_refresh_token",
            "google_refresh_token",
            "credential",
        ),
    )
    if not client_id or not client_secret or not refresh_token:
        return None

    synthesized: dict[str, Any] = {
        "type": "authorized_user",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }
    token_uri = _first_string(values, ("token_uri",)) or str(embedded_bundle.get("token_uri") or "").strip() or None
    quota_project_id = _first_string(
        values,
        ("quota_project_id", "billing_project_id", "project_id", "gcp_project_id", "bigquery_project_id"),
    ) or str(
        embedded_bundle.get("quota_project_id")
        or embedded_bundle.get("billing_project_id")
        or embedded_bundle.get("project_id")
        or ""
    ).strip() or None
    if token_uri:
        synthesized["token_uri"] = token_uri
    if quota_project_id:
        synthesized["quota_project_id"] = quota_project_id
    return synthesized


def _extract_project_ids(text: str | None) -> list[str]:
    if not text:
        return []
    decoded = urllib.parse.unquote(str(text))
    patterns = [
        r"\bproject(?:_id)?\s*[:=]\s*([a-z][a-z0-9-]{4,61}[a-z0-9])\b",
        r"\(([a-z][a-z0-9-]{4,61}[a-z0-9])\)",
        r"[?&]project=([a-z][a-z0-9-]{4,61}[a-z0-9])\b",
        r"/projects/([a-z][a-z0-9-]{4,61}[a-z0-9])\b",
        r"\bprojects/([a-z][a-z0-9-]{4,61}[a-z0-9])\b",
    ]
    project_ids: list[str] = []
    for pattern in patterns:
        project_ids.extend(re.findall(pattern, decoded, flags=re.I))
    return _dedupe_strings([value.lower() for value in project_ids])


def _redact_url_for_artifact(url: str | None) -> str | None:
    if not url:
        return url
    parts = urllib.parse.urlsplit(url)
    if not parts.query:
        return url
    allowed_keys = {"project", "supportedpurview", "organizationId", "service", "authuser", "creatingProject", "pli"}
    kept: list[tuple[str, str]] = []
    for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True):
        if key in allowed_keys:
            kept.append((key, value))
    query = urllib.parse.urlencode(kept)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def _extract_emails(text: str | None) -> list[str]:
    if not text:
        return []
    return _dedupe_strings([match.lower() for match in re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, flags=re.I)])


def _bigquery_bundle_material(item: dict[str, Any]) -> tuple[bool, list[str], dict[str, Any]]:
    values = _field_value_map(item)
    embedded_bundle = _extract_embedded_bundle(item, values)
    explicit_auth_mode = (
        _first_string(values, ("auth_mode", "authentication_mode"))
        or str(embedded_bundle.get("auth_mode") or "").strip()
        or None
    )
    service_account_json = _extract_service_account_json(item, values, embedded_bundle)
    authorized_user_json = _extract_authorized_user_json(item, values, embedded_bundle)
    service_account_email = (
        _first_string(
            values,
            (
                "service_account_email",
                "impersonated_service_account_email",
                "target_service_account_email",
            ),
        )
        or str(embedded_bundle.get("service_account_email") or "").strip()
        or None
    )

    billing_project_id = (
        _first_string(values, ("billing_project_id", "project_id", "gcp_project_id", "bigquery_project_id"))
        or str(embedded_bundle.get("billing_project_id") or embedded_bundle.get("project_id") or "").strip()
        or None
    )
    location = _first_string(values, ("location", "bigquery_location", "region")) or str(
        embedded_bundle.get("location") or ""
    ).strip() or None
    allowed_dataset_refs = _parse_string_list(
        _first_value(values, ("allowed_dataset_refs", "allowed_dataset_ref", "dataset_refs", "dataset_ref"))
        or embedded_bundle.get("allowed_dataset_refs")
    )
    allowed_table_refs = _parse_string_list(
        _first_value(values, ("allowed_table_refs", "allowed_table_ref", "table_refs", "table_ref"))
        or embedded_bundle.get("allowed_table_refs")
    )

    has_google_oauth_material = all(
        _first_string(values, aliases)
        for aliases in (("client_id",), ("client_secret",), ("project_id",), ("account",))
    )
    auth_mode = str(explicit_auth_mode or "").strip().lower()
    if not auth_mode:
        if authorized_user_json is not None or service_account_email or has_google_oauth_material:
            auth_mode = "service_account_impersonation"
        elif service_account_json is not None:
            auth_mode = "service_account_json"
        else:
            auth_mode = "service_account_json"

    missing: list[str] = []
    if auth_mode == "service_account_impersonation":
        if authorized_user_json is None:
            missing.append("authorized_user_json")
        if not service_account_email:
            missing.append("service_account_email")
    else:
        if service_account_json is None:
            missing.append("service_account_json")
    if not billing_project_id:
        missing.append("billing_project_id")
    if not location:
        missing.append("location")
    if not allowed_dataset_refs:
        missing.append("allowed_dataset_refs")
    if not allowed_table_refs:
        missing.append("allowed_table_refs")

    project_ids: list[str] = []
    if billing_project_id:
        project_ids.append(billing_project_id)
    if service_account_json and service_account_json.get("project_id"):
        project_ids.append(str(service_account_json.get("project_id")))
    if authorized_user_json and authorized_user_json.get("quota_project_id"):
        project_ids.append(str(authorized_user_json.get("quota_project_id")))
    for key in (
        "project_id",
        "gcp_project_id",
        "bigquery_project_id",
        "billing_project_id",
        "notesplain",
        "notes_plain",
        "notes",
    ):
        project_ids.extend(_extract_project_ids(str(values.get(key) or "")))
    project_ids.extend(_extract_project_ids(str(item.get("notesPlain") or "")))
    for ref in [*allowed_dataset_refs, *allowed_table_refs]:
        if "." in ref:
            project_ids.append(ref.split(".", 1)[0])

    accounts: list[str] = []
    if service_account_json and service_account_json.get("client_email"):
        accounts.append(str(service_account_json.get("client_email")))
    if service_account_email:
        accounts.append(service_account_email)
    for key in (
        "account",
        "owner_email",
        "email",
        "username",
        "client_email",
        "service_account_email",
        "impersonated_service_account_email",
        "target_service_account_email",
        "notesplain",
        "notes_plain",
        "notes",
    ):
        accounts.extend(_extract_emails(str(values.get(key) or "")))
    accounts.extend(_extract_emails(str(item.get("notesPlain") or "")))

    details = {
        "project_ids": _dedupe_strings([value.lower() for value in project_ids if value]),
        "candidate_accounts": _dedupe_strings([value.lower() for value in accounts if value]),
        "auth_mode": auth_mode,
        "has_service_account_json": service_account_json is not None,
        "has_authorized_user_json": authorized_user_json is not None,
        "has_embedded_bundle_json": bool(embedded_bundle),
        "has_google_oauth_material": has_google_oauth_material,
        "service_account_email": service_account_email,
        "billing_project_id": billing_project_id,
        "location": location,
        "allowed_dataset_refs": allowed_dataset_refs,
        "allowed_table_refs": allowed_table_refs,
    }
    return not missing, missing, details


def _load_vault_item(item_id: str, vault: str) -> tuple[dict[str, Any] | None, str | None]:
    payload, error = _run_json(["sop", "item", "get", item_id, "--vault", vault, "--format", "json"])
    if error:
        return None, error
    if not isinstance(payload, dict):
        return None, "unexpected item payload"
    return payload, None


def audit_vault(provider: ProviderConfig, vault: str, max_hits: int) -> dict[str, Any]:
    payload, error = _run_json(["sop", "item", "list", "--vault", vault, "--format", "json"])
    if error:
        return {"ok": False, "error": error, "hits": []}

    hits: list[dict[str, Any]] = []
    bundle_ready_hit_count = 0
    project_ids: list[str] = []
    candidate_accounts: list[str] = []

    for item in payload or []:
        blob = json.dumps(item).lower()
        if not any(token in blob for token in provider.vault_tokens):
            continue
        item_id = str(item.get("id") or "").strip()
        item_detail = None
        item_error = None
        bundle_material_ready = False
        missing_bundle_fields: list[str] = []
        details: dict[str, Any] = {
            "project_ids": [],
            "candidate_accounts": [],
            "has_service_account_json": False,
            "has_embedded_bundle_json": False,
            "has_google_oauth_material": False,
            "billing_project_id": None,
            "location": None,
            "allowed_dataset_refs": [],
            "allowed_table_refs": [],
        }
        if item_id:
            item_detail, item_error = _load_vault_item(item_id, vault)
        if item_detail is not None:
            bundle_material_ready, missing_bundle_fields, details = _bigquery_bundle_material(item_detail)
        if bundle_material_ready:
            bundle_ready_hit_count += 1
        project_ids.extend(details.get("project_ids") or [])
        candidate_accounts.extend(details.get("candidate_accounts") or [])
        hits.append(
            {
                "id": item_id,
                "title": item.get("title"),
                "category": item.get("category"),
                "urls": item.get("urls") or [],
                "tags": item.get("tags") or [],
                "bundle_material_ready": bundle_material_ready,
                "missing_bundle_fields": missing_bundle_fields,
                "project_ids": details.get("project_ids") or [],
                "candidate_accounts": details.get("candidate_accounts") or [],
                "auth_mode": details.get("auth_mode"),
                "has_service_account_json": bool(details.get("has_service_account_json")),
                "has_authorized_user_json": bool(details.get("has_authorized_user_json")),
                "has_embedded_bundle_json": bool(details.get("has_embedded_bundle_json")),
                "has_google_oauth_material": bool(details.get("has_google_oauth_material")),
                "service_account_email": details.get("service_account_email"),
                "billing_project_id": details.get("billing_project_id"),
                "location": details.get("location"),
                "allowed_dataset_refs": details.get("allowed_dataset_refs") or [],
                "allowed_table_refs": details.get("allowed_table_refs") or [],
                "item_error": item_error,
            }
        )
        if len(hits) >= max_hits:
            break

    return {
        "ok": True,
        "hits": hits,
        "hit_count": len(hits),
        "bundle_ready_hit_count": bundle_ready_hit_count,
        "project_ids": _dedupe_strings(project_ids),
        "candidate_accounts": _dedupe_strings(candidate_accounts),
    }


def audit_browser_history(provider: ProviderConfig, history_db: Path, max_hits: int) -> dict[str, Any]:
    if not history_db.exists():
        return {"ok": False, "error": f"history DB not found at {history_db}", "hits": []}

    with tempfile.TemporaryDirectory(prefix="warehouse-proof-history-") as tmpdir:
        copy_path = Path(tmpdir) / "History.sqlite"
        shutil.copy2(history_db, copy_path)
        conn = sqlite3.connect(copy_path)
        try:
            where = " OR ".join(["lower(url) LIKE ?", "lower(title) LIKE ?"] * len(provider.browser_like_terms))
            params: list[str] = []
            for term in provider.browser_like_terms:
                like = f"%{term.lower()}%"
                params.extend([like, like])
            rows = conn.execute(
                f"SELECT url, title, last_visit_time FROM urls WHERE {where} ORDER BY last_visit_time DESC LIMIT ?",
                [*params, max_hits],
            ).fetchall()
        finally:
            conn.close()

    hits: list[dict[str, Any]] = []
    hosts: list[str] = []
    workspace_hosts: list[str] = []
    project_ids: list[str] = []

    for url, title, last_visit_time in rows:
        host = _host_from_url(url or "")
        if host:
            hosts.append(host)
            if host not in provider.generic_public_hosts:
                workspace_hosts.append(host)
        project_ids.extend(_extract_project_ids(url or ""))
        project_ids.extend(_extract_project_ids(title or ""))
        hits.append(
            {
                "url": _redact_url_for_artifact(url),
                "title": title,
                "host": host,
                "last_visit_time": last_visit_time,
                "project_ids": _dedupe_strings(_extract_project_ids(url or "") + _extract_project_ids(title or "")),
            }
        )

    return {
        "ok": True,
        "hits": hits,
        "hit_count": len(hits),
        "hosts": _dedupe_strings(hosts),
        "workspace_hosts": _dedupe_strings(workspace_hosts),
        "project_ids": _dedupe_strings(project_ids),
    }


def audit_browser_saved_logins(provider: ProviderConfig, login_data_db: Path, max_hits: int) -> dict[str, Any]:
    if not login_data_db.exists():
        return {"ok": False, "error": f"login DB not found at {login_data_db}", "hits": []}

    with tempfile.TemporaryDirectory(prefix="warehouse-proof-logins-") as tmpdir:
        copy_path = Path(tmpdir) / "Login Data.sqlite"
        shutil.copy2(login_data_db, copy_path)
        conn = sqlite3.connect(copy_path)
        try:
            where = " OR ".join(
                [
                    "lower(origin_url) LIKE ?",
                    "lower(action_url) LIKE ?",
                    "lower(username_value) LIKE ?",
                ]
                * len(provider.login_like_terms)
            )
            params: list[str] = []
            for term in provider.login_like_terms:
                like = f"%{term.lower()}%"
                params.extend([like, like, like])
            rows = conn.execute(
                f"SELECT origin_url, action_url, username_value, date_created FROM logins WHERE {where} ORDER BY date_created DESC LIMIT ?",
                [*params, max_hits],
            ).fetchall()
        finally:
            conn.close()

    hits: list[dict[str, Any]] = []
    hosts: list[str] = []
    usernames: list[str] = []
    for origin_url, action_url, username_value, date_created in rows:
        host = _host_from_url(origin_url or "") or _host_from_url(action_url or "")
        if host:
            hosts.append(host)
        username = str(username_value or "").strip()
        if username:
            usernames.append(username)
        hits.append(
            {
                "origin_url": origin_url,
                "action_url": action_url,
                "host": host,
                "username": username,
                "date_created": date_created,
            }
        )

    return {
        "ok": True,
        "hits": hits,
        "hit_count": len(hits),
        "hosts": _dedupe_strings(hosts),
        "usernames": _dedupe_strings(usernames),
    }


def audit_gmail(provider: ProviderConfig, accounts: list[str], max_hits: int) -> dict[str, Any]:
    account_results: list[dict[str, Any]] = []
    all_hits: list[dict[str, Any]] = []
    project_ids: list[str] = []
    candidate_accounts: list[str] = []

    for account in accounts:
        payload, error = _run_json(
            [
                "gog",
                "gmail",
                "messages",
                "search",
                provider.gmail_query,
                "--max",
                str(max_hits),
                "--json",
                "--no-input",
                "--account",
                account,
            ]
        )
        if error:
            account_results.append({"account": account, "ok": False, "error": error, "hits": []})
            continue

        messages = payload.get("messages") or []
        filtered_hits: list[dict[str, Any]] = []
        for message in messages:
            sender = str(message.get("from") or "")
            subject = str(message.get("subject") or "")
            joined = f"{sender} {subject}".lower()
            if not any(term in joined for term in provider.gmail_terms):
                continue
            hit = {
                "account": account,
                "id": message.get("id"),
                "date": message.get("date"),
                "from": sender,
                "subject": subject,
                "labels": message.get("labels") or [],
                "project_ids": _dedupe_strings(_extract_project_ids(subject) + _extract_project_ids(sender)),
                "emails": _extract_emails(f"{sender} {subject}"),
            }
            project_ids.extend(hit["project_ids"])
            candidate_accounts.extend(hit["emails"])
            filtered_hits.append(hit)
            all_hits.append(hit)

        account_results.append(
            {
                "account": account,
                "ok": True,
                "hit_count": len(filtered_hits),
                "hits": filtered_hits,
            }
        )

    return {
        "ok": all(result.get("ok") for result in account_results) if account_results else True,
        "accounts": account_results,
        "hit_count": len(all_hits),
        "hits": all_hits,
        "project_ids": _dedupe_strings(project_ids),
        "candidate_accounts": _dedupe_strings(candidate_accounts),
    }


def audit_hosted_surface(provider: ProviderConfig, api_base: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    overall_ok = True
    overall_live = True
    overall_configured = True

    for capability_id in provider.hosted_capability_ids:
        get_status, get_payload, get_error = _fetch_json_url(f"{api_base}/v1/capabilities/{capability_id}")
        resolve_status, resolve_payload, resolve_error = _fetch_json_url(
            f"{api_base}/v1/capabilities/{capability_id}/resolve"
        )
        modes_status, modes_payload, modes_error = _fetch_json_url(
            f"{api_base}/v1/capabilities/{capability_id}/credential-modes"
        )

        resolve_provider = None
        if isinstance(resolve_payload, dict):
            providers = ((resolve_payload.get("data") or {}).get("providers") or [])
            resolve_provider = next(
                (item for item in providers if item.get("service_slug") == provider.name),
                providers[0] if providers else None,
            )

        mode_provider = None
        byok_mode = None
        if isinstance(modes_payload, dict):
            providers = ((modes_payload.get("data") or {}).get("providers") or [])
            mode_provider = next(
                (item for item in providers if item.get("service_slug") == provider.name),
                providers[0] if providers else None,
            )
            modes = ((mode_provider or {}).get("modes") or []) if isinstance(mode_provider, dict) else []
            byok_mode = next((item for item in modes if item.get("mode") == "byok"), None)

        live = get_status == 200 and resolve_status == 200 and modes_status == 200
        configured = bool((resolve_provider or {}).get("configured")) and bool((byok_mode or {}).get("configured"))
        ok = all(error is None for error in (get_error, resolve_error, modes_error))
        checks.append(
            {
                "capability_id": capability_id,
                "get_status": get_status,
                "resolve_status": resolve_status,
                "credential_modes_status": modes_status,
                "live": live,
                "resolve_configured": bool((resolve_provider or {}).get("configured")),
                "credential_modes_configured": bool((byok_mode or {}).get("configured"))
                or bool((mode_provider or {}).get("any_configured")),
                "errors": {
                    "get": get_error,
                    "resolve": resolve_error,
                    "credential_modes": modes_error,
                },
                "payloads": {
                    "get": get_payload,
                    "resolve": resolve_payload,
                    "credential_modes": modes_payload,
                },
            }
        )
        overall_ok = overall_ok and ok
        overall_live = overall_live and live
        overall_configured = overall_configured and configured

    return {
        "ok": overall_ok,
        "supported": bool(provider.hosted_capability_ids),
        "checks": checks,
        "live": overall_live,
        "configured": overall_configured,
    }


def audit_local_tooling() -> dict[str, Any]:
    gcloud_path = shutil.which("gcloud")
    return {
        "ok": True,
        "gcloud_installed": bool(gcloud_path),
        "gcloud_path": gcloud_path,
    }


def audit_local_service_account_files(
    roots: list[Path],
    candidate_project_ids: list[str],
    max_hits: int,
) -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    project_ids: list[str] = []
    scanned_file_count = 0
    candidate_project_hit_count = 0
    unrelated_service_account_hit_count = 0

    for root in roots:
        if not root.exists():
            continue
        stop_scan = False
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [name for name in dirnames if name not in LOCAL_FILE_SCAN_SKIP_DIRS]
            for filename in filenames:
                if not filename.lower().endswith(".json"):
                    continue
                path = Path(dirpath) / filename
                scanned_file_count += 1
                try:
                    if path.stat().st_size > LOCAL_FILE_SCAN_MAX_BYTES:
                        continue
                    payload = json.loads(path.read_text())
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if not isinstance(payload, dict):
                    continue
                if str(payload.get("type") or "").strip().lower() != "service_account":
                    continue

                project_id = str(payload.get("project_id") or "").strip()
                project_ids.append(project_id)
                candidate_project_match = bool(project_id and project_id in candidate_project_ids)
                if candidate_project_match:
                    candidate_project_hit_count += 1
                else:
                    unrelated_service_account_hit_count += 1
                hits.append(
                    {
                        "path": str(path),
                        "project_id": project_id or None,
                        "private_key_present": bool(payload.get("private_key")),
                        "private_key_id_present": bool(payload.get("private_key_id")),
                        "candidate_project_match": candidate_project_match,
                    }
                )
                if len(hits) >= max_hits:
                    stop_scan = True
                    break
            if stop_scan:
                break
        if stop_scan:
            break

    return {
        "ok": True,
        "roots": [str(root) for root in roots],
        "scanned_file_count": scanned_file_count,
        "hit_count": len(hits),
        "candidate_project_hit_count": candidate_project_hit_count,
        "unrelated_service_account_hit_count": unrelated_service_account_hit_count,
        "project_ids": _dedupe_strings(project_ids),
        "hits": hits,
    }


def summarize_provider(
    provider: ProviderConfig,
    vault: dict[str, Any],
    browser: dict[str, Any],
    browser_saved_logins: dict[str, Any],
    gmail: dict[str, Any],
    hosted_surface: dict[str, Any],
    local_tooling: dict[str, Any],
    local_service_account_files: dict[str, Any],
) -> dict[str, Any]:
    vault_hit_count = int(vault.get("hit_count") or 0)
    vault_bundle_ready_hit_count = int(vault.get("bundle_ready_hit_count") or 0)
    vault_project_ids = vault.get("project_ids") or []
    vault_candidate_accounts = vault.get("candidate_accounts") or []
    browser_workspace_hosts = browser.get("workspace_hosts") or []
    browser_project_ids = browser.get("project_ids") or []
    browser_saved_login_hits = int(browser_saved_logins.get("hit_count") or 0)
    browser_saved_login_usernames = browser_saved_logins.get("usernames") or []
    gmail_project_ids = gmail.get("project_ids") or []
    gmail_candidate_accounts = gmail.get("candidate_accounts") or []
    proof_material_ready = vault_bundle_ready_hit_count > 0
    likely_blocked = not proof_material_ready
    hosted_surface_live = bool(hosted_surface.get("live"))
    hosted_configured = bool(hosted_surface.get("configured"))
    gcloud_installed = bool(local_tooling.get("gcloud_installed"))
    local_service_account_hit_count = int(local_service_account_files.get("hit_count") or 0)
    local_candidate_project_hit_count = int(local_service_account_files.get("candidate_project_hit_count") or 0)
    local_service_account_project_ids = local_service_account_files.get("project_ids") or []

    candidate_project_ids = _dedupe_strings(
        [*vault_project_ids, *browser_project_ids, *gmail_project_ids]
    )
    candidate_accounts = _dedupe_strings(
        [*vault_candidate_accounts, *browser_saved_login_usernames, *gmail_candidate_accounts]
    )

    if not hosted_surface.get("supported"):
        blocker = "No hosted direct warehouse rail is published yet for this provider."
    elif not hosted_surface_live:
        blocker = "Hosted warehouse surface is not fully live yet, so deploy truth still needs verification before credentials matter."
    elif likely_blocked and vault_hit_count > 0:
        blocker = (
            "Hosted warehouse surface is live, and candidate Google/GCP vault items exist, but none currently contain the scoped BigQuery auth bundle fields required for hosted proof. "
            "Browser, login, and Gmail traces may show project or account history, but they do not constitute operator-ready proof material."
        )
    elif likely_blocked:
        blocker = (
            "Hosted warehouse surface is live, but no vault-backed BigQuery auth bundle was detected. "
            "Browser, login, and Gmail traces may show project or account history, but they do not constitute operator-ready proof material."
        )
    else:
        blocker = "Vault inspection found at least one BigQuery item with the scoped bundle fields required for hosted proof."

    if likely_blocked and candidate_project_ids:
        blocker += f" Candidate project ids surfaced during the audit: {', '.join(candidate_project_ids)}."
    if likely_blocked and candidate_accounts:
        blocker += f" Candidate operator or service accounts surfaced during the audit: {', '.join(candidate_accounts)}."
    if likely_blocked and local_service_account_hit_count and not local_candidate_project_hit_count:
        blocker += " Local file scan found service-account JSON on this machine, but none matched the candidate project ids surfaced for this provider."
    if likely_blocked and not gcloud_installed:
        blocker += " Direct local GCP minting is also blocked on this machine right now because `gcloud` is not installed."

    return {
        "provider": provider.name,
        "vault_hit_count": vault_hit_count,
        "vault_bundle_ready_hit_count": vault_bundle_ready_hit_count,
        "vault_project_ids": vault_project_ids,
        "vault_candidate_accounts": vault_candidate_accounts,
        "browser_workspace_host_count": len(browser_workspace_hosts),
        "browser_workspace_hosts": browser_workspace_hosts,
        "browser_project_ids": browser_project_ids,
        "browser_saved_login_hit_count": browser_saved_login_hits,
        "browser_saved_login_usernames": browser_saved_login_usernames,
        "gmail_hit_count": int(gmail.get("hit_count") or 0),
        "gmail_project_ids": gmail_project_ids,
        "gmail_candidate_accounts": gmail_candidate_accounts,
        "hosted_surface_live": hosted_surface_live,
        "hosted_surface_configured": hosted_configured,
        "gcloud_installed": gcloud_installed,
        "local_service_account_hit_count": local_service_account_hit_count,
        "local_service_account_candidate_project_hit_count": local_candidate_project_hit_count,
        "local_service_account_project_ids": local_service_account_project_ids,
        "proof_material_ready": proof_material_ready,
        "likely_blocked_on_credentials": likely_blocked,
        "assessment": blocker,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit local warehouse proof-source signals")
    parser.add_argument("--provider", choices=["bigquery", "all"], default="all")
    parser.add_argument("--vault", default=DEFAULT_VAULT)
    parser.add_argument("--browser-history", type=Path, default=DEFAULT_HISTORY_DB)
    parser.add_argument("--browser-login-data", type=Path, default=DEFAULT_LOGIN_DATA_DB)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--gmail-account", action="append", default=[])
    parser.add_argument("--local-file-scan-root", action="append", default=[])
    parser.add_argument("--skip-local-file-scan", action="store_true")
    parser.add_argument("--max-hits", type=int, default=25)
    parser.add_argument("--json-out")
    parser.add_argument("--summary-only", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    providers = [args.provider] if args.provider != "all" else list(PROVIDERS.keys())
    accounts = args.gmail_account or DEFAULT_GMAIL_ACCOUNTS
    local_file_scan_roots = [Path(root) for root in (args.local_file_scan_root or [])] or DEFAULT_LOCAL_FILE_SCAN_ROOTS

    result: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "vault": args.vault,
        "browser_history": str(args.browser_history),
        "browser_login_data": str(args.browser_login_data),
        "api_base": args.api_base,
        "gmail_accounts": accounts,
        "local_file_scan_roots": [str(root) for root in local_file_scan_roots],
        "providers": {},
        "summary": [],
    }

    for provider_name in providers:
        provider = PROVIDERS[provider_name]
        vault = audit_vault(provider, args.vault, args.max_hits)
        browser = audit_browser_history(provider, args.browser_history, args.max_hits)
        browser_saved_logins = audit_browser_saved_logins(provider, args.browser_login_data, args.max_hits)
        gmail = audit_gmail(provider, accounts, args.max_hits)
        hosted_surface = audit_hosted_surface(provider, args.api_base)
        local_tooling = audit_local_tooling()
        candidate_project_ids = _dedupe_strings(
            [
                *(vault.get("project_ids") or []),
                *(browser.get("project_ids") or []),
                *(gmail.get("project_ids") or []),
            ]
        )
        local_service_account_files = (
            {"ok": True, "roots": [], "scanned_file_count": 0, "hit_count": 0, "candidate_project_hit_count": 0, "unrelated_service_account_hit_count": 0, "project_ids": [], "hits": []}
            if args.skip_local_file_scan
            else audit_local_service_account_files(local_file_scan_roots, candidate_project_ids, args.max_hits)
        )
        summary = summarize_provider(
            provider,
            vault,
            browser,
            browser_saved_logins,
            gmail,
            hosted_surface,
            local_tooling,
            local_service_account_files,
        )
        result["providers"][provider_name] = {
            "vault": vault,
            "browser": browser,
            "browser_saved_logins": browser_saved_logins,
            "gmail": gmail,
            "hosted_surface": hosted_surface,
            "local_tooling": local_tooling,
            "local_service_account_files": local_service_account_files,
            "summary": summary,
        }
        result["summary"].append(summary)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = (
        Path(args.json_out) if args.json_out else ARTIFACTS_DIR / f"aud18-bigquery-proof-source-audit-{_now_slug()}.json"
    )
    artifact_path.write_text(json.dumps(result, indent=2))

    print(str(artifact_path))
    if args.summary_only:
        for summary in result["summary"]:
            print(
                f"{summary['provider']}: vault_hits={summary['vault_hit_count']} "
                f"bundle_ready={summary['vault_bundle_ready_hit_count']} "
                f"vault_projects={','.join(summary['vault_project_ids']) or '-'} "
                f"saved_logins={summary['browser_saved_login_hit_count']} "
                f"browser_projects={','.join(summary['browser_project_ids']) or '-'} "
                f"gmail_hits={summary['gmail_hit_count']} "
                f"gmail_projects={','.join(summary['gmail_project_ids']) or '-'} "
                f"local_sa_hits={summary['local_service_account_hit_count']} "
                f"local_sa_candidate_hits={summary['local_service_account_candidate_project_hit_count']} "
                f"gcloud_installed={summary['gcloud_installed']} "
                f"hosted_live={summary['hosted_surface_live']} "
                f"hosted_configured={summary['hosted_surface_configured']} "
                f"proof_ready={summary['proof_material_ready']}"
            )
    else:
        print(json.dumps(result["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
