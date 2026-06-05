#!/usr/bin/env python3
"""Resolve launch-catalog smoke for Rhumb-managed agent capabilities.

This script proves the P0 public launch catalog through resolve + estimate, and
can execute only bounded, non-send/non-post/non-CRM fixtures. It writes compact
redacted artifacts only. Secrets are loaded from RHUMB_DOGFOOD_API_KEY or
1Password via `sop` and are never written to disk.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://api.rhumb.dev"
DEFAULT_VAULT = "OpenClaw Agents"
DEFAULT_RHUMB_KEY_ITEMS = (
    "Rhumb API Key - pedro-dogfood",
    "Rhumb API Key - atlas@supertrained.ai",
)

P0_CATALOG: dict[str, dict[str, Any]] = {
    "search.query": {
        "provider": "exa",
        "safety": "green",
        "execution_policy": "safe_execute",
        "body": {"query": "agent native API capability routing", "numResults": 3},
    },
    "scrape.extract": {
        "provider": "firecrawl",
        "safety": "green",
        "execution_policy": "safe_execute",
        "body": {
            "url": "https://example.com",
            "formats": ["markdown"],
            "onlyMainContent": True,
        },
    },
    "ai.generate_text": {
        "provider": "openai",
        "safety": "green",
        "execution_policy": "safe_execute",
        "body": {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "Answer with exactly four words."},
                {"role": "user", "content": "Name the purpose of Resolve."},
            ],
            "max_tokens": 20,
            "temperature": 0,
        },
    },
    "ai.generate_image": {
        "provider": "openai",
        "safety": "amber",
        "execution_policy": "safe_execute",
        "body": {
            "model": "gpt-image-1",
            "prompt": (
                "A simple abstract blue compass icon on a plain white background, "
                "no text, no people."
            ),
            "size": "1024x1024",
            "quality": "low",
            "n": 1,
        },
    },
    "data.enrich_person": {
        "provider": "people-data-labs",
        "safety": "amber",
        "execution_policy": "proof_substitute",
        "proof_substitute": (
            "Resolve + estimate only until a consented internal person fixture is approved."
        ),
    },
    "data.enrich_company": {
        "provider": "apollo",
        "safety": "amber",
        "execution_policy": "safe_execute",
        "body": {"domain": "rhumb.dev"},
    },
    "geo.lookup": {
        "provider": "ipinfo",
        "safety": "green",
        "execution_policy": "safe_execute",
        "body": {"ip": "8.8.8.8"},
    },
    "maps.places_search": {
        "provider": "google-places",
        "safety": "green",
        "execution_policy": "safe_execute",
        "body": {"query": "Golden Gate Park San Francisco"},
    },
}

DEFERRED_CAPABILITIES: dict[str, str] = {
    "email.send": "External-write capability; requires owned sender, one-message cap, idempotency, and explicit approval.",
    "email.verify": "No managed provider is configured in the current hosted Resolve surface.",
    "sendgrid": "Registered proxy provider, but non-callable until RHUMB_CREDENTIAL_SENDGRID_API_KEY is configured.",
}


def _json_hash16(value: Any) -> str:
    rendered = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()[:16]


def _load_key_from_sop(title: str, vault: str) -> str | None:
    try:
        cp = subprocess.run(
            ["sop", "item", "get", title, "--vault", vault, "--fields", "credential", "--reveal"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=25,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if cp.returncode != 0:
        return None
    value = (cp.stdout or "").replace("\r", "").replace("\n", "").strip()
    return value or None


class RhumbClient:
    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def request(
        self,
        method: str,
        path: str,
        *,
        auth: bool = False,
        body: Any | None = None,
        timeout: float = 90.0,
    ) -> tuple[int, Any]:
        data = None
        headers = {
            "Accept": "application/json",
            "User-Agent": "rhumb-launch-catalog-smoke/2026-06",
        }
        if auth and self.api_key:
            headers["X-Rhumb-Key"] = self.api_key
        if body is not None:
            data = json.dumps(body, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                status = int(getattr(resp, "status", 0) or 0)
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = int(exc.code)
        except Exception as exc:  # pragma: no cover - live diagnostic path
            return 0, {"transport_error": type(exc).__name__, "message": str(exc)}

        if not raw:
            return status, None
        try:
            return status, json.loads(raw.decode("utf-8"))
        except Exception:
            return status, {
                "non_json_bytes": len(raw),
                "sha256_16": hashlib.sha256(raw).hexdigest()[:16],
            }


def load_working_key(base_url: str, vault: str, item_names: tuple[str, ...]) -> tuple[str, str]:
    env_value = os.environ.get("RHUMB_DOGFOOD_API_KEY", "").strip()
    candidates: list[tuple[str, str]] = []
    if env_value:
        candidates.append(("RHUMB_DOGFOOD_API_KEY", env_value))
    for item_name in item_names:
        value = _load_key_from_sop(item_name, vault)
        if value:
            candidates.append((item_name, value))

    for source, key in candidates:
        status, _payload = RhumbClient(base_url, key).request(
            "GET",
            "/v1/billing/balance",
            auth=True,
            timeout=20,
        )
        if 200 <= status < 300:
            return source, key
    raise SystemExit("No working Rhumb governed API key found.")


def _find_scalar_values(value: Any, keys: set[str]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in keys and isinstance(child, (str, int, float, bool)):
                found.append({key: child if not isinstance(child, str) else child[:160]})
            found.extend(_find_scalar_values(child, keys))
    elif isinstance(value, list):
        for child in value:
            found.extend(_find_scalar_values(child, keys))
    return found[:8]


def compact_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"payload_type": type(payload).__name__, "payload_hash16": _json_hash16(payload)}

    out: dict[str, Any] = {"top_keys": sorted(payload.keys())[:20]}
    for key in ("error", "message", "detail", "resolution", "request_id"):
        if isinstance(payload.get(key), str):
            out[key] = payload[key]

    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if isinstance(data, dict):
        out["data_keys"] = sorted(data.keys())[:30]
        for key in (
            "capability_id",
            "provider",
            "provider_used",
            "credential_mode",
            "upstream_status",
            "execution_id",
            "receipt_id",
            "latency_ms",
            "cost_estimate_usd",
            "estimated_cost_usd",
        ):
            if key in data:
                out[key] = data[key]

        upstream = data.get("upstream_response")
        if upstream is not None:
            out["upstream_type"] = type(upstream).__name__
            out["upstream_hash16"] = _json_hash16(upstream)
            if isinstance(upstream, dict):
                out["upstream_keys"] = sorted(upstream.keys())[:25]
                out["evidence_values"] = _find_scalar_values(
                    upstream,
                    {
                        "ip",
                        "city",
                        "region",
                        "country",
                        "name",
                        "formatted_address",
                        "title",
                        "url",
                        "link",
                    },
                )
                if isinstance(upstream.get("data"), list):
                    out["upstream_data_count"] = len(upstream["data"])
                    out["upstream_data_shapes"] = [
                        {
                            "keys": sorted(item.keys()),
                            "b64_json_len": (
                                len(item.get("b64_json", ""))
                                if isinstance(item, dict) and isinstance(item.get("b64_json"), str)
                                else None
                            ),
                            "url_present": (
                                isinstance(item.get("url"), str)
                                if isinstance(item, dict)
                                else False
                            ),
                            "item_hash16": _json_hash16(item),
                        }
                        for item in upstream["data"][:2]
                    ]
                nested = upstream.get("data") if isinstance(upstream.get("data"), dict) else {}
                if isinstance(nested, dict):
                    if isinstance(nested.get("markdown"), str):
                        markdown = nested["markdown"]
                        out["markdown_len"] = len(markdown)
                        out["markdown_hash16"] = hashlib.sha256(
                            markdown.encode("utf-8")
                        ).hexdigest()[:16]
                    if isinstance(nested.get("metadata"), dict):
                        out["metadata_keys"] = sorted(nested["metadata"].keys())[:20]

                candidates: list[Any] = []
                for result_key in ("results", "web", "items"):
                    if isinstance(upstream.get(result_key), list):
                        candidates = upstream[result_key]
                        break
                if isinstance(nested, dict):
                    for result_key in ("results", "items"):
                        if isinstance(nested.get(result_key), list):
                            candidates = nested[result_key]
                            break
                if candidates:
                    out["result_count_observed"] = len(candidates)
                    out["top_result_shapes"] = [
                        (
                            {"keys": sorted(item.keys())[:12], "hash16": _json_hash16(item)}
                            if isinstance(item, dict)
                            else {"type": type(item).__name__, "hash16": _json_hash16(item)}
                        )
                        for item in candidates[:3]
                    ]
    return out


def prove_catalog(client: RhumbClient, *, execute_safe: bool) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for capability, spec in P0_CATALOG.items():
        provider = str(spec["provider"])
        encoded_cap = urllib.parse.quote(capability, safe="")
        encoded_provider = urllib.parse.quote(provider, safe="")
        record: dict[str, Any] = {
            "capability": capability,
            "provider": provider,
            "safety": spec["safety"],
            "execution_policy": spec["execution_policy"],
        }

        resolve_status, resolve_payload = client.request(
            "GET",
            f"/v1/capabilities/{encoded_cap}/resolve?credential_mode=rhumb_managed",
            auth=True,
            timeout=45,
        )
        record["resolve_status"] = resolve_status
        record["resolve"] = compact_payload(resolve_payload)

        estimate_status, estimate_payload = client.request(
            "GET",
            (
                f"/v1/capabilities/{encoded_cap}/execute/estimate"
                f"?credential_mode=rhumb_managed&provider={encoded_provider}"
            ),
            auth=True,
            timeout=45,
        )
        record["estimate_status"] = estimate_status
        record["estimate"] = compact_payload(estimate_payload)

        should_execute = (
            execute_safe
            and spec["execution_policy"] == "safe_execute"
            and 200 <= estimate_status < 300
        )
        record["execute_ran"] = False
        if should_execute:
            status, payload = client.request(
                "POST",
                f"/v1/capabilities/{encoded_cap}/execute",
                auth=True,
                body={
                    "provider": provider,
                    "credential_mode": "rhumb_managed",
                    "interface": "launch-catalog-smoke-202606",
                    "idempotency_key": f"launch-{capability}-{provider}-{int(time.time() * 1000)}",
                    "body": spec["body"],
                },
                timeout=120,
            )
            record["execute_ran"] = True
            record["execute_status"] = status
            record["execute"] = compact_payload(payload)
        elif spec["execution_policy"] == "proof_substitute":
            record["proof_substitute"] = spec.get("proof_substitute")

        records.append(record)
    return records


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--out", required=True, help="Path for compact redacted JSON artifact")
    ap.add_argument("--execute-safe", action="store_true", help="Run bounded non-write executions")
    ap.add_argument("--vault", default=DEFAULT_VAULT)
    args = ap.parse_args()

    key_source, api_key = load_working_key(args.base_url, args.vault, DEFAULT_RHUMB_KEY_ITEMS)
    client = RhumbClient(args.base_url, api_key)
    records = prove_catalog(client, execute_safe=args.execute_safe)
    summary = {
        "base_url": args.base_url,
        "key_source": key_source,
        "execute_safe": args.execute_safe,
        "p0_count": len(P0_CATALOG),
        "deferred_capabilities": DEFERRED_CAPABILITIES,
        "records": records,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, sort_keys=True))
    print(
        json.dumps(
            [
                {
                    "capability": r["capability"],
                    "provider": r["provider"],
                    "resolve_status": r.get("resolve_status"),
                    "estimate_status": r.get("estimate_status"),
                    "execute_ran": r.get("execute_ran"),
                    "execute_status": r.get("execute_status"),
                    "receipt_id": (r.get("execute") or {}).get("receipt_id"),
                    "proof_substitute": r.get("proof_substitute"),
                }
                for r in records
            ],
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
