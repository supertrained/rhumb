"""Public read routes for service reviews, evidence, and aggregate stats."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query

from routes._supabase import cached_query, supabase_fetch
from services.service_slugs import (
    CANONICAL_TO_PROXY,
    public_service_slug,
    public_service_slug_candidates,
)

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
_VALID_EVIDENCE_KINDS = (
    "failure_mode",
    "latency_snapshot",
    "circuit_state",
    "schema_change",
    "credential_lifecycle",
    "support_state",
    "usage_summary",
)
_VALID_EVIDENCE_KIND_SET = frozenset(_VALID_EVIDENCE_KINDS)


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


def _validated_evidence_kind(kind: str | None) -> str | None:
    if kind is None:
        return None

    normalized = kind.strip().lower()
    if not normalized:
        return None

    if normalized not in _VALID_EVIDENCE_KIND_SET:
        valid_kinds = ", ".join(_VALID_EVIDENCE_KINDS)
        raise HTTPException(
            status_code=400,
            detail=f"Invalid kind: use one of {valid_kinds}",
        )

    return normalized


def _fallback_review_source_type(review_type: str | None) -> str | None:
    """Conservative fallback when review provenance has not been materialized.

    Important: do NOT infer runtime-backed trust from linked evidence at read time.
    Public review truth should come from the review row's materialized provenance
    (`highest_trust_source`) so it can be compared independently against the
    public evidence surface.
    """
    return {
        "docs": "docs_derived",
        "manual": "manual_operator",
        "provider": "manual_operator",
        "tester": "tester_generated",
        "crawler": "probe_generated",
        "synthesized": "docs_derived",
    }.get(review_type)


def _postgrest_in(values: list[str]) -> str:
    return ",".join(quote(value, safe="-_") for value in values)


def _canonicalize_known_service_aliases(
    text: Any,
    *,
    preserve_canonical: str | None = None,
) -> str | None:
    if text is None:
        return None

    preserved = str(preserve_canonical or "").strip().lower() or None
    replacements: dict[str, str] = {}
    for canonical in CANONICAL_TO_PROXY:
        if preserved and canonical.lower() == preserved:
            continue
        for candidate in public_service_slug_candidates(canonical):
            cleaned = str(candidate or "").strip()
            if not cleaned or cleaned.lower() == canonical.lower():
                continue
            replacements[cleaned.lower()] = canonical

    if not replacements:
        return str(text)

    pattern = re.compile(
        rf"(?<![a-z0-9-])(?:{'|'.join(re.escape(candidate) for candidate in sorted(replacements, key=len, reverse=True))})(?![a-z0-9-])",
        re.IGNORECASE,
    )
    return pattern.sub(lambda match: replacements[match.group(0).lower()], str(text))


def _canonicalize_service_text(
    text: Any,
    response_service_slug: str | None,
    stored_service_slug: str | None,
) -> str | None:
    """Rewrite alias-backed service-id mentions onto the canonical public slug."""
    if text is None:
        return None

    canonical = public_service_slug(response_service_slug)
    if canonical is None:
        return str(text)

    raw_stored_slug = str(stored_service_slug).strip().lower() if stored_service_slug else None
    preserve_human_shorthand = raw_stored_slug == canonical.lower()

    canonicalized = str(text)
    for candidate in sorted(public_service_slug_candidates(canonical), key=len, reverse=True):
        cleaned = str(candidate or "").strip()
        if not cleaned or cleaned.lower() == canonical.lower():
            continue

        pattern = re.compile(
            rf"(?<![a-z0-9-]){re.escape(cleaned)}(?![a-z0-9-])",
            re.IGNORECASE,
        )

        def _replace(match: re.Match[str]) -> str:
            matched = match.group(0)
            if preserve_human_shorthand and cleaned.isalpha() and matched == cleaned.upper():
                return matched
            return canonical

        canonicalized = pattern.sub(_replace, canonicalized)

    return _canonicalize_known_service_aliases(
        canonicalized,
        preserve_canonical=canonical if preserve_human_shorthand else None,
    )


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
    canonical_slug = public_service_slug(slug) or slug
    slug_candidates = public_service_slug_candidates(slug)
    reviews = await _cached_fetch(
        "service_reviews",
        "service_reviews"
        f"?service_slug=in.({_postgrest_in(slug_candidates)})"
        "&review_status=eq.published"
        "&order=reviewed_at.desc"
        "&select=id,service_slug,review_type,review_status,headline,summary,reviewer_label,reviewed_at,"
        "confidence,evidence_count,highest_trust_source"
    )
    review_rows = reviews or []
    review_ids = [str(row["id"]) for row in review_rows if row.get("id") is not None]
    source_types_by_review, linked_evidence = await _fetch_review_evidence(review_ids)

    response_reviews = []
    review_source_types: list[str] = []
    for row in review_rows:
        review_id = str(row["id"])
        review_source_type = row.get("highest_trust_source") or _fallback_review_source_type(
            row.get("review_type")
        )
        if review_source_type is not None:
            review_source_types.append(str(review_source_type))
        response_reviews.append(
            {
                "id": review_id,
                "review_type": row.get("review_type"),
                "review_status": row.get("review_status"),
                "headline": _canonicalize_service_text(
                    row.get("headline"), canonical_slug, row.get("service_slug")
                ),
                "summary": _canonicalize_service_text(
                    row.get("summary"), canonical_slug, row.get("service_slug")
                ),
                "reviewer_label": row.get("reviewer_label"),
                "reviewed_at": row.get("reviewed_at"),
                "confidence": row.get("confidence"),
                "evidence_count": row.get("evidence_count", 0),
                "trust_label": trust_label(review_source_type),
            }
        )

    freshest_evidence_at = None
    if linked_evidence:
        freshest_evidence_at = max(
            (_parse_datetime(row.get("observed_at")) for row in linked_evidence),
            default=None,
        )

    highest_source_type = _pick_highest_source_type(review_source_types)

    runtime_backed_reviews = sum(
        1
        for source_type in review_source_types
        if source_type in _RUNTIME_BACKED_SOURCE_TYPES
    )
    runtime_backed_pct = (
        round((runtime_backed_reviews / len(review_ids)) * 100, 1)
        if review_ids
        else 0.0
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
    normalized_kind = _validated_evidence_kind(kind)
    canonical_slug = public_service_slug(slug) or slug
    slug_candidates = public_service_slug_candidates(slug)
    path = (
        "evidence_records"
        f"?service_slug=in.({_postgrest_in(slug_candidates)})"
        "&order=observed_at.desc"
        "&select=id,service_slug,evidence_kind,source_type,title,summary,observed_at,fresh_until,"
        "confidence,source_ref"
    )
    if normalized_kind:
        path += f"&evidence_kind=eq.{quote(normalized_kind)}"

    evidence_rows = (await _cached_fetch("evidence_records", path)) or []
    return {
        "service_slug": canonical_slug,
        "evidence": [
            {
                "id": str(row["id"]),
                "evidence_kind": row.get("evidence_kind"),
                "source_type": row.get("source_type"),
                "title": _canonicalize_service_text(
                    row.get("title"), canonical_slug, row.get("service_slug")
                ),
                "summary": _canonicalize_service_text(
                    row.get("summary"), canonical_slug, row.get("service_slug")
                ),
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
