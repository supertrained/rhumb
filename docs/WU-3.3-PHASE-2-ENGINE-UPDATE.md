# WU 3.3 Phase 2 — AN Score v0.3 Engine Integration

**Objective:** Integrate Payment Autonomy (P1), Governance Readiness (G1), and Web Agent Accessibility (W1) dimensions into the scoring engine. Bump AN Score to v0.3.

**Dependencies:** WU 3.3 Phase 1 complete (research + scoring delivered in `artifacts/autonomy-scores.json`)

**Timeline:** Single focused task, ~2-4 hours execution

## Deliverables

### 1. `packages/api/services/scoring.py` — Three New Dimensions
Add three new dimension modules to the scoring engine. Each dimension:
- **Input:** Service profile (from `services` table or scored JSON)
- **Output:** Score 0–10, rationale (2–5 words), confidence 0–1.0

#### P1 — Payment Autonomy (Weight: 6% of new autonomy axis)
Measure: Can agents autonomously initiate payments for this service?
- **10:** x402/AP2 native, agent-callable without human approval
- **8–9:** Stripe Virtual Cards (Issuing API), Coinbase AgentKit
- **5–7:** Standard card payments automatable (need provisioning proxy)
- **2–4:** Sales/custom payment required, no standard agent flow
- **0–1:** No payment model (free-only or human-negotiated)

Reference: `artifacts/autonomy-scores.json` (P1 column)

#### G1 — Governance Readiness (Weight: 5% of new autonomy axis)
Measure: Can enterprises audit and control multi-agent access?
- **10:** RBAC, audit logs, non-human identity (Okta, Entra Agent, AWS IAM)
- **8–9:** API keys + activity logs (Stripe, GitHub, Sendgrid)
- **5–7:** Basic API auth, partial audit trail
- **2–4:** Limited governance, API-only or weak audit
- **0–1:** No governance primitives, shared credentials required

Reference: `artifacts/autonomy-scores.json` (G1 column)

#### W1 — Web Agent Accessibility (Weight: 4% of new autonomy axis)
Measure: Can agents navigate and interact with the dashboard/admin UI? (AAG Level)
- **8–10:** AAG Level AAA (semantic HTML, llms.txt, agent-flows.json, token-efficient)
- **6–7:** AAG Level AA (keyboard nav, ARIA, structured DOM)
- **4–5:** AAG Level A (semantic HTML, basic accessibility)
- **2–3:** Limited accessibility, forms/buttons but no semantic markup
- **0–1:** No web UI (API-only) or inaccessible (JS-only, dynamic, no labels)

Reference: `artifacts/autonomy-scores.json` (W1 column)

### 2. Update `DIMENSION_WEIGHTS` in `scoring.py`
Current weight structure (17 dimensions for Execution + Access):
```python
DIMENSION_WEIGHTS = {
    # Execution (I1–I7: 45%)
    'integration_layers': 0.07,  # I1
    'latency_p99': 0.07,         # I2
    'error_handling': 0.06,       # I3
    'schema_stability': 0.06,     # I4
    'idempotency': 0.07,          # I5
    'graceful_degradation': 0.03, # I6
    'pagination': 0.01,           # I7
    # Access (A1–A6: 40%)
    'oauth_support': 0.08,        # A1
    'api_documentation': 0.06,    # A2
    'rate_limiting': 0.06,        # A3
    'auth_methods': 0.07,         # A4
    'webhook_support': 0.04,      # A5
    'async_capabilities': 0.03,   # A6
    # Observation (O1–O3: 15%)
    'feature_completeness': 0.05, # O1
    'api_stability': 0.05,        # O2
    'support_quality': 0.05,      # O3
}
```

**Autonomy axis is NEW (15% aggregate weight):**
- P1 (Payment): 0.06
- G1 (Governance): 0.05
- W1 (Web Accessibility): 0.04

Execution + Access remain 45% + 40%. Autonomy is inserted as a new pillar, shifting Observation down to deferred status.

### 3. Add New Columns to Supabase `scores` Table
Create migration `0009_autonomy_dimensions.sql`:
```sql
ALTER TABLE scores ADD COLUMN IF NOT EXISTS
  payment_autonomy SMALLINT CHECK (payment_autonomy BETWEEN 0 AND 10),
  payment_autonomy_rationale TEXT,
  payment_autonomy_confidence NUMERIC(3,2) CHECK (payment_autonomy_confidence BETWEEN 0 AND 1),

  governance_readiness SMALLINT CHECK (governance_readiness BETWEEN 0 AND 10),
  governance_readiness_rationale TEXT,
  governance_readiness_confidence NUMERIC(3,2) CHECK (governance_readiness_confidence BETWEEN 0 AND 1),

  web_accessibility SMALLINT CHECK (web_accessibility BETWEEN 0 AND 10),
  web_accessibility_rationale TEXT,
  web_accessibility_confidence NUMERIC(3,2) CHECK (web_accessibility_confidence BETWEEN 0 AND 1);

-- Update `aggregate_score` calculation to include new dimensions
-- Formula: (Execution avg × 0.45) + (Access avg × 0.40) + (Autonomy avg × 0.15)
-- Autonomy avg = (P1 + G1 + W1) / 3
```

Run migration via Supabase CLI or psql wrapper.

### 4. Seed Autonomy Scores from `artifacts/autonomy-scores.json`
Create `0010_seed_autonomy_scores.sql`:
- Load `autonomy-scores.json`
- Map each service's P1/G1/W1 scores + rationales to corresponding rows in `scores` table
- Update `aggregate_score` for all 50 services
- Verify no nulls, all ranges valid

### 5. Update Tests
- Add dimension calculation unit tests (each dimension 0–10, rationale non-empty, confidence 0–1)
- Add Supabase seeding validation (all 50 rows have autonomy scores)
- Add aggregate_score recalculation test (verify formula applies weights correctly)
- Add integration test: fetch updated service score via API, verify autonomy fields present + correct

### 6. Update `GET /v1/services/{slug}/score` Response
Extend response schema to include autonomy dimensions:
```json
{
  "service": "stripe",
  "aggregate_score": 8.3,
  "tier": "L4 Native",
  "execution": { "avg": 8.5, "confidence": 0.92, "dimensions": [...] },
  "access": { "avg": 8.1, "confidence": 0.88, "dimensions": [...] },
  "autonomy": {
    "avg": 8.7,
    "confidence": 0.85,
    "dimensions": [
      { "name": "payment_autonomy", "score": 10, "rationale": "x402 native" },
      { "name": "governance_readiness", "score": 10, "rationale": "RBAC + audit logs" },
      { "name": "web_accessibility", "score": 8, "rationale": "AAG Level AA" }
    ]
  },
  "freshness": "12 minutes ago"
}
```

### 7. Update AN Score Spec Document
Add autonomy section to `docs/AN-SCORE-V2-SPEC.md`:
- Full dimension definitions (copy from this kickoff)
- Weight justification (15% autonomy axis)
- Response schema example
- Tier mapping (L1–L4 unchanged, now driven by three-pillar model)

## Acceptance Criteria

- [ ] P1/G1/W1 calculation functions added to `scoring.py`
- [ ] DIMENSION_WEIGHTS updated with new weights
- [ ] Migration `0009_autonomy_dimensions.sql` created + runs without error
- [ ] Autonomy scores seeded into all 50 services via `0010_seed_autonomy_scores.sql`
- [ ] `GET /v1/services/{slug}/score` returns autonomy dimensions in response
- [ ] All 50 services have non-null autonomy scores
- [ ] Aggregate score recalculated correctly (new 3-pillar formula)
- [ ] Unit tests: dimension calculations (P1/G1/W1), formula validation
- [ ] Integration tests: API response schema, seeding validation
- [ ] AN Score spec document updated with autonomy sections
- [ ] Zero regressions: all existing tests pass

## Agent Assignment
- **Sub-agent:** Codex 5.3 (backend coding)
- **Model override:** `model="codex53"`
- **Time budget:** 4 hours
- **Success signal:** PR created, all tests passing, autonomous score seeding complete

## Success Metrics
1. All 50 services scored on three autonomy dimensions
2. New fields queryable via API with correct weights applied
3. Aggregate score distribution shifts to reflect autonomy pillar (avg should increase slightly due to payment gap research insights)
4. Ready for WU 3.3 Phase 3 (web surface integration)

## Post-Completion
- PR review + merge to main
- Continue to WU 3.3 Phase 3: Add autonomy badges to leaderboard + service pages
