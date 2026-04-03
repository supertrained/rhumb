#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import uuid
from dataclasses import asdict, dataclass
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
REPLICATE_BASE_URL = "https://api.replicate.com/v1"
SERVICE_SLUG = "replicate"
CAPABILITY_ID = "ai.generate_text"
MODEL_VERSION = "5a6809ca6288247d06daf6365557e5e429063f32a21146b2a807c682652136b8"
SYSTEM_PROMPT = "You are a precise assistant."
MAX_DIRECT_CREATE_ATTEMPTS = 3
DIRECT_RETRY_AFTER_SECONDS = 10
POLL_TIMEOUT_SECONDS = 120.0


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


async def _poll_prediction(api_token: str, prediction_id: str, *, timeout_seconds: float = POLL_TIMEOUT_SECONDS) -> HttpResult:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    last: HttpResult | None = None
    while True:
        last = await _request_json(
            "GET",
            f"{REPLICATE_BASE_URL}/predictions/{prediction_id}",
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=60.0,
        )
        status = last.body.get("status") if isinstance(last.body, dict) else None
        if status in {"succeeded", "failed", "canceled"}:
            return last
        if asyncio.get_running_loop().time() >= deadline:
            return last
        await asyncio.sleep(2.0)


async def _create_direct_prediction(
    api_token: str,
    payload: dict[str, Any],
    *,
    max_attempts: int = MAX_DIRECT_CREATE_ATTEMPTS,
) -> tuple[HttpResult, list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    last: HttpResult | None = None
    for attempt in range(1, max_attempts + 1):
        last = await _request_json(
            "POST",
            f"{REPLICATE_BASE_URL}/predictions",
            headers={"Authorization": f"Bearer {api_token}"},
            json_body=payload,
            timeout=120.0,
        )
        attempts.append(
            {
                "attempt": attempt,
                "status_code": last.status_code,
                "body": last.body,
            }
        )
        if last.status_code != 429:
            return last, attempts
        retry_after = DIRECT_RETRY_AFTER_SECONDS
        if isinstance(last.body, dict):
            retry_after = int(last.body.get("retry_after") or last.body.get("retryAfter") or retry_after)
        await asyncio.sleep(float(retry_after))
    assert last is not None
    return last, attempts


def _iso_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


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
        if source_type == "runtime_verified" or trust_label in {"🟢 Runtime-verified", "🧪 Tester-generated"}:
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
        [
            str(REPO_ROOT / "packages/api/.venv/bin/python"),
            str(REPO_ROOT / "scripts/publish_runtime_review_pair.py"),
            *args,
        ],
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


def _flatten_output(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = [chunk for chunk in value if isinstance(chunk, str)]
        return "".join(parts).strip()
    return None


async def main() -> None:
    started_at = datetime.now(tz=UTC)
    stamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    short = uuid.uuid4().hex[:8]
    expected_output = f"REPLICATE_DEPTH10_OK_{stamp}"
    prompt = f"Reply with exactly {expected_output}"
    model_input = {
        "prompt": prompt,
        "system_prompt": SYSTEM_PROMPT,
        "max_new_tokens": 20,
        "temperature": 0.1,
    }
    execute_body = {
        "version": MODEL_VERSION,
        "input": model_input,
    }
    artifact_path = REPO_ROOT / f"artifacts/runtime-review-pass-{stamp}-replicate-depth10.json"
    publication_path = REPO_ROOT / "artifacts/runtime-review-publication-2026-04-02-replicate-depth10.json"
    org_id = f"org_runtime_review_replicate_{stamp.lower()}_{short}"

    payload: dict[str, Any] = {
        "provider": SERVICE_SLUG,
        "capability_id": CAPABILITY_ID,
        "review_kind": "current_depth10",
        "started_at": started_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "artifact_path": str(artifact_path.relative_to(REPO_ROOT)),
        "organization_id": org_id,
        "execute_body": execute_body,
        "expected_output": expected_output,
    }
    _json_dump(artifact_path, payload)

    supabase = await get_supabase_client()
    store = AgentIdentityStore(supabase)

    bootstrap = await ensure_org_billing_bootstrap(
        org_id,
        name=f"runtime-review-replicate-{stamp}",
        starter_credits_cents=5000,
    )
    payload["wallet_bootstrap"] = bootstrap
    _json_dump(artifact_path, payload)

    agent_id, api_key = await store.register_agent(
        name=f"runtime-review-replicate-{stamp}",
        organization_id=org_id,
        rate_limit_qpm=100,
        description="Temp review agent for Replicate depth-10 runtime pass",
        tags=["runtime_review", "phase3", "current_pass", SERVICE_SLUG, "depth10"],
    )
    payload["review_agent"] = {
        "agent_id": agent_id,
        "organization_id": org_id,
    }

    access_id = await store.grant_service_access(agent_id, SERVICE_SLUG)
    payload["grant_access"] = {
        "service": SERVICE_SLUG,
        "status": "success",
        "access_id": access_id,
    }
    _json_dump(artifact_path, payload)

    api_headers = {"X-Rhumb-Key": api_key}
    replicate_token = os.environ["RHUMB_CREDENTIAL_REPLICATE_API_TOKEN"]

    try:
        counts_before = await _fetch_public_review_stats(SERVICE_SLUG)
        estimate = await _request_json(
            "GET",
            f"{BASE_URL}/capabilities/{CAPABILITY_ID}/execute/estimate",
            headers=api_headers,
            params={"provider": SERVICE_SLUG, "credential_mode": "rhumb_managed"},
            timeout=60.0,
        )
        execute = await _request_json(
            "POST",
            f"{BASE_URL}/capabilities/{CAPABILITY_ID}/execute",
            headers=api_headers,
            params={"provider": SERVICE_SLUG, "credential_mode": "rhumb_managed"},
            json_body=execute_body,
            timeout=120.0,
        )

        execute_data = ((execute.body or {}).get("data") or {}) if isinstance(execute.body, dict) else {}
        rhumb_upstream = (execute_data.get("upstream_response") or {}) if isinstance(execute_data, dict) else {}
        rhumb_prediction_id = rhumb_upstream.get("id")
        rhumb_final = (
            await _poll_prediction(replicate_token, rhumb_prediction_id)
            if rhumb_prediction_id
            else HttpResult(status_code=0, body=None)
        )

        direct_create, direct_attempts = await _create_direct_prediction(
            replicate_token,
            execute_body,
            max_attempts=MAX_DIRECT_CREATE_ATTEMPTS,
        )
        direct_create_body = direct_create.body if isinstance(direct_create.body, dict) else {}
        direct_prediction_id = direct_create_body.get("id")
        direct_final = (
            await _poll_prediction(replicate_token, direct_prediction_id)
            if direct_prediction_id
            else HttpResult(status_code=0, body=None)
        )

        rhumb_final_body = rhumb_final.body if isinstance(rhumb_final.body, dict) else {}
        direct_final_body = direct_final.body if isinstance(direct_final.body, dict) else {}
        rhumb_output = _flatten_output(rhumb_final_body.get("output"))
        direct_output = _flatten_output(direct_final_body.get("output"))

        comparison = {
            "prompt": prompt,
            "rhumb_prediction_id": rhumb_prediction_id,
            "direct_prediction_id": direct_prediction_id,
            "rhumb_status": rhumb_final_body.get("status"),
            "direct_status": direct_final_body.get("status"),
            "rhumb_output": rhumb_output,
            "direct_output": direct_output,
            "status_match": rhumb_final_body.get("status") == direct_final_body.get("status"),
            "output_match": rhumb_output == direct_output == expected_output,
            "provider_used": execute_data.get("provider_used"),
            "upstream_status": execute_data.get("upstream_status"),
            "execution_id": execute_data.get("execution_id"),
        }

        verdict = "pass" if (
            estimate.status_code == 200
            and execute.status_code == 200
            and execute_data.get("provider_used") == SERVICE_SLUG
            and execute_data.get("upstream_status") == 201
            and rhumb_final.status_code == 200
            and direct_create.status_code == 201
            and direct_final.status_code == 200
            and comparison["status_match"]
            and comparison["output_match"]
            and comparison["rhumb_status"] == "succeeded"
        ) else "fail"

        observed_at = _iso_now()
        fresh_until = (
            datetime.fromisoformat(observed_at.replace("Z", "+00:00")) + timedelta(days=30)
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        payload.update(
            {
                "reviewed_at": observed_at,
                "fresh_until": fresh_until,
                "counts_before": counts_before,
                "estimate": asdict(estimate),
                "rhumb_execute": asdict(execute),
                "rhumb_final": asdict(rhumb_final),
                "direct_create_attempts": direct_attempts,
                "direct_create": asdict(direct_create),
                "direct_final": asdict(direct_final),
                "comparison": comparison,
                "verdict": verdict,
            }
        )
        _json_dump(artifact_path, payload)

        if verdict != "pass":
            raise RuntimeError("Replicate depth-10 runtime pass failed; inspect artifact for parity details")

        publication = _run_publish(
            [
                "--service", SERVICE_SLUG,
                "--headline", "Replicate: depth-10 runtime review confirms ai.generate_text parity through Rhumb Resolve",
                "--summary", "Fresh depth-10 runtime review passed for Replicate ai.generate_text through Rhumb Resolve. Managed and direct executions both created successful predictions and matched on final succeeded state and exact text output for the same pinned model version.",
                "--evidence-title", "Replicate depth-10 runtime review parity check via Rhumb Resolve",
                "--evidence-summary", "Fresh depth-10 runtime review passed for Replicate ai.generate_text through Rhumb Resolve. Managed and direct executions both created successful predictions and matched on final succeeded state and exact text output for the same pinned model version.",
                "--source-ref", f"runtime-review:replicate:{stamp}",
                "--source-batch-id", f"runtime-review:replicate:{stamp}",
                "--reviewed-at", observed_at,
                "--fresh-until", fresh_until,
                "--reviewer-agent-id", agent_id,
                "--agent-id", agent_id,
                "--run-id", execute_data.get("execution_id") or "",
                "--tag", "runtime_review",
                "--tag", SERVICE_SLUG,
                "--tag", CAPABILITY_ID,
                "--tag", "current_pass",
                "--tag", "phase3",
                "--tag", "depth10",
                "--raw-payload-file", str(artifact_path.relative_to(REPO_ROOT)),
            ],
            publication_path,
        )
        payload["publication"] = publication
        payload["counts_after"] = await _fetch_public_review_stats(SERVICE_SLUG)
        _json_dump(artifact_path, payload)
    finally:
        disabled = await store.disable_agent(agent_id)
        payload["disable_agent"] = {
            "status_code": 200 if disabled else 404,
            "body": {"status": "success" if disabled else "not_found", "agent_id": agent_id},
        }
        _json_dump(artifact_path, payload)


if __name__ == "__main__":
    asyncio.run(main())
