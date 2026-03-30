#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages/api"))

from db.client import get_supabase_client  # noqa: E402
from schemas.agent_identity import AgentIdentityStore  # noqa: E402
from services.billing_bootstrap import ensure_org_billing_bootstrap  # noqa: E402

BASE_URL = "https://api.rhumb.dev/v1"
GOOGLE_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
SERVICE_SLUG = "google-ai"
MODEL = "gemini-2.5-flash"
SENTINEL = "RHUMB_GOOGLE_AI_20260330_DEPTH5"
INPUT_BODY = {
    "model": MODEL,
    "contents": [
        {
            "parts": [
                {
                    "text": f"Reply with exactly: {SENTINEL}",
                }
            ]
        }
    ],
    "generationConfig": {"temperature": 0},
}


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
        if source_type == "runtime_verified" or trust_label == "🟢 Runtime-verified":
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


def _extract_text(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    candidates = body.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return None
    candidate = candidates[0]
    if not isinstance(candidate, dict):
        return None
    content = candidate.get("content")
    if not isinstance(content, dict):
        return None
    parts = content.get("parts")
    if not isinstance(parts, list) or not parts:
        return None
    part = parts[0]
    if not isinstance(part, dict):
        return None
    text = part.get("text")
    return text if isinstance(text, str) else None


async def main() -> None:
    started_at = datetime.now(tz=UTC)
    stamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    artifact_path = REPO_ROOT / f"artifacts/runtime-review-pass-{stamp}-google-ai-current-depth5.json"
    publication_path = REPO_ROOT / "artifacts/runtime-review-publication-2026-03-30-google-ai-depth5.json"
    org_id = f"org_runtime_review_google_ai_{stamp.lower()}"

    payload: dict[str, Any] = {
        "provider": SERVICE_SLUG,
        "model": MODEL,
        "sentinel": SENTINEL,
        "review_kind": "current_depth5",
        "organization_id": org_id,
        "artifact_path": str(artifact_path),
    }
    _json_dump(artifact_path, payload)

    supabase = await get_supabase_client()
    store = AgentIdentityStore(supabase)

    bootstrap = await ensure_org_billing_bootstrap(
        org_id,
        name=f"runtime-review-google-ai-{stamp}",
        starter_credits_cents=5000,
    )
    payload["bootstrap"] = bootstrap

    agent_id, api_key = await store.register_agent(
        name=f"runtime-review-google-ai-{stamp}",
        organization_id=org_id,
        rate_limit_qpm=100,
        description="Temp review agent for Google AI depth-5 runtime pass",
        tags=["runtime_review", "phase3", "current_pass", "google-ai"],
    )
    payload["review_agent"] = {
        "agent_id": agent_id,
        "organization_id": org_id,
    }

    access_id = await store.grant_service_access(agent_id, SERVICE_SLUG)
    payload["grant_access"] = {
        "status": "success",
        "access_id": access_id,
    }
    _json_dump(artifact_path, payload)

    api_headers = {"X-Rhumb-Key": api_key}
    google_api_key = os.environ["RHUMB_CREDENTIAL_GOOGLE_AI_API_KEY"]
    direct_url = f"{GOOGLE_BASE_URL}/models/{quote(MODEL, safe='')}:generateContent"

    try:
        counts_before = await _fetch_public_review_stats(SERVICE_SLUG)
        estimate = await _request_json(
            "GET",
            f"{BASE_URL}/capabilities/ai.generate_text/execute/estimate",
            headers=api_headers,
            params={"provider": SERVICE_SLUG, "credential_mode": "rhumb_managed"},
            timeout=60.0,
        )
        execute = await _request_json(
            "POST",
            f"{BASE_URL}/capabilities/ai.generate_text/execute",
            headers=api_headers,
            params={"provider": SERVICE_SLUG, "credential_mode": "rhumb_managed"},
            json_body=INPUT_BODY,
            timeout=120.0,
        )
        direct = await _request_json(
            "POST",
            direct_url,
            headers={"Content-Type": "application/json"},
            params={"key": google_api_key},
            json_body={
                "contents": INPUT_BODY["contents"],
                "generationConfig": INPUT_BODY["generationConfig"],
            },
            timeout=120.0,
        )

        rhumb_payload = ((execute.body or {}).get("data") or {}) if isinstance(execute.body, dict) else {}
        rhumb_upstream = (rhumb_payload.get("upstream_response") or {}) if isinstance(rhumb_payload, dict) else {}
        rhumb_text = _extract_text(rhumb_upstream)
        direct_text = _extract_text(direct.body)
        observed_at = _iso_now()
        reviewed_at_dt = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        fresh_until = (reviewed_at_dt + timedelta(days=30)).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        comparison = {
            "rhumb_provider_used": rhumb_payload.get("provider_used"),
            "rhumb_upstream_status": rhumb_payload.get("upstream_status"),
            "rhumb_model_version": rhumb_upstream.get("modelVersion") if isinstance(rhumb_upstream, dict) else None,
            "direct_model_version": direct.body.get("modelVersion") if isinstance(direct.body, dict) else None,
            "rhumb_text": rhumb_text,
            "direct_text": direct_text,
            "text_match": rhumb_text == direct_text,
            "sentinel_match": rhumb_text == SENTINEL == direct_text,
        }

        verdict = "pass" if (
            estimate.status_code == 200
            and execute.status_code == 200
            and direct.status_code == 200
            and rhumb_payload.get("provider_used") == SERVICE_SLUG
            and rhumb_payload.get("upstream_status") == 200
            and comparison["text_match"]
            and comparison["sentinel_match"]
        ) else "fail"

        payload.update(
            {
                "observed_at": observed_at,
                "fresh_until": fresh_until,
                "counts_before": counts_before,
                "estimate": {"status": estimate.status_code, "data": estimate.body},
                "rhumb": {
                    "status": execute.status_code,
                    "data": execute.body,
                },
                "direct": {
                    "status": direct.status_code,
                    "data": direct.body,
                },
                "comparison": comparison,
                "verdict": verdict,
            }
        )
        _json_dump(artifact_path, payload)

        if verdict != "pass":
            raise RuntimeError("Google AI depth-5 runtime pass failed; inspect artifact for parity details")

        execution_id = rhumb_payload.get("execution_id") or ""
        publication = _run_publish(
            [
                "--service", SERVICE_SLUG,
                "--headline", "Google AI: current-depth rerun confirms ai.generate_text parity through Rhumb Resolve again",
                "--summary", "Fresh current-depth runtime rerun passed for Google AI ai.generate_text through Rhumb Resolve. Managed and direct executions matched on exact output text for the same Gemini 2.5 Flash prompt, lifting the public runtime-backed review stack another layer.",
                "--evidence-title", "Google AI current-depth runtime rerun parity check via Rhumb Resolve",
                "--evidence-summary", "Fresh current-depth runtime rerun passed for Google AI ai.generate_text through Rhumb Resolve. Managed and direct executions matched on exact output text for the same Gemini 2.5 Flash prompt.",
                "--source-ref", f"runtime-review:google-ai:{stamp}",
                "--source-batch-id", f"runtime-review:google-ai:{stamp}",
                "--reviewed-at", observed_at,
                "--fresh-until", fresh_until,
                "--reviewer-agent-id", agent_id,
                "--agent-id", agent_id,
                "--run-id", execution_id,
                "--tag", "runtime_review",
                "--tag", "google-ai",
                "--tag", "ai.generate_text",
                "--tag", "current_pass",
                "--tag", "phase3",
                "--raw-payload-file", str(artifact_path.relative_to(REPO_ROOT)),
            ],
            publication_path,
        )
        payload["published"] = {
            "service_slug": SERVICE_SLUG,
            "evidence_id": (publication.get("evidence") or {}).get("id"),
            "review_id": (publication.get("review") or {}).get("id"),
            "execution_id": execution_id,
        }
        payload["counts_after"] = await _fetch_public_review_stats(SERVICE_SLUG)
        _json_dump(artifact_path, payload)
    finally:
        disabled = await store.disable_agent(agent_id)
        payload["agent_disabled"] = bool(disabled)
        _json_dump(artifact_path, payload)


if __name__ == "__main__":
    asyncio.run(main())
