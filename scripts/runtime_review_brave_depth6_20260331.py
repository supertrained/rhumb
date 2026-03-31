#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
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
BRAVE_BASE_URL = "https://api.search.brave.com/res/v1/web/search"
QUERY = "LLM observability tools"
RESULT_COUNT = 5
PUBLIC_SERVICE_SLUG = "brave-search-api"
CANONICAL_PUBLISH_SLUG = "brave-search"


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


def _web_results(body: Any) -> list[dict[str, Any]]:
    if not isinstance(body, dict):
        return []
    web = body.get("web")
    if not isinstance(web, dict):
        return []
    results = web.get("results")
    return results if isinstance(results, list) else []


def _top_result(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not results:
        return None
    item = results[0]
    if not isinstance(item, dict):
        return None
    return {
        "title": item.get("title"),
        "url": item.get("url"),
        "description": item.get("description"),
    }


async def main() -> None:
    started_at = datetime.now(tz=UTC)
    stamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    artifact_path = REPO_ROOT / f"artifacts/runtime-review-pass-{stamp}-brave-current-depth6.json"
    publication_path = REPO_ROOT / "artifacts/runtime-review-publication-2026-03-31-brave-depth6.json"
    org_id = f"org_runtime_review_brave_{stamp.lower()}"

    payload: dict[str, Any] = {
        "provider": PUBLIC_SERVICE_SLUG,
        "canonical_publish_slug": CANONICAL_PUBLISH_SLUG,
        "query": QUERY,
        "numResults": RESULT_COUNT,
        "review_kind": "current_depth6",
        "organization_id": org_id,
        "artifact_path": str(artifact_path),
    }
    _json_dump(artifact_path, payload)

    supabase = await get_supabase_client()
    store = AgentIdentityStore(supabase)

    bootstrap = await ensure_org_billing_bootstrap(
        org_id,
        name=f"runtime-review-brave-{stamp}",
        starter_credits_cents=5000,
    )
    payload["bootstrap"] = bootstrap

    agent_id, api_key = await store.register_agent(
        name=f"runtime-review-brave-{stamp}",
        organization_id=org_id,
        rate_limit_qpm=100,
        description="Temp review agent for Brave Search depth-6 runtime pass",
        tags=["runtime_review", "phase3", "current_pass", "brave-search"],
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
    _json_dump(artifact_path, payload)

    api_headers = {"X-Rhumb-Key": api_key}
    brave_token = os.environ["RHUMB_CREDENTIAL_BRAVE_SEARCH_API_KEY"]

    try:
        counts_before = await _fetch_public_review_stats(PUBLIC_SERVICE_SLUG)
        estimate = await _request_json(
            "GET",
            f"{BASE_URL}/capabilities/search.query/execute/estimate",
            headers=api_headers,
            params={"provider": PUBLIC_SERVICE_SLUG, "credential_mode": "rhumb_managed"},
            timeout=60.0,
        )
        execute = await _request_json(
            "POST",
            f"{BASE_URL}/capabilities/search.query/execute",
            headers=api_headers,
            params={"provider": PUBLIC_SERVICE_SLUG, "credential_mode": "rhumb_managed"},
            json_body={"query": QUERY, "numResults": RESULT_COUNT},
            timeout=120.0,
        )
        direct = await _request_json(
            "GET",
            BRAVE_BASE_URL,
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": brave_token,
            },
            params={"q": QUERY, "count": RESULT_COUNT},
            timeout=60.0,
        )

        rhumb_payload = ((execute.body or {}).get("data") or {}) if isinstance(execute.body, dict) else {}
        rhumb_upstream = (rhumb_payload.get("upstream_response") or {}) if isinstance(rhumb_payload, dict) else {}
        rhumb_results = _web_results(rhumb_upstream)
        direct_results = _web_results(direct.body)
        rhumb_top = _top_result(rhumb_results)
        direct_top = _top_result(direct_results)
        observed_at = _iso_now()
        reviewed_at_dt = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        fresh_until = (reviewed_at_dt + timedelta(days=30)).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        comparison = {
            "rhumb_count": len(rhumb_results),
            "direct_count": len(direct_results),
            "rhumb_top": rhumb_top,
            "direct_top": direct_top,
            "parity": {
                "result_count_match": len(rhumb_results) == len(direct_results) == RESULT_COUNT,
                "top_title_match": (rhumb_top or {}).get("title") == (direct_top or {}).get("title"),
                "top_url_match": (rhumb_top or {}).get("url") == (direct_top or {}).get("url"),
            },
        }

        verdict = "pass" if (
            estimate.status_code == 200
            and execute.status_code == 200
            and direct.status_code == 200
            and rhumb_payload.get("provider_used") == CANONICAL_PUBLISH_SLUG
            and rhumb_payload.get("upstream_status") == 200
            and comparison["parity"]["result_count_match"]
            and comparison["parity"]["top_title_match"]
            and comparison["parity"]["top_url_match"]
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
            raise RuntimeError("Brave Search depth-6 runtime pass failed; inspect artifact for parity details")

        execution_id = rhumb_payload.get("execution_id") or ""
        publication = _run_publish(
            [
                "--service", CANONICAL_PUBLISH_SLUG,
                "--headline", "Brave Search: depth-6 rerun confirms search.query parity through Rhumb Resolve again",
                "--summary", "Fresh depth-6 runtime rerun passed for Brave Search search.query through Rhumb Resolve. Managed and direct executions matched on result count, top title, and top URL for the same live query, lifting the public runtime-backed review stack from 5 to 6.",
                "--evidence-title", "Brave Search depth-6 runtime rerun parity check via Rhumb Resolve",
                "--evidence-summary", "Fresh depth-6 runtime rerun passed for Brave Search search.query through Rhumb Resolve. Managed and direct executions matched on result count, top title, and top URL for the same live query.",
                "--source-ref", f"runtime-review:brave-search:{stamp}",
                "--source-batch-id", f"runtime-review:brave-search:{stamp}",
                "--reviewed-at", observed_at,
                "--fresh-until", fresh_until,
                "--reviewer-agent-id", agent_id,
                "--agent-id", agent_id,
                "--run-id", execution_id,
                "--tag", "runtime_review",
                "--tag", "brave-search",
                "--tag", "search.query",
                "--tag", "current_pass",
                "--tag", "phase3",
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
