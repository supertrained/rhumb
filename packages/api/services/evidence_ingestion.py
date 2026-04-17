"""Evidence ingestion adapter for operational facts and usage events."""

from __future__ import annotations

import logging
from dataclasses import field
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable

from pydantic.dataclasses import dataclass

from services.service_slugs import public_service_slug, public_service_slug_candidates

logger = logging.getLogger(__name__)

_ADAPTER_CREATED_BY = "evidence_ingestion_adapter_v1"
_SUPPORT_STATE_DOWNGRADE_NOTE = (
    "source_type downgraded from runtime_verified to manual_operator"
)
_VALID_CREDENTIAL_EVENT_TYPES = frozenset(
    {
        "credential_injected",
        "credential_missing",
        "credential_lookup_failed",
        "credential_rejected_by_provider",
    }
)


@dataclass
class IngestResult:
    """Mutable ingestion summary."""

    admitted: int = 0
    rejected: int = 0
    skipped_duplicate: int = 0
    errors: list[str] = field(default_factory=list)
    rejection_reasons: list[dict[str, str]] = field(default_factory=list)

    def merge(self, other: "IngestResult") -> "IngestResult":
        """Combine another result into a new aggregate."""
        return IngestResult(
            admitted=self.admitted + other.admitted,
            rejected=self.rejected + other.rejected,
            skipped_duplicate=self.skipped_duplicate + other.skipped_duplicate,
            errors=[*self.errors, *other.errors],
            rejection_reasons=[*self.rejection_reasons, *other.rejection_reasons],
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict for route responses."""
        return {
            "admitted": self.admitted,
            "rejected": self.rejected,
            "skipped_duplicate": self.skipped_duplicate,
            "errors": list(self.errors),
            "rejection_reasons": list(self.rejection_reasons),
        }


@dataclass
class _AdmissionRule:
    evidence_kind: str
    source_type: str
    fresh_offset: timedelta


_FACT_RULES: dict[str, _AdmissionRule] = {
    "latency_snapshot": _AdmissionRule(
        evidence_kind="latency_snapshot",
        source_type="runtime_verified",
        fresh_offset=timedelta(minutes=10),
    ),
    "circuit_state": _AdmissionRule(
        evidence_kind="circuit_state",
        source_type="runtime_verified",
        fresh_offset=timedelta(minutes=30),
    ),
    "schema_change": _AdmissionRule(
        evidence_kind="schema_change",
        source_type="runtime_verified",
        fresh_offset=timedelta(days=7),
    ),
    "credential_lifecycle": _AdmissionRule(
        evidence_kind="credential_lifecycle",
        source_type="runtime_verified",
        fresh_offset=timedelta(hours=24),
    ),
    "provider_support_state": _AdmissionRule(
        evidence_kind="support_state",
        source_type="manual_operator",
        fresh_offset=timedelta(days=7),
    ),
    "usage_attribution": _AdmissionRule(
        evidence_kind="usage_summary",
        source_type="runtime_verified",
        fresh_offset=timedelta(hours=24),
    ),
}


class EvidenceIngestionAdapter:
    """Adapter that admits operational facts into evidence records."""

    def __init__(self, supabase_client: Any = None) -> None:
        self.client = supabase_client

    async def ensure_supabase(self) -> bool:
        """Resolve a Supabase client if none was injected."""
        if self.client is not None:
            return True

        try:
            from db.client import get_supabase_client

            self.client = await get_supabase_client()
            return True
        except Exception:
            logger.exception("Evidence ingestion could not initialize Supabase")
            return False

    async def ingest_operational_facts(
        self,
        since: datetime | None = None,
        limit: int = 100,
    ) -> IngestResult:
        """Read access_operational_facts, apply admission, and write evidence."""
        result = IngestResult()
        if not await self.ensure_supabase():
            result.errors.append("Supabase client unavailable")
            return result

        try:
            facts = await self._fetch_rows(
                table_name="access_operational_facts",
                timestamp_column="observed_at",
                since=since,
                limit=limit,
            )
        except Exception as exc:
            result.errors.append(f"failed_to_fetch_access_operational_facts:{exc}")
            return result

        for fact in facts:
            fact_id = str(fact.get("id", ""))
            try:
                fact_type = str(fact.get("fact_type", ""))
                rule = _FACT_RULES.get(fact_type)
                if rule is None:
                    self._record_rejection(result, fact_id, "unadmitted_fact_type")
                    continue

                if fact_type == "credential_lifecycle" and str(
                    fact.get("event_type", "")
                ) not in _VALID_CREDENTIAL_EVENT_TYPES:
                    self._record_rejection(
                        result,
                        fact_id,
                        "unadmitted_credential_event_type",
                    )
                    continue

                source_ref = fact_id
                if await self._is_duplicate(source_ref):
                    result.skipped_duplicate += 1
                    continue

                observed_at = _parse_datetime(fact.get("observed_at"))
                summary = _coerce_optional_text(fact.get("notes"))
                source_type = rule.source_type
                public_service = _public_evidence_service_slug(fact.get("service_slug"))
                if (
                    fact_type == "provider_support_state"
                    and str(fact.get("source_type", "")) == "runtime_verified"
                ):
                    summary = _append_note(summary, _SUPPORT_STATE_DOWNGRADE_NOTE)

                fresh_until = observed_at + rule.fresh_offset
                payload = {
                    "service_slug": public_service,
                    "source_type": source_type,
                    "source_ref": source_ref,
                    "evidence_kind": rule.evidence_kind,
                    "title": f"{rule.evidence_kind} for {public_service}",
                    "summary": summary,
                    "raw_payload_json": fact.get("payload") or {},
                    "normalized_payload_json": {},
                    "observed_at": observed_at.isoformat(),
                    "fresh_until": fresh_until.isoformat(),
                    "confidence": _coerce_optional_float(fact.get("confidence")),
                    "agent_id": _coerce_optional_text(fact.get("agent_id")),
                    "run_id": _coerce_optional_text(fact.get("run_id")),
                    "created_by": _ADAPTER_CREATED_BY,
                }
                await self.client.table("evidence_records").insert(payload).execute()
                result.admitted += 1
            except Exception as exc:
                result.errors.append(f"failed_to_ingest_fact:{fact_id}:{exc}")

        return result

    async def ingest_usage_summaries(
        self,
        since: datetime | None = None,
        limit: int = 100,
    ) -> IngestResult:
        """Aggregate agent usage events into daily service evidence rows."""
        result = IngestResult()
        if not await self.ensure_supabase():
            result.errors.append("Supabase client unavailable")
            return result

        try:
            rows = await self._fetch_rows(
                table_name="agent_usage_events",
                timestamp_column="created_at",
                since=since,
                limit=limit,
            )
        except Exception as exc:
            result.errors.append(f"failed_to_fetch_agent_usage_events:{exc}")
            return result

        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in rows:
            created_at = _parse_datetime(row.get("created_at"))
            service = _public_evidence_service_slug(row.get("service"))
            group_key = (service, created_at.date().isoformat())
            grouped.setdefault(group_key, []).append(row)

        for (service, date_str), group_rows in grouped.items():
            try:
                source_ref_candidates = _usage_summary_source_ref_candidates(group_rows, date_str)
                if await self._has_any_duplicate(source_ref_candidates):
                    result.skipped_duplicate += 1
                    continue

                source_ref = f"usage_events:{service}:{date_str}"
                observed_at = max(
                    _parse_datetime(row.get("created_at")) for row in group_rows
                )
                result_counts = _count_results(group_rows)
                total_events = len(group_rows)
                total_response_size = sum(
                    int(row.get("response_size_bytes", 0) or 0) for row in group_rows
                )
                avg_latency_ms = (
                    sum(float(row.get("latency_ms", 0.0) or 0.0) for row in group_rows)
                    / total_events
                    if total_events
                    else 0.0
                )
                agent_ids = sorted(
                    {
                        str(agent_id)
                        for agent_id in (row.get("agent_id") for row in group_rows)
                        if agent_id
                    }
                )

                usage_fresh_until = observed_at + timedelta(hours=24)
                payload = {
                    "service_slug": service,
                    "source_type": "runtime_verified",
                    "source_ref": source_ref,
                    "evidence_kind": "usage_summary",
                    "title": f"Usage summary for {service} ({date_str})",
                    "summary": f"Aggregated {total_events} usage events for {service}",
                    "raw_payload_json": {
                        "service": service,
                        "date": date_str,
                        "total_events": total_events,
                        "result_counts": result_counts,
                        "avg_latency_ms": avg_latency_ms,
                        "total_response_size_bytes": total_response_size,
                        "agent_ids": agent_ids,
                    },
                    "normalized_payload_json": {},
                    "observed_at": observed_at.isoformat(),
                    "fresh_until": usage_fresh_until.isoformat(),
                    "confidence": 0.9,
                    "agent_id": agent_ids[0] if len(agent_ids) == 1 else None,
                    "run_id": None,
                    "created_by": _ADAPTER_CREATED_BY,
                }
                await self.client.table("evidence_records").insert(payload).execute()
                result.admitted += 1
            except Exception as exc:
                result.errors.append(
                    f"failed_to_ingest_usage_summary:{service}:{date_str}:{exc}"
                )

        return result

    async def run_full_ingestion(self) -> IngestResult:
        """Run both ingestion paths and combine their results."""
        operational_result = IngestResult()
        usage_result = IngestResult()

        try:
            operational_result = await self.ingest_operational_facts()
        except Exception as exc:
            operational_result.errors.append(f"operational_ingestion_failed:{exc}")

        try:
            usage_result = await self.ingest_usage_summaries()
        except Exception as exc:
            usage_result.errors.append(f"usage_ingestion_failed:{exc}")

        return operational_result.merge(usage_result)

    async def _fetch_rows(
        self,
        *,
        table_name: str,
        timestamp_column: str,
        since: datetime | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Read rows from one source table."""
        query = self.client.table(table_name).select("*").order(timestamp_column, desc=False)
        if since is not None:
            query = query.gte(timestamp_column, since.isoformat())
        response = await query.limit(limit).execute()
        data = response.data or []
        if isinstance(data, list):
            return [dict(row) for row in data]
        if isinstance(data, dict):
            return [dict(data)]
        return []

    async def _is_duplicate(self, source_ref: str) -> bool:
        """Check whether one source_ref is already present in evidence_records."""
        response = (
            await self.client.table("evidence_records")
            .select("id")
            .eq("source_ref", source_ref)
            .limit(1)
            .execute()
        )
        data = response.data or []
        if isinstance(data, list):
            return len(data) > 0
        return data is not None

    async def _has_any_duplicate(self, source_refs: Iterable[str]) -> bool:
        """Check whether any candidate source_ref is already present."""
        seen: set[str] = set()
        for source_ref in source_refs:
            if not source_ref or source_ref in seen:
                continue
            seen.add(source_ref)
            if await self._is_duplicate(source_ref):
                return True
        return False

    @staticmethod
    def _record_rejection(result: IngestResult, fact_id: str, reason: str) -> None:
        """Add a rejection entry to the result."""
        result.rejected += 1
        result.rejection_reasons.append({"fact_id": fact_id, "reason": reason})


def _append_note(summary: str | None, note: str) -> str:
    """Append a short note to an existing summary."""
    if summary:
        return f"{summary} ({note})"
    return note


def _coerce_optional_float(value: Any) -> float | None:
    """Convert optional numeric values to float."""
    if value is None:
        return None
    return float(value)


def _coerce_optional_text(value: Any) -> str | None:
    """Convert an optional value to text while preserving None."""
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _count_results(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Count usage results in one aggregate group."""
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get("result", "unknown"))
        counts[key] = counts.get(key, 0) + 1
    return counts


def _public_evidence_service_slug(value: Any) -> str:
    """Normalize evidence-facing service ids onto canonical public slugs."""
    cleaned = str(value or "").strip().lower()
    if not cleaned:
        return ""
    return public_service_slug(cleaned) or cleaned


def _usage_summary_source_ref_candidates(
    rows: Iterable[dict[str, Any]],
    date_str: str,
) -> list[str]:
    """Return duplicate-check candidates for canonicalized usage summaries."""
    candidates: list[str] = []
    seen_services: set[str] = set()
    for row in rows:
        raw_service = str(row.get("service", "")).strip().lower()
        for service_candidate in public_service_slug_candidates(raw_service) or [raw_service]:
            if not service_candidate or service_candidate in seen_services:
                continue
            seen_services.add(service_candidate)
            candidates.append(f"usage_events:{service_candidate}:{date_str}")
    return candidates


def _parse_datetime(value: Any) -> datetime:
    """Accept datetime or ISO-8601 text and return an aware UTC datetime."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed

    raise TypeError(f"Unsupported datetime value: {value!r}")
