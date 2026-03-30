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
TEXT_FILENAME = "runtime-review-unstructured-depth4.txt"
TEXT_CONTENT = (
    "Rhumb Runtime Review\n\n"
    "Unstructured should parse this short sample into a Title and a NarrativeText block."
)
PDL_PROFILE = "https://www.linkedin.com/in/satyanadella/"


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
    data: dict[str, Any] | list[tuple[str, str]] | None = None,
    files: Any | None = None,
    timeout: float = 60.0,
) -> HttpResult:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(
            method,
            url,
            headers=headers,
            params=params,
            json=json_body,
            data=data,
            files=files,
        )
    try:
        body: Any = response.json()
    except Exception:
        body = response.text
    return HttpResult(status_code=response.status_code, body=body)


def _iso_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _extract_review_stats(body: Any) -> dict[str, int | None]:
    reviews = []
    if isinstance(body, dict):
        data = body.get("data")
        if isinstance(data, dict):
            reviews = data.get("reviews") or []
        elif isinstance(data, list):
            reviews = data
    runtime_backed = 0
    published = 0
    if isinstance(reviews, list):
        for review in reviews:
            if not isinstance(review, dict):
                continue
            if review.get("status") == "published":
                published += 1
            source_type = review.get("source_type") or review.get("sourceType")
            if source_type == "runtime_verified":
                runtime_backed += 1
    return {
        "published_reviews": published or (len(reviews) if isinstance(reviews, list) else None),
        "runtime_backed_reviews": runtime_backed,
    }


async def _fetch_public_review_stats(service_slug: str) -> dict[str, int | None]:
    result = await _request_json("GET", f"{BASE_URL}/services/{service_slug}/reviews")
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
    skip_pdl = os.environ.get("SKIP_PDL", "").strip().lower() in {"1", "true", "yes", "on"}
    skip_unstructured = os.environ.get("SKIP_UNSTRUCTURED", "").strip().lower() in {"1", "true", "yes", "on"}

    started_at = datetime.now(tz=UTC)
    stamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    short = uuid.uuid4().hex[:8]
    run_id = f"runtime-review-{stamp}-{short}"
    artifact_path = REPO_ROOT / f"artifacts/runtime-review-pass-{stamp}-pdl-unstructured-depth4.json"
    pdl_pub_path = REPO_ROOT / "artifacts/runtime-review-publication-2026-03-30-pdl-fix-verify.json"
    unstructured_pub_path = REPO_ROOT / "artifacts/runtime-review-publication-2026-03-30-unstructured-depth4.json"
    org_id = f"org_runtime_review_{stamp.lower()}_{short}"

    payload: dict[str, Any] = {
        "run_started_at": started_at.isoformat(),
        "run_id": run_id,
        "organization_id": org_id,
    }

    supabase = await get_supabase_client()
    store = AgentIdentityStore(supabase)

    bootstrap = await ensure_org_billing_bootstrap(
        org_id,
        name=f"runtime-review-{stamp}",
        starter_credits_cents=5000,
    )
    payload["wallet_bootstrap"] = bootstrap

    agent_id, api_key = await store.register_agent(
        name=f"runtime-review-{stamp}",
        organization_id=org_id,
        rate_limit_qpm=100,
        description="Temp review agent for PDL fix-verify + Unstructured depth4 runtime pass",
        tags=["runtime_review", "phase3", "current_pass"],
    )
    payload["review_agent"] = {
        "agent_id": agent_id,
        "organization_id": org_id,
    }

    grant_results: list[dict[str, Any]] = []
    for service in ["people-data-labs", "unstructured"]:
        access_id = await store.grant_service_access(agent_id, service)
        grant_results.append(
            {
                "service": service,
                "status_code": 200,
                "body": {"status": "success", "access_id": access_id},
            }
        )
    payload["grant_results"] = grant_results
    _json_dump(artifact_path, payload)

    api_headers = {"X-Rhumb-Key": api_key}

    try:
        # Mission 0 — PDL fix verify using canonical slug only.
        if skip_pdl:
            payload["mission0_pdl"] = {
                "status": "skipped",
                "reason": "SKIP_PDL=1",
            }
        else:
            pdl_before = await _fetch_public_review_stats("people-data-labs")
            pdl_estimate = await _request_json(
                "GET",
                f"{BASE_URL}/capabilities/data.enrich_person/execute/estimate",
                headers=api_headers,
                params={"provider": "people-data-labs", "credential_mode": "rhumb_managed"},
            )
            pdl_execute = await _request_json(
                "POST",
                f"{BASE_URL}/capabilities/data.enrich_person/execute",
                headers=api_headers,
                params={"provider": "people-data-labs", "credential_mode": "rhumb_managed"},
                json_body={"profile": PDL_PROFILE},
            )
            pdl_direct = await _request_json(
                "GET",
                "https://api.peopledatalabs.com/v5/person/enrich",
                headers={"X-Api-Key": os.environ["RHUMB_CREDENTIAL_PDL_API_KEY"]},
                params={"profile": PDL_PROFILE},
            )

            pdl_rhumb_data = (((pdl_execute.body or {}).get("data") or {}).get("upstream_response") or {}).get("data") if isinstance(pdl_execute.body, dict) else None
            pdl_direct_data = ((pdl_direct.body or {}).get("data")) if isinstance(pdl_direct.body, dict) else None
            sampled_keys = ["full_name", "job_title", "job_company_name", "linkedin_url"]
            pdl_checks = {
                key: (pdl_rhumb_data or {}).get(key) == (pdl_direct_data or {}).get(key)
                for key in sampled_keys
            }
            control_quota_blocked = (
                pdl_direct.status_code == 402
                and isinstance(pdl_direct.body, dict)
                and "account maximum" in json.dumps(pdl_direct.body).lower()
            )
            pdl_observed_at = _iso_now()

            verdict = "fail"
            if pdl_execute.status_code == 200 and pdl_direct.status_code == 200 and all(pdl_checks.values()):
                verdict = "pass"
            elif pdl_execute.status_code == 200 and control_quota_blocked:
                verdict = "pass_control_blocked"

            payload["mission0_pdl"] = {
                "service_slug": "people-data-labs",
                "provider": "people-data-labs",
                "capability_id": "data.enrich_person",
                "run_id": f"{run_id}-pdl",
                "input": {"profile": PDL_PROFILE},
                "counts_before": pdl_before,
                "estimate": asdict(pdl_estimate),
                "rhumb_execute": asdict(pdl_execute),
                "direct_control": asdict(pdl_direct),
                "control_quota_blocked": control_quota_blocked,
                "parity": {
                    "sampled_keys": sampled_keys,
                    "rhumb_sample": {key: (pdl_rhumb_data or {}).get(key) for key in sampled_keys},
                    "direct_sample": {key: (pdl_direct_data or {}).get(key) for key in sampled_keys},
                    "checks": pdl_checks,
                    "all_matched": all(pdl_checks.values()),
                    "provider_used": (((pdl_execute.body or {}).get("data") or {}).get("provider_used")) if isinstance(pdl_execute.body, dict) else None,
                    "execution_id": (((pdl_execute.body or {}).get("data") or {}).get("execution_id")) if isinstance(pdl_execute.body, dict) else None,
                    "upstream_status": (((pdl_execute.body or {}).get("data") or {}).get("upstream_status")) if isinstance(pdl_execute.body, dict) else None,
                },
                "observed_at": pdl_observed_at,
                "verdict": verdict,
            }
            _json_dump(artifact_path, payload)

            if verdict == "fail":
                raise RuntimeError("PDL fix-verify rerun failed; inspect artifact for execute vs direct-control details")

            if verdict == "pass":
                pdl_reviewed_at = pdl_observed_at
                pdl_fresh_until = (
                    datetime.fromisoformat(pdl_reviewed_at.replace("Z", "+00:00")) + timedelta(days=30)
                ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                pdl_publish = _run_publish(
                    [
                        "--service", "people-data-labs",
                        "--headline", "People Data Labs: fix-verify rerun confirms data.enrich_person parity through Rhumb Resolve",
                        "--summary", "Fresh post-fix runtime rerun passed for canonical People Data Labs data.enrich_person through Rhumb Resolve. Managed and direct executions matched on full_name, job_title, job_company_name, and linkedin_url for the same live LinkedIn input.",
                        "--evidence-title", "People Data Labs fix-verify runtime rerun parity check via Rhumb Resolve",
                        "--evidence-summary", "Fresh post-fix runtime rerun passed for canonical People Data Labs data.enrich_person through Rhumb Resolve. Managed and direct executions matched on full_name, job_title, job_company_name, and linkedin_url for the same live LinkedIn input.",
                        "--source-ref", f"runtime-review:people-data-labs:{stamp}",
                        "--source-batch-id", f"runtime-review:people-data-labs:{stamp}",
                        "--reviewed-at", pdl_reviewed_at,
                        "--fresh-until", pdl_fresh_until,
                        "--reviewer-agent-id", agent_id,
                        "--agent-id", agent_id,
                        "--run-id", payload["mission0_pdl"]["parity"]["execution_id"] or "",
                        "--tag", "runtime_review",
                        "--tag", "people-data-labs",
                        "--tag", "data.enrich_person",
                        "--tag", "current_pass",
                        "--tag", "phase3",
                        "--tag", "fix_verify",
                        "--raw-payload-file", str(artifact_path.relative_to(REPO_ROOT)),
                    ],
                    pdl_pub_path,
                )
                payload["mission0_pdl"]["evidence_id"] = ((pdl_publish.get("evidence") or {}).get("id"))
                payload["mission0_pdl"]["review_id"] = ((pdl_publish.get("review") or {}).get("id"))
            else:
                payload["mission0_pdl"]["publication_skipped_reason"] = (
                    "direct control immediately hit provider account max after the managed pass; logged for internal verification only"
                )
            payload["mission0_pdl"]["counts_after"] = await _fetch_public_review_stats("people-data-labs")
            _json_dump(artifact_path, payload)

        # Mission 1 — next weakest callable provider, fresh ordering => unstructured.
        if skip_unstructured:
            payload["mission1_unstructured"] = {
                "status": "skipped",
                "reason": "SKIP_UNSTRUCTURED=1",
            }
        else:
            un_before = await _fetch_public_review_stats("unstructured")
            un_estimate = await _request_json(
                "GET",
                f"{BASE_URL}/capabilities/document.parse/execute/estimate",
                headers=api_headers,
                params={"provider": "unstructured", "credential_mode": "rhumb_managed"},
            )
            un_execute = await _request_json(
                "POST",
                f"{BASE_URL}/capabilities/document.parse/execute",
                headers=api_headers,
                params={"provider": "unstructured", "credential_mode": "rhumb_managed"},
                json_body={
                    "strategy": "fast",
                    "files": [
                        {
                            "filename": TEXT_FILENAME,
                            "text": TEXT_CONTENT,
                            "content_type": "text/plain",
                        }
                    ],
                },
                timeout=120.0,
            )
            un_direct = await _request_json(
                "POST",
                "https://api.unstructuredapp.io/general/v0/general",
                headers={"unstructured-api-key": os.environ["RHUMB_CREDENTIAL_UNSTRUCTURED_API_KEY"]},
                data={"strategy": "fast"},
                files={"files": (TEXT_FILENAME, TEXT_CONTENT.encode("utf-8"), "text/plain")},
                timeout=120.0,
            )

            rhumb_elements = (((un_execute.body or {}).get("data") or {}).get("upstream_response")) if isinstance(un_execute.body, dict) else None
            direct_elements = un_direct.body if isinstance(un_direct.body, list) else []
            rhumb_types = [row.get("type") for row in rhumb_elements or [] if isinstance(row, dict)]
            direct_types = [row.get("type") for row in direct_elements or [] if isinstance(row, dict)]
            un_observed_at = _iso_now()

            payload["mission1_unstructured"] = {
                "service_slug": "unstructured",
                "provider": "unstructured",
                "capability_id": "document.parse",
                "run_id": f"{run_id}-unstructured",
                "counts_before": un_before,
                "input_shape": {
                    "filename": TEXT_FILENAME,
                    "strategy": "fast",
                },
                "estimate": asdict(un_estimate),
                "rhumb_execute": asdict(un_execute),
                "direct_control": asdict(un_direct),
                "parity": {
                    "rhumb_types": rhumb_types,
                    "direct_types": direct_types,
                    "rhumb_count": len(rhumb_elements or []),
                    "direct_count": len(direct_elements or []),
                    "types_match": rhumb_types == direct_types,
                    "count_match": len(rhumb_elements or []) == len(direct_elements or []),
                    "provider_used": (((un_execute.body or {}).get("data") or {}).get("provider_used")) if isinstance(un_execute.body, dict) else None,
                    "execution_id": (((un_execute.body or {}).get("data") or {}).get("execution_id")) if isinstance(un_execute.body, dict) else None,
                    "upstream_status": (((un_execute.body or {}).get("data") or {}).get("upstream_status")) if isinstance(un_execute.body, dict) else None,
                },
                "observed_at": un_observed_at,
                "verdict": "pass" if un_execute.status_code == 200 and un_direct.status_code == 200 and rhumb_types == direct_types and len(rhumb_elements or []) == len(direct_elements or []) else "fail",
            }
            _json_dump(artifact_path, payload)

            if payload["mission1_unstructured"]["verdict"] != "pass":
                raise RuntimeError("Unstructured depth4 runtime pass failed; inspect artifact for execute vs direct-control details")

            un_reviewed_at = un_observed_at
            un_fresh_until = (
                datetime.fromisoformat(un_reviewed_at.replace("Z", "+00:00")) + timedelta(days=30)
            ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            un_publish = _run_publish(
                [
                    "--service", "unstructured",
                    "--headline", "Unstructured: current-depth rerun confirms document.parse parity through Rhumb Resolve",
                    "--summary", "Fresh current-depth runtime rerun passed for Unstructured document.parse through Rhumb Resolve. Managed and direct executions matched exactly on element types and element count for the same text file input.",
                    "--evidence-title", "Unstructured current-depth runtime rerun parity check via Rhumb Resolve",
                    "--evidence-summary", "Fresh current-depth runtime rerun passed for Unstructured document.parse through Rhumb Resolve. Managed and direct executions matched exactly on element types and element count for the same text file input.",
                    "--source-ref", f"runtime-review:unstructured:{stamp}",
                    "--source-batch-id", f"runtime-review:unstructured:{stamp}",
                    "--reviewed-at", un_reviewed_at,
                    "--fresh-until", un_fresh_until,
                    "--reviewer-agent-id", agent_id,
                    "--agent-id", agent_id,
                    "--run-id", payload["mission1_unstructured"]["parity"]["execution_id"] or "",
                    "--tag", "runtime_review",
                    "--tag", "unstructured",
                    "--tag", "document.parse",
                    "--tag", "current_pass",
                    "--tag", "phase3",
                    "--raw-payload-file", str(artifact_path.relative_to(REPO_ROOT)),
                ],
                unstructured_pub_path,
            )
            payload["mission1_unstructured"]["evidence_id"] = ((un_publish.get("evidence") or {}).get("id"))
            payload["mission1_unstructured"]["review_id"] = ((un_publish.get("review") or {}).get("id"))
            payload["mission1_unstructured"]["counts_after"] = await _fetch_public_review_stats("unstructured")
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
