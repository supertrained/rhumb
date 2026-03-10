# Stripe — Agent-Native Service Guide

> **AN Score:** 8.9 · **Tier:** L4 · **Category:** Payments & Billing

---

## 1. Synopsis

Stripe is the dominant payments infrastructure for internet businesses. It handles credit card processing, subscriptions, invoicing, and financial reporting through a clean, RESTful API. For agents, Stripe is the default payment rail — any workflow that involves charging customers, managing subscriptions, or generating invoices routes through Stripe. The API is exceptionally well-documented, idempotency-native, and has first-class support for programmatic access. Free to create an account; transaction fees apply (2.9% + $0.30 per charge in the US). Test mode available with no charges.

---

## 2. Connection Methods

### REST API
- **Base URL:** `https://api.stripe.com/v1`
- **Auth:** Bearer token (`Authorization: Bearer sk_live_...` or `sk_test_...`)
- **Content-Type:** `application/x-www-form-urlencoded` (not JSON for writes)
- **Rate Limits:** 100 read requests/sec, 100 write requests/sec per secret key (live mode). Test mode is more lenient.
- **Docs:** https://docs.stripe.com/api

### SDKs
- **Python:** `pip install stripe` — official, well-maintained
- **JavaScript/Node:** `npm install stripe` — TypeScript types included
- **Go:** `go get github.com/stripe/stripe-go/v81`
- **Ruby, PHP, Java, .NET** — all officially supported

### MCP
- Community MCP servers exist for Stripe (check https://github.com/modelcontextprotocol/servers for current listings)
- No official Stripe-published MCP server as of early 2026

### Webhooks
- **Endpoint:** Configure in Dashboard → Developers → Webhooks
- **Events:** 200+ event types (`charge.succeeded`, `invoice.paid`, `customer.subscription.updated`)
- **Signature verification:** HMAC-SHA256 via `Stripe-Signature` header
- **Retry policy:** Up to 3 days with exponential backoff

### Auth Flows
- **API Keys:** Secret key (server-side) + Publishable key (client-side)
- **Restricted Keys:** Scoped permissions per key (recommended for agents)
- **OAuth (Stripe Connect):** For platform/marketplace patterns

---

## 3. Key Primitives

| Primitive | Endpoint | Description |
|-----------|----------|-------------|
| `charge.create` | `POST /v1/charges` | One-time payment (legacy; prefer PaymentIntents) |
| `payment_intent.create` | `POST /v1/payment_intents` | Modern payment flow with SCA support |
| `customer.create` | `POST /v1/customers` | Create a customer record |
| `subscription.create` | `POST /v1/subscriptions` | Recurring billing |
| `invoice.list` | `GET /v1/invoices` | Query invoices with filters |
| `refund.create` | `POST /v1/refunds` | Issue a refund on a charge |
| `balance.retrieve` | `GET /v1/balance` | Current account balance |

---

## 4. Setup Guide

### For Humans
1. Create account at https://dashboard.stripe.com/register
2. Complete business verification (name, address, bank account)
3. Navigate to **Developers → API Keys**
4. Copy your **Secret key** (starts with `sk_test_` for test mode)
5. Store securely — this key has full account access
6. Enable **Restricted keys** for production agent use (scope to only needed resources)

### For Agents
1. **Credential retrieval:** Pull API key from secure store (e.g., Rhumb Access layer, 1Password, environment variable `STRIPE_SECRET_KEY`)
2. **Connection validation:**
   ```bash
   curl -s https://api.stripe.com/v1/balance \
     -H "Authorization: Bearer $STRIPE_SECRET_KEY" | jq .object
   # Should return "balance"
   ```
3. **Error handling:** Check for `error.type` in responses — `card_error`, `rate_limit_error`, `invalid_request_error`, `authentication_error`, `api_error`
4. **Fallback:** If rate-limited (HTTP 429), back off exponentially starting at 1s. If API error (500+), retry up to 3 times then alert.

---

## 5. Integration Example

```python
import stripe
import os

# Credential setup
stripe.api_key = os.environ["STRIPE_SECRET_KEY"]

# Create a customer
customer = stripe.Customer.create(
    email="agent-created@example.com",
    name="Demo Customer",
    metadata={"created_by": "rhumb-agent", "workflow": "onboarding"}
)
print(f"Customer created: {customer.id}")

# Create a PaymentIntent (modern payment flow)
intent = stripe.PaymentIntent.create(
    amount=2000,  # $20.00 in cents
    currency="usd",
    customer=customer.id,
    payment_method_types=["card"],
    idempotency_key="order_abc_123",  # Safe to retry
    metadata={"order_id": "abc_123"}
)
print(f"PaymentIntent: {intent.id} — status: {intent.status}")

# List recent invoices
invoices = stripe.Invoice.list(limit=5, status="paid")
for inv in invoices.data:
    print(f"  Invoice {inv.id}: ${inv.amount_paid / 100:.2f}")
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| **Latency (P50)** | ~200ms | Simple reads (balance, customer.retrieve) |
| **Latency (P95)** | ~500ms | Writes (payment_intent.create) |
| **Latency (P99)** | ~1.2s | Complex operations (subscription creation with proration) |
| **Uptime SLA** | 99.99% | Stripe publishes status at https://status.stripe.com |
| **Rate Limits** | 100 req/sec read, 100 req/sec write | Per secret key; higher limits available on request |
| **Free Tier** | Test mode unlimited | No charges in test mode; live mode: 2.9% + $0.30/txn |

---

## 7. Agent-Native Notes

- **Idempotency:** First-class support. Pass `Idempotency-Key` header on any POST. Stripe caches results for 24 hours. Essential for agent retry safety.
- **Retry behavior:** Use exponential backoff on 429 and 500+ errors. Stripe's own SDKs implement automatic retries (configurable via `max_network_retries`).
- **Error codes → agent decisions:** `card_declined` → prompt user for new payment method. `rate_limit_error` → back off. `idempotency_key_in_use` → previous request still processing, wait and poll.
- **Schema stability:** Stripe uses API versioning (`Stripe-Version` header). Pin your version to avoid breaking changes. MTBBC is excellent — Stripe maintains backward compatibility aggressively.
- **Cost-per-operation:** No per-API-call cost. Charges only on successful transactions (2.9% + $0.30 US). Agent routing decision: prefer Stripe for reliability even if slightly more expensive than alternatives.
- **Test mode:** Use `sk_test_` keys for development. Test card numbers: `4242424242424242` (success), `4000000000000002` (decline). Agents should always validate in test mode first.
- **Metadata:** Every Stripe object supports `metadata` (up to 50 key-value pairs, 500 char values). Agents should tag all created objects with `created_by`, `workflow`, and `idempotency_ref` for traceability.

---

## 8. Rhumb Context: Why Stripe Scores 8.9 (L4)

Stripe's **8.9 score** reflects excellence across three dimensions:

1. **Execution Autonomy (9.0)** — Idempotency + deterministic error codes allow agents to operate without human supervision. The `Idempotency-Key` header is the difference between "I can retry safely" and "I might double-charge."

2. **Access Readiness (8.8)** — Test mode is free and frictionless. Agents can validate the entire flow (create customer, charge card, handle errors) without production risk. Restricted API keys add fine-grained permission control.

3. **Agent Autonomy (9.0)** — Stripe supports webhook-based async workflows and provides webhook signing. No manual intervention needed for payment verification. The x402 payment protocol integrations are emerging (e.g., Stripe ACP). Metadata support enables agent-side traceability.

**Bottom line:** Stripe is the default choice for payment-critical agent workflows. When agents need to collect money or route payments, Stripe earns its score through reliability + autonomy.

**Competitor context:** PayPal (5.2) scores lower due to async callbacks without webhooks and more rigid error responses. Consider Stripe unless you have legacy constraints or specific regulatory requirements.
