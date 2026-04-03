#!/usr/bin/env python3
"""Twilio current-depth runtime review pass — 2026-04-03.

Twilio is the stalest provider in the live weakest callable bucket after Stripe
moved to depth 10. This pass re-verifies the safe BYO `phone.lookup` path through
Rhumb Resolve against direct Twilio Lookup v2 and publishes a fresh runtime-backed
review pair.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages/api"))

from db.client import get_supabase_client  # noqa: E402
from schemas.agent_identity import AgentIdentityStore  # noqa: E402
from services.billing_bootstrap import ensure_org_billing_bootstrap  # noqa: E402

BASE_URL = "https://api.rhumb.dev/v1"
PROVIDER = "twilio"
CAPABILITY_ID = "phone.lookup"
NUMBER = "+14155552671"
LOOKUP_FIELDS = "line_type_intelligence"
TWILIO_LOOKUP_URL = f"https://lookups.twilio.com/v2/PhoneNumbers/{NUMBER}"
PUBLIC_SERVICE_SLUG = "twilio"
CANONICAL_PUBLISH_SLUG = "twilio"
POST_GRANT_PROPAGATION_DELAY_SECONDS = 5
ESTIMATE_AUTH_RETRY_ATTEMPTS = 4
ESTIMATE_AUTH_RETRY_DELAY_SECONDS = 5
RUNTIME_BACKED_TRUST_LABELS = {"🟢 Runtime-verified", "🧪 Tester-generated"}


@dataclass
class HttpResult:
    status_code: int
    body: Any


async def _request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json_body: Any | None = None,
    timeout: float = 120.0,
) -> HttpResult:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(
            method,
            url,
            headers=headers,
            params=params,
            json=json_body,
        )
    try:
        body: Any = response.json()
    except Exception:
        body = response.text
    return HttpResult(status_code=response.status_code, body=body)


def _json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _looks_like_invalid_key(body: Any) -> bool:
    if not isinstance(body, dict):
        return False
    detail = str(body.get("detail") or "").lower()
    error = str(body.get("error") or "").lower()
    return "invalid or expired rhumb api key" in detail or "invalid or expired rhumb api key" in error


def _iso_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _extract_review_stats(body: Any) -> dict[str, int | None]:
    reviews = []
    if isinstance(body, dict):
        maybe_reviews = body.get("reviews")
        if isinstance(maybe_reviews, list):
            reviews = maybe_reviews
        else:
            data = body.get("data")
            if isinstance(data, dict) and isinstance(data.get("reviews"), list):
                reviews = data.get("reviews") or []
    runtime_backed = 0
    published = 0
    for review in reviews:
        if not isinstance(review, dict):
            continue
        if review.get("status") == "published" or review.get("review_status") == "published":
            published += 1
        source_type = review.get("source_type") or review.get("sourceType")
        trust_label = review.get("trust_label") or review.get("trustLabel")
        if source_type == "runtime_verified" or trust_label in RUNTIME_BACKED_TRUST_LABELS:
            runtime_backed += 1
    return {
        "published_reviews": published or (len(reviews) if isinstance(reviews, list) else None),
        "runtime_backed_reviews": runtime_backed,
    }


async def _fetch_public_review_stats(service_slug: str) -> dict[str, int | None]:
    result = await _request_json("GET", f"{BASE_URL}/services/{service_slug}/reviews", timeout=60.0)
    if result.status_code != 200:
        return {"published_reviews": None, "runtime_backed_reviews": None}
    return _extract_review_stats(result.body)


def _run_publish(args: list[str], output_path: Path) -> dict[str, Any]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(REPO_ROOT / "packages/api") + (f":{existing}" if existing else "")
    proc = subprocess.run(
        [str(REPO_ROOT / "packages/api/.venv/bin/python"), str(REPO_ROOT / "scripts/publish_runtime_review_pair.py"), *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"publish_runtime_review_pair.py failed ({proc.returncode})\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    payload = json.loads(proc.stdout)
    _json_dump(output_path, payload)
    return payload


def _pick_fields(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    line_type = payload.get("line_type_intelligence")
    if not isinstance(line_type, dict):
        line_type = {}
    return {
        "phone_number": payload.get("phone_number"),
        "valid": payload.get("valid"),
        "country_code": payload.get("country_code"),
        "calling_country_code": payload.get("calling_country_code"),
        "national_format": payload.get("national_format"),
        "line_type_intelligence": {
            "type": line_type.get("type"),
            "carrier_name": line_type.get("carrier_name"),
            "error_code": line_type.get("error_code"),
        },
    }


async def main() -> None:
    started_at = datetime.now(tz=UTC)
    stamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    short = uuid.uuid4().hex[:8]
    artifact_path = REPO_ROOT / f"artifacts/runtime-review-pass-{stamp}-twilio-depth10.json"
    publication_path = REPO_ROOT / "artifacts/runtime-review-publication-2026-04-03-twilio-depth10.json"
    org_id = f"org_runtime_review_twilio_{stamp.lower()}_{short}"

    payload: dict[str, Any] = {
        "provider": PROVIDER,
        "canonical_publish_slug": CANONICAL_PUBLISH_SLUG,
        "capability_id": CAPABILITY_ID,
        "number": NUMBER,
        "fields": LOOKUP_FIELDS,
        "review_kind": "current_depth10",
        "organization_id": org_id,
        "artifact_path": str(artifact_path.relative_to(REPO_ROOT)),
        "started_at": started_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    _json_dump(artifact_path, payload)

    supabase = await get_supabase_client()
    store = AgentIdentityStore(supabase)

    bootstrap = await ensure_org_billing_bootstrap(
        org_id,
        name=f"runtime-review-twilio-{stamp}",
        starter_credits_cents=5000,
    )
    payload["bootstrap"] = bootstrap

    agent_id, api_key = await store.register_agent(
        name=f"runtime-review-twilio-{stamp}",
        organization_id=org_id,
        rate_limit_qpm=100,
        description="Temp review agent for Twilio depth-10 runtime pass",
        tags=["runtime_review", "phase3", "current_pass", "twilio", "depth10"],
    )
    payload["review_agent"] = {
        "agent_id": agent_id,
        "organization_id": org_id,
    }

    access_id = await store.grant_service_access(agent_id, CANONICAL_PUBLISH_SLUG)
    payload["grant_access"] = {
        "status": "success",
        "access_id": access_id,
    }
    payload["post_grant_delay_seconds"] = POST_GRANT_PROPAGATION_DELAY_SECONDS
    _json_dump(artifact_path, payload)

    await asyncio.sleep(POST_GRANT_PROPAGATION_DELAY_SECONDS)

    api_headers = {"X-Rhumb-Key": api_key}
    twilio_basic_auth = os.environ["RHUMB_CREDENTIAL_TWILIO_BASIC_AUTH"]
    basic_header = "Basic " + base64.b64encode(twilio_basic_auth.encode("utf-8")).decode("ascii")

    try:
        counts_before = await _fetch_public_review_stats(PUBLIC_SERVICE_SLUG)
        estimate_attempts = 0
        estimate = HttpResult(status_code=0, body=None)
        while estimate_attempts < ESTIMATE_AUTH_RETRY_ATTEMPTS:
            estimate_attempts += 1
            estimate = await _request_json(
                "GET",
                f"{BASE_URL}/capabilities/{CAPABILITY_ID}/execute/estimate",
                headers=api_headers,
                params={"provider": PROVIDER, "credential_mode": "byo"},
                timeout=60.0,
            )
            if not (
                estimate.status_code == 401
                and _looks_like_invalid_key(estimate.body)
                and estimate_attempts < ESTIMATE_AUTH_RETRY_ATTEMPTS
            ):
                break
            await asyncio.sleep(ESTIMATE_AUTH_RETRY_DELAY_SECONDS)

        execute = await _request_json(
            "POST",
            f"{BASE_URL}/capabilities/{CAPABILITY_ID}/execute",
            headers=api_headers,
            params={"provider": PROVIDER, "credential_mode": "byo"},
            json_body={
                "method": "GET",
                "path": f"/v2/PhoneNumbers/{NUMBER}",
                "params": {"Fields": LOOKUP_FIELDS},
            },
            timeout=120.0,
        )
        direct = await _request_json(
            "GET",
            TWILIO_LOOKUP_URL,
            headers={"Authorization": basic_header},
            params={"Fields": LOOKUP_FIELDS},
            timeout=60.0,
        )

        rhumb_payload = ((execute.body or {}).get("data") or {}) if isinstance(execute.body, dict) else {}
        rhumb_upstream = (rhumb_payload.get("upstream_response") or {}) if isinstance(rhumb_payload, dict) else {}
        rhumb_fields = _pick_fields(rhumb_upstream if isinstance(rhumb_upstream, dict) else {})
        direct_fields = _pick_fields(direct.body if isinstance(direct.body, dict) else {})
        observed_at = _iso_now()
        reviewed_at_dt = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        fresh_until = (reviewed_at_dt + timedelta(days=30)).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        comparison = {
            "provider_used": rhumb_payload.get("provider_used"),
            "upstream_status": rhumb_payload.get("upstream_status"),
            "execution_id": rhumb_payload.get("execution_id"),
            "rhumb_fields": rhumb_fields,
            "direct_fields": direct_fields,
            "parity": rhumb_fields == direct_fields,
        }

        estimate_pattern = (((estimate.body or {}).get("data") or {}).get("endpoint_pattern")) if isinstance(estimate.body, dict) else None
        catalog_note = None
        if isinstance(estimate_pattern, str) and "carrier" in estimate_pattern.lower() and LOOKUP_FIELDS != "carrier":
            catalog_note = {
                "estimate_endpoint_pattern": estimate_pattern,
                "runtime_field_used": LOOKUP_FIELDS,
                "observation": "Twilio Lookup v2 accepted Fields=line_type_intelligence; estimate still advertises the deprecated carrier field.",
            }

        verdict = "pass" if (
            estimate.status_code == 200
            and execute.status_code == 200
            and direct.status_code == 200
            and rhumb_payload.get("provider_used") == CANONICAL_PUBLISH_SLUG
            and rhumb_payload.get("upstream_status") == 200
            and comparison["parity"]
        ) else "fail"

        payload.update(
            {
                "observed_at": observed_at,
                "fresh_until": fresh_until,
                "counts_before": counts_before,
                "estimate": {
                    "status": estimate.status_code,
                    "attempts": estimate_attempts,
                    "data": estimate.body,
                },
                "rhumb": {
                    "status": execute.status_code,
                    "data": execute.body,
                },
                "direct": {
                    "status": direct.status_code,
                    "data": direct.body,
                },
                "comparison": comparison,
                "catalog_note": catalog_note,
                "verdict": verdict,
            }
        )
        _json_dump(artifact_path, payload)

        if verdict != "pass":
            raise RuntimeError("Twilio depth-10 runtime pass failed; inspect artifact for parity details")

        execution_id = rhumb_payload.get("execution_id") or ""
        publication = _run_publish(
            [
                "--service", CANONICAL_PUBLISH_SLUG,
                "--headline", "Twilio: depth-10 runtime review confirms phone.lookup parity through Rhumb Resolve",
                "--summary", "Fresh depth-10 runtime review passed for Twilio phone.lookup through Rhumb Resolve. BYO execution and direct Twilio Lookup v2 returned the same normalized phone record for the same number using Fields=line_type_intelligence.",
                "--evidence-title", "Twilio depth-10 runtime review parity check via Rhumb Resolve",
                "--evidence-summary", "Fresh depth-10 runtime review passed for Twilio phone.lookup through Rhumb Resolve. BYO execution matched direct Twilio Lookup v2 on phone_number, validity, country metadata, and line_type_intelligence payload.",
                "--source-ref", f"runtime-review:twilio:{stamp}",
                "--source-batch-id", f"runtime-review:twilio:{stamp}",
                "--reviewed-at", observed_at,
                "--fresh-until", fresh_until,
                "--reviewer-agent-id", agent_id,
                "--agent-id", agent_id,
                "--run-id", execution_id,
                "--tag", "runtime_review",
                "--tag", "twilio",
                "--tag", "phone.lookup",
                "--tag", "current_pass",
                "--tag", "phase3",
                "--tag", "depth10",
                "--raw-payload-file", str(artifact_path.relative_to(REPO_ROOT)),
            ],
            publication_path,
        )
        payload["published"] = {
            "canonical_service_slug": CANONICAL_PUBLISH_SLUG,
            "public_service_route": PUBLIC_SERVICE_SLUG,
            "evidence_id": (publication.get("evidence") or {}).get("id"),
            "review_id": (publication.get("review") or {}).get("id"),
            "execution_id": execution_id,
        }
        payload["counts_after"] = await _fetch_public_review_stats(PUBLIC_SERVICE_SLUG)
        _json_dump(artifact_path, payload)
    finally:
        disabled = await store.disable_agent(agent_id)
        payload["agent_disabled"] = bool(disabled)
        _json_dump(artifact_path, payload)


if __name__ == "__main__":
    asyncio.run(main())
