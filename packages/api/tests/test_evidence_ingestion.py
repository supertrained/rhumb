"""Acceptance tests for GAP-6 evidence ingestion."""

from __future__ import annotations

import asyncio
import copy
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from services.evidence_ingestion import EvidenceIngestionAdapter


def _run(coro):  # type: ignore[no-untyped-def]
    """Run one async coroutine in a dedicated event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _FakeResponse:
    def __init__(self, data: Any) -> None:
        self.data = data


class _FakeSupabaseQuery:
    def __init__(self, client: "_FakeSupabaseClient", table_name: str) -> None:
        self._client = client
        self._table_name = table_name
        self._selected_columns = "*"
        self._filters: list[tuple[str, str, Any]] = []
        self._insert_payload: Any = None
        self._limit: int | None = None
        self._order_column: str | None = None
        self._order_desc = False

    def select(self, columns: str) -> "_FakeSupabaseQuery":
        self._selected_columns = columns
        return self

    def eq(self, column: str, value: Any) -> "_FakeSupabaseQuery":
        self._filters.append(("eq", column, value))
        return self

    def gte(self, column: str, value: Any) -> "_FakeSupabaseQuery":
        self._filters.append(("gte", column, value))
        return self

    def order(self, column: str, desc: bool = False) -> "_FakeSupabaseQuery":
        self._order_column = column
        self._order_desc = desc
        return self

    def limit(self, value: int) -> "_FakeSupabaseQuery":
        self._limit = value
        return self

    def insert(self, payload: Any) -> "_FakeSupabaseQuery":
        self._insert_payload = payload
        return self

    async def execute(self) -> _FakeResponse:
        return self._client.execute(self)


class _FakeSupabaseClient:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            "access_operational_facts": [],
            "agent_usage_events": [],
            "evidence_records": [],
            "service_reviews": [],
        }

    def table(self, table_name: str) -> _FakeSupabaseQuery:
        return _FakeSupabaseQuery(self, table_name)

    def rows(self, table_name: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(table_name, [])

    def row_count(self, table_name: str) -> int:
        return len(self.rows(table_name))

    def execute(self, query: _FakeSupabaseQuery) -> _FakeResponse:
        rows = self.rows(query._table_name)

        if query._insert_payload is not None:
            payload = query._insert_payload
            if isinstance(payload, list):
                inserted = [copy.deepcopy(row) for row in payload]
                rows.extend(inserted)
                return _FakeResponse(inserted)

            inserted_row = copy.deepcopy(payload)
            rows.append(inserted_row)
            return _FakeResponse(inserted_row)

        selected_rows = [copy.deepcopy(row) for row in rows if _matches_filters(row, query._filters)]

        if query._order_column is not None:
            selected_rows.sort(
                key=lambda row: _comparable_value(row.get(query._order_column or "")),
                reverse=query._order_desc,
            )

        if query._limit is not None:
            selected_rows = selected_rows[: query._limit]

        if query._selected_columns != "*":
            requested_columns = [
                column.strip() for column in query._selected_columns.split(",") if column.strip()
            ]
            selected_rows = [
                {
                    column: row[column]
                    for column in requested_columns
                    if column in row
                }
                for row in selected_rows
            ]

        return _FakeResponse(selected_rows)


def _matches_filters(
    row: dict[str, Any],
    filters: list[tuple[str, str, Any]],
) -> bool:
    for operator, column, value in filters:
        row_value = row.get(column)
        if operator == "eq" and _comparable_value(row_value) != _comparable_value(value):
            return False
        if operator == "gte" and _comparable_value(row_value) < _comparable_value(value):
            return False
    return True


def _comparable_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed
    return value


def _fact(
    *,
    fact_type: str,
    event_type: str = "observed",
    source_type: str = "runtime_verified",
    observed_at: datetime | None = None,
    fact_id: str | None = None,
    notes: str | None = "captured",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    timestamp = observed_at or datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
    return {
        "id": fact_id or str(uuid.uuid4()),
        "schema_version": "access_operational_fact_v1",
        "fact_type": fact_type,
        "service_slug": "stripe",
        "provider_slug": "stripe",
        "agent_id": "agent-1",
        "run_id": "run-1",
        "event_type": event_type,
        "observed_at": timestamp,
        "environment": "production",
        "source_type": source_type,
        "confidence": 0.85,
        "fresh_until": timestamp + timedelta(hours=1),
        "artifact_ref": None,
        "notes": notes,
        "payload": payload or {"sample": True},
        "ingress_channel": "access_proxy",
    }


def _usage_event(
    *,
    service: str = "stripe",
    created_at: datetime | None = None,
    agent_id: str = "agent-1",
    result: str = "success",
    latency_ms: float = 120.0,
    response_size_bytes: int = 512,
) -> dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        "agent_id": agent_id,
        "service": service,
        "result": result,
        "latency_ms": latency_ms,
        "response_size_bytes": response_size_bytes,
        "created_at": created_at or datetime(2026, 1, 11, 8, 0, tzinfo=UTC),
    }


def test_admits_latency_snapshot() -> None:
    client = _FakeSupabaseClient()
    observed_at = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
    client.rows("access_operational_facts").append(
        _fact(fact_type="latency_snapshot", observed_at=observed_at)
    )

    adapter = EvidenceIngestionAdapter(client)
    result = _run(adapter.ingest_operational_facts())

    assert result.admitted == 1
    evidence = client.rows("evidence_records")[0]
    assert evidence["evidence_kind"] == "latency_snapshot"
    assert evidence["source_type"] == "runtime_verified"
    assert evidence["fresh_until"] == (observed_at + timedelta(minutes=10)).isoformat()


def test_admits_latency_snapshot_with_canonical_public_service_slug() -> None:
    client = _FakeSupabaseClient()
    observed_at = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
    fact = _fact(fact_type="latency_snapshot", observed_at=observed_at)
    fact["service_slug"] = "brave-search"
    fact["provider_slug"] = "brave-search"
    client.rows("access_operational_facts").append(fact)

    adapter = EvidenceIngestionAdapter(client)
    result = _run(adapter.ingest_operational_facts())

    assert result.admitted == 1
    evidence = client.rows("evidence_records")[0]
    assert evidence["service_slug"] == "brave-search-api"
    assert evidence["title"] == "latency_snapshot for brave-search-api"
    assert evidence["source_ref"] == fact["id"]


def test_admits_circuit_state() -> None:
    client = _FakeSupabaseClient()
    observed_at = datetime(2026, 1, 10, 14, 30, tzinfo=UTC)
    client.rows("access_operational_facts").append(
        _fact(fact_type="circuit_state", observed_at=observed_at)
    )

    adapter = EvidenceIngestionAdapter(client)
    result = _run(adapter.ingest_operational_facts())

    assert result.admitted == 1
    evidence = client.rows("evidence_records")[0]
    assert evidence["evidence_kind"] == "circuit_state"
    assert evidence["source_type"] == "runtime_verified"
    assert evidence["fresh_until"] == (observed_at + timedelta(minutes=30)).isoformat()


def test_admits_schema_change() -> None:
    client = _FakeSupabaseClient()
    observed_at = datetime(2026, 1, 12, 9, 15, tzinfo=UTC)
    client.rows("access_operational_facts").append(
        _fact(fact_type="schema_change", observed_at=observed_at)
    )

    adapter = EvidenceIngestionAdapter(client)
    result = _run(adapter.ingest_operational_facts())

    assert result.admitted == 1
    evidence = client.rows("evidence_records")[0]
    assert evidence["evidence_kind"] == "schema_change"
    assert evidence["fresh_until"] == (observed_at + timedelta(days=7)).isoformat()


def test_admits_credential_lifecycle_valid_events() -> None:
    client = _FakeSupabaseClient()
    valid_events = [
        "credential_injected",
        "credential_missing",
        "credential_lookup_failed",
        "credential_rejected_by_provider",
    ]
    client.rows("access_operational_facts").extend(
        [
            _fact(
                fact_type="credential_lifecycle",
                event_type=event_type,
                fact_id=f"fact-{index}",
            )
            for index, event_type in enumerate(valid_events, start=1)
        ]
    )

    adapter = EvidenceIngestionAdapter(client)
    result = _run(adapter.ingest_operational_facts())

    assert result.admitted == 4
    assert result.rejected == 0
    assert client.row_count("evidence_records") == 4
    assert {row["evidence_kind"] for row in client.rows("evidence_records")} == {
        "credential_lifecycle"
    }


def test_rejects_credential_lifecycle_invalid_event() -> None:
    client = _FakeSupabaseClient()
    client.rows("access_operational_facts").append(
        _fact(
            fact_type="credential_lifecycle",
            event_type="credential_rotated",
            fact_id="cred-invalid",
        )
    )

    adapter = EvidenceIngestionAdapter(client)
    result = _run(adapter.ingest_operational_facts())

    assert result.admitted == 0
    assert result.rejected == 1
    assert client.row_count("evidence_records") == 0
    assert result.rejection_reasons == [
        {
            "fact_id": "cred-invalid",
            "reason": "unadmitted_credential_event_type",
        }
    ]


def test_admits_support_state_manual_operator() -> None:
    client = _FakeSupabaseClient()
    client.rows("access_operational_facts").append(
        _fact(
            fact_type="provider_support_state",
            source_type="manual_operator",
            notes="operator verified support",
        )
    )

    adapter = EvidenceIngestionAdapter(client)
    result = _run(adapter.ingest_operational_facts())

    assert result.admitted == 1
    evidence = client.rows("evidence_records")[0]
    assert evidence["evidence_kind"] == "support_state"
    assert evidence["source_type"] == "manual_operator"
    assert evidence["summary"] == "operator verified support"


def test_downgrades_support_state_runtime_to_manual() -> None:
    client = _FakeSupabaseClient()
    client.rows("access_operational_facts").append(
        _fact(
            fact_type="provider_support_state",
            source_type="runtime_verified",
            notes="runtime detected support toggle",
        )
    )

    adapter = EvidenceIngestionAdapter(client)
    result = _run(adapter.ingest_operational_facts())

    assert result.admitted == 1
    evidence = client.rows("evidence_records")[0]
    assert evidence["source_type"] == "manual_operator"
    assert "downgraded from runtime_verified to manual_operator" in evidence["summary"]


def test_admits_usage_summary() -> None:
    client = _FakeSupabaseClient()
    created_at = datetime(2026, 1, 11, 8, 0, tzinfo=UTC)
    client.rows("agent_usage_events").extend(
        [
            _usage_event(
                service="stripe",
                created_at=created_at,
                result="success",
                latency_ms=100.0,
                response_size_bytes=500,
            ),
            _usage_event(
                service="stripe",
                created_at=created_at + timedelta(hours=2),
                result="error",
                latency_ms=200.0,
                response_size_bytes=700,
            ),
        ]
    )

    adapter = EvidenceIngestionAdapter(client)
    result = _run(adapter.ingest_usage_summaries())

    assert result.admitted == 1
    evidence = client.rows("evidence_records")[0]
    assert evidence["evidence_kind"] == "usage_summary"
    assert evidence["source_type"] == "runtime_verified"
    assert evidence["source_ref"] == "usage_events:stripe:2026-01-11"
    assert evidence["title"] == "Usage summary for stripe (2026-01-11)"
    assert evidence["confidence"] == 0.9
    assert evidence["fresh_until"] == (created_at + timedelta(hours=26)).isoformat()
    assert evidence["raw_payload_json"]["total_events"] == 2
    assert evidence["raw_payload_json"]["result_counts"] == {"success": 1, "error": 1}


def test_usage_summary_canonicalizes_alias_backed_service_groups() -> None:
    client = _FakeSupabaseClient()
    created_at = datetime(2026, 1, 11, 8, 0, tzinfo=UTC)
    client.rows("agent_usage_events").extend(
        [
            _usage_event(
                service="brave-search",
                created_at=created_at,
                result="success",
                latency_ms=100.0,
                response_size_bytes=500,
            ),
            _usage_event(
                service="brave-search-api",
                created_at=created_at + timedelta(hours=2),
                result="error",
                latency_ms=200.0,
                response_size_bytes=700,
            ),
        ]
    )

    adapter = EvidenceIngestionAdapter(client)
    result = _run(adapter.ingest_usage_summaries())

    assert result.admitted == 1
    evidence = client.rows("evidence_records")[0]
    assert evidence["service_slug"] == "brave-search-api"
    assert evidence["source_ref"] == "usage_events:brave-search-api:2026-01-11"
    assert evidence["title"] == "Usage summary for brave-search-api (2026-01-11)"
    assert evidence["summary"] == "Aggregated 2 usage events for brave-search-api"
    assert evidence["raw_payload_json"]["service"] == "brave-search-api"
    assert evidence["raw_payload_json"]["total_events"] == 2
    assert evidence["raw_payload_json"]["result_counts"] == {"success": 1, "error": 1}


def test_usage_summary_skips_duplicate_when_existing_source_ref_uses_alias() -> None:
    client = _FakeSupabaseClient()
    created_at = datetime(2026, 1, 11, 8, 0, tzinfo=UTC)
    client.rows("agent_usage_events").append(
        _usage_event(service="brave-search", created_at=created_at)
    )
    client.rows("evidence_records").append(
        {
            "id": str(uuid.uuid4()),
            "service_slug": "brave-search",
            "source_ref": "usage_events:brave-search:2026-01-11",
            "evidence_kind": "usage_summary",
        }
    )

    adapter = EvidenceIngestionAdapter(client)
    result = _run(adapter.ingest_usage_summaries())

    assert result.admitted == 0
    assert result.skipped_duplicate == 1
    assert client.row_count("evidence_records") == 1


def test_rejects_unknown_fact_type() -> None:
    client = _FakeSupabaseClient()
    client.rows("access_operational_facts").extend(
        [
            _fact(fact_type="benchmark_artifact", fact_id="unknown-1"),
            _fact(fact_type="provider_friction", fact_id="unknown-2"),
        ]
    )

    adapter = EvidenceIngestionAdapter(client)
    result = _run(adapter.ingest_operational_facts())

    assert result.admitted == 0
    assert result.rejected == 2
    assert client.row_count("evidence_records") == 0
    assert result.rejection_reasons == [
        {"fact_id": "unknown-1", "reason": "unadmitted_fact_type"},
        {"fact_id": "unknown-2", "reason": "unadmitted_fact_type"},
    ]


def test_skips_duplicate() -> None:
    client = _FakeSupabaseClient()
    fact = _fact(fact_type="latency_snapshot", fact_id="dup-fact")
    client.rows("access_operational_facts").append(fact)
    client.rows("evidence_records").append(
        {
            "id": str(uuid.uuid4()),
            "service_slug": "stripe",
            "source_ref": "dup-fact",
            "evidence_kind": "latency_snapshot",
        }
    )

    adapter = EvidenceIngestionAdapter(client)
    result = _run(adapter.ingest_operational_facts())

    assert result.admitted == 0
    assert result.skipped_duplicate == 1
    assert client.row_count("evidence_records") == 1


def test_never_creates_service_reviews() -> None:
    client = _FakeSupabaseClient()
    client.rows("access_operational_facts").append(_fact(fact_type="latency_snapshot"))
    client.rows("agent_usage_events").append(_usage_event())

    adapter = EvidenceIngestionAdapter(client)
    result = _run(adapter.run_full_ingestion())

    assert result.admitted == 2
    assert client.row_count("service_reviews") == 0


def test_rejection_reasons_logged() -> None:
    client = _FakeSupabaseClient()
    client.rows("access_operational_facts").extend(
        [
            _fact(
                fact_type="credential_lifecycle",
                event_type="credential_rotated",
                fact_id="reject-credential",
                observed_at=datetime(2026, 1, 10, 9, 0, tzinfo=UTC),
            ),
            _fact(
                fact_type="benchmark_artifact",
                fact_id="reject-unknown",
                observed_at=datetime(2026, 1, 10, 10, 0, tzinfo=UTC),
            ),
        ]
    )

    adapter = EvidenceIngestionAdapter(client)
    result = _run(adapter.ingest_operational_facts())

    assert result.rejection_reasons == [
        {
            "fact_id": "reject-credential",
            "reason": "unadmitted_credential_event_type",
        },
        {
            "fact_id": "reject-unknown",
            "reason": "unadmitted_fact_type",
        },
    ]


def test_full_ingestion_runs_both_paths() -> None:
    client = _FakeSupabaseClient()
    client.rows("access_operational_facts").append(
        _fact(fact_type="schema_change", fact_id="schema-1")
    )
    client.rows("agent_usage_events").append(
        _usage_event(service="github", created_at=datetime(2026, 1, 12, 6, 0, tzinfo=UTC))
    )

    adapter = EvidenceIngestionAdapter(client)
    result = _run(adapter.run_full_ingestion())

    assert result.admitted == 2
    assert result.rejected == 0
    assert client.row_count("evidence_records") == 2
    assert {row["source_ref"] for row in client.rows("evidence_records")} == {
        "schema-1",
        "usage_events:github:2026-01-12",
    }
