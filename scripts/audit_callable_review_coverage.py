#!/usr/bin/env python3
"""Audit public runtime-review coverage across Rhumb callable providers.

This script queries the public callable inventory and each service's public review
surface, then ranks providers by runtime-backed review depth.

Why it exists:
- Keel runtime-review loops need a deterministic "next weakest provider" view.
- Some provider reruns are temporarily blocked by direct-credential access.
- Public trust coverage should be auditable without private DB access.

Examples:
    python scripts/audit_callable_review_coverage.py
    python scripts/audit_callable_review_coverage.py --json
    python scripts/audit_callable_review_coverage.py --json-out artifacts/callable-review-coverage.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

RUNTIME_TRUST_LABEL = "🟢 Runtime-verified"
DEFAULT_BASE_URL = "https://api.rhumb.dev/v1"
DEFAULT_TIMEOUT = 30.0
RUNTIME_BACKED_EVIDENCE_SOURCE_TYPES = frozenset(
    {"runtime_verified", "tester_generated", "probe_generated"}
)


@dataclass
class CoverageRow:
    service_slug: str
    proxy_name: str
    auth_type: str | None
    callable: bool
    total_reviews: int
    runtime_backed_reviews: int
    non_runtime_reviews: int
    total_evidence_records: int
    runtime_backed_evidence_records: int
    runtime_backed_evidence_pct: float
    evidence_review_gap_suspected: bool
    highest_source_type: str | None
    runtime_backed_review_pct: float
    reported_runtime_backed_pct: float
    freshest_evidence_at: str | None


def _fetch_json(url: str, timeout: float) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "rhumb-callable-review-audit/0.1",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} for {url}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error for {url}: {exc.reason}") from exc


def _callable_services(base_url: str, timeout: float) -> list[dict[str, Any]]:
    payload = _fetch_json(f"{base_url}/proxy/services", timeout)
    services = payload.get("data", {}).get("services", [])
    return [service for service in services if service.get("callable")]


def _service_reviews(base_url: str, service_slug: str, timeout: float) -> dict[str, Any]:
    return _fetch_json(f"{base_url}/services/{service_slug}/reviews", timeout)


def _service_evidence(base_url: str, service_slug: str, timeout: float) -> dict[str, Any]:
    return _fetch_json(f"{base_url}/services/{service_slug}/evidence", timeout)


def audit(base_url: str, timeout: float) -> dict[str, Any]:
    services = _callable_services(base_url, timeout)
    rows: list[CoverageRow] = []

    for service in services:
        slug = str(service.get("canonical_slug") or service.get("name") or service.get("proxy_name"))
        review_payload = _service_reviews(base_url, slug, timeout)
        evidence_payload = _service_evidence(base_url, slug, timeout)
        reviews = review_payload.get("reviews", [])
        evidence_records = evidence_payload.get("evidence", [])
        runtime_backed_reviews = sum(
            1 for review in reviews if review.get("trust_label") == RUNTIME_TRUST_LABEL
        )
        runtime_backed_evidence_records = sum(
            1
            for record in evidence_records
            if record.get("source_type") in RUNTIME_BACKED_EVIDENCE_SOURCE_TYPES
        )
        total_reviews = int(review_payload.get("total_reviews") or len(reviews))
        total_evidence_records = int(evidence_payload.get("total_evidence") or len(evidence_records))
        trust_summary = review_payload.get("trust_summary") or {}

        runtime_backed_review_pct = (
            round((runtime_backed_reviews / total_reviews) * 100, 1)
            if total_reviews
            else 0.0
        )
        runtime_backed_evidence_pct = (
            round((runtime_backed_evidence_records / total_evidence_records) * 100, 1)
            if total_evidence_records
            else 0.0
        )
        evidence_review_gap_suspected = (
            runtime_backed_evidence_records > 0
            and runtime_backed_reviews == 0
            and total_reviews > 0
        )

        rows.append(
            CoverageRow(
                service_slug=slug,
                proxy_name=str(service.get("proxy_name") or slug),
                auth_type=service.get("auth_type"),
                callable=bool(service.get("callable")),
                total_reviews=total_reviews,
                runtime_backed_reviews=runtime_backed_reviews,
                non_runtime_reviews=max(total_reviews - runtime_backed_reviews, 0),
                total_evidence_records=total_evidence_records,
                runtime_backed_evidence_records=runtime_backed_evidence_records,
                runtime_backed_evidence_pct=runtime_backed_evidence_pct,
                evidence_review_gap_suspected=evidence_review_gap_suspected,
                highest_source_type=trust_summary.get("highest_source_type"),
                runtime_backed_review_pct=runtime_backed_review_pct,
                reported_runtime_backed_pct=float(trust_summary.get("runtime_backed_pct") or 0.0),
                freshest_evidence_at=trust_summary.get("freshest_evidence_at"),
            )
        )

    rows.sort(key=lambda row: (row.runtime_backed_reviews, row.total_reviews, row.service_slug))

    weakest_depth = rows[0].runtime_backed_reviews if rows else 0
    weakest_bucket = [row.service_slug for row in rows if row.runtime_backed_reviews == weakest_depth]

    return {
        "base_url": base_url,
        "callable_provider_count": len(rows),
        "weakest_runtime_depth": weakest_depth,
        "weakest_bucket": weakest_bucket,
        "providers": [asdict(row) for row in rows],
    }


def _print_human(payload: dict[str, Any]) -> None:
    print(f"Base URL: {payload['base_url']}")
    print(f"Callable providers: {payload['callable_provider_count']}")
    print(
        "Weakest runtime-backed depth: "
        f"{payload['weakest_runtime_depth']} ({len(payload['weakest_bucket'])} providers)"
    )
    mismatch_rows = [
        row["service_slug"] for row in payload["providers"] if row["evidence_review_gap_suspected"]
    ]
    print(f"Evidence/review mismatches suspected: {len(mismatch_rows)}")
    if mismatch_rows:
        print(f"Flagged providers: {', '.join(mismatch_rows)}")
    print()
    print(
        f"{'service':20} {'rev_rt':>6} {'reviews':>7} {'ev_rt':>6} {'evidence':>8} "
        f"{'gap':>8} {'highest':>18}  freshest_evidence"
    )
    print("-" * 120)
    for row in payload["providers"]:
        highest = row["highest_source_type"] or "-"
        freshest = row["freshest_evidence_at"] or "-"
        gap = "MISMATCH" if row["evidence_review_gap_suspected"] else "-"
        print(
            f"{row['service_slug'][:20]:20} "
            f"{row['runtime_backed_reviews']:>7} "
            f"{row['total_reviews']:>5} "
            f"{row['runtime_backed_evidence_records']:>6} "
            f"{row['total_evidence_records']:>8} "
            f"{gap:>8} "
            f"{highest[:18]:>18}  {freshest}"
        )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Rhumb API base URL")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="HTTP timeout seconds")
    parser.add_argument("--json", action="store_true", help="Print JSON to stdout")
    parser.add_argument("--json-out", help="Write JSON payload to a file")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    payload = audit(args.base_url.rstrip("/"), args.timeout)

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_human(payload)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
