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
import time
from dataclasses import asdict, dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
from urllib.request import Request, urlopen

RUNTIME_TRUST_LABEL = "🟢 Runtime-verified"
DEFAULT_BASE_URL = "https://api.rhumb.dev/v1"
DEFAULT_TIMEOUT = 30.0
RUNTIME_BACKED_EVIDENCE_SOURCE_TYPES = frozenset(
    {"runtime_verified", "tester_generated", "probe_generated"}
)

# Claim-safe counting: the minimum of review trust_label count and
# evidence source_type count. A review is only claim-safe runtime-backed
# if BOTH the review label and evidence source agree.
# See: Keel alert 2026-03-31 re: google-ai depth-6 overclaim risk.


@dataclass
class CoverageRow:
    service_slug: str
    proxy_name: str
    auth_type: str | None
    callable: bool
    total_reviews: int
    runtime_backed_reviews: int  # By trust_label on review surface
    non_runtime_reviews: int
    total_evidence_records: int
    runtime_backed_evidence_records: int  # By source_type on evidence surface
    runtime_backed_evidence_pct: float
    evidence_review_gap_suspected: bool
    highest_source_type: str | None
    runtime_backed_review_pct: float
    reported_runtime_backed_pct: float
    freshest_evidence_at: str | None
    # Claim-safe count: min(review trust_label count, evidence source_type count)
    # Only this number should be used in public claims.
    claim_safe_runtime_backed: int = 0
    label_evidence_mismatch: bool = False


def _with_cache_bust(url: str, token: str | None) -> str:
    if not token:
        return url
    parts = urlsplit(url)
    params = parse_qsl(parts.query, keep_blank_values=True)
    params.append(("__fresh", token))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params), parts.fragment))


def _fetch_json(url: str, timeout: float) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "rhumb-callable-review-audit/0.1",
        },
    )
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            last_error = exc
            if exc.code >= 500 and attempt < 3:
                time.sleep(float(attempt))
                continue
            raise RuntimeError(f"HTTP {exc.code} for {url}") from exc
        except URLError as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(float(attempt))
                continue
            raise RuntimeError(f"Network error for {url}: {exc.reason}") from exc
    assert last_error is not None
    raise RuntimeError(f"Unable to fetch {url}: {last_error}")


def _callable_services(base_url: str, timeout: float, cache_bust_token: str | None = None) -> list[dict[str, Any]]:
    payload = _fetch_json(_with_cache_bust(f"{base_url}/proxy/services", cache_bust_token), timeout)
    services = payload.get("data", {}).get("services", [])
    return [service for service in services if service.get("callable")]


def _service_reviews(base_url: str, service_slug: str, timeout: float, cache_bust_token: str | None = None) -> dict[str, Any]:
    return _fetch_json(_with_cache_bust(f"{base_url}/services/{service_slug}/reviews", cache_bust_token), timeout)


def _service_evidence(base_url: str, service_slug: str, timeout: float, cache_bust_token: str | None = None) -> dict[str, Any]:
    return _fetch_json(_with_cache_bust(f"{base_url}/services/{service_slug}/evidence", cache_bust_token), timeout)


def audit(base_url: str, timeout: float, cache_bust: bool = False) -> dict[str, Any]:
    cache_bust_token = str(int(time.time() * 1000)) if cache_bust else None
    services = _callable_services(base_url, timeout, cache_bust_token)
    rows: list[CoverageRow] = []

    for service in services:
        slug = str(service.get("canonical_slug") or service.get("name") or service.get("proxy_name"))
        review_payload = _service_reviews(base_url, slug, timeout, cache_bust_token)
        evidence_payload = _service_evidence(base_url, slug, timeout, cache_bust_token)
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

        # Claim-safe: the conservative minimum of both counting methods.
        # A public claim of "N runtime-backed reviews" must be supportable
        # by BOTH the review trust_label surface AND the evidence source_type surface.
        claim_safe = min(runtime_backed_reviews, runtime_backed_evidence_records)
        label_evidence_mismatch = runtime_backed_reviews != runtime_backed_evidence_records

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
                claim_safe_runtime_backed=claim_safe,
                label_evidence_mismatch=label_evidence_mismatch,
            )
        )

    rows.sort(key=lambda row: (row.claim_safe_runtime_backed, row.total_reviews, row.service_slug))

    weakest_depth = rows[0].claim_safe_runtime_backed if rows else 0
    weakest_bucket = [row.service_slug for row in rows if row.claim_safe_runtime_backed == weakest_depth]
    mismatched = [row.service_slug for row in rows if row.label_evidence_mismatch]

    return {
        "base_url": base_url,
        "callable_provider_count": len(rows),
        "weakest_claim_safe_depth": weakest_depth,
        "weakest_bucket": weakest_bucket,
        # Legacy alias for backward compat with existing artifact consumers
        "weakest_runtime_depth": weakest_depth,
        "label_evidence_mismatches": mismatched,
        "providers": [asdict(row) for row in rows],
    }


def _print_human(payload: dict[str, Any]) -> None:
    print(f"Base URL: {payload['base_url']}")
    print(f"Callable providers: {payload['callable_provider_count']}")
    print(
        "Weakest claim-safe depth: "
        f"{payload['weakest_claim_safe_depth']} ({len(payload['weakest_bucket'])} providers)"
    )
    label_ev_mismatches = payload.get("label_evidence_mismatches", [])
    if label_ev_mismatches:
        print(f"⚠️  Label/evidence count mismatches: {', '.join(label_ev_mismatches)}")
    mismatch_rows = [
        row["service_slug"] for row in payload["providers"] if row["evidence_review_gap_suspected"]
    ]
    if mismatch_rows:
        print(f"Evidence/review gap suspected: {', '.join(mismatch_rows)}")
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
    parser.add_argument(
        "--cache-bust",
        action="store_true",
        help="Append a unique query parameter to public reads so freshly-published review/evidence rows are visible immediately",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    payload = audit(args.base_url.rstrip("/"), args.timeout, cache_bust=args.cache_bust)

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
