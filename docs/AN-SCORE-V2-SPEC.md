# AN Score v2 — Three New Dimensions

> **Work Unit:** WU 3.3
> **Author:** Pedro (operator)
> **Date:** 2026-03-09
> **Status:** Implemented (engine + API + migrations)
> **AN Score Version:** 0.3

## Overview

AN Score v0.2 evaluates tools on two axes:
- **Execution** (17 dimensions: I1-I7 infrastructure, F1-F7 interface, O1-O3 operational)
- **Access Readiness** (6 dimensions: A1-A6)

v0.3 adds a third axis: **Agent Autonomy** — measuring a tool's support for fully autonomous agent operations. This captures capabilities that don't fit neatly into execution quality or access friction, but matter enormously for the agent future:

1. **P1 — Payment Autonomy**: Can an agent pay for this tool without human intervention?
2. **G1 — Governance Readiness**: Does the tool support enterprise-grade agent oversight?
3. **W1 — Web Agent Accessibility**: Can a web agent navigate the tool's dashboard/admin UI?

## Why These Three

### Research Base

**Payment Autonomy** — From Levie's "trillions of agents" thesis + Tom's insight about agent microtransactions:
- **x402 protocol**: HTTP 402 Payment Required → instant stablecoin micropayments. 75M tx in last 30 days, $24M volume. Coinbase-led, Cloudflare integrated, Google A2A extension live.
- **Stripe Issuing**: Virtual cards via API ($0.10/card), per-merchant spending controls, Agentic Commerce Protocol (ACP) with OpenAI. Manus uses this.
- **Coinbase AgentKit/Agentic Wallets**: Agent-owned wallets (Feb 2026), built-in security guardrails, Base L2 stablecoins.
- **Google AP2**: Agent Payments Protocol, 60+ partners (Visa, Mastercard, Coinbase), Verifiable Credentials for authorization.
- **Reality**: Most SaaS tools require human credit card entry. This dimension measures how close a tool is to accepting agent-initiated payment.

**Governance Readiness** — From enterprise agent deployment patterns:
- Agents need per-agent identity, RBAC/ABAC scoped access, audit trails, kill switches.
- Standards: NIST AI RMF, ISO/IEC 42001, EU AI Act (high-risk tier, 2025 enforcement).
- Azure RBAC + Entra Agent Identity, Okta non-human identity, MintMCP compliance proxy.
- **Reality**: Enterprise won't deploy agents on tools without audit trails and access controls. This is the enterprise gatekeeping dimension.

**Web Agent Accessibility** — From AAG v0.1 (Agent Accessibility Guidelines):
- Agents interact via 6 channels: DOM/a11y tree, screenshots, CDP, HTML parsing, structured data, keyboard simulation.
- Three conformance levels: A (Parseable), AA (Navigable), AAA (Native).
- Key gaps: CAPTCHA/bot detection, dynamic content without aria labels, non-semantic HTML.
- **Reality**: Agents that can't use the web UI are limited to API-only. This dimension captures web-layer operability for agents that browse.

## Dimension Definitions

### P1 — Payment Autonomy (weight: 0.06)

**Question:** Can an agent acquire and pay for this tool without human intervention?

**Scoring Rubric (1-10):**

| Score | Description |
|-------|-------------|
| 9-10 | **Native agent payment**: Supports x402, AP2, or programmatic payment via API. Agent can go from discovery to paid access with zero human steps. Consumption billing available. |
| 7-8 | **API-provisioned billing**: Credit card or payment method can be added via API (Stripe Issuing virtual card accepted). Usage-based or per-seat billing programmatically manageable. |
| 5-6 | **Semi-automated**: Payment requires web form, but standard card fields (no CAPTCHA). Agent with web access could complete with Stripe Issuing card. Invoicing available for enterprise. |
| 3-4 | **Human-gated**: Payment requires interactive verification (3D Secure mandatory, phone verification, human-reviewed invoice). Agent needs human handoff for payment. |
| 1-2 | **Fully manual**: Custom pricing, sales-led only, no self-serve payment. "Contact sales" is the only path. |

**Evidence Sources:**
- Pricing page structure (self-serve vs. sales-led)
- API billing endpoints (if any)
- Payment method acceptance (x402, API card, web form, invoice)
- Trial/freemium availability (reduces payment friction)
- Consumption vs. commitment billing model

### G1 — Governance Readiness (weight: 0.05)

**Question:** Does this tool support enterprise-grade agent oversight, audit, and access control?

**Scoring Rubric (1-10):**

| Score | Description |
|-------|-------------|
| 9-10 | **Full agent governance**: Per-agent identity/API keys, RBAC/ABAC with granular scoping, immutable audit logs, data residency controls, SOC 2/ISO 27001 certified, SCIM provisioning, webhook events for all mutations. |
| 7-8 | **Strong controls**: Team/org-level access control, API key scoping (read/write/admin), activity logs with timestamps, SSO/SAML, data processing agreements. Missing per-agent identity or granular RBAC. |
| 5-6 | **Basic controls**: API keys with some scoping, basic activity logs in dashboard, team management, but no RBAC granularity. No audit log export. Limited data residency options. |
| 3-4 | **Minimal**: Single API key per account, no activity logging visible to customer, no access scoping, no compliance certifications publicly listed. |
| 1-2 | **None**: No access controls beyond login. No audit trail. No compliance documentation. |

**Evidence Sources:**
- API key scoping (read-only, write, admin, custom)
- RBAC/team management in API
- Audit log availability + export
- Compliance certifications (SOC 2, ISO 27001, HIPAA, GDPR DPA)
- SCIM/SSO support
- Data residency options
- Webhook coverage for mutations

### W1 — Web Agent Accessibility (weight: 0.04)

**Question:** Can a web-browsing agent effectively operate this tool's dashboard and admin interface?

**Scoring Rubric (1-10):**

| Score | Description |
|-------|-------------|
| 9-10 | **AAA: Agent-Native Web UI**: Semantic HTML + ARIA throughout, keyboard-navigable, no CAPTCHA on authenticated sessions, API parity (anything in UI is also in API), llms.txt or agent-flows.json published, token-efficient DOM. |
| 7-8 | **AA: Agent-Navigable**: Good semantic structure, most interactive elements labeled, keyboard-accessible forms, no anti-bot measures on authenticated paths. Minor gaps (some custom components without ARIA). |
| 5-6 | **A: Agent-Parseable**: Standard HTML forms, some semantic structure. Dashboard usable by screenshot+click agent but fragile. Some unlabeled interactive elements. No aggressive anti-bot. |
| 3-4 | **Poor**: Heavy JavaScript rendering (SPA with client-side only), unlabeled buttons/inputs, some bot detection on authenticated paths, significant portions require visual interpretation. |
| 1-2 | **Hostile**: Aggressive CAPTCHA/bot detection, entirely canvas-rendered UI, no semantic structure, anti-automation measures on all paths. |

**Evidence Sources:**
- Lighthouse accessibility score (proxy)
- Semantic HTML usage (headings, landmarks, labels)
- ARIA attributes on interactive elements
- Keyboard navigability
- CAPTCHA/bot detection on authenticated sessions
- API parity (can API do everything dashboard can?)
- llms.txt or agent discovery metadata

## Weight Distribution (v0.3)

The three new dimensions add a third aggregate axis. Implemented weight allocation:

```
Execution axis (I1-I7, F1-F7, O1-O3): 0.45
Access axis (A1-A6):                   0.40
Autonomy axis (P1, G1, W1):            0.15
  - P1 (Payment Autonomy):             0.06
  - G1 (Governance Readiness):         0.05
  - W1 (Web Agent Accessibility):      0.04
```

**Aggregate formula (v0.3):**

`AN = (execution × 0.45) + (access × 0.40) + (autonomy × 0.15)`

Where:
- `execution` is the weighted I/F/O score (0-10)
- `access` is the weighted A1-A6 score (0-10)
- `autonomy` is the weighted P1/G1/W1 score (0-10)

**Rationale:** These dimensions are forward-looking. Today, most agents don't pay autonomously. But the trajectory is clear: Stripe ACP + x402 + Coinbase AgentKit = payment autonomy within 12 months. Governance is already gating enterprise adoption. Web accessibility is the present (agents browse now). Weighting autonomy at 15% of aggregate reflects importance without overwhelming validated execution/access signal.

## Implementation Plan

### Phase 1: Score 50 Services (This Week)

For each of the 50 services in `artifacts/dataset-scores.json`:

1. **P1 (Payment Autonomy)**: Research pricing page, billing API, payment acceptance
2. **G1 (Governance Readiness)**: Research RBAC, audit logs, compliance certs, API key scoping
3. **W1 (Web Agent Accessibility)**: Quick audit of dashboard accessibility (semantic HTML, ARIA, CAPTCHA)

**Output:** Updated dataset with 3 new dimension scores per service.

### Phase 2: Engine Update ✅

1. Added `P1`, `G1`, `W1` autonomy weighting (`0.06/0.05/0.04`) in `scoring.py`
2. Added `AUTONOMY_DIMENSION_WEIGHTS` and three calculator functions:
   - `calculate_payment_autonomy()`
   - `calculate_governance_readiness()`
   - `calculate_web_accessibility()`
3. Updated `AN_SCORE_VERSION` to `"0.3"`
4. Rebalanced aggregate formula to `execution(0.45) + access(0.40) + autonomy(0.15)`
5. Added Supabase migrations:
   - `0009_autonomy_dimensions.sql`
   - `0010_seed_autonomy_scores.sql`

#### API Response Contract (v0.3)

`GET /v1/services/{slug}/score` now includes an `autonomy` section:

```json
{
  "autonomy_score": 9.3,
  "autonomy": {
    "avg": 9.3,
    "confidence": 0.9,
    "dimensions": [
      {"code": "P1", "name": "payment_autonomy", "score": 10.0, "rationale": "x402 / API-native payments", "confidence": 0.9},
      {"code": "G1", "name": "governance_readiness", "score": 10.0, "rationale": "RBAC + audit logs", "confidence": 0.9},
      {"code": "W1", "name": "web_accessibility", "score": 8.0, "rationale": "AAG AA/AAA structure", "confidence": 0.9}
    ]
  }
}
```

### Phase 3: Web Surface

1. Add autonomy axis to service detail pages
2. Add new dimensions to leaderboard cards
3. Update `llms.txt` with new dimension definitions
4. Blog post: "We Added 3 New Dimensions to the AN Score" (content + MEO)

## Agent Payment Landscape Map

This is the research nobody has published yet. First-mover content opportunity.

### Protocols
| Protocol | Owner | Status | Mechanism | Agent Support |
|----------|-------|--------|-----------|---------------|
| **x402** | Coinbase | Production (75M tx) | HTTP 402 → stablecoin | Native (designed for agents) |
| **AP2** | Google | Production (60+ partners) | Verifiable Credentials + Mandates | Native |
| **ACP** | Stripe + OpenAI | Production (ChatGPT) | Shared Payment Tokens | Native |
| **UCP** | Google | Production (Jan 2026) | Standardized checkout | Agent-compatible |

### Infrastructure
| Product | Owner | Mechanism | Use Case |
|---------|-------|-----------|----------|
| **Stripe Issuing** | Stripe | Virtual cards via API | Agent purchases at any merchant |
| **AgentKit** | Coinbase | Wallet SDK | Agent-owned crypto wallets |
| **Agentic Wallets** | Coinbase | Managed wallets | Autonomous spending/earning |
| **Base L2** | Coinbase | Low-fee blockchain | $0.001/tx stablecoin payments |

### Reality Check (March 2026)
- **0 of 50 scored services** accept x402 or AP2 natively
- **~5 of 50** have API-manageable billing (Stripe, Vercel, Supabase, Cloudflare, Resend)
- **~30 of 50** accept standard card payment via web form (automatable with Stripe Issuing)
- **~15 of 50** require sales/custom pricing or have complex payment flows
- The gap is enormous. This is why Rhumb's Access layer exists.

## Scoring Notes for 50 Services

### Top Tier (expected P1 ≥ 7)
- **Stripe**: API billing, consumption model, obviously 10/10
- **Vercel**: API billing, team management, usage-based
- **Supabase**: Self-serve, API-manageable, usage-based
- **Cloudflare**: Workers has API billing, pay-per-use
- **Resend**: Self-serve, usage-based, API billing

### Mid Tier (expected P1 4-6)
- Most SaaS with self-serve credit card forms
- GitHub, Linear, Notion, Slack, etc.

### Low Tier (expected P1 1-3)
- Enterprise-only tools (Salesforce, custom pricing)
- Tools requiring phone/human verification
- Sales-led platforms

---

## MEO Positioning

This spec and its outputs create content for three meaning-space positions:

1. **"agent payment landscape"** — Nobody has mapped this comprehensively. Own it.
2. **"AN Score dimensions"** — Rhumb is the only entity defining scoring dimensions for agent-tool compatibility. Compound position.
3. **"agent accessibility guidelines"** (AAG) — Empty meaning-space. The WCAG for AI agents. Own it.

Each dimension produces a blog post, a leaderboard filter, and a data point in every service profile. Compound content generation from a single research effort.
