# Panel 3: Economics, Billing & Scaling
## Rhumb Resolve — Founding Product Specification

**Panel Composition:** Usage-based billing architects, API marketplace operators, fintech billing specialists, infrastructure economists, pricing strategists, cost accounting specialists, payment systems architects (x402/crypto), managed service operators.

**Status:** v1 — Founding Spec  
**Date:** 2026-03-30  
**Scope:** Full economics stack from per-call pricing through regulatory compliance

---

## Table of Contents

1. [Pricing Model Per Layer](#1-pricing-model-per-layer)
2. [Cost Accounting Architecture](#2-cost-accounting-architecture)
3. [Billing Pipeline Design](#3-billing-pipeline-design)
4. [Margin Analysis Per Layer](#4-margin-analysis-per-layer)
5. [Provider Cost Management](#5-provider-cost-management)
6. [Budget Enforcement](#6-budget-enforcement)
7. [Overdraft and Credit Management](#7-overdraft-and-credit-management)
8. [Revenue Recognition](#8-revenue-recognition)
9. [Scaling Economics](#9-scaling-economics)
10. [Float Management and Regulatory Considerations](#10-float-management-and-regulatory-considerations)
11. [x402 Integration Design](#11-x402-integration-design)

---

## 1. Pricing Model Per Layer

### Philosophy

Rhumb's pricing is transparently layered: agents pay for what they get, and each layer's price reflects the corresponding level of value-add Rhumb provides. Thin infrastructure fee at Layer 1, routing/reliability premium at Layer 2, full orchestration premium at Layer 3. Every price published at call time via the `X-Rhumb-Price` response header — no invoice surprises.

### 1.1 Layer 1: Raw Provider Access

**What it is:** Direct provider API call proxied through Rhumb. Rhumb handles credentials, rate limiting, observability, billing consolidation. Agent specifies exact provider and exact parameters.

**Pricing formula:**
```
agent_charge = provider_cost_passthrough + infrastructure_fee
infrastructure_fee = max($0.0002, provider_cost * 0.08)
```

**Justification for 8% + floor model:**
- Provider cost varies 1000x across capabilities (e.g., a GPT-4o call vs. a weather lookup). A flat per-call fee would over-charge for cheap calls and under-charge for expensive ones.
- 8% markup on provider cost scales naturally and covers: API key management, credential rotation, rate limit handling, observability, billing reconciliation.
- Floor of $0.0002 covers minimum infrastructure overhead for any call (DB write, auth check, ledger deduction).
- This is intentionally thin — Layer 1 is the trust anchor and escape hatch, not the revenue engine.

**Concrete pricing examples:**

| Scenario | Provider | Provider Cost | Rhumb Fee | Agent Pays |
|----------|----------|---------------|-----------|------------|
| GPT-4o 1K tokens | OpenAI | $0.005000 | $0.000400 | $0.005400 |
| Weather lookup | WeatherAPI | $0.000010 | $0.000200 (floor) | $0.000210 |
| Stable Diffusion image | Replicate | $0.002300 | $0.000200 | $0.002500 |
| Twilio SMS | Twilio | $0.007500 | $0.000600 | $0.008100 |
| Web scrape 1 URL | Apify | $0.000300 | $0.000200 (floor) | $0.000500 |
| Embedding 10K tokens | OpenAI | $0.000100 | $0.000200 (floor) | $0.000300 |

**Effective margin range:** 3.7% (expensive calls) to 95% (cheap calls hitting floor). **Blended target: 8-12%.**

Layer 1 is a volume game. At 1M calls/day, even at $0.0003 average infrastructure fee, that's $300/day ($109K/year) from Layer 1 alone.

---

### 1.2 Layer 2: Single Capability Delivery

**What it is:** Agent requests a capability outcome (e.g., "transcribe audio," "classify sentiment," "geocode address"). Rhumb selects provider, handles retries, normalization, fallback, and delivers to a stable schema.

**Pricing formula:**
```
agent_charge = best_provider_cost + routing_premium + reliability_premium
routing_premium = capability_base_fee (fixed per capability tier)
reliability_premium = 0.12 * best_provider_cost  (12% of selected provider cost)
```

**Capability tier structure:**

| Tier | Description | Base Fee | Examples |
|------|-------------|----------|---------|
| T1 | Commodity lookup | $0.0005 | Geocoding, weather, currency rates, IP lookup |
| T2 | Simple ML inference | $0.0015 | Sentiment, classification, entity extraction |
| T3 | Rich ML inference | $0.0040 | Summarization, translation, moderation |
| T4 | Generative (text) | $0.0080 | Completion, chat, structured generation |
| T5 | Generative (media) | $0.0200 | Image generation, audio synthesis, video |
| T6 | Composed single-pass | $0.0350 | OCR+extract, transcribe+diarize, analyze+structure |

**Justification for tiered base + percentage hybrid:**
- Base fee covers Rhumb's routing engine overhead regardless of provider cost
- Percentage component (12%) scales with the actual execution cost, creating alignment between what Rhumb charges and what executes
- Tier determines the "complexity tax" — higher tiers require more normalization logic, schema mapping, and retry sophistication
- Flat base fees are easier for agents to reason about when pre-estimating costs

**Concrete pricing examples:**

| Scenario | Tier | Provider Cost | Base Fee | 12% Markup | Agent Pays | Effective Margin |
|----------|------|---------------|----------|------------|------------|-----------------|
| Geocode "123 Main St" | T1 | $0.0001 | $0.0005 | $0.000012 | $0.000612 | 83.7% |
| Sentiment: 500 chars | T2 | $0.0008 | $0.0015 | $0.000096 | $0.002396 | 66.6% |
| Translate 200 words | T3 | $0.0024 | $0.0040 | $0.000288 | $0.006688 | 64.1% |
| Summarize 2K tokens | T4 | $0.0080 | $0.0080 | $0.000960 | $0.017060 | 53.1% |
| Generate 1024px image | T5 | $0.0200 | $0.0200 | $0.002400 | $0.042400 | 52.8% |
| Transcribe 5min audio | T4 | $0.0150 | $0.0080 | $0.001800 | $0.025000 | 40.0% |

**Blended target margin: 18-28%** (weighted toward T1/T2 volume, T4/T5 revenue).

---

### 1.3 Layer 3: Deterministic Composed Capabilities (Recipes)

**What it is:** Multi-step compiled recipe execution. Rhumb orchestrates across providers with step-level budgets, artifact capture, partial-failure handling, and deterministic replay.

**Pricing formula:**
```
agent_charge = recipe_execution_fee + sum(step_charges) + orchestration_premium
recipe_execution_fee = $0.01 to $0.25 (fixed, by recipe complexity class)
step_charges = each step billed at Layer 2 rates
orchestration_premium = 0.15 * sum(step_charges)
```

**Recipe complexity classes:**

| Class | Steps | Parallelism | Artifacts | Execution Fee |
|-------|-------|-------------|-----------|---------------|
| RC1 | 2-3 | Sequential only | None | $0.010 |
| RC2 | 4-6 | Sequential + simple branch | Files | $0.025 |
| RC3 | 7-12 | Parallel + fan-out | Files + structured | $0.060 |
| RC4 | 13-25 | Complex DAG | Files + DB + webhooks | $0.150 |
| RC5 | 26+ | Full orchestration | Any | $0.250 |

**Concrete recipe pricing examples:**

**Example A: Document Intelligence Pipeline (RC2)**
```
Recipe: extract_document_data
Steps:
  1. OCR PDF → text                    [T6: $0.035 * 1 page = $0.035]
  2. Extract entities from text        [T2: $0.002396]
  3. Classify document type            [T2: $0.002396]
  4. Structure into JSON schema        [T3: $0.006688]

Step total:     $0.046480
Orch premium:  +$0.006972 (15%)
Execution fee: +$0.025000 (RC2)
──────────────────────────────
Agent pays:     $0.078452
Provider cost:  $0.044280 (est.)
Rhumb margin:   $0.034172 (43.5%)
```

**Example B: Content Generation + Distribution (RC3)**
```
Recipe: generate_and_distribute_content
Steps:
  1. Research topic via web search     [T3: $0.006688 * 3 searches = $0.020064]
  2. Generate article (2K tokens)      [T4: $0.017060]
  3. Generate header image             [T5: $0.042400]
  4. Translate to Spanish              [T3: $0.006688]
  5. Translate to French               [T3: $0.006688]
  6. Post to CMS via webhook           [T1: $0.000612]
  7. Schedule social posts (3x)        [T1: $0.000612 * 3 = $0.001836]

Step total:     $0.095736
Orch premium:  +$0.014360 (15%)
Execution fee: +$0.060000 (RC3)
──────────────────────────────
Agent pays:     $0.170096
Provider cost:  $0.081372 (est.)
Rhumb margin:   $0.088724 (52.2%)
```

**Example C: Lead Enrichment Pipeline (RC2)**
```
Recipe: enrich_lead
Steps:
  1. Geocode company address           [T1: $0.000612]
  2. Lookup company by domain          [T2: $0.002396]
  3. Classify company size/industry    [T2: $0.002396]
  4. Generate personalized intro line  [T4: $0.017060]

Step total:     $0.022464
Orch premium:  +$0.003370 (15%)
Execution fee: +$0.025000 (RC2)
──────────────────────────────
Agent pays:     $0.050834
Provider cost:  $0.018800 (est.)
Rhumb margin:   $0.032034 (63.0%)
```

**Layer 3 target margin: 35-55%** — highest because orchestration logic, artifact management, and partial-failure handling represent genuine engineering value.

---

## 2. Cost Accounting Architecture

### 2.1 Cost Event Schema

Every billable action produces a `CostEvent`. These are the atomic units of the billing system.

```json
{
  "cost_event_id": "ce_01HZ9XK2M3P4Q5R6S7T8U9V0W1",
  "tenant_id": "ten_abc123",
  "agent_id": "agt_xyz789",
  "execution_id": "exec_01HZ9XK2M3P4Q5R6S7T8",
  "recipe_id": "rcp_document_extract_v2",
  "step_id": "step_003_classify",
  "step_name": "classify_document_type",
  "layer": 2,
  "capability": "document.classify",
  "provider_id": "openai",
  "provider_model": "gpt-4o-mini",
  "timestamp_start": "2026-03-30T20:44:00.123Z",
  "timestamp_end": "2026-03-30T20:44:00.891Z",
  "duration_ms": 768,
  "provider_cost": {
    "amount": 800,
    "currency": "USD",
    "unit": "microdollars",
    "input_tokens": 312,
    "output_tokens": 45,
    "rate_input_per_mtok": 150000,
    "rate_output_per_mtok": 600000
  },
  "rhumb_fee": {
    "base_fee": 1500,
    "markup_amount": 96,
    "markup_rate": 0.12,
    "tier": "T2",
    "total": 2396
  },
  "agent_charge": {
    "amount": 2396,
    "currency": "USD",
    "unit": "microdollars"
  },
  "payment_method": "prepaid_credits",
  "ledger_deduction_id": "ldg_deduct_01HZ9XK2",
  "status": "settled",
  "retry_count": 0,
  "fallback_triggered": false,
  "budget_checkpoint": {
    "budget_id": "bgt_agent_daily_001",
    "spent_before": 45200,
    "spent_after": 47596,
    "limit": 100000,
    "utilization_pct": 47.6
  },
  "tags": {
    "workflow": "lead_pipeline_v3",
    "session": "sess_abc",
    "environment": "production"
  }
}
```

### 2.2 Real-Time Cost Accumulation

Costs are accumulated in a multi-tier architecture:

**Tier 1: In-memory (Redis)** — Sub-millisecond reads for budget enforcement
```
Key: budget:{tenant_id}:{scope}:{budget_id}
TTL: budget.reset_interval + 1 hour buffer
Value: {spent_microdollars, last_event_ts, event_count}
```

**Tier 2: Supabase (PostgreSQL)** — Durable ledger, queryable history
```sql
CREATE TABLE cost_events (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  agent_id TEXT NOT NULL,
  execution_id TEXT,
  recipe_id TEXT,
  step_id TEXT,
  layer SMALLINT NOT NULL,
  provider_id TEXT NOT NULL,
  timestamp_start TIMESTAMPTZ NOT NULL,
  provider_cost_microdollars BIGINT NOT NULL,
  rhumb_fee_microdollars BIGINT NOT NULL,
  agent_charge_microdollars BIGINT NOT NULL,
  payment_method TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  raw JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX cost_events_tenant_time ON cost_events(tenant_id, timestamp_start DESC);
CREATE INDEX cost_events_agent ON cost_events(agent_id, timestamp_start DESC);
CREATE INDEX cost_events_execution ON cost_events(execution_id) WHERE execution_id IS NOT NULL;
```

**Tier 3: Aggregated daily rollups** — For invoicing and analytics
```sql
CREATE TABLE cost_daily_rollups (
  tenant_id TEXT NOT NULL,
  agent_id TEXT NOT NULL,
  date DATE NOT NULL,
  layer SMALLINT NOT NULL,
  call_count BIGINT DEFAULT 0,
  provider_cost_microdollars BIGINT DEFAULT 0,
  rhumb_fee_microdollars BIGINT DEFAULT 0,
  agent_charge_microdollars BIGINT DEFAULT 0,
  PRIMARY KEY (tenant_id, agent_id, date, layer)
);
```

### 2.3 Budget Checkpoint Design

Budget checkpoints enforce limits at three granularities: **pre-execution estimation**, **mid-execution step gates**, and **post-execution reconciliation**.

```json
{
  "budget_checkpoint": {
    "checkpoint_id": "chk_01HZ9XK2M3P4Q5",
    "execution_id": "exec_01HZ9XK2M3P4Q5R6S7T8",
    "recipe_id": "rcp_document_extract_v2",
    "step_index": 3,
    "step_id": "step_003_classify",
    "check_type": "pre_step",
    "timestamp": "2026-03-30T20:44:00.100Z",
    "budget_states": [
      {
        "budget_id": "bgt_agent_daily_001",
        "scope": "agent_daily",
        "limit_microdollars": 100000,
        "spent_microdollars": 45200,
        "reserved_microdollars": 5000,
        "available_microdollars": 49800,
        "utilization_pct": 50.2,
        "action_required": "none"
      },
      {
        "budget_id": "bgt_recipe_exec_001",
        "scope": "execution",
        "limit_microdollars": 500000,
        "spent_microdollars": 42804,
        "reserved_microdollars": 10000,
        "available_microdollars": 447196,
        "utilization_pct": 10.6,
        "action_required": "none"
      }
    ],
    "step_estimated_cost_microdollars": 2396,
    "decision": "proceed",
    "decision_latency_ms": 2
  }
}
```

**Checkpoint decision logic:**
```
IF available < step_estimated_cost → BLOCK (hard stop)
IF utilization_pct >= 90 → WARN (emit warning event, proceed if not hard limit)
IF utilization_pct >= 100 AND overdraft_enabled → OVERDRAFT (proceed, flag)
IF utilization_pct >= 100 AND NOT overdraft_enabled → BLOCK
```

### 2.4 Partial Execution Cost Attribution

When a recipe fails mid-execution, costs are attributed to completed steps only:

```json
{
  "partial_execution": {
    "execution_id": "exec_01HZ9FAILED",
    "recipe_id": "rcp_content_pipeline_v1",
    "status": "partial_failure",
    "failure_step": "step_004_translate_es",
    "failure_reason": "provider_timeout",
    "steps_completed": 3,
    "steps_total": 7,
    "cost_attribution": {
      "step_001_research": {"status": "completed", "charged_microdollars": 20064},
      "step_002_generate": {"status": "completed", "charged_microdollars": 17060},
      "step_003_image": {"status": "completed", "charged_microdollars": 42400},
      "step_004_translate_es": {"status": "failed", "charged_microdollars": 0, "refund_eligible": false},
      "step_005_translate_fr": {"status": "skipped", "charged_microdollars": 0},
      "step_006_cms_post": {"status": "skipped", "charged_microdollars": 0},
      "step_007_social": {"status": "skipped", "charged_microdollars": 0}
    },
    "total_charged_microdollars": 79524,
    "execution_fee_charged_microdollars": 25000,
    "orchestration_premium_charged_microdollars": 11929,
    "refund_policy": "completed_steps_non_refundable",
    "partial_completion_pct": 42.9
  }
}
```

**Rule:** Failed steps are not charged. Completed steps are charged at full rate. Execution fee is prorated by completion percentage for failures at < 50% completion; full fee for failures at ≥ 50% completion.

### 2.5 Cost Reconciliation with Provider Invoices

Monthly reconciliation process:

1. **Export Rhumb cost events** by provider, by month
2. **Request provider usage reports** (OpenAI: usage endpoint; Twilio: usage records API; etc.)
3. **Reconcile at transaction level** where provider exposes per-request IDs; at aggregate level otherwise
4. **Variance tolerance:** ±2% acceptable (rounding, timing differences)
5. **Variance >2%:** Investigate — usually clock skew, retry double-billing, or provider-side adjustments
6. **Adjustments:** If Rhumb over-charged provider costs → issue credit to tenant. If Rhumb under-charged → absorb (do not back-bill).

```json
{
  "reconciliation_run": {
    "run_id": "recon_2026_03",
    "period": "2026-03",
    "provider_id": "openai",
    "rhumb_recorded_cost_usd": 1842.33,
    "provider_invoice_usd": 1856.41,
    "variance_usd": 14.08,
    "variance_pct": 0.76,
    "status": "within_tolerance",
    "transaction_count": 284719,
    "matched_count": 284502,
    "unmatched_count": 217,
    "adjustment_issued": false
  }
}
```

---

## 3. Billing Pipeline Design

### 3.1 Prepaid Credits (Stripe)

**Purchase flow:**
```
1. Agent/user initiates credit purchase → POST /billing/credits/purchase
2. Rhumb creates Stripe PaymentIntent for credit amount
3. Stripe returns client_secret → agent completes payment (card/ACH)
4. Stripe webhook: payment_intent.succeeded → Rhumb credits ledger
5. Ledger entry created with status=active, expires_at=purchase_date+12months
6. Agent receives credit confirmation with new balance
```

**Credit ledger schema:**
```json
{
  "ledger_entry": {
    "entry_id": "ldg_01HZ9XK2M3P4Q5R6",
    "tenant_id": "ten_abc123",
    "type": "credit_purchase",
    "amount_microdollars": 10000000000,
    "currency": "USD",
    "balance_before": 2500000000,
    "balance_after": 12500000000,
    "stripe_payment_intent_id": "pi_3OzK2LJKa1b2c3d4",
    "stripe_charge_id": "ch_3OzK2LJKa1b2c3d4",
    "amount_paid_usd": 10.00,
    "processing_fee_usd": 0.39,
    "net_amount_usd": 9.61,
    "created_at": "2026-03-30T20:44:00.000Z",
    "expires_at": "2027-03-30T20:44:00.000Z",
    "status": "active",
    "description": "Credit purchase — $10.00 package",
    "metadata": {
      "package_id": "pkg_10usd",
      "bonus_pct": 0,
      "promo_code": null
    }
  }
}
```

**Deduction mechanics:**
```json
{
  "ledger_entry": {
    "entry_id": "ldg_01HZ9DEDUCT001",
    "tenant_id": "ten_abc123",
    "type": "execution_charge",
    "amount_microdollars": -2396,
    "balance_before": 12500000000,
    "balance_after": 12497603604,
    "cost_event_id": "ce_01HZ9XK2M3P4Q5R6S7T8U9V0W1",
    "created_at": "2026-03-30T20:44:00.891Z",
    "status": "settled",
    "description": "Layer 2 / document.classify / openai:gpt-4o-mini"
  }
}
```

**Credit balance logic:**
- Credits tracked as integer microdollars (1 USD = 1,000,000,000 microdollars) to avoid floating-point errors
- FIFO expiry: oldest credits consumed first
- Negative balance only permitted if overdraft enabled
- Balance cached in Redis, DB is the source of truth; Redis rebuilt from DB on cache miss

**Credit packages (v1):**

| Package | Price | Credits | Bonus |
|---------|-------|---------|-------|
| Starter | $10 | $10 | — |
| Growth | $50 | $50 | — |
| Scale | $200 | $215 | +7.5% |
| Pro | $500 | $550 | +10% |
| Enterprise | Custom | Custom | Negotiated |

---

### 3.2 x402 USDC Payments

Described in full in Section 11.

---

### 3.3 Stripe Subscriptions (v1: Deferred)

**v1 decision:** No subscription tiers at launch. Reasoning:
- Usage-based billing aligns with agent usage patterns (bursty, unpredictable)
- Subscriptions add committed revenue but complicate proration, upgrades, and the prepaid credit interaction
- Revisit when ARR > $50K and we see clear demand for committed spend

**Deferred design (for reference):**

| Tier | Monthly | Included Credits | Overage Rate |
|------|---------|-----------------|--------------|
| Dev | $29/mo | $25 credits | Standard |
| Growth | $149/mo | $150 credits | -5% |
| Scale | $499/mo | $550 credits | -10% |
| Enterprise | Custom | Custom | Negotiated |

---

### 3.4 Enterprise Invoicing (v1: Basic; v2: Full)

**v1:** Manual invoicing for enterprise pilots. Rhumb generates CSV usage report + sends to AP contact. Net-30.

**v2 design (target Q3 2026):**

```json
{
  "invoice": {
    "invoice_id": "inv_2026_03_ten_enterprise001",
    "tenant_id": "ten_enterprise001",
    "period_start": "2026-03-01T00:00:00Z",
    "period_end": "2026-03-31T23:59:59Z",
    "generated_at": "2026-04-01T02:00:00Z",
    "due_date": "2026-05-01",
    "payment_terms": "net_30",
    "line_items": [
      {
        "description": "Layer 1 Raw Provider Access",
        "call_count": 184201,
        "amount_usd": 36.84
      },
      {
        "description": "Layer 2 Single Capability Delivery",
        "call_count": 92441,
        "amount_usd": 892.33
      },
      {
        "description": "Layer 3 Recipe Executions",
        "execution_count": 3821,
        "amount_usd": 612.87
      },
      {
        "description": "Volume Discount (10%)",
        "amount_usd": -154.20
      }
    ],
    "subtotal_usd": 1387.84,
    "tax_usd": 0.00,
    "total_usd": 1387.84,
    "currency": "USD",
    "status": "sent",
    "stripe_invoice_id": "in_3OzK2LJKa1b2c3d4"
  }
}
```

**Usage report format:** Monthly CSV + JSON attachment with per-agent, per-capability, per-day breakdown. Delivered via email and accessible via `/billing/invoices/{invoice_id}/usage-report`.

---

### 3.5 Billing Event Stream

All billing events published to a durable event stream for downstream processing (audit, analytics, reconciliation):

```json
{
  "billing_event": {
    "event_id": "bev_01HZ9XK2M3P4Q5R6",
    "event_type": "charge.settled",
    "tenant_id": "ten_abc123",
    "agent_id": "agt_xyz789",
    "timestamp": "2026-03-30T20:44:00.891Z",
    "payload": {
      "cost_event_id": "ce_01HZ9XK2M3P4Q5R6S7T8U9V0W1",
      "amount_microdollars": 2396,
      "layer": 2,
      "provider_id": "openai",
      "capability": "document.classify"
    },
    "schema_version": "1.0"
  }
}
```

Event types: `charge.initiated`, `charge.settled`, `charge.failed`, `charge.refunded`, `credit.purchased`, `credit.expired`, `budget.warning`, `budget.exhausted`, `overdraft.triggered`, `invoice.generated`, `invoice.paid`.

---

## 4. Margin Analysis Per Layer

### 4.1 Layer 1 Margin Analysis

**Sources of margin:**
- Infrastructure fee (8% + $0.0002 floor)
- Volume rebates from providers negotiated at scale (deferred until >$50K/mo provider spend)
- Credential management value (avoiding per-key cost for agents)

**Target gross margin: 8-12%**

**Risk factors:**
| Risk | Impact | Mitigation |
|------|--------|-----------|
| Provider price decreases | Margin compression if not passed through | Proactive repricing quarterly |
| Credit card processing fees (2.9% + $0.30) | Eats 3%+ of small purchases | Minimum purchase floor ($5), ACH push for enterprise |
| Provider outage → fallback to pricier provider | Rhumb absorbs cost difference at Layer 1 | Only fall back at Layer 2+; Layer 1 returns error |
| Volume rebates not materializing | No margin improvement at scale | Accept thin L1 margin; volume game |

**Break-even at scale:** Layer 1 becomes profitable with >$30K/mo provider cost flowing through (at 10% margin = $3K/mo gross).

---

### 4.2 Layer 2 Margin Analysis

**Sources of margin:**
- Tier base fee (covers routing engine, schema normalization, contract maintenance)
- 12% reliability markup (covers retries, fallback, SLA guarantee)
- Provider arbitrage (selecting cheaper provider while charging stable price)

**Target gross margin: 18-28%**

**Concrete arbitrage example:**
```
Capability: sentiment.analyze
Provider A (OpenAI): $0.0008 per call
Provider B (Anthropic): $0.0010 per call
Rhumb charges: $0.0015 + $0.0008 * 1.12 = $0.002396 (routes to Provider A)
Arbitrage savings: $0.0002/call retained by Rhumb when routing to cheaper provider
→ Marginal margin from arbitrage: 8.4% on top of base margin
```

**Risk factors:**
| Risk | Impact | Mitigation |
|------|--------|-----------|
| Provider prices converge | Arbitrage margin disappears | Tier base fee provides floor margin regardless |
| Retry cost spikes (provider instability) | Increases provider cost without increasing agent charge | SLA budget per capability; cap retries at 3 |
| Schema normalization complexity | Engineering cost not reflected in price | Tier assignment considers normalization complexity |
| Race to bottom by competitors | Margin pressure | Routing intelligence and stability as differentiation |

---

### 4.3 Layer 3 Margin Analysis

**Sources of margin:**
- Recipe execution fee ($0.01-$0.25 fixed per execution)
- Orchestration premium (15% of step costs)
- Compilation and caching value (agents don't re-engineer orchestration)
- Artifact management and storage

**Target gross margin: 35-55%**

**Margin is highest at Layer 3 because:**
1. Orchestration logic represents weeks of engineering value
2. Partial-failure handling is complex infrastructure
3. Deterministic replay is a unique promise
4. Step-level budget enforcement is irreplaceable for autonomous agents
5. Artifact capture solves a real problem (not just a pass-through)

**Risk factors:**
| Risk | Impact | Mitigation |
|------|--------|-----------|
| Agents bypass Layer 3 for simple recipes | Revenue stays at L2 | Keep L3 clearly differentiated for multi-step |
| Recipe compilation maintenance cost | Engineering overhead | Invest in recipe DSL that self-maintains |
| Orchestration bugs cause over-charging | Refund liability + trust damage | Comprehensive test coverage; idempotent step execution |
| Provider latency in sequential recipes | Poor UX reduces adoption | Parallel step execution where possible; async recipes |

---

## 5. Provider Cost Management

### 5.1 Volume Milestone Tracking

Rhumb tracks provider spend monthly and triggers negotiation workflows at thresholds:

```json
{
  "provider_volume_tracker": {
    "provider_id": "openai",
    "current_month_spend_usd": 8420.33,
    "trailing_3mo_avg_usd": 6200.00,
    "milestones": [
      {"threshold_usd": 5000, "status": "crossed", "crossed_at": "2026-03-15", "action": "request_startup_credits"},
      {"threshold_usd": 10000, "status": "approaching", "estimated_eta": "2026-04-05", "action": "schedule_account_review"},
      {"threshold_usd": 25000, "status": "future", "action": "negotiate_volume_discount"},
      {"threshold_usd": 100000, "status": "future", "action": "negotiate_enterprise_agreement"}
    ],
    "current_discount_pct": 0,
    "negotiated_rate_expires": null
  }
}
```

**Negotiation playbook:**
- $5K/mo: Request startup credits program (OpenAI, Anthropic both offer this)
- $10K/mo: Schedule CSM call, request 5-10% volume discount commitment
- $25K/mo: Negotiate annual committed spend for 15-20% discount
- $100K/mo: Enterprise agreement, SLA, dedicated support

### 5.2 Provider Cost Change Detection

```json
{
  "provider_price_change": {
    "provider_id": "anthropic",
    "model_id": "claude-3-5-haiku",
    "change_type": "decrease",
    "old_price_input_per_mtok": 800,
    "new_price_input_per_mtok": 600,
    "old_price_output_per_mtok": 2400,
    "new_price_output_per_mtok": 1200,
    "effective_date": "2026-04-01",
    "detected_at": "2026-03-30T18:00:00Z",
    "source": "provider_api_pricing_endpoint",
    "impact_analysis": {
      "affected_capabilities": 12,
      "monthly_call_volume": 284000,
      "monthly_cost_change_usd": -142.00,
      "margin_impact_pct": "+1.8%",
      "action": "reprice_capabilities_within_7_days"
    }
  }
}
```

**Response policy:**
- Provider price **increase** >5%: Reprice within 14 days; notify affected agents 7 days before
- Provider price **decrease** >5%: Pass 50% of savings to agents within 30 days; retain 50% as margin improvement
- Price change <5%: Absorb until quarterly repricing cycle

**Detection mechanism:** Nightly job polls provider pricing APIs (or scrapes pricing pages where APIs unavailable). Alert if any capability cost changes >3%.

### 5.3 Multi-Provider Arbitrage

When multiple providers can fulfill the same capability:

```
arbitrage_score(provider) = 
  (provider_cost_rank * 0.40) + 
  (latency_rank * 0.25) + 
  (quality_rank * 0.25) + 
  (reliability_rank * 0.10)

where:
  cost_rank: 1=cheapest, N=most expensive (normalized 0-1)
  latency_rank: 1=fastest, normalized 0-1
  quality_rank: from AN Score, normalized 0-1
  reliability_rank: uptime * success_rate, normalized 0-1
```

Rhumb routes to the highest-scored provider. When cost is equal within 10%, quality and latency break the tie. Agents can inspect routing decisions via `/executions/{id}/routing-trace`.

### 5.4 Cost Optimization Algorithms

**v1 (shipped):** Simple cost-minimizing routing with quality floor (don't route to provider below AN Score threshold for capability).

**v2 (deferred):** Predictive routing based on:
- Time-of-day pricing patterns (some providers cheaper during off-peak)
- Batch accumulation (batch 50 small requests → 1 API call where provider supports it)
- Caching layer (deduplicate identical requests within 60-second window for deterministic capabilities)
- Speculative prefetch (pre-execute likely next steps while current step completes)

---

## 6. Budget Enforcement

### 6.1 Budget Definition Schema

```json
{
  "budget": {
    "budget_id": "bgt_agent_daily_001",
    "tenant_id": "ten_abc123",
    "agent_id": "agt_xyz789",
    "name": "Agent Daily Limit",
    "scope": "agent",
    "granularity": "daily",
    "limit_microdollars": 100000000,
    "reset_cron": "0 0 * * *",
    "reset_timezone": "UTC",
    "currency": "USD",
    "policy": {
      "at_80_pct": "warn",
      "at_90_pct": "warn_and_throttle",
      "at_100_pct": "hard_stop",
      "overdraft_enabled": false,
      "overdraft_limit_microdollars": 0
    },
    "notification_channels": ["webhook:https://agent.example.com/budget-alert", "email:ops@example.com"],
    "created_at": "2026-03-01T00:00:00Z",
    "active": true,
    "layer_overrides": {
      "1": {"limit_microdollars": 20000000, "policy_override": null},
      "3": {"limit_microdollars": 50000000, "policy_override": {"at_100_pct": "soft_stop"}}
    },
    "capability_overrides": {
      "image.generate": {"limit_microdollars": 5000000}
    }
  }
}
```

**Budget hierarchy:**
```
Organization budget
  └── Tenant budget
        └── Agent budget (most common)
              ├── Capability budget (optional override)
              └── Recipe budget (optional override)
```

When multiple budgets apply, the most restrictive wins. All budgets are checked before every execution.

### 6.2 Real-Time Enforcement Architecture

```
Request → Auth → Budget Check (Redis) → Execute → Deduct (Redis + DB) → Respond
                        ↑                                    ↓
                 [<2ms latency]                    [async DB write, ~50ms]
```

**Budget check pseudocode:**
```python
def check_budget(agent_id, estimated_cost_microdollars):
    budgets = get_applicable_budgets(agent_id)  # from Redis
    for budget in budgets:
        spent = redis.get(f"budget:{budget.id}:spent")
        available = budget.limit - spent - budget.reserved
        
        if estimated_cost > available:
            if budget.overdraft_enabled and spent < (budget.limit + budget.overdraft_limit):
                return BudgetDecision(action="overdraft", budget_id=budget.id)
            else:
                return BudgetDecision(action="block", budget_id=budget.id, available=available)
        
        utilization = (spent + estimated_cost) / budget.limit
        if utilization >= 0.90:
            return BudgetDecision(action="warn_and_proceed", budget_id=budget.id, utilization=utilization)
    
    return BudgetDecision(action="proceed")
```

**Reservation pattern:** For Layer 3 recipes, Rhumb reserves the maximum estimated cost at recipe start, then releases unused reservation at completion. Prevents over-commitment mid-execution.

### 6.3 Pre-Execution Cost Estimation

```json
{
  "cost_estimate": {
    "estimate_id": "est_01HZ9XK2M3P4Q5",
    "requested_at": "2026-03-30T20:43:59.000Z",
    "capability": "recipe:rcp_content_pipeline_v1",
    "input_summary": {"word_count": 500, "target_languages": 2},
    "estimates": {
      "minimum_usd": 0.145,
      "expected_usd": 0.170,
      "maximum_usd": 0.220
    },
    "breakdown": [
      {"step": "step_001_research", "expected_usd": 0.020, "confidence": "high"},
      {"step": "step_002_generate", "expected_usd": 0.017, "confidence": "medium"},
      {"step": "step_003_image", "expected_usd": 0.042, "confidence": "high"},
      {"step": "step_004_translate_es", "expected_usd": 0.007, "confidence": "high"},
      {"step": "step_005_translate_fr", "expected_usd": 0.007, "confidence": "high"},
      {"step": "step_006_cms_post", "expected_usd": 0.001, "confidence": "high"},
      {"step": "step_007_social", "expected_usd": 0.002, "confidence": "high"},
      {"orchestration_premium": 0.014, "confidence": "computed"},
      {"execution_fee": 0.060, "confidence": "fixed"}
    ],
    "estimate_valid_seconds": 300,
    "confidence_overall": "medium"
  }
}
```

Agents can call `/billing/estimate` before execution to check affordability against their budget without committing.

### 6.4 Budget Exhaustion Handling

| Mode | Behavior | Use Case |
|------|----------|---------|
| `hard_stop` | Execution blocked immediately; error returned | Default for most agents |
| `soft_stop` | Warning returned, execution proceeds once, then blocked | Human-in-the-loop workflows |
| `overdraft` | Execution proceeds up to overdraft limit; flags account | Trusted enterprise agents |
| `queue` | Request queued until budget resets (v2 deferred) | Low-priority batch jobs |

Error response on hard stop:
```json
{
  "error": {
    "code": "BUDGET_EXHAUSTED",
    "message": "Agent daily budget exhausted. Available: $0.00234. Required: $0.00240.",
    "budget_id": "bgt_agent_daily_001",
    "budget_scope": "agent_daily",
    "available_microdollars": 2340,
    "required_microdollars": 2396,
    "resets_at": "2026-03-31T00:00:00Z",
    "upgrade_url": "https://rhumb.run/billing/credits"
  }
}
```

---

## 7. Overdraft and Credit Management

### 7.1 Grace Period Design

Default grace period: **none** for prepaid. Overdraft is opt-in and risk-scored.

For enterprise accounts on net-30:
- Soft warning at 90% of credit line
- Hard block at 110% (10% grace)
- Grace period: 48 hours to add credits before hard block kicks in

```json
{
  "grace_period": {
    "account_id": "ten_enterprise001",
    "trigger_event": "credit_line_exceeded",
    "grace_start": "2026-03-30T20:00:00Z",
    "grace_end": "2026-04-01T20:00:00Z",
    "grace_amount_microdollars": 5000000000,
    "usage_during_grace_microdollars": 1200000000,
    "notifications_sent": ["email:2026-03-30T20:00:00Z", "webhook:2026-03-30T20:00:00Z"],
    "status": "active",
    "resolution_required_by": "2026-04-01T20:00:00Z"
  }
}
```

### 7.2 Overdraft Limits

Overdraft limits are set per-account based on risk score:

| Risk Tier | Overdraft Limit | Conditions |
|-----------|----------------|------------|
| Tier 0 (new) | $0 | No history |
| Tier 1 (established) | $5 | >30 days, >$50 lifetime spend |
| Tier 2 (trusted) | $25 | >90 days, >$500 lifetime, <1% failure rate |
| Tier 3 (enterprise) | $500+ | Contract in place |

### 7.3 Risk Scoring

```json
{
  "agent_risk_score": {
    "agent_id": "agt_xyz789",
    "scored_at": "2026-03-30T00:00:00Z",
    "score": 72,
    "tier": 2,
    "factors": {
      "account_age_days": {"value": 94, "score": 20, "weight": 0.20},
      "lifetime_spend_usd": {"value": 842.33, "score": 20, "weight": 0.20},
      "payment_failure_rate": {"value": 0.002, "score": 18, "weight": 0.25},
      "chargeback_count": {"value": 0, "score": 10, "weight": 0.15},
      "avg_monthly_spend_consistency": {"value": 0.87, "score": 4, "weight": 0.20}
    },
    "overdraft_limit_usd": 25,
    "review_scheduled": false
  }
}
```

### 7.4 Collection Mechanisms

1. **Prepaid accounts:** Execution blocked when balance goes negative beyond overdraft. No collection needed — money was collected upfront.
2. **Enterprise net-30:** Standard AR process. Rhumb uses Stripe Invoicing with auto-collection attempt.
3. **Disputed charges:** Must be raised within 30 days. Rhumb provides full audit log per-execution.
4. **Fraud response:** Immediate account suspension, execution halt, preserve audit trail.

---

## 8. Revenue Recognition

### 8.1 Recognition Policy

**ASC 606 framework:** Revenue recognized when performance obligation is satisfied.

| Revenue Type | Recognition Trigger | ASC 606 Basis |
|-------------|--------------------|-|
| Credit purchase | NOT at purchase | Credits are advance payments (deferred revenue liability) |
| Layer 1 execution | On successful API response | Performance obligation: proxied the call |
| Layer 2 execution | On delivery of normalized output | Performance obligation: delivered the capability |
| Layer 3 completion | On recipe completion or partial attribution | Performance obligation: executed the workflow |
| Enterprise subscription (deferred) | Ratably over subscription period | Time-based performance obligation |

### 8.2 Deferred Revenue Liability

```json
{
  "deferred_revenue": {
    "tenant_id": "ten_abc123",
    "balance_microdollars": 10000000000,
    "usd_equivalent": 10.00,
    "components": [
      {
        "purchase_id": "ldg_01HZ9XK2M3P4Q5R6",
        "purchased_at": "2026-03-30T20:44:00Z",
        "original_amount_usd": 10.00,
        "remaining_amount_usd": 10.00,
        "expires_at": "2027-03-30T20:44:00Z"
      }
    ],
    "as_of": "2026-03-30T20:44:00Z"
  }
}
```

Revenue is recognized credit by credit as executions consume the balance.

### 8.3 Partial Execution Recognition

For Layer 3 partial failures:
- Completed steps: Revenue recognized on step completion
- Failed step: No revenue recognized for that step
- Execution fee: Prorated (see Section 2.4 rules)
- Orchestration premium: Recognized on completed steps only

### 8.4 Refund Handling

**Refund policy:**
- Layer 1: Refund only if Rhumb's infrastructure caused the failure (not provider-side). Provider-side failures → no refund (Rhumb passed through faithfully).
- Layer 2: Refund if Rhumb failed to deliver normalized output after 3 retry attempts.
- Layer 3: No refund for completed steps. Full execution fee refunded if recipe fails at step 1.

```json
{
  "refund": {
    "refund_id": "ref_01HZ9XK2M3P4Q5",
    "cost_event_id": "ce_01HZ9FAILED",
    "tenant_id": "ten_abc123",
    "reason": "rhumb_infrastructure_failure",
    "amount_microdollars": 2396,
    "credit_method": "prepaid_credit_restoration",
    "ledger_entry_id": "ldg_01HZ9REFUND001",
    "created_at": "2026-03-30T20:50:00Z",
    "status": "settled",
    "revenue_reversal": {
      "original_recognition_date": "2026-03-30T20:44:00Z",
      "reversal_date": "2026-03-30T20:50:00Z",
      "amount_usd": 0.002396
    }
  }
}
```

---

## 9. Scaling Economics

### 9.1 Assumptions

| Assumption | Value |
|------------|-------|
| Average Layer 2 call charge | $0.008 |
| Layer 1 / Layer 2 / Layer 3 mix | 20% / 65% / 15% |
| Average Layer 1 call charge | $0.0005 |
| Average Layer 3 recipe charge | $0.085 |
| Calls per active agent per day | 150 |
| Recipe executions per active agent per day | 8 |
| Infrastructure base cost (Railway + Supabase) | $400/mo |
| Redis + CDN | $80/mo |
| Stripe processing (2.9% + $0.30 per purchase) | ~3.5% of revenue |
| Payment method mix | 70% prepaid credit, 20% enterprise, 10% x402 |

### 9.2 100 Agents

**Scale:** 100 active agents, ~15,000 Layer 2 calls/day, ~800 recipe executions/day

| Metric | Value |
|--------|-------|
| Daily L2 revenue | $120.00 |
| Daily L3 revenue | $68.00 |
| Daily L1 revenue | $1.50 |
| **Daily gross revenue** | **$189.50** |
| **Monthly gross revenue** | **$5,685** |
| Provider costs (est.) | $3,700/mo |
| Stripe fees | $200/mo |
| Infrastructure | $480/mo |
| **Monthly gross margin** | **$1,305 (23%)** |
| **Break-even status** | Below ($1,305 vs ~$3K ops cost) |

**Conclusion at 100 agents:** Pre-revenue-break-even. Rhumb needs ~250 agents to cover fully loaded ops costs. Key lever: increase calls/agent/day (onboard higher-usage agents).

### 9.3 1,000 Agents

**Scale:** 1,000 active agents, ~150,000 Layer 2 calls/day, ~8,000 recipe executions/day

| Metric | Value |
|--------|-------|
| Monthly gross revenue | $56,850 |
| Provider costs | $37,000/mo |
| Stripe fees | $1,990/mo |
| Infrastructure | $1,200/mo (scaled) |
| Provider volume discounts (est. 5%) | -$1,850/mo savings |
| **Monthly gross margin** | **$18,510 (32.6%)** |
| **Annual run rate** | **$222,120** |

**Infrastructure scaling:** At 1K agents, add Redis cluster ($200/mo), second Railway service ($300/mo), read replica ($200/mo). Total infra: ~$1,200/mo.

**Provider negotiations:** At ~$37K/mo provider spend, credible ask for 5-10% volume discount with top 2-3 providers. $1,850-$3,700/mo margin improvement.

### 9.4 10,000 Agents

**Scale:** 10,000 active agents, ~1.5M Layer 2 calls/day, ~80,000 recipe executions/day

| Metric | Value |
|--------|-------|
| Monthly gross revenue | $568,500 |
| Provider costs | $370,000/mo |
| Provider volume discounts (est. 12%) | -$44,400/mo savings |
| Stripe fees | $19,900/mo |
| Infrastructure | $8,000/mo (dedicated) |
| **Monthly gross margin** | **$214,600 (37.8%)** |
| **Annual run rate** | **$6.8M** |

**Infrastructure at 10K:** Dedicated Railway plan, Supabase Scale, dedicated Redis cluster, CDN for static assets. Consider AWS/GCP direct for some workloads to reduce Railway margin.

**Enterprise tier unlocks at 10K:** Dedicated infrastructure offering ($2,500-$10,000/mo MRR), SLA guarantees, private recipe libraries, custom provider integrations.

**Key insight:** Margin improves from 23% → 33% → 38% as volume grows, driven by:
1. Provider volume discounts
2. Infrastructure fixed cost amortization
3. Better routing intelligence reducing retry overhead
4. Recipe compilation caching reducing orchestration cost per execution

---

## 10. Float Management and Regulatory Considerations

### 10.1 Float from Prepaid Credits

**Float definition:** Unearned credit balances sitting in Rhumb's payment processor represent a float liability.

| Scale | Est. Average Float | Annual Interest (4% rate) | Float Revenue |
|-------|-------------------|--------------------------|---------------|
| 100 agents | $2,000 | $80/yr | Negligible |
| 1K agents | $20,000 | $800/yr | Minor |
| 10K agents | $200,000 | $8,000/yr | Meaningful |
| 100K agents | $2,000,000 | $80,000/yr | Material |

**v1 float policy:** Float sits in Stripe balance. No active management. Interest not a material consideration until >$100K float.

**v2 (deferred, >$100K float):** Sweep idle float to money market account via Stripe Treasury (4.xx% annualized). Regulatory review required.

### 10.2 Money Transmission Considerations

**Current structure (prepaid credits):**
- Credits are a prepayment for services, not stored value for transfer
- Rhumb is the merchant; credits can only be redeemed against Rhumb services
- Non-transferable credits → **not** money transmission in most US jurisdictions
- Expiration policy (12 months) must be disclosed clearly (some states require no expiry or longer)

**State-specific risks:**
- California: Unclaimed property law — unclaimed credits >3 years may need to be escheated
- New York: Similar unclaimed property requirements
- EU: PSD2 considerations if serving EU customers (v2 concern)

**v1 safe harbor:** US-only focus, non-transferable credits, clear expiry disclosure, <$5M float. No money transmitter license required under this structure.

**x402 USDC:** See Section 11.4.

### 10.3 KYC/AML at Different Volumes

| Volume Threshold | KYC Requirement |
|-----------------|----------------|
| <$3,000 lifetime | None (self-serve, email only) |
| $3,000-$10,000 lifetime | Basic: name, email, company |
| >$10,000 lifetime | Enhanced: business verification, Stripe Identity |
| Enterprise contract | Full business KYC + AML screening |
| x402 USDC >$10K/mo | Enhanced due diligence, transaction monitoring |

**v1:** Stripe handles KYC for card transactions. x402 requires Rhumb-side address screening. Use Chainalysis or similar for basic wallet screening above $1K/mo USDC volume.

---

## 11. x402 Integration Design

### 11.1 Overview

x402 is an HTTP-native payment protocol where clients send USDC payments in the HTTP request itself. Rhumb supports x402 as a first-class payment method for permissionless, key-based agent billing.

**x402 value proposition for Rhumb:**
- Agents can pay per-call without pre-registering or holding prepaid credits
- Enables truly autonomous payment flow: agent obtains USDC, calls Rhumb, pays inline
- No Stripe account required — critical for anonymous/pseudonymous agent deployments
- Natural fit for Layer 1 "escape hatch" use case: low friction, direct

### 11.2 Per-Call Payment Flow (Layer 1 / Layer 2)

```
1. Agent sends request to Rhumb without payment
   → Rhumb responds: 402 Payment Required
   
2. 402 response body:
{
  "x402Version": 1,
  "accepts": [
    {
      "scheme": "exact",
      "network": "base",
      "maxAmountRequired": "2396",
      "resource": "https://resolve.rhumb.run/v1/capability/document.classify",
      "description": "Layer 2 / document.classify / estimated 2396 microdollars",
      "mimeType": "application/json",
      "payTo": "0xRhumb_Settlement_Address",
      "maxTimeoutSeconds": 300,
      "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
      "extra": {
        "rhumb_estimate_id": "est_01HZ9XK2M3P4Q5",
        "rhumb_capability": "document.classify",
        "rhumb_layer": 2
      }
    }
  ],
  "error": "Payment required"
}

3. Agent creates USDC transaction on Base L2:
   - Amount: 2396 (in microdollars, sent as USDC microunits)
   - To: Rhumb settlement address
   - Calldata: encodes resource URL + request hash

4. Agent re-sends request with X-PAYMENT header:
   X-PAYMENT: <base64-encoded SignedPayment JSON>

5. Rhumb verifies payment:
   a. Decode SignedPayment
   b. Check signature against agent's known wallet
   c. Verify tx on Base (via cached RPC or light-client proof)
   d. Check amount >= required (never block if agent overpays)
   e. Check nonce not replayed
   f. Mark payment as consumed in Redis (idempotency key: tx_hash)

6. Execute capability
7. Return result with X-PAYMENT-RESPONSE header
```

### 11.3 SignedPayment Schema

```json
{
  "x402Version": 1,
  "scheme": "exact",
  "network": "base",
  "payload": {
    "from": "0xAgentWalletAddress",
    "to": "0xRhumb_Settlement_Address",
    "value": "2396",
    "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "chainId": 8453,
    "validAfter": "1743381840",
    "validBefore": "1743382140",
    "nonce": "0x7f3a1b2c4d5e6f7a8b9c0d1e2f3a4b5c",
    "authorization": "<EIP-712-signature>"
  }
}
```

**Payment verification Redis cache:**
```
Key: x402:consumed:{tx_hash}
Value: 1
TTL: 7 days (prevents replay; tx finality is permanent but cache provides fast-path)
```

### 11.4 Batched Payment Flow (Layer 3 Recipes)

For multi-step recipes, two options:

**Option A (v1 — default):** Single upfront payment for estimated total
```
1. Agent requests recipe cost estimate → returns max_cost_usdc
2. Agent pays estimated max in single x402 transaction
3. Rhumb executes recipe steps, tracking actual costs
4. On completion: if actual < estimated → return difference as x402 payment back to agent wallet
5. If actual > estimated (rare): recipe marked as underpaid; Rhumb absorbs difference up to 10%
```

**Option B (v2 — deferred):** Per-step micro-payments via payment channel
```
1. Agent opens ERC-20 payment channel with Rhumb
2. Each step: agent signs off-chain update increasing channel balance
3. Recipe completion: Rhumb closes channel and settles net amount on-chain
4. Gas cost: 1 on-chain tx regardless of step count
```

Option A is simpler and sufficient for v1. Option B required for recipes >$0.50 where gas cost of upfront payment becomes material.

### 11.5 Payment Verification Latency

| Verification Method | Latency | Use Case |
|--------------------|---------|---------|
| Redis cache hit | <1ms | Replay detection |
| Base finality (soft confirmation) | 2-3s | Normal verification |
| Base finality (hard confirmation, 2 blocks) | 4-6s | High-value calls (>$1) |
| Fallback RPC poll | 100-500ms | When light-client unavailable |

**Verification SLA:** Payment verification must complete in <5 seconds to not degrade Rhumb's execution SLA.

**Optimization:** Maintain a warm RPC connection to Base L2 via Coinbase CDP or Alchemy. Cache recent block headers for light-client verification. For calls <$0.10, accept soft confirmation (2s); for calls >$1, require 2-block confirmation (6s).

### 11.6 Failed Payment Handling

```json
{
  "payment_failure": {
    "type": "insufficient_funds",
    "response": {
      "status": 402,
      "error": "PAYMENT_INSUFFICIENT",
      "message": "Payment amount 2000 microdollars below required 2396 microdollars.",
      "required": "2396",
      "received": "2000",
      "shortfall": "396",
      "retry_with_amount": "2396"
    }
  }
}

{
  "payment_failure": {
    "type": "replay_detected",
    "response": {
      "status": 402,
      "error": "PAYMENT_REPLAYED",
      "message": "Transaction hash already consumed.",
      "tx_hash": "0xabcdef..."
    }
  }
}

{
  "payment_failure": {
    "type": "verification_timeout",
    "response": {
      "status": 402,
      "error": "PAYMENT_UNVERIFIABLE",
      "message": "Could not verify payment within 5 seconds. Retry or use prepaid credits.",
      "fallback_url": "https://resolve.rhumb.run/billing/credits"
    }
  }
}
```

### 11.7 Gas Cost Considerations

**Base L2 economics (as of 2026-03):**
- Average transaction gas cost: ~$0.00005 - $0.0005 (0.005-0.05 cents)
- Gas cost as % of typical Rhumb call ($0.008): 0.006% to 0.6%
- Gas cost is borne by the agent (they submit the tx)
- Rhumb has zero gas exposure on Base L2 for payment receipt

**Rhumb gas exposure:** Only on Option B payment channel closings (v2). v1 has no gas exposure.

**Agent gas estimation:** Rhumb includes `estimated_gas_cost_usd` in 402 responses to help agents budget total cost including gas.

### 11.8 Settlement Architecture

```
Agent payments → Rhumb Hot Wallet (Base L2)
                    ↓ (daily sweep, threshold: >$500 or >24h)
              Rhumb Treasury Wallet (Base L2, multisig)
                    ↓ (weekly settlement, threshold: >$5,000)
              Rhumb Operating Account (Coinbase → USD via USDC/USD conversion)
```

**Custody model (v1):** Self-custody with multisig (2-of-3 Gnosis Safe). Keys held by: Pedro (operator wallet), Tom (board wallet), cold storage (hardware wallet).

**USDC → USD conversion:** Via Coinbase Commerce or Circle API. Conversion frequency: weekly. Conversion cost: ~0.1% spread.

**Regulatory note:** USDC receipts at <$100K/mo threshold: no MSB registration required in most US states under the "software provider" exemption for self-custodied USDC flows where Rhumb provides services and receives payment, not stored value. Review annually.

---

## Implementation Roadmap

### v1 (Launch)
- [x] Prepaid credits via Stripe (purchase + deduction)
- [x] x402 USDC per-call payments (Layer 1/2)
- [x] Basic budget enforcement (hard stop only)
- [x] Cost event logging to Supabase
- [ ] Budget definition API
- [ ] Pre-execution cost estimation endpoint
- [ ] Real-time Redis budget cache
- [ ] Manual enterprise invoicing (CSV export)
- [ ] x402 batched payment for Layer 3 (Option A: upfront estimate)

### v2 (Post-Launch, Months 2-4)
- [ ] Subscription tiers
- [ ] Full automated enterprise invoicing (Stripe Invoicing)
- [ ] Provider cost change detection + automated repricing
- [ ] Arbitrage routing with score-based selection
- [ ] Overdraft with risk scoring
- [ ] Float management + interest sweep
- [ ] Stripe Treasury integration

### v3 (Scale, Months 5-12)
- [ ] Payment channel support for Layer 3 (Option B)
- [ ] Provider volume milestone automation + negotiation workflow
- [ ] ASC 606-compliant revenue recognition reporting
- [ ] Multi-currency support
- [ ] EU regulatory compliance (PSD2)
- [ ] Advanced cost optimization (batching, caching, speculative prefetch)

---

*Panel 3 — Economics, Billing & Scaling — v1.0 — 2026-03-30*
