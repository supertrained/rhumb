# Discovery expansion — agent-payments

Date: 2026-03-31
Owner: Pedro / Keel runtime review loop

## Why this category

Live production still shows `agent-payments` at only **5** providers:
- `circle`
- `coinbase-commerce`
- `dots-api`
- `ramp-agent-cards`
- `wise`

That remains too thin for a category agents increasingly need for:
- creating and controlling virtual cards
- reading transaction receipts and authorization outcomes
- enforcing spend limits and merchant controls
- separating agent budgets from human-operated finance rails
- funding wallet-adjacent workflows with safer programmable payment primitives
- building auditable operator loops around agent spend

So the honest Mission 2 move was to deepen **agent-payments** rather than keep the catalog shallow around one of the most strategically important agent-economy surfaces.

## Added services

### 1. Lithic
- Slug: `lithic`
- Score: **8.35**
- Execution: **8.55**
- Access readiness: **8.10**
- Why it made the cut:
  - explicit APIs for cards, authorizations, spend controls, and transactions
  - cleanest first Phase 0 wedge for programmable agent spend

### 2. Stripe Issuing
- Slug: `stripe-issuing`
- Score: **8.20**
- Execution: **8.35**
- Access readiness: **8.00**
- Why it made the cut:
  - mature API for cards, cardholders, authorizations, and disputes
  - strong practical fit for commercial card workflows and wallet-linked spend programs

### 3. Marqeta
- Slug: `marqeta`
- Score: **8.10**
- Execution: **8.25**
- Access readiness: **7.90**
- Why it made the cut:
  - category heavyweight with broad card-program coverage
  - strong execution depth for transaction lifecycle and funding-control workflows

### 4. Highnote
- Slug: `highnote`
- Score: **8.05**
- Execution: **8.20**
- Access readiness: **7.85**
- Why it made the cut:
  - modern issuing + acquiring posture with unified ledger semantics
  - useful depth for more advanced agent payment orchestration over time

### 5. Unit
- Slug: `unit`
- Score: **7.95**
- Execution: **8.00**
- Access readiness: **7.80**
- Why it made the cut:
  - unified cards/accounts/payments API surface
  - strong operational relevance for programmable spend and transaction visibility

## Phase 0 capability assessment

All five additions expose accessible APIs and are viable Resolve candidates.

### Strongest candidates for Resolve capability addition
1. **Lithic**
2. **Stripe Issuing**
3. **Marqeta**
4. **Highnote**

### Candidate capability shapes
- `virtual_card.create`
- `virtual_card.list`
- `transaction.list`
- `authorization.read`
- `spend_limit.update`
- `cardholder.list`

### Best initial Phase 0 wedge
The cleanest first move is:
- `virtual_card.create`
- `virtual_card.list`
- `transaction.list`

Why:
- these are the highest-value cross-provider primitives for safe agent spending
- they let agents operate within bounded budgets instead of broad human payment access
- they create a practical bridge between wallet funding and real spend execution
- **Lithic** is the best first provider target because the API is explicit, card-native, and cleaner to normalize than the broader banking or enterprise-heavy platforms in the batch

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0138_agent_payments_expansion.sql`

## Verdict

Agent-payments was still underrepresented in live production. This batch adds five real API-backed providers and sharpens the next honest Resolve wedge around **virtual cards + transaction visibility**, with **Lithic** as the cleanest first implementation target.
