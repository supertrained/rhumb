#!/usr/bin/env python3
"""GitHub current-depth3 runtime review pass — 2026-03-31."""
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

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages/api"))

from db.client import get_supabase_client  # noqa: E402
from schemas.agent_identity import AgentIdentityStore  # noqa: E402
from services.billing_bootstrap import ensure_org_billing_bootstrap  # noqa: E402

BASE_URL = "https://api.rhumb.dev/v1"
GITHUB_URL = "https://api.github.com/users/supertrained"
SERVICE_SLUG = "github"
CAPABILITY_ID = "social.get_profile"
TARGET_USERNAME = "supertrained"


@dataclass
class HttpResult:
    status_code: int
    body: Any


def _json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _iso_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
        response = await client.request(method, url, headers=headers, params=params, json=json_body)
    try:
        body: Any = response.json()
    except Exception:
        body = response.text
    return HttpResult(status_code=response.status_code, body=body)


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


async def main() -> None:
    started_at = datetime.now(tz=UTC)
    stamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    artifact_path = REPO_ROOT / f"artifacts/runtime-review-pass-{stamp}-github-depth3.json"
    publication_path = REPO_ROOT / "artifacts/runtime-review-publication-2026-03-31-github-depth3.json"
    org_id = f"org_runtime_review_github_{stamp.lower()}"

    payload: dict[str, Any] = {
        "provider": SERVICE_SLUG,
        "capability_id": CAPABILITY_ID,
        "target_username": TARGET_USERNAME,
        "review_kind": "current_depth3",
        "organization_id": org_id,
        "artifact_path": str(artifact_path),
    }
    _json_dump(artifact_path, payload)

    supabase = await get_supabase_client()
    store = AgentIdentityStore(supabase)

    bootstrap = await ensure_org_billing_bootstrap(
        org_id,
        name=f"runtime-review-github-{stamp}",
        starter_credits_cents=5000,
    )
    payload["bootstrap"] = bootstrap

    agent_id, api_key = await store.register_agent(
        name=f"runtime-review-github-{stamp}",
        organization_id=org_id,
        rate_limit_qpm=100,
        description="Temp review agent for GitHub depth-3 runtime pass",
        tags=["runtime_review", "phase3", "current_pass", "github"],
    )
    payload["review_agent"] = {"agent_id": agent_id, "organization_id": org_id}

    access_id = await store.grant_service_access(agent_id, SERVICE_SLUG)
    payload["grant_access"] = {"status": "success", "access_id": access_id}
    _json_dump(artifact_path, payload)

    api_headers = {"X-Rhumb-Key": api_key}
    direct_headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "rhumb-runtime-review/1.0",
    }

    try:
        counts_before = await _fetch_public_review_stats(SERVICE_SLUG)

        estimate = await _request_json(
            "GET",
            f"{BASE_URL}/capabilities/{CAPABILITY_ID}/execute/estimate",
            headers=api_headers,
            params={"provider": SERVICE_SLUG, "credential_mode": "byo"},
            timeout=60.0,
        )

        execute = await _request_json(
            "POST",
            f"{BASE_URL}/capabilities/{CAPABILITY_ID}/execute",
            headers=api_headers,
            json_body={
                "provider": SERVICE_SLUG,
                "credential_mode": "byo",
                "method": "GET",
                "path": f"/users/{TARGET_USERNAME}",
                "interface": "runtime_review",
            },
            timeout=120.0,
        )

        direct = await _request_json(
            "GET",
            GITHUB_URL,
            headers=direct_headers,
            timeout=120.0,
        )

        rhumb_payload = ((execute.body or {}).get("data") or {}) if isinstance(execute.body, dict) else {}
        rhumb_upstream = (rhumb_payload.get("upstream_response") or {}) if isinstance(rhumb_payload, dict) else {}

        observed_at = _iso_now()
        reviewed_at_dt = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        fresh_until = (reviewed_at_dt + timedelta(days=30)).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        comparison = {
            "rhumb_provider_used": rhumb_payload.get("provider_used"),
            "rhumb_upstream_status": rhumb_payload.get("upstream_status"),
            "rhumb_login": rhumb_upstream.get("login") if isinstance(rhumb_upstream, dict) else None,
            "direct_login": direct.body.get("login") if isinstance(direct.body, dict) else None,
            "rhumb_public_repos": rhumb_upstream.get("public_repos") if isinstance(rhumb_upstream, dict) else None,
            "direct_public_repos": direct.body.get("public_repos") if isinstance(direct.body, dict) else None,
            "rhumb_created_at": rhumb_upstream.get("created_at") if isinstance(rhumb_upstream, dict) else None,
            "direct_created_at": direct.body.get("created_at") if isinstance(direct.body, dict) else None,
            "rhumb_updated_at": rhumb_upstream.get("updated_at") if isinstance(rhumb_upstream, dict) else None,
            "direct_updated_at": direct.body.get("updated_at") if isinstance(direct.body, dict) else None,
            "login_match": (rhumb_upstream.get("login") if isinstance(rhumb_upstream, dict) else None) == (direct.body.get("login") if isinstance(direct.body, dict) else None),
            "public_repos_match": (rhumb_upstream.get("public_repos") if isinstance(rhumb_upstream, dict) else None) == (direct.body.get("public_repos") if isinstance(direct.body, dict) else None),
            "created_at_match": (rhumb_upstream.get("created_at") if isinstance(rhumb_upstream, dict) else None) == (direct.body.get("created_at") if isinstance(direct.body, dict) else None),
            "updated_at_match": (rhumb_upstream.get("updated_at") if isinstance(rhumb_upstream, dict) else None) == (direct.body.get("updated_at") if isinstance(direct.body, dict) else None),
        }

        verdict = "pass" if (
            estimate.status_code == 200
            and execute.status_code == 200
            and direct.status_code == 200
            and rhumb_payload.get("provider_used") == SERVICE_SLUG
            and rhumb_payload.get("upstream_status") == 200
            and comparison["login_match"]
            and comparison["public_repos_match"]
            and comparison["created_at_match"]
            and comparison["updated_at_match"]
        ) else "fail"

        payload.update({
            "observed_at": observed_at,
            "fresh_until": fresh_until,
            "counts_before": counts_before,
            "estimate": {"status": estimate.status_code, "data": estimate.body},
            "rhumb": {"status": execute.status_code, "data": execute.body},
            "direct": {"status": direct.status_code, "data": direct.body},
            "comparison": comparison,
            "verdict": verdict,
        })
        _json_dump(artifact_path, payload)

        if verdict != "pass":
            raise RuntimeError("GitHub depth-3 runtime pass failed; inspect artifact for parity details")

        execution_id = rhumb_payload.get("execution_id") or ""
        publication = _run_publish(
            [
                "--service", SERVICE_SLUG,
                "--headline", "GitHub: current-depth rerun confirms social.get_profile parity through Rhumb Resolve at depth 3",
                "--summary", "Fresh current-depth runtime rerun passed for GitHub social.get_profile through Rhumb Resolve. Rhumb and direct GitHub control matched on login identity, public repo count, and account timestamps for the same public profile, lifting GitHub from claim-safe depth 2 to 3 in the callable rotation.",
                "--evidence-title", "GitHub current-depth runtime rerun parity check via Rhumb Resolve",
                "--evidence-summary", "Fresh current-depth runtime rerun passed for GitHub social.get_profile through Rhumb Resolve. Rhumb and direct GitHub control matched on login identity, public repo count, and account timestamps for the same public profile.",
                "--source-ref", f"runtime-review:github:{stamp}",
                "--source-batch-id", f"runtime-review:github:{stamp}",
                "--reviewed-at", observed_at,
                "--fresh-until", fresh_until,
                "--reviewer-agent-id", agent_id,
                "--agent-id", agent_id,
                "--run-id", execution_id,
                "--tag", "runtime_review",
                "--tag", "github",
                "--tag", CAPABILITY_ID,
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
