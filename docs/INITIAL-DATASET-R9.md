# Round 9 Kickoff: Initial 50 Service Dataset (WU 1.7)

> **Work Unit:** 1.7 — Initial 50 Service Dataset
> **Owner:** Pedro (curation + hand-verification) + Tester Fleet (automated scoring)
> **Goal:** Curate 50 essential services, fully score them, hand-verify methodology, and publish leaderboard
> **Phase:** 1 — Discover MVP
> **Dependencies:** WU 1.3 (Tester Fleet v0) — ✅ complete

---

## Context

Round 8 completed the MCP server directory surface (WU 1.6). All 4 tools are live and tested:
- `find_tools` — semantic search over service index
- `get_score` — full AN Score breakdown
- `get_alternatives` — ranked alternatives by category
- `get_failure_modes` — failure patterns and resilience guidance

The Tester Fleet (WU 1.3) is fully operational:
- Battery YAML format for standardized test specifications
- Runner harness for HTTP probes + schema capture
- Artifact writer + probe metadata bridge
- CLI entrypoint: `rhumb test-battery <service>`

**This round unlocks the first real dataset:** 50 hand-curated, fully-scored, operator-validated services that become Rhumb's "hypothesis" on what matters most.

---

## Strategy

### Category Selection (8–10 categories, ~50 services)

Prioritize by operator frequency and cross-cutting dependencies:

| Category | Archetypes | Priority |
|----------|-----------|----------|
| **Email** | Sendgrid, Resend, Postmark, Mailgun | High — foundational |
| **CRM** | HubSpot, Salesforce, Pipedrive, Copper | High — core business logic |
| **Payments** | Stripe, Adyen, Braintree, PayPal | High — revenue-critical |
| **Calendar** | Cal.com, Calendly, Google Calendar API | Medium — scheduling pattern |
| **Analytics** | Mixpanel, Segment, PostHog, Amplitude | Medium — observability |
| **Search/Indexing** | Algolia, Meilisearch, Elasticsearch | Medium — discovery pattern |
| **Social / Content** | Twitter API, LinkedIn API, Bluesky API | Medium — distribution |
| **DevOps / Infra** | Vercel, Netlify, AWS, Digital Ocean, Render | Medium — deployment |
| **Auth** | Auth0, Okta, Firebase Auth, Clerk | High — security-critical |
| **AI/ML** | OpenAI, Anthropic, HuggingFace | High — emerging pattern |

**Target: 50 services across these categories, with emphasis on high-frequency integrations and representative patterns.**

---

## Scoring Methodology

### Automated Scoring (Tester Fleet)
1. **Probe execution** via `rhumb test-battery <service>`
   - Standardized test battery (auth, rate limits, schema capture, error modes)
   - Latency distribution (P50/P95/P99)
   - Schema fingerprint (structural + semantic)
   - Failure classification (retry-safe? circuit-breaker friendly?)
2. **AN Score calculation** via WU 1.1 engine
   - 17 dimensions (I1-I7, F1-F7, O1-O3)
   - Confidence scoring (freshness + diversity + telemetry bonus)
   - Tier assignment (L1-L4)
   - Contextual one-sentence explanation
3. **Probe metadata** stored in Supabase
   - `tested_at`, `schema_version`, `latency_distribution`, `failure_modes`

### Hand-Verification (Top 20)
1. **Spot-check methodology** on top 20 services by AN Score
   - Verify probe behaviors are realistic (not false positives)
   - Verify dimension weights align with operator reality
   - Validate failure mode classification
   - Check contextual explanations for clarity
2. **Calibration loop** if methodology drift detected
   - Adjust probe specs (test batteries)
   - Rerun affected services
   - Update AN Score weights if needed
3. **Sign-off:** Pedro validates that top 20 scores reflect true operator experience

---

## Thin-Slice Decomposition

### Slice A: Curation + Dataset Bootstrap
**Deliverable:** `data/initial-dataset.yaml` (50 services metadata + category mapping)

- Curate 50 services across categories (name, slug, category, description, official_docs_url)
- Create initial service records in Supabase (`services` table)
- Generate service slugs + URL routes
- Add to API index for `find_tools` search
- Tests: dataset schema validation, slug uniqueness, category consistency

**Owner:** Pedro (direct write)
**Timeline:** Day 1 (2–3 hours)
**Success Criteria:**
- ✅ 50 services defined with consistent metadata
- ✅ All slugs valid (alphanumeric, dashes, 3-50 chars)
- ✅ Each service assigned exactly one primary category
- ✅ Tests validate schema, slug uniqueness, category coverage

---

### Slice B: Tester Fleet Execution
**Deliverable:** Scored dataset (50 services × AN Score + probe metadata)

- For each of 50 services, run `rhumb test-battery <service>`
- Capture probe results: latency, schema, error modes, auth behavior
- Trigger AN Score calculation for each service
- Store results in Supabase (`scores` table, `probes` table)
- Handle failures gracefully (missing docs, auth walls, timeouts)
- Tests: probe resilience, score persistence, metadata integrity

**Owner:** Codex sub-agent (spawn as `mode=run` for parallelizable probe loop)
**Timeline:** Day 2 (2–4 hours, parallelizable)
**Success Criteria:**
- ✅ 50 services scored (AN Score calculated)
- ✅ Probe metadata captured (latency, schema, error modes)
- ✅ All scores persisted in Supabase
- ✅ Fallback behavior validated for auth-gated/missing services
- ✅ No regression in existing service scores

---

### Slice C: Hand-Verification + Calibration
**Deliverable:** Verified scores + calibration report (top 20) + contextual explanations

- Sample top 20 services by AN Score
- Spot-check each:
  - Probe behaviors (are they realistic?)
  - Dimension scoring (do weights match operator reality?)
  - Failure modes (are they correct?)
  - Tier assignment (does L1-L4 classification feel right?)
- If drift detected, document calibration adjustments:
  - Probe spec changes (test battery updates)
  - Weight rebalancing (dimension adjustments)
  - Rerun affected services
- Refine one-sentence explanations for clarity
- Tests: explanation length + clarity, tier consistency, dimension weight validation

**Owner:** Pedro (direct verification) + Codex (if rerun needed)
**Timeline:** Day 3 (3–4 hours)
**Success Criteria:**
- ✅ Top 20 services hand-verified
- ✅ All explanations clear + concise (under 15 words)
- ✅ Tier assignment feels aligned with operator experience
- ✅ Calibration report written (if adjustments made)
- ✅ No scores regressed from verification

---

### Slice D: Leaderboard Publishing + Documentation
**Deliverable:** Public leaderboard (web) + CLI index + deployment

- Publish `/leaderboard` with category filters
  - Service cards with aggregate AN Score + execution/access badges
  - Freshness indicator ("Tested 45 minutes ago")
  - Click-through to service profile pages
- Update `rhumb find` CLI to include dataset (indexed for search)
- Generate category-specific leaderboards (top 10 per category)
- Deploy to production (web + API)
- Update README with leaderboard link
- Tests: web rendering, CLI search accuracy, category filtering

**Owner:** Codex sub-agent (spawn as `mode=run`)
**Timeline:** Day 4 (2–3 hours)
**Success Criteria:**
- ✅ Leaderboard renders without errors
- ✅ Category filtering works
- ✅ Search CLI includes all 50 services
- ✅ Freshness metadata displays correctly
- ✅ Service profile links resolve
- ✅ No regressions in web/API tests

---

## Success Criteria (Round-Level)

- ✅ 50 services fully defined and indexed
- ✅ All 50 scored (AN Score + probe metadata)
- ✅ Top 20 hand-verified for methodology validation
- ✅ Public leaderboard deployed and functional
- ✅ `rhumb find` CLI updated with indexed dataset
- ✅ All tests passing (dataset schema + probe resilience + web rendering + search)
- ✅ Documentation updated (categories, methodology, leaderboard overview)
- ✅ Zero regressions in existing scoring/probe infrastructure

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Probe failures (auth walls, timeouts) | Fallback behavior in Tester Fleet; hand-verify affected services |
| Dimension weight misalignment | Hand-verification catches and triggers calibration loop |
| Category imbalance | Curate for distribution; document any gaps |
| Data quality | Hand-verify top 20; sign-off before publish |
| Schema evolution (providers change) | Probe metadata captures version; schema fingerprinting detects drift |

---

## External Dependencies

- **Supabase** (services + scores + probes tables) — ✅ existing
- **Tester Fleet CLI** (`rhumb test-battery <service>`) — ✅ existing (WU 1.3)
- **AN Score engine** (scoring calculation) — ✅ existing (WU 1.1)
- **Web/CLI** (leaderboard rendering + search) — ✅ existing (WU 1.5 + WU 1.4)

---

## Blockers

**None identified.** All dependencies are complete. Execution can begin immediately.

---

## What's Next After This Round

Once the initial 50-service leaderboard is published and verified:

1. **WU 2.1 (Access — Proxy Core):** Minimal-viable API key proxy (sub-10ms overhead)
2. **WU 2.2 (Access — Agent Identity):** Per-agent rate limits + billing
3. **WU 2.3 (Access — Provisioning):** Signup + payment handling for credential gatekeeping

The 50-service dataset validates the scoring methodology and becomes the first public artifact. It proves the ON Score hypothesis and drives the first wave of operator discovery.
