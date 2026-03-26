"""Public read routes for service reviews, evidence, and aggregate stats."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Query

from routes._supabase import cached_query, supabase_fetch
from services.service_slugs import canonicalize_service_slug, normalize_proxy_slug

router = APIRouter()
_READ_CACHE_TTL_SECONDS = 60.0

_TRUST_LABELS = {
    "runtime_verified": "\U0001F7E2 Runtime-verified",
    "tester_generated": "\U0001F9EA Tester-generated",
    "probe_generated": "\U0001F50D Probe-generated",
    "manual_operator": "\U0001F527 Operator-verified",
    "docs_derived": "\U0001F4C4 Docs-derived",
}
_SOURCE_PRIORITY = {
    "runtime_verified": 5,
    "tester_generated": 4,
    "probe_generated": 3,
    "manual_operator": 2,
    "docs_derived": 1,
}
_RUNTIME_BACKED_SOURCE_TYPES = {
    "runtime_verified",
    "tester_generated",
    "probe_generated",
}
_REVIEW_TYPE_BREAKDOWN_KEYS = ("docs", "manual", "tester", "automated")
_SOURCE_TYPE_BREAKDOWN_KEYS = (
    "docs_derived",
    "runtime_verified",
    "tester_generated",
    "probe_generated",
    "manual_operator",
)


async def _cached_fetch(table: str, path: str, ttl: float = _READ_CACHE_TTL_SECONDS) -> Any | None:
    return await cached_query(table, lambda: supabase_fetch(path), cache_key=path, ttl=ttl)


def trust_label(source_type: str | None) -> str:
    """Return the public trust label for a source type."""
    if source_type is None:
        return "\u2753 Unknown"
    return _TRUST_LABELS.get(source_type, "\u2753 Unknown")


def _utc_now() -> datetime:
    """Provide a testable UTC clock source."""
    return datetime.now(UTC)


def is_fresh(fresh_until: str | datetime | None) -> bool:
    """Determine freshness by comparing fresh_until to UTC now."""
    parsed = _parse_datetime(fresh_until)
    if parsed is None:
        return False
    return _utc_now() < parsed


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _normalize_timestamp(value: str | datetime | None) -> str | None:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    return parsed.isoformat().replace("+00:00", "Z")


def _pick_highest_source_type(source_types: list[str]) -> str | None:
    if not source_types:
        return None
    return max(source_types, key=lambda item: _SOURCE_PRIORITY.get(item, 0))


def _review_type_bucket(review_type: str | None) -> str:
    if review_type in {"docs", "manual", "tester"}:
        return review_type
    return "automated"


def _postgrest_in(values: list[str]) -> str:
    return ",".join(quote(value, safe="-_") for value in values)


def _service_slug_candidates(slug: str) -> list[str]:
    canonical_slug = canonicalize_service_slug(slug)
    candidates: list[str] = [canonical_slug]
    proxy_slug = normalize_proxy_slug(canonical_slug)
    if proxy_slug not in candidates:
        candidates.append(proxy_slug)
    return candidates


def _quality_floor(
    total_reviews: int,
    source_types_by_review: dict[str, list[str]],
) -> dict[str, Any]:
    """Compute quality floor from review-level evidence links.

    A review is "runtime-backed" if it has at least one linked evidence
    record whose source_type is in _RUNTIME_BACKED_SOURCE_TYPES.
    The percentage is: runtime-backed reviews / total published reviews.
    """
    runtime_backed_reviews = sum(
        1
        for sources in source_types_by_review.values()
        if any(s in _RUNTIME_BACKED_SOURCE_TYPES for s in sources)
    )
    docs_only_reviews = total_reviews - runtime_backed_reviews

    runtime_backed_pct = (
        round((runtime_backed_reviews / total_reviews) * 100, 1) if total_reviews else 0.0
    )
    docs_only_pct = (
        round((docs_only_reviews / total_reviews) * 100, 1) if total_reviews else 0.0
    )
    public_claim_eligible = total_reviews >= 100 and runtime_backed_pct >= 20.0

    if public_claim_eligible:
        reason = "Eligible for public claims"
    elif total_reviews < 100 and runtime_backed_pct < 20.0:
        reason = f"Below 100 reviews and {runtime_backed_pct:.0f}% runtime-backed (requires ≥20%)"
    elif total_reviews < 100:
        reason = "Below 100 reviews"
    else:
        reason = f"{runtime_backed_pct:.0f}% runtime-backed (requires ≥20%)"

    return {
        "runtime_backed_reviews": runtime_backed_reviews,
        "runtime_backed_pct": runtime_backed_pct,
        "docs_only_pct": docs_only_pct,
        "public_claim_eligible": public_claim_eligible,
        "reason": reason,
    }


async def _fetch_review_evidence(review_ids: list[str]) -> tuple[dict[str, list[str]], list[dict[str, Any]]]:
    if not review_ids:
        return {}, []

    links = await _cached_fetch(
        "review_evidence_links",
        "review_evidence_links"
        f"?review_id=in.({_postgrest_in(review_ids)})"
        "&select=review_id,evidence_record_id"
    )
    if not links:
        return {}, []

    evidence_ids = sorted({str(link["evidence_record_id"]) for link in links if link.get("evidence_record_id")})
    if not evidence_ids:
        return {}, []

    evidence_rows = await _cached_fetch(
        "evidence_records",
        "evidence_records"
        f"?id=in.({_postgrest_in(evidence_ids)})"
        "&select=id,source_type,observed_at"
    )
    if not evidence_rows:
        return {}, []

    evidence_by_id = {
        str(row["id"]): row
        for row in evidence_rows
        if row.get("id") is not None
    }
    source_types_by_review: dict[str, list[str]] = {}

    for link in links:
        review_id = link.get("review_id")
        evidence_record_id = link.get("evidence_record_id")
        if review_id is None or evidence_record_id is None:
            continue
        evidence_row = evidence_by_id.get(str(evidence_record_id))
        if evidence_row is None or evidence_row.get("source_type") is None:
            continue
        source_types_by_review.setdefault(str(review_id), []).append(str(evidence_row["source_type"]))

    return source_types_by_review, evidence_rows


@router.get("/services/{slug}/reviews")
async def get_service_reviews(slug: str) -> dict[str, Any]:
    """Return published reviews for one service."""
    canonical_slug = canonicalize_service_slug(slug)
    slug_candidates = _service_slug_candidates(slug)
    reviews = await _cached_fetch(
        "service_reviews",
        "service_reviews"
        f"?service_slug=in.({_postgrest_in(slug_candidates)})"
        "&review_status=eq.published"
        "&order=reviewed_at.desc"
        "&select=id,review_type,review_status,headline,summary,reviewer_label,reviewed_at,"
        "confidence,evidence_count"
    )
    review_rows = reviews or []
    review_ids = [str(row["id"]) for row in review_rows if row.get("id") is not None]
    source_types_by_review, linked_evidence = await _fetch_review_evidence(review_ids)

    response_reviews = []
    for row in review_rows:
        review_id = str(row["id"])
        highest_source_type = _pick_highest_source_type(source_types_by_review.get(review_id, []))
        response_reviews.append(
            {
                "id": review_id,
                "review_type": row.get("review_type"),
                "review_status": row.get("review_status"),
                "headline": row.get("headline"),
                "summary": row.get("summary"),
                "reviewer_label": row.get("reviewer_label"),
                "reviewed_at": row.get("reviewed_at"),
                "confidence": row.get("confidence"),
                "evidence_count": row.get("evidence_count", 0),
                "trust_label": trust_label(highest_source_type),
            }
        )

    freshest_evidence_at = None
    highest_source_type = None
    if linked_evidence:
        freshest_evidence_at = max(
            (_parse_datetime(row.get("observed_at")) for row in linked_evidence),
            default=None,
        )
        highest_source_type = _pick_highest_source_type(
            [str(row["source_type"]) for row in linked_evidence if row.get("source_type") is not None]
        )

    runtime_backed_pct = 0.0
    if linked_evidence:
        runtime_backed_pct = round(
            (
                sum(
                    1
                    for row in linked_evidence
                    if row.get("source_type") in _RUNTIME_BACKED_SOURCE_TYPES
                )
                / len(linked_evidence)
            )
            * 100,
            1,
        )

    return {
        "service_slug": canonical_slug,
        "reviews": response_reviews,
        "total_reviews": len(response_reviews),
        "trust_summary": {
            "highest_source_type": highest_source_type,
            "runtime_backed_pct": runtime_backed_pct,
            "freshest_evidence_at": _normalize_timestamp(freshest_evidence_at),
        },
    }


@router.get("/services/{slug}/evidence")
async def get_service_evidence(
    slug: str, kind: str | None = Query(default=None)
) -> dict[str, Any]:
    """Return evidence records for one service."""
    canonical_slug = canonicalize_service_slug(slug)
    slug_candidates = _service_slug_candidates(slug)
    path = (
        "evidence_records"
        f"?service_slug=in.({_postgrest_in(slug_candidates)})"
        "&order=observed_at.desc"
        "&select=id,evidence_kind,source_type,title,summary,observed_at,fresh_until,"
        "confidence,source_ref"
    )
    if kind:
        path += f"&evidence_kind=eq.{quote(kind)}"

    evidence_rows = (await _cached_fetch("evidence_records", path)) or []
    return {
        "service_slug": canonical_slug,
        "evidence": [
            {
                "id": str(row["id"]),
                "evidence_kind": row.get("evidence_kind"),
                "source_type": row.get("source_type"),
                "title": row.get("title"),
                "summary": row.get("summary"),
                "observed_at": row.get("observed_at"),
                "fresh_until": row.get("fresh_until"),
                "is_fresh": is_fresh(row.get("fresh_until")),
                "confidence": row.get("confidence"),
                "source_ref": row.get("source_ref"),
            }
            for row in evidence_rows
            if row.get("id") is not None
        ],
        "total_evidence": len(evidence_rows),
    }


@router.get("/reviews/stats")
async def get_review_stats() -> dict[str, Any]:
    """Return aggregate review and evidence coverage stats."""
    review_rows = (
        await _cached_fetch("service_reviews", "service_reviews?review_status=eq.published&select=id,review_type")
    ) or []
    evidence_rows = (
        await _cached_fetch("evidence_records", "evidence_records?select=id,source_type")
    ) or []

    review_type_breakdown = {key: 0 for key in _REVIEW_TYPE_BREAKDOWN_KEYS}
    for row in review_rows:
        review_type_breakdown[_review_type_bucket(row.get("review_type"))] += 1

    source_type_breakdown: dict[str, int] = {key: 0 for key in _SOURCE_TYPE_BREAKDOWN_KEYS}
    for row in evidence_rows:
        source_type = row.get("source_type")
        if source_type is None:
            continue
        source_type_breakdown.setdefault(str(source_type), 0)
        source_type_breakdown[str(source_type)] += 1

    total_reviews = len(review_rows)

    # Quality floor: compute from review-level evidence links, not raw evidence ratios.
    review_ids = [str(row["id"]) for row in review_rows if row.get("id") is not None]
    source_types_by_review, _ = await _fetch_review_evidence(review_ids)

    return {
        "total_published_reviews": total_reviews,
        "total_evidence_records": len(evidence_rows),
        "review_type_breakdown": review_type_breakdown,
        "source_type_breakdown": source_type_breakdown,
        "quality_floor": _quality_floor(total_reviews, source_types_by_review),
        "gate_4_progress": f"{total_reviews} / 500",
    }
