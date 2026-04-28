#!/usr/bin/env python3
"""Prove the bounded DC90 ElevenLabs managed text-to-speech fixture.

The fixture generates exactly one tiny "OK" audio sample through Rhumb-managed
`media.generate_speech`, stores only compact evidence (byte length/hash), and
loads the governed Rhumb key from 1Password at runtime. No secrets or audio bytes
are written to disk.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

BASE_URL = "https://api.rhumb.dev"
VAULT = "OpenClaw Agents"
RHUMB_KEY_ITEMS = (
    "Rhumb API Key - pedro-dogfood",
    "Rhumb API Key - atlas@supertrained.ai",
)
CAPABILITY_ID = "media.generate_speech"
PROVIDER = "elevenlabs"
VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # ElevenLabs Rachel, standard low-cost fixture voice.
MODEL_ID = "eleven_multilingual_v2"
FIXTURE_TEXT = "OK"


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sop_field(title: str, field: str = "credential") -> str | None:
    cp = subprocess.run(
        ["sop", "item", "get", title, "--vault", VAULT, "--fields", field, "--reveal"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=25,
        check=False,
    )
    if cp.returncode != 0:
        return None
    value = (cp.stdout or "").replace("\r", "").replace("\n", "").strip()
    return value or None


def request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: Any | None = None,
    timeout: float = 60.0,
) -> tuple[int, Any]:
    data = None
    merged_headers = {
        "Accept": "application/json",
        "User-Agent": "rhumb-dc90-elevenlabs-tts-smoke/2026-04-28",
    }
    if headers:
        merged_headers.update(headers)
    if body is not None:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        merged_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=merged_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = int(getattr(resp, "status", 0) or 0)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = int(exc.code)
    except Exception as exc:  # pragma: no cover - diagnostic path for cron runs
        return 0, {"transport_error": type(exc).__name__, "message": str(exc)}

    try:
        return status, json.loads(raw.decode("utf-8"))
    except Exception:
        return status, {
            "non_json_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }


def rhumb_url(path: str) -> str:
    return f"{BASE_URL.rstrip('/')}{path}"


def rhumb_headers(api_key: str) -> dict[str, str]:
    return {"X-Rhumb-Key": api_key, "x-api-key": api_key}


def load_working_rhumb_key() -> tuple[str, str]:
    for title in RHUMB_KEY_ITEMS:
        key = sop_field(title)
        if not key:
            continue
        status, _payload = request_json(
            "GET",
            rhumb_url("/v1/capabilities?limit=1"),
            headers=rhumb_headers(key),
            timeout=20,
        )
        if 200 <= status < 300:
            return title, key
        status, _payload = request_json(
            "GET",
            rhumb_url("/v1/billing/balance"),
            headers=rhumb_headers(key),
            timeout=20,
        )
        if 200 <= status < 300:
            return title, key
    raise SystemExit("No working Rhumb dogfood governed key found in 1Password")


def compact_step(name: str, status: int, payload: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"name": name, "http_status": status}
    if not isinstance(payload, dict):
        out["payload_type"] = type(payload).__name__
        out["payload_hash16"] = hashlib.sha256(str(payload).encode()).hexdigest()[:16]
        return out

    out["top_level_keys"] = sorted(payload.keys())[:20]
    if payload.get("error") is not None:
        out["error"] = payload.get("error")
    for key in ("detail", "message", "resolution", "request_id"):
        if isinstance(payload.get(key), str):
            out[key] = payload[key]

    data = payload.get("data")
    if isinstance(data, dict):
        out["data_keys"] = sorted(data.keys())[:30]
        for key in (
            "capability_id",
            "provider",
            "credential_mode",
            "provider_used",
            "receipt_id",
            "execution_id",
            "cost_estimate_usd",
            "budget_remaining_usd",
            "latency_ms",
            "upstream_status",
        ):
            if key in data:
                out[key] = data[key]
        upstream = data.get("upstream_response")
        if isinstance(upstream, str):
            # ElevenLabs returns base64-ish/audio payload through Rhumb; do not
            # persist the bytes. Keep only compact evidence that audio returned.
            out["upstream_audio_text_len"] = len(upstream)
            out["upstream_audio_sha256_16"] = hashlib.sha256(upstream.encode()).hexdigest()[:16]
        elif isinstance(upstream, dict):
            out["upstream_keys"] = sorted(upstream.keys())[:30]
            rendered = json.dumps(upstream, sort_keys=True, separators=(",", ":"))
            out["upstream_json_sha256_16"] = hashlib.sha256(rendered.encode()).hexdigest()[:16]
        elif upstream is not None:
            out["upstream_summary"] = {
                "type": type(upstream).__name__,
                "sha256_16": hashlib.sha256(str(upstream).encode()).hexdigest()[:16],
            }
    return out


def main() -> int:
    global BASE_URL
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=BASE_URL)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    BASE_URL = args.base_url.rstrip("/")

    stamp = utc_stamp()
    out = args.out or f"artifacts/dc90-elevenlabs-tts-smoke-{stamp}.json"
    key_title, api_key = load_working_rhumb_key()
    cap = urllib.parse.quote(CAPABILITY_ID, safe="")
    steps: list[dict[str, Any]] = []

    status, payload = request_json(
        "GET",
        rhumb_url(f"/v1/capabilities/{cap}/resolve?credential_mode=rhumb_managed"),
        headers=rhumb_headers(api_key),
        timeout=30,
    )
    steps.append(compact_step("resolve", status, payload))

    status, payload = request_json(
        "GET",
        rhumb_url(f"/v1/capabilities/{cap}/execute/estimate?provider={PROVIDER}&credential_mode=rhumb_managed"),
        headers=rhumb_headers(api_key),
        timeout=30,
    )
    estimate_step = compact_step("estimate", status, payload)
    steps.append(estimate_step)

    execute_ran = False
    if 200 <= status < 300:
        body = {
            "provider": PROVIDER,
            "credential_mode": "rhumb_managed",
            "interface": "dc90-elevenlabs-tts-smoke-20260428",
            "idempotency_key": f"dc90-elevenlabs-tts-{int(time.time() * 1000)}",
            "body": {
                "voice_id": VOICE_ID,
                "text": FIXTURE_TEXT,
                "model_id": MODEL_ID,
            },
        }
        status, payload = request_json(
            "POST",
            rhumb_url(f"/v1/capabilities/{cap}/execute"),
            headers=rhumb_headers(api_key),
            body=body,
            timeout=90,
        )
        execute_ran = True
        steps.append(compact_step("execute", status, payload))

    execute_step = steps[-1] if execute_ran else {}
    audio_len = execute_step.get("upstream_audio_text_len")
    passed = bool(
        execute_ran
        and execute_step.get("http_status") == 200
        and execute_step.get("provider_used") == PROVIDER
        and execute_step.get("credential_mode") == "rhumb_managed"
        and execute_step.get("upstream_status") == 200
        and execute_step.get("receipt_id")
        and isinstance(audio_len, int)
        and audio_len > 100
    )

    report = {
        "timestamp_utc": stamp,
        "base_url": BASE_URL,
        "secret_written": False,
        "audio_bytes_written": False,
        "rhumb_key_item": key_title,
        "fixture": {
            "capability_id": CAPABILITY_ID,
            "provider": PROVIDER,
            "safety_class": "amber",
            "text": FIXTURE_TEXT,
            "voice_id": VOICE_ID,
            "model_id": MODEL_ID,
            "execute_ran": execute_ran,
            "passed": passed,
            "steps": steps,
        },
        "summary": {
            "passed": passed,
            "execute_ran": execute_ran,
            "receipt_id": execute_step.get("receipt_id"),
            "upstream_status": execute_step.get("upstream_status"),
            "audio_evidence_hash16": execute_step.get("upstream_audio_sha256_16"),
            "audio_evidence_len": audio_len,
            "estimated_cost_usd": estimate_step.get("cost_estimate_usd"),
        },
    }

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    print(json.dumps({"out": out, "summary": report["summary"]}, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
