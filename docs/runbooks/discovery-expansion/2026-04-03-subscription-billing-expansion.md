# Discovery expansion — subscription billing

Date: 2026-04-03
Owner: Pedro / Keel runtime review loop

## Why this category

Live production category counts still show **`subscription-billing`** at only **5** providers:
- `chargebee`
- `lago`
- `orb-billing`
- `recurly`
- `revenuecat`

That is too thin for a category agents increasingly need for:
- subscription-state lookup during support and renewal workflows
- invoice and payment-status inspection before customer communication
- entitlement debugging when access depends on billing state
- finance and revenue-ops reporting against real recurring-revenue systems
- lifecycle automation triggered by cancel, renewal, trial, or delinquency state

The honest Mission 2 move was to deepen **subscription-billing** with more API-backed recurring-revenue rails rather than leave a strategically important operator category shallow.

## Added services

### 1. Lemon Squeezy
- Slug: `lemonsqueezy`
- Score: **8.50**
- Execution: **8.60**
- Access readiness: **8.30**
- Why it made the cut:
  - clean API-key REST surface for customers, subscriptions, orders, and license artifacts
  - strongest immediate Phase 0 wedge in the batch
  - excellent fit for read-first subscription inspection and entitlement support workflows
  - lighter operational setup than larger enterprise billing suites

### 2. Rebilly
- Slug: `rebilly`
- Score: **8.35**
- Execution: **8.50**
- Access readiness: **8.05**
- Why it made the cut:
  - broad recurring billing + payments API with strong customer, subscription, invoice, and dunning depth
  - strong fit for operator workflows that need subscription and invoice truth in one place
  - modern API surface with serious execution potential

### 3. Zuora
- Slug: `zuora`
- Score: **8.20**
- Execution: **8.35**
- Access readiness: **7.85**
- Why it made the cut:
  - category-defining enterprise system of record for subscription revenue operations
  - deep account, subscription, invoice, and amendment coverage
  - strategically important enterprise catalog inclusion even if it is not the easiest first managed provider

### 4. ChargeOver
- Slug: `chargeover`
- Score: **8.05**
- Execution: **8.15**
- Access readiness: **7.95**
- Why it made the cut:
  - practical REST API for customers, subscriptions, invoices, plans, and payments
  - useful SMB/midmarket category depth beyond the best-known billing brands
  - strong fit for customer-support and recurring billing inspection workflows

### 5. Billsby
- Slug: `billsby`
- Score: **7.95**
- Execution: **8.05**
- Access readiness: **7.80**
- Why it made the cut:
  - real subscription lifecycle API with plans, customers, subscriptions, and usage state
  - adds SaaS billing breadth outside the current top-five set
  - useful later Resolve target even if it is not the cleanest first wedge

## Phase 0 capability assessment

### Services with accessible APIs
All five added services expose accessible developer APIs.

Strongest early Resolve targets:
1. **Lemon Squeezy**
2. **Rebilly**
3. **ChargeOver**

### Candidate capability shapes
- `subscription.list`
- `subscription.get`
- `customer.get`
- `invoice.list`
- `invoice.get`

### Best initial Phase 0 wedge
The cleanest first move is:
- `subscription.list`
- `subscription.get`
- `customer.get`
- `invoice.list`

Why:
- these are read-first and broadly reusable across support, finance, and product-ops workflows
- they let agents inspect recurring-revenue state without mutating customer billing
- they map cleanly onto the top providers in this batch without forcing a write-heavy abstraction first
- **Lemon Squeezy** is the best initial provider because its API is explicit, lightweight, and useful immediately for subscription and entitlement debugging

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0154_subscription_billing_expansion.sql`

## Verdict

Subscription billing is still underrepresented relative to demand. This batch adds five real API-backed providers and sharpens the next honest Resolve wedge around **read-first subscription inspection**, with **Lemon Squeezy** now the clearest Phase 0 target when the billing lane opens.
