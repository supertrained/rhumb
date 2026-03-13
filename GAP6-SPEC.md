# GAP-6 Implementation Spec — Evidence Ingestion Adapter

## Goal
Build `packages/api/services/evidence_ingestion.py` — an adapter that reads from `access_operational_facts` and `agent_usage_events`, applies admission rules, and writes to `evidence_records`.

## Files to create/modify
1. **CREATE** `packages/api/services/evidence_ingestion.py` — the adapter
2. **CREATE** `packages/api/tests/test_evidence_ingestion.py` — full test coverage
3. **MODIFY** `packages/api/routes/admin_agents.py` — add `POST /v1/admin/evidence/ingest` trigger endpoint

## Adapter class: `EvidenceIngestionAdapter`

```python
class EvidenceIngestionAdapter:
    def __init__(self, supabase_client):
        self.client = supabase_client
    
    async def ingest_operational_facts(self, since: datetime | None = None, limit: int = 100) -> IngestResult:
        """Read from access_operational_facts, apply admission, write to evidence_records."""
    
    async def ingest_usage_summaries(self, since: datetime | None = None, limit: int = 100) -> IngestResult:
        """Read from agent_usage_events, apply admission, write to evidence_records."""
    
    async def run_full_ingestion(self) -> IngestResult:
        """Run both ingestion paths."""
```

## IngestResult dataclass
```python
@dataclass
class IngestResult:
    admitted: int
    rejected: int
    skipped_duplicate: int
    errors: list[str]
    rejection_reasons: list[dict]  # {"fact_id": ..., "reason": ...}
```

## Admission Rules (6 families)

### Admitted fact_types with mapping:
| Source `fact_type` | Target `evidence_kind` | Default `source_type` | `fresh_until` offset |
|---|---|---|---|
| `latency_snapshot` | `latency_snapshot` | `runtime_verified` | +10 minutes |
| `circuit_state` | `circuit_state` | `runtime_verified` | +30 minutes |
| `schema_change` | `schema_change` | `runtime_verified` | +7 days |
| `credential_lifecycle` | `credential_lifecycle` | `runtime_verified` | +24 hours |
| `provider_support_state` | `support_state` | `manual_operator` | +7 days |
| `usage_attribution` | `usage_summary` | `runtime_verified` | +24 hours |

### Rejection rules:
1. **Unknown fact_type** → reject with reason "unadmitted_fact_type"
2. **credential_lifecycle with wrong event_type** → reject unless `event_type IN ('credential_injected', 'credential_missing', 'credential_lookup_failed', 'credential_rejected_by_provider')`; reason: "unadmitted_credential_event_type"
3. **provider_support_state with source_type=runtime_verified** → downgrade to `manual_operator` (not reject), add note
4. **Duplicate** (same fact already ingested by `source_ref` matching `access_operational_facts.id`) → skip with reason "duplicate"

### Write to evidence_records:
```python
{
    "service_slug": fact.service_slug,
    "source_type": mapped_source_type,
    "source_ref": str(fact.id),  # FK back to operational fact for audit
    "evidence_kind": mapped_kind,
    "title": f"{mapped_kind} for {fact.service_slug}",
    "summary": fact.notes or None,
    "raw_payload_json": fact.payload,
    "normalized_payload_json": {},  # v1: pass-through
    "observed_at": fact.observed_at,
    "fresh_until": computed_fresh_until,
    "confidence": fact.confidence,
    "agent_id": fact.agent_id,
    "run_id": fact.run_id,
    "created_by": "evidence_ingestion_adapter_v1",
}
```

### Usage summary special path:
For `agent_usage_events`, aggregate by service per day:
- `evidence_kind`: `usage_summary`
- `source_type`: `runtime_verified`
- `source_ref`: `usage_events:{service}:{date}`
- `title`: `Usage summary for {service} ({date})`
- `fresh_until`: observed_at + 24 hours
- `confidence`: 0.9 (metering is durable but doesn't prove provider success)

## Hard constraints
- **NEVER** create or modify `service_reviews` rows
- **NEVER** increment review counts
- All rejections must be logged (not silent drops)
- Duplicate detection by `source_ref` in `evidence_records`

## Acceptance tests (test_evidence_ingestion.py)
1. `test_admits_latency_snapshot` — correct evidence_kind, source_type, fresh_until
2. `test_admits_circuit_state` — same
3. `test_admits_schema_change` — 7-day freshness
4. `test_admits_credential_lifecycle_valid_events` — only 4 admitted event_types
5. `test_rejects_credential_lifecycle_invalid_event` — unadmitted event_type rejected with reason
6. `test_admits_support_state_manual_operator` — source_type preserved as manual_operator
7. `test_downgrades_support_state_runtime_to_manual` — runtime_verified → manual_operator with note
8. `test_admits_usage_summary` — from agent_usage_events
9. `test_rejects_unknown_fact_type` — benchmark_artifact, provider_friction rejected
10. `test_skips_duplicate` — same source_ref already in evidence_records
11. `test_never_creates_service_reviews` — assert 0 rows in service_reviews after ingestion
12. `test_rejection_reasons_logged` — rejected facts appear in IngestResult.rejection_reasons
13. `test_full_ingestion_runs_both_paths` — run_full_ingestion returns combined result

## Notes
- Use Supabase REST client (httpx) for all DB operations, consistent with existing codebase
- Import pattern: `from db.client import get_supabase_client`
- Tests should use the same in-memory fake pattern as `test_agent_identity_integration.py`
