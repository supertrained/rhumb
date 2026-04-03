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
E2B_BASE_URL = "https://api.e2b.app"
SERVICE_SLUG = "e2b"
CREATE_CAPABILITY_ID = "agent.spawn"
STATUS_CAPABILITY_ID = "agent.get_status"
POST_GRANT_PROPAGATION_DELAY_SECONDS = 5
ESTIMATE_AUTH_RETRY_ATTEMPTS = 4
ESTIMATE_AUTH_RETRY_DELAY_SECONDS = 5
REVIEW_TEMPLATE = {
    "templateID": "base",
    "timeout": 300,
}


@dataclass
class HttpResult:
    status_code: int
    body: Any


RUNTIME_BACKED_TRUST_LABELS = {"🟢 Runtime-verified", "🧪 Tester-generated"}


def _json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _iso_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _looks_like_invalid_key(body: Any) -> bool:
    if not isinstance(body, dict):
        return False
    detail = str(body.get("detail") or "").lower()
    error = str(body.get("error") or "").lower()
    return "invalid or expired rhumb api key" in detail or "invalid or expired rhumb api key" in error


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


async def _delete_direct_sandbox(api_key: str, sandbox_id: str | None) -> int | None:
    if not sandbox_id:
        return None
    result = await _request_json(
        "DELETE",
        f"{E2B_BASE_URL}/sandboxes/{sandbox_id}",
        headers={"X-API-Key": api_key},
        timeout=60.0,
    )
    return result.status_code


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


def _summarize_create(result: HttpResult) -> dict[str, Any]:
    body = result.body if isinstance(result.body, dict) else {}
    data = (body.get("data") or {}) if isinstance(body, dict) else {}
    upstream = (data.get("upstream_response") or {}) if isinstance(data, dict) else {}
    return {
        "status_code": result.status_code,
        "execution_id": data.get("execution_id"),
        "provider_used": data.get("provider_used"),
        "credential_mode": data.get("credential_mode"),
        "upstream_status": data.get("upstream_status"),
        "sandbox": {
            "sandboxID": upstream.get("sandboxID"),
            "templateID": upstream.get("templateID"),
            "alias": upstream.get("alias"),
            "envdVersion": upstream.get("envdVersion"),
        },
        "raw": result.body,
    }


def _summarize_status(result: HttpResult) -> dict[str, Any]:
    body = result.body if isinstance(result.body, dict) else {}
    data = (body.get("data") or {}) if isinstance(body, dict) else {}
    upstream = (data.get("upstream_response") or {}) if isinstance(data, dict) else {}
    return {
        "status_code": result.status_code,
        "execution_id": data.get("execution_id"),
        "provider_used": data.get("provider_used"),
        "credential_mode": data.get("credential_mode"),
        "upstream_status": data.get("upstream_status"),
        "sandbox": {
            "sandboxID": upstream.get("sandboxID"),
            "templateID": upstream.get("templateID"),
            "alias": upstream.get("alias"),
            "state": upstream.get("state"),
            "envdVersion": upstream.get("envdVersion"),
            "cpuCount": upstream.get("cpuCount"),
            "memoryMB": upstream.get("memoryMB"),
        },
        "raw": result.body,
    }


def _summarize_direct_create(result: HttpResult) -> dict[str, Any]:
    body = result.body if isinstance(result.body, dict) else {}
    return {
        "status_code": result.status_code,
        "sandbox": {
            "sandboxID": body.get("sandboxID"),
            "templateID": body.get("templateID"),
            "alias": body.get("alias"),
            "envdVersion": body.get("envdVersion"),
        },
        "raw": result.body,
    }


def _summarize_direct_status(result: HttpResult) -> dict[str, Any]:
    body = result.body if isinstance(result.body, dict) else {}
    return {
        "status_code": result.status_code,
        "sandbox": {
            "sandboxID": body.get("sandboxID"),
            "templateID": body.get("templateID"),
            "alias": body.get("alias"),
            "state": body.get("state"),
            "envdVersion": body.get("envdVersion"),
            "cpuCount": body.get("cpuCount"),
            "memoryMB": body.get("memoryMB"),
        },
        "raw": result.body,
    }


async def main() -> None:
    started_at = datetime.now(tz=UTC)
    stamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    short = uuid.uuid4().hex[:8]
    artifact_path = REPO_ROOT / f"artifacts/runtime-review-pass-{stamp}-e2b-depth11.json"
    publication_path = REPO_ROOT / "artifacts/runtime-review-publication-2026-04-03-e2b-depth11.json"
    org_id = f"org_runtime_review_e2b_{stamp.lower()}_{short}"
    review_template = {
        **REVIEW_TEMPLATE,
        "metadata": {
            "source": "rhumb-runtime-review",
            "service": SERVICE_SLUG,
            "stamp": stamp,
        },
    }

    payload: dict[str, Any] = {
        "provider": SERVICE_SLUG,
        "create_capability_id": CREATE_CAPABILITY_ID,
        "status_capability_id": STATUS_CAPABILITY_ID,
        "review_kind": "current_depth11",
        "organization_id": org_id,
        "artifact_path": str(artifact_path.relative_to(REPO_ROOT)),
        "started_at": started_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "review_template": review_template,
    }
    _json_dump(artifact_path, payload)

    e2b_api_key = os.environ["RHUMB_CREDENTIAL_E2B_API_KEY"]

    supabase = await get_supabase_client()
    store = AgentIdentityStore(supabase)

    bootstrap = await ensure_org_billing_bootstrap(
        org_id,
        name=f"runtime-review-e2b-{stamp}",
        starter_credits_cents=5000,
    )
    payload["wallet_bootstrap"] = bootstrap

    agent_id, api_key = await store.register_agent(
        name=f"runtime-review-e2b-{stamp}",
        organization_id=org_id,
        rate_limit_qpm=100,
        description="Temp review agent for E2B depth-11 runtime pass",
        tags=["runtime_review", "phase3", "current_pass", SERVICE_SLUG, "depth11"],
    )
    payload["review_agent"] = {"agent_id": agent_id, "organization_id": org_id}

    access_id = await store.grant_service_access(agent_id, SERVICE_SLUG)
    payload["grant_access"] = {"status": "success", "access_id": access_id}
    payload["post_grant_delay_seconds"] = POST_GRANT_PROPAGATION_DELAY_SECONDS
    _json_dump(artifact_path, payload)

    await asyncio.sleep(POST_GRANT_PROPAGATION_DELAY_SECONDS)

    api_headers = {"X-Rhumb-Key": api_key}
    rhumb_sandbox_id: str | None = None
    direct_sandbox_id: str | None = None

    try:
        counts_before = await _fetch_public_review_stats(SERVICE_SLUG)

        estimate_attempts = 0
        estimate = HttpResult(status_code=0, body=None)
        while estimate_attempts < ESTIMATE_AUTH_RETRY_ATTEMPTS:
            estimate_attempts += 1
            estimate = await _request_json(
                "GET",
                f"{BASE_URL}/capabilities/{CREATE_CAPABILITY_ID}/execute/estimate",
                headers=api_headers,
                params={"provider": SERVICE_SLUG, "credential_mode": "rhumb_managed"},
                timeout=60.0,
            )
            if not (
                estimate.status_code == 401
                and _looks_like_invalid_key(estimate.body)
                and estimate_attempts < ESTIMATE_AUTH_RETRY_ATTEMPTS
            ):
                break
            await asyncio.sleep(ESTIMATE_AUTH_RETRY_DELAY_SECONDS)

        rhumb_create = await _request_json(
            "POST",
            f"{BASE_URL}/capabilities/{CREATE_CAPABILITY_ID}/execute",
            headers=api_headers,
            params={"provider": SERVICE_SLUG, "credential_mode": "rhumb_managed"},
            json_body=review_template,
            timeout=120.0,
        )
        rhumb_create_summary = _summarize_create(rhumb_create)
        rhumb_sandbox_id = (rhumb_create_summary.get("sandbox") or {}).get("sandboxID")

        rhumb_status = await _request_json(
            "POST",
            f"{BASE_URL}/capabilities/{STATUS_CAPABILITY_ID}/execute",
            headers=api_headers,
            params={"provider": SERVICE_SLUG, "credential_mode": "rhumb_managed"},
            json_body={"sandboxId": rhumb_sandbox_id},
            timeout=120.0,
        )
        rhumb_status_summary = _summarize_status(rhumb_status)

        direct_create = await _request_json(
            "POST",
            f"{E2B_BASE_URL}/sandboxes",
            headers={"X-API-Key": e2b_api_key},
            json_body=review_template,
            timeout=120.0,
        )
        direct_create_summary = _summarize_direct_create(direct_create)
        direct_sandbox_id = (direct_create_summary.get("sandbox") or {}).get("sandboxID")

        direct_status = await _request_json(
            "GET",
            f"{E2B_BASE_URL}/sandboxes/{direct_sandbox_id}",
            headers={"X-API-Key": e2b_api_key},
            timeout=120.0,
        )
        direct_status_summary = _summarize_direct_status(direct_status)

        comparison = {
            "create_template_match": (
                rhumb_create_summary["sandbox"]["alias"] == direct_create_summary["sandbox"]["alias"]
                and rhumb_create_summary["sandbox"]["templateID"] == direct_create_summary["sandbox"]["templateID"]
            ),
            "status_template_match": (
                rhumb_status_summary["sandbox"]["alias"] == direct_status_summary["sandbox"]["alias"]
                and rhumb_status_summary["sandbox"]["templateID"] == direct_status_summary["sandbox"]["templateID"]
            ),
            "status_state_match": rhumb_status_summary["sandbox"]["state"] == direct_status_summary["sandbox"]["state"],
            "envd_version_match": rhumb_status_summary["sandbox"]["envdVersion"] == direct_status_summary["sandbox"]["envdVersion"],
            "compute_shape_match": (
                rhumb_status_summary["sandbox"]["cpuCount"] == direct_status_summary["sandbox"]["cpuCount"]
                and rhumb_status_summary["sandbox"]["memoryMB"] == direct_status_summary["sandbox"]["memoryMB"]
            ),
        }

        observed_at = _iso_now()
        fresh_until = (
            datetime.fromisoformat(observed_at.replace("Z", "+00:00")) + timedelta(days=30)
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        verdict = "pass" if (
            estimate.status_code == 200
            and rhumb_create.status_code == 200
            and rhumb_status.status_code == 200
            and rhumb_create_summary["upstream_status"] == 201
            and rhumb_status_summary["upstream_status"] == 200
            and direct_create.status_code == 201
            and direct_status.status_code == 200
            and rhumb_create_summary["provider_used"] == SERVICE_SLUG
            and rhumb_status_summary["provider_used"] == SERVICE_SLUG
            and all(comparison.values())
        ) else "fail"

        payload.update(
            {
                "reviewed_at": observed_at,
                "fresh_until": fresh_until,
                "counts_before": counts_before,
                "estimate": {
                    "status_code": estimate.status_code,
                    "body": estimate.body,
                    "attempts": estimate_attempts,
                },
                "rhumb_create": rhumb_create_summary,
                "rhumb_status": rhumb_status_summary,
                "direct_create": direct_create_summary,
                "direct_status": direct_status_summary,
                "comparison": comparison,
                "verdict": verdict,
            }
        )
        _json_dump(artifact_path, payload)

        if verdict != "pass":
            raise RuntimeError("E2B depth-11 runtime pass failed; inspect artifact for parity details")

        publication = _run_publish(
            [
                "--service", SERVICE_SLUG,
                "--headline", "E2B: depth-11 runtime review confirms sandbox parity through Rhumb Resolve",
                "--summary", "Fresh depth-11 runtime review passed for E2B agent.spawn plus agent.get_status through Rhumb Resolve. Managed and direct executions matched on template alias, internal template id, running state, envd version, and sandbox compute shape.",
                "--evidence-title", "E2B depth-11 runtime review parity check via Rhumb Resolve",
                "--evidence-summary", "Fresh depth-11 runtime review passed for E2B agent.spawn plus agent.get_status through Rhumb Resolve. Managed and direct executions matched on template alias, internal template id, running state, envd version, and sandbox compute shape.",
                "--source-ref", f"runtime-review:e2b:{stamp}",
                "--source-batch-id", f"runtime-review:e2b:{stamp}",
                "--reviewed-at", observed_at,
                "--fresh-until", fresh_until,
                "--reviewer-agent-id", agent_id,
                "--agent-id", agent_id,
                "--run-id", rhumb_create_summary.get("execution_id") or "",
                "--tag", "runtime_review",
                "--tag", SERVICE_SLUG,
                "--tag", CREATE_CAPABILITY_ID,
                "--tag", STATUS_CAPABILITY_ID,
                "--tag", "current_pass",
                "--tag", "phase3",
                "--tag", "depth11",
                "--raw-payload-file", str(artifact_path.relative_to(REPO_ROOT)),
            ],
            publication_path,
        )
        payload["publication"] = publication
        payload["counts_after"] = await _fetch_public_review_stats(SERVICE_SLUG)
        _json_dump(artifact_path, payload)
    finally:
        payload.setdefault("cleanup", {})
        payload["cleanup"]["rhumb_sandbox_delete_status"] = await _delete_direct_sandbox(e2b_api_key, rhumb_sandbox_id)
        payload["cleanup"]["direct_sandbox_delete_status"] = await _delete_direct_sandbox(e2b_api_key, direct_sandbox_id)
        disabled = await store.disable_agent(agent_id)
        payload["disable_agent"] = {
            "status_code": 200 if disabled else 404,
            "body": {"status": "success" if disabled else "not_found", "agent_id": agent_id},
        }
        _json_dump(artifact_path, payload)


if __name__ == "__main__":
    asyncio.run(main())
