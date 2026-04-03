# Runtime review loop — PDL fix-verify rerun + Tavily depth-11 publication + subscription-billing expansion

Date: 2026-04-03 (~08:48 PT)
Owner: Pedro / Keel runtime review loop
Priority: Mission 0 fix-verify first (PDL), then Mission 1 freshness pass (Tavily), then Mission 2 discovery (subscription-billing)

---

## Mission 0 — mandated PDL rerun

**Context:** PDL slug-normalization fix shipped in commit `94c8df8`. Cron mandates a live rerun every loop to confirm it still holds in production.

### Execution

- Script: `scripts/runtime_review_pdl_fix_verify_20260401.py`
- Run: `railway run -s rhumb-api packages/api/.venv/bin/python scripts/runtime_review_pdl_fix_verify_20260401.py`
- Capability: `data.enrich_person`
- Input: `https://www.linkedin.com/in/satyanadella/`
- Credential mode: `rhumb_managed`

### Result

- Estimate: **200** (2 attempts; first estimate hit the known fresh-grant auth propagation race)
- Rhumb execute: **200**
- Provider used: **`people-data-labs`**
- Rhumb upstream: **402**
- Direct provider control: **402**
- Error message parity: **`You have hit your account maximum for person enrichment (all matches used)`** — exact match
- control_quota_blocked: `true`

### Verdict

**PASS.** Commit `94c8df8` still holds in production. Canonical slug `people-data-labs` resolves correctly through the Rhumb execution layer. The only blocker is provider quota exhaustion, not Rhumb routing.

No Rhumb-side investigation or fix required.

### Artifact

`artifacts/runtime-review-pass-20260403T154857Z-pdl-fix-verify-20260401b.json`

---

## Mission 1 — Tavily freshness pass to depth 11

### Why Tavily was selected

- Fresh callable coverage audit (pre-pass) showed all 16 callable providers at claim-safe runtime-backed depth **10**.
- PDL remained the oldest member of that bucket, but PDL already received separate Mission 0 fix-verification attention this run.
- After skipping already-rerun PDL, **Tavily** was the freshness-ordered oldest remaining member of the weakest bucket:
  - `tavily` — `2026-03-31T19:23:59Z`
- Therefore Tavily was the honest next Mission 1 target.

Pre-pass coverage artifact: `artifacts/callable-review-coverage-2026-04-03-pre-tavily-depth11.json`

### Rhumb execution

- Script: `scripts/runtime_review_tavily_depth11_20260403.py`
- Run: `railway run -s rhumb-api packages/api/.venv/bin/python scripts/runtime_review_tavily_depth11_20260403.py`
- Capability: `search.query`
- Provider: `tavily`
- Query: `LLM observability tools`
- Search depth: `basic`
- Max results: `5`
- Credential mode: `rhumb_managed`
- Post-grant delay: `5` seconds
- Estimate: **200**
- Rhumb execute: **200**
- Execution ID: `exec_f0bdd52fbf8447a3ac3a85b4a7eb0cd3`

### Direct provider control

- Endpoint: `POST https://api.tavily.com/search`
- Auth: `RHUMB_CREDENTIAL_TAVILY_API_KEY`
- Direct Tavily control: **200**

### Parity checked

- provider used
- upstream status
- result count
- top result title
- top result URL
- top result content
- top-3 URL ordering

### Observed parity

Rhumb and direct control matched exactly on:
- result count: `5`
- top result title:
  - `Top 10 LLM observability tools: Complete guide for 2025 - Braintrust`
- top result URL:
  - `https://www.braintrust.dev/articles/top-10-llm-observability-tools-2025`
- top result content excerpt
- top-3 URLs:
  1. `https://www.braintrust.dev/articles/top-10-llm-observability-tools-2025`
  2. `https://www.firecrawl.dev/blog/best-llm-observability-tools`
  3. `https://posthog.com/blog/best-open-source-llm-observability-tools`

### Verdict

**PASS. Full production parity confirmed for Tavily `search.query` through Rhumb Resolve.**

Published trust rows:
- evidence `57c2cece-0ef2-4285-be4a-18ce1522eb15`
- review `b42553ff-ffbd-43f4-9505-ce228ef047b7`

### Coverage impact

- Tavily moved **10 → 11** claim-safe runtime-backed reviews.
- Callable floor stays **10**.
- Providers now above the floor:
  - `e2b`
  - `brave-search`
  - `google-ai`
  - `tavily`
- The weakest depth-10 bucket now starts with:
  - `people-data-labs`
  - `firecrawl`
  - `apollo`
  - `exa`
- Freshness-ordered next honest non-PDL target is now **Firecrawl**.

Post-pass coverage artifact: `artifacts/callable-review-coverage-2026-04-03-post-tavily-depth11.json`

### Artifacts

- `artifacts/runtime-review-pass-20260403T155152Z-tavily-depth11.json`
- `artifacts/runtime-review-publication-2026-04-03-tavily-depth11.json`
- `artifacts/callable-review-coverage-2026-04-03-pre-tavily-depth11.json`
- `artifacts/callable-review-coverage-2026-04-03-post-tavily-depth11.json`
- `scripts/runtime_review_tavily_depth11_20260403.py`

---

## Mission 2 — subscription-billing expansion

### Why subscription-billing was selected

Live production category counts still show **`subscription-billing`** at only **5** providers:
- `chargebee`
- `lago`
- `orb-billing`
- `recurly`
- `revenuecat`

That is too thin for a category agents increasingly need for subscription-state lookup, invoice inspection, entitlement debugging, renewal monitoring, and recurring-revenue support workflows.

### Added services

| Slug | Name | Score | Execution | Access | Phase 0 |
|------|------|-------|-----------|--------|---------|
| `lemonsqueezy` | Lemon Squeezy | 8.50 | 8.60 | 8.30 | Best first candidate |
| `rebilly` | Rebilly | 8.35 | 8.50 | 8.05 | Strong second candidate |
| `zuora` | Zuora | 8.20 | 8.35 | 7.85 | Enterprise depth |
| `chargeover` | ChargeOver | 8.05 | 8.15 | 7.95 | Good midmarket wedge |
| `billsby` | Billsby | 7.95 | 8.05 | 7.80 | Breadth addition |

### Best Phase 0 wedge

The cleanest first move is read-first subscription inspection:
- `subscription.list`
- `subscription.get`
- `customer.get`
- `invoice.list`

**Best first provider:** **Lemon Squeezy**

Why:
- API-key auth
- explicit REST surface for subscriptions, customers, orders, and license artifacts
- immediately useful for support, entitlement, and renewal-state workflows
- lower setup weight than the larger enterprise billing systems

### Artifacts

- `packages/api/migrations/0154_subscription_billing_expansion.sql`
- `docs/runbooks/discovery-expansion/2026-04-03-subscription-billing-expansion.md`

---

## Next honest runtime-review target

With Tavily lifted to depth 11, the freshness-ordered next non-PDL callable target is now **Firecrawl**.
