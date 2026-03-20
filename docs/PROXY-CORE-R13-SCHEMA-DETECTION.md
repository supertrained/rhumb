# Round 13: WU 2.4 — Schema Change Detection

**Work Unit:** 2.4  
**Objective:** Detect and alert on API schema changes — the #1 unsolved problem in autonomous agent infrastructure  
**Status:** KICKOFF  
**Depends on:** WU 2.1 (proxy core), WU 2.2 (agent identity), WU 2.3 (metering)  
**Assigned to:** Codex sub-agent (`model="codex53"`)  
**Timeline:** ~11–13 hours (thin-slice execution, 4 slices, 12-15 min each)  
**Target metrics:** 40+ tests, 5 modules, 0 regressions

---

## Why This Work

Schema changes are the #1 unsolved problem. From research:
- **Cost cited:** $2.1K–$45M in losses per incident
- **Frequency:** Weekly for actively-developed APIs (OpenAI, Stripe, HubSpot)
- **Current status:** No standard detection mechanism
- **Impact:** Agents silently fail or return garbled data when schemas drift

Rhumb's unique advantage: we see every call through the proxy. We can fingerprint schema, detect diffs, and alert **before agents break**.

---

## Deliverables

### Module 1: Schema Fingerprinting Engine
**File:** `packages/api/services/schema_fingerprint.py`  
**Responsibility:** Capture and normalize API response schemas

**Key Components:**
- `SchemaFingerprint` dataclass: captures structure of response (field names, types, nested structure)
- `fingerprint_response()` function: parse response → structural hash (content-agnostic)
- Deep structural comparison: field add/remove, type change, nesting depth, cardinality (singular vs array)
- Semantic drift detection: detect common renames (parse similarity, levenshtein distance on field names)
- Metadata extraction: latency, status code, headers (content-type, cache-control)

**Tests (10 tests):**
- Fingerprint stable response → consistent hash
- Add field → detected as change
- Remove field → detected as change
- Type change (string → int) → detected
- Nested object structure change → detected
- Same fields, different order → same fingerprint (order-insensitive)
- Semantic rename (old_field → new_field) → similarity score >0.8 flags as likely rename
- Null/optional fields → treated as cardinality change
- Array → single object change → detected
- Complex nested structure (3+ levels) → fingerprinted correctly

---

### Module 2: Schema Change Detector
**File:** `packages/api/services/schema_change_detector.py`  
**Responsibility:** Detect, classify, and track schema drift

**Key Components:**
- `SchemaChangeDetector` class: compares current vs baseline fingerprint
- `detect_changes()` method: returns list of `SchemaChange` (add, remove, rename, type_change, nesting_change)
- `classify_severity()` method: breaking vs non-breaking vs advisory
  - **Breaking:** field removal, type change, nesting change
  - **Non-breaking:** field addition, optional field changes
  - **Advisory:** naming convention changes
- `alert_required()` method: returns bool (breaking changes → alert always, non-breaking → only if configured)
- Redis-backed baseline tracking: `schema:baseline:{service}:{endpoint}` → latest fingerprint hash + timestamp

**Tests (12 tests):**
- No changes detected when responses identical
- Field addition flagged as non-breaking
- Field removal flagged as breaking
- Type change flagged as breaking
- Multiple changes in single response → detected and classified
- Empty response → handled gracefully
- Breaking change + advisory change in same diff → both surfaced
- Baseline update flow (store new fingerprint after validation)
- Stale baseline (>7 days old) → handled with age warning
- Non-JSON response (HTML error) → graceful fallback
- Rate limit response (429) → not treated as schema drift
- Error response schema (500) → separate from success schema

---

### Module 3: Alert Pipeline
**File:** `packages/api/services/schema_alert_pipeline.py`  
**Responsibility:** Route schema change alerts to operators

**Key Components:**
- `AlertDispatcher` class: routes breaking changes to webhook + email + in-app
- `webhook_dispatch()`: POST to operator's configured webhook URL (auth token in header)
  - Payload: service name, endpoint, change detail, severity, timestamp, fingerprint diff
  - Retry logic: exponential backoff (3x, max 1h)
  - Error handling: webhook failure logged, alert marked retry_pending
- `email_dispatch()`: Slack/email notification (mock for now, real integration in Phase 3)
- `inapp_dispatch()`: Store schema alert in `schema_alerts` table, queryable via `/v1/admin/schema-alerts`
- Alert deduplication: same change on same endpoint → only alert once per 24h (unless severity escalates)

**Tests (8 tests):**
- Breaking change → webhook dispatched
- Non-breaking change → no alert (unless configured)
- Webhook success (200 OK) → logged, alert marked sent
- Webhook failure (500) → retry scheduled, alert marked pending
- Alert deduplication: same change 2x in 1h → only one webhook call
- Payload shape validation: includes all required fields
- Email dispatch (mock) → logged with recipient
- Alert query: `/v1/admin/schema-alerts?service=stripe&limit=10` → returns recent alerts

---

### Module 4: Proxy Integration
**File:** `packages/api/routes/proxy.py` (extension)  
**Responsibility:** Integrate schema detection into the proxy call path

**Key Components:**
- Extend `POST /proxy/` to call `schema_change_detector.detect_changes()` after every proxied call
- Store fingerprint in `schema_events` table (lightweight, no blocking)
- If breaking change detected: dispatch alert asynchronously (don't block response)
- New endpoint: `GET /v1/admin/schema/{service}/{endpoint}` → returns latest fingerprint + change history
- Leaderboard integration: schema freshness feeds into AN Score confidence (if schema stable 30 days, freshness bonus)

**Integration tests (10 tests):**
- Proxy call + schema stable → response unaffected, fingerprint stored
- Proxy call + breaking change detected → response unaffected, alert dispatched async
- Multiple calls, same schema → fingerprint reused (no re-computation)
- Admin endpoint `/v1/admin/schema/stripe/create-payment-intent` → returns current fingerprint + last 5 changes
- Leaderboard: service with stable schema (30d no changes) → freshness multiplier applied
- Operator receives webhook on breaking change → webhook payload well-formed
- Schema drift on error response (500) → not treated as drift on success schema
- High-volume endpoint (1,000 calls/sec) → fingerprinting doesn't block, stored async
- Multi-tenant: agent A's schema alert doesn't leak to agent B
- Admin schema-alerts query: filters by service, date range, severity

---

### Module 5: Supabase Migration
**File:** `packages/api/migrations/0007_schema_detection.sql`  
**Responsibility:** Database schema for schema tracking

**Tables:**
```sql
CREATE TABLE schema_fingerprints (
  id BIGSERIAL PRIMARY KEY,
  service_id BIGINT NOT NULL,
  endpoint TEXT NOT NULL,
  fingerprint_hash TEXT NOT NULL,
  updated_at TIMESTAMP DEFAULT now(),
  UNIQUE(service_id, endpoint)
);

CREATE TABLE schema_events (
  id BIGSERIAL PRIMARY KEY,
  service_id BIGINT NOT NULL,
  endpoint TEXT NOT NULL,
  fingerprint_hash TEXT NOT NULL,
  change_type TEXT, -- add, remove, type_change, rename, nesting_change
  severity TEXT, -- breaking, non_breaking, advisory
  captured_at TIMESTAMP DEFAULT now(),
  CONSTRAINT fk_service FOREIGN KEY (service_id) REFERENCES services(id)
);

CREATE INDEX idx_schema_events_service_endpoint ON schema_events(service_id, endpoint);
CREATE INDEX idx_schema_events_captured_at ON schema_events(captured_at DESC);

CREATE TABLE schema_alerts (
  id BIGSERIAL PRIMARY KEY,
  service_id BIGINT NOT NULL,
  endpoint TEXT NOT NULL,
  change_detail JSONB,
  severity TEXT,
  alert_sent_at TIMESTAMP,
  webhook_url TEXT,
  webhook_status INT,
  retry_count INT DEFAULT 0,
  retry_at TIMESTAMP,
  CONSTRAINT fk_service FOREIGN KEY (service_id) REFERENCES services(id)
);

CREATE INDEX idx_schema_alerts_service_pending ON schema_alerts(service_id) WHERE webhook_status IS NULL;
CREATE INDEX idx_schema_alerts_created_at ON schema_alerts(created_at DESC);
```

---

## Acceptance Criteria

### Functional
- ✅ Fingerprint captures schema structure (fields, types, nesting)
- ✅ Detector identifies changes (add, remove, type change, rename, nesting)
- ✅ Severity classification (breaking vs non-breaking vs advisory)
- ✅ Alert dispatch (webhook + email + in-app) for breaking changes
- ✅ Deduplication (same change only alerts once per 24h)
- ✅ Proxy integration (non-blocking, async alert dispatch)
- ✅ Admin endpoint: `/v1/admin/schema/{service}/{endpoint}` returns fingerprint + change history
- ✅ Leaderboard integration: schema stability feeds AN Score freshness

### Quality
- ✅ 40+ integration tests (fingerprint, detector, alerts, proxy, admin)
- ✅ Type annotations complete (mypy clean)
- ✅ Linting clean (flake8, isort)
- ✅ Zero regressions from Phase 2 (239 tests still passing)
- ✅ Supabase migration idempotent (no side effects)

### Performance
- ✅ Fingerprinting: <5ms per response (streaming, not blocking)
- ✅ Change detection: <10ms per call (O(n) in field count, not response size)
- ✅ Alert dispatch: async (webhook calls don't block proxy response)
- ✅ Baseline lookups: O(1) Redis (or in-memory cache)

### Operability
- ✅ Config: operator can set webhook URL + alert preferences per service
- ✅ Logging: all fingerprints + changes logged (queryable via admin endpoint)
- ✅ Monitoring: alert success/failure rates visible in dashboards
- ✅ Graceful degradation: if Redis unavailable, in-memory fallback (with limits)

---

## Thin-Slice Decomposition

| Slice | Focus | Deliverables | Tests | Approx Time |
|-------|-------|---------------|----|------------|
| A | Fingerprinting + comparison | Module 1 + tests | 10 | 12 min |
| B | Change detection + classification | Module 2 + tests | 12 | 13 min |
| C | Alert pipeline + integration | Module 3 + Module 4 integration | 10 | 14 min |
| D | Admin endpoints + E2E | Module 4 completion + Module 5 + integration tests | 10+ | 12 min |

**Total target:** 40+ tests, 4–5 modules, 50–60 min execution time (single sub-agent run)

---

## Dependencies

**Runtime:** Depends on Phase 2 (WU 2.1–2.3) being live
- Proxy router must be operational (for call interception)
- Agent identity must be in place (for per-agent alert routing)
- Billing/metering must exist (for schema events to include cost context)

**No blocking dependencies:** All modules can be developed in parallel slices

---

## Success Signal

By end of Round 13:
- ✅ Proxy detects schema changes on every call (non-blocking)
- ✅ Breaking changes trigger webhook alerts within 1 second
- ✅ Operators can query schema history per endpoint
- ✅ Leaderboard scores account for schema stability (freshness bonus for stable services)
- ✅ 239 Phase 2 tests still passing + 40+ new tests
- ✅ Ready for Phase 3 GTM launch with complete Access Layer

---

## Questions / Clarifications

**Q: How do we handle schema versioning (e.g., API v1 → v2)?**  
A: Currently treat as separate endpoint. Future: add version parameter to fingerprint key.

**Q: What if an endpoint returns different schemas based on auth level?**  
A: Each (agent + endpoint) pair gets separate baseline. Schema changes scoped per agent if needed.

**Q: Real Stripe integration for alerts?**  
A: No. Phase 3 work. For now: webhook dispatch + in-app alerts. Email is mocked.

**Q: How do we avoid false positives (e.g., timestamps, UUIDs)?**  
A: Fingerprint ignores scalar values, only captures structure. Timestamps/UUIDs don't trigger alerts.

**Q: Can operators opt-out of alerts for non-breaking changes?**  
A: Yes. Config: `alert_severity: breaking_only` (default) or `all`. Per-service setting.
