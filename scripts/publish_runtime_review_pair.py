#!/usr/bin/env python3
"""Publish one runtime-backed evidence+review pair to the public trust surface.

Why it exists:
- Runtime reruns can finish successfully while the public trust surface stays stale.
- Keel / Pedro loops need a repeatable, idempotent way to publish the finished pass.
- The publish path should work from the linked Railway production context without
  copy-pasting ad hoc curl blobs.

Usage example:
    railway run -s rhumb-api python3 scripts/publish_runtime_review_pair.py \
      --service replicate \
      --headline "Replicate: current-pass rerun confirms ai.generate_text parity through Rhumb Resolve" \
      --summary "Fresh current-pass runtime rerun passed for Replicate ai.generate_text through Rhumb Resolve. Managed and direct executions both created successful predictions and matched on final succeeded state and exact text output." \
      --evidence-title "Replicate current-pass runtime rerun parity check via Rhumb Resolve" \
      --evidence-summary "Fresh current-pass runtime rerun passed for Replicate ai.generate_text through Rhumb Resolve. Managed and direct executions both created successful predictions and matched on final succeeded state and exact text output." \
      --source-ref runtime-review:replicate:20260329T231345Z \
      --source-batch-id runtime-review:replicate:20260329T231345Z \
      --reviewed-at 2026-03-29T23:13:55.412121752Z \
      --fresh-until 2026-04-28T23:13:55.412121752Z \
      --reviewer-agent-id 06b352f9-05f7-4064-9432-c9c8de858276 \
      --agent-id 06b352f9-05f7-4064-9432-c9c8de858276 \
      --run-id exec_c512c7fc9e4c4d35a5f2a675eb71e97c \
      --tag runtime_review --tag replicate --tag ai.generate_text --tag current_pass --tag phase3 \
      --raw-payload-file artifacts/runtime-review-pass-20260329T231345Z-pdl-replicate-current.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

DEFAULT_CREATED_BY = "pedro_runtime_review_loop"
DEFAULT_CONFIDENCE = 0.99
DEFAULT_REVIEWER_LABEL = "Pedro / Keel runtime review loop"


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _base_url() -> str:
    return _require_env("SUPABASE_URL").rstrip("/") + "/rest/v1"


def _headers(*, return_representation: bool = False) -> dict[str, str]:
    key = _require_env("SUPABASE_SERVICE_ROLE_KEY")
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    headers["Prefer"] = "return=representation" if return_representation else "return=minimal"
    return headers


def _request(method: str, path: str, *, payload: Any | None = None, return_representation: bool = False) -> Any:
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    req = Request(
        _base_url() + path,
        data=body,
        headers=_headers(return_representation=return_representation),
        method=method,
    )
    try:
        with urlopen(req, timeout=60) as response:
            raw = response.read().decode("utf-8")
            if not raw:
                return None
            return json.loads(raw)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed with HTTP {exc.code}: {detail}") from exc


def _fetch_one(path: str) -> dict[str, Any] | None:
    data = _request("GET", path)
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data
    return None


def _insert_returning(table: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = _request("POST", f"/{table}", payload=payload, return_representation=True)
    if isinstance(data, list) and data:
        return data[0]
    if isinstance(data, dict):
        return data
    raise RuntimeError(f"Insert into {table} returned no row")


def _load_optional_json(path: str | None) -> Any:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _existing_evidence(service: str, source_ref: str) -> dict[str, Any] | None:
    return _fetch_one(
        "/evidence_records"
        f"?service_slug=eq.{quote(service, safe='-_')}"
        f"&source_ref=eq.{quote(source_ref, safe='-_:')}"
        "&limit=1"
        "&select=id,service_slug,source_ref"
    )


def _existing_review(service: str, source_batch_id: str) -> dict[str, Any] | None:
    return _fetch_one(
        "/service_reviews"
        f"?service_slug=eq.{quote(service, safe='-_')}"
        f"&source_batch_id=eq.{quote(source_batch_id, safe='-_:')}"
        "&limit=1"
        "&select=id,service_slug,source_batch_id,evidence_refs_json"
    )


def _existing_link(review_id: str, evidence_id: str) -> dict[str, Any] | None:
    return _fetch_one(
        "/review_evidence_links"
        f"?review_id=eq.{quote(review_id, safe='-_')}"
        f"&evidence_record_id=eq.{quote(evidence_id, safe='-_')}"
        "&limit=1"
        "&select=review_id,evidence_record_id,role"
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", required=True)
    parser.add_argument("--headline", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--evidence-title", required=True)
    parser.add_argument("--evidence-summary", required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--source-batch-id", required=True)
    parser.add_argument("--reviewed-at", required=True)
    parser.add_argument("--fresh-until", required=True)
    parser.add_argument("--review-type", default="manual")
    parser.add_argument("--review-status", default="published")
    parser.add_argument("--reviewer-label", default=DEFAULT_REVIEWER_LABEL)
    parser.add_argument("--reviewer-agent-id")
    parser.add_argument("--agent-id")
    parser.add_argument("--run-id")
    parser.add_argument("--confidence", type=float, default=DEFAULT_CONFIDENCE)
    parser.add_argument("--source-type", default="runtime_verified")
    parser.add_argument("--evidence-kind", default="runtime_review")
    parser.add_argument("--created-by", default=DEFAULT_CREATED_BY)
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--raw-payload-file")
    parser.add_argument("--normalized-payload-file")
    parser.add_argument("--link-role", default="primary")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    raw_payload = _load_optional_json(args.raw_payload_file)
    normalized_payload = _load_optional_json(args.normalized_payload_file)

    evidence = _existing_evidence(args.service, args.source_ref)
    evidence_state = "reused"
    if evidence is None:
        evidence = _insert_returning(
            "evidence_records",
            {
                "service_slug": args.service,
                "source_type": args.source_type,
                "source_ref": args.source_ref,
                "evidence_kind": args.evidence_kind,
                "title": args.evidence_title,
                "summary": args.evidence_summary,
                "raw_payload_json": raw_payload,
                "normalized_payload_json": normalized_payload,
                "observed_at": args.reviewed_at,
                "fresh_until": args.fresh_until,
                "confidence": args.confidence,
                "agent_id": args.agent_id,
                "run_id": args.run_id,
                "created_by": args.created_by,
            },
        )
        evidence_state = "inserted"

    evidence_id = str(evidence["id"])

    review = _existing_review(args.service, args.source_batch_id)
    review_state = "reused"
    if review is None:
        review = _insert_returning(
            "service_reviews",
            {
                "service_slug": args.service,
                "review_type": args.review_type,
                "review_status": args.review_status,
                "headline": args.headline,
                "summary": args.summary,
                "confidence": args.confidence,
                "reviewed_at": args.reviewed_at,
                "reviewer_agent_id": args.reviewer_agent_id,
                "reviewer_label": args.reviewer_label,
                "source_batch_id": args.source_batch_id,
                "fresh_until": args.fresh_until,
                "evidence_count": 1,
                "evidence_refs_json": [evidence_id],
                "tags_json": args.tag,
                "highest_trust_source": args.source_type,
            },
        )
        review_state = "inserted"

    review_id = str(review["id"])

    link = _existing_link(review_id, evidence_id)
    link_state = "reused"
    if link is None:
        link = _insert_returning(
            "review_evidence_links",
            {
                "review_id": review_id,
                "evidence_record_id": evidence_id,
                "role": args.link_role,
            },
        )
        link_state = "inserted"

    result = {
        "service": args.service,
        "evidence": {"state": evidence_state, "id": evidence_id, "source_ref": args.source_ref},
        "review": {"state": review_state, "id": review_id, "source_batch_id": args.source_batch_id},
        "link": {"state": link_state, "review_id": review_id, "evidence_record_id": evidence_id, "role": args.link_role},
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
