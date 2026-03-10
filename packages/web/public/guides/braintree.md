# Braintree — Agent-Native Service Guide

> **AN Score:** 5.44 · **Tier:** L2 · **Category:** Payments & Billing

---

## 1. Synopsis
Braintree is a full-stack payment platform owned by PayPal that allows agents to process credit cards, digital wallets (PayPal, Venmo, Apple Pay), and ACH transfers. For agents, Braintree is a critical utility for executing financial workflows like subscription management, automated refunds, and marketplace disbursements. Its primary value to autonomous systems is the robust "Sandbox" environment which allows for 1:1 simulation of production payment flows without financial risk. While it offers a powerful GraphQL API and mature SDKs, the service requires significant human-in-the-loop (HITL) effort for production onboarding due to KYC (Know Your Customer) and merchant account requirements. Braintree provides a free, unlimited sandbox; production pricing is typically 2.9% + $0.30 per transaction.

---

## 2. Connection Methods

### GraphQL API
Braintree has shifted toward a GraphQL-first architecture for its modern integrations. This is the preferred method for agents as it allows for precise data fetching and strongly typed schemas. The GraphQL endpoint (`https://payments.braintree-api.com/graphql`) supports complex queries for transaction history and mutations for processing payments.

### SDKs
Braintree maintains high-quality server-side SDKs for Python (`braintree`), Node.js (`braintree`), Ruby, PHP, Java, and .NET. For agentic workflows, the Python and Node.js SDKs are the most common, providing built-in wrappers for credential management and error parsing.

### Webhooks
To maintain state without constant polling, agents should register for webhooks. Braintree supports notifications for transaction status changes (e.g., `transaction_settled`, `transaction_declined`), subscription updates, and dispute creations. Webhooks are signed to ensure authenticity.

### Auth Flows
Braintree uses a set of three credentials for server-to-server communication: `Merchant ID`, `Public Key`, and `Private Key`. These are passed to the SDK's `BraintreeGateway` or used as Basic Auth headers in direct API calls. Production access requires a separate set of keys from the sandbox environment.

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **Transaction** | `gateway.transaction.sale()` | Creates a charge against a payment method or vault record. |
| **Customer** | `gateway.customer.create()` | Stores user info and links multiple payment methods in the Vault. |
| **Payment Method** | `gateway.payment_method.create()` | Adds a credit card or PayPal account to a specific customer. |
| **Subscription** | `gateway.subscription.create()` | Initiates recurring billing based on a predefined plan. |
| **Refund** | `gateway.transaction.refund()` | Issues a full or partial refund for a settled transaction. |
| **Disbursement** | `gateway.disbursement.transactions()` | Retrieves details on funds being moved to the merchant bank account. |
| **Address** | `gateway.address.create()` | Stores billing/shipping details for fraud verification (AVS). |

---

## 4. Setup Guide

### For Humans
1.  **Create Sandbox:** Sign up at `sandbox.braintreegateway.com`.
2.  **Retrieve Keys:** Navigate to Account > User Requests > API Keys to find your Merchant ID and Public/Private keys.
3.  **Configure Processing:** In the sandbox, enable specific payment methods (e.g., PayPal, Venmo) for testing.
4.  **Define Plans:** If using subscriptions, create "Plans" in the dashboard with specific price points.
5.  **Production Onboarding:** Submit a business application via the Braintree site; requires tax IDs and bank details.

### For Agents
1.  **Credential Injection:** Load `BRAINTREE_MERCHANT_ID`, `BRAINTREE_PUBLIC_KEY`, and `BRAINTREE_PRIVATE_KEY` into the environment.
2.  **Gateway Initialization:** Instantiate the SDK using `braintree.BraintreeGateway`.
3.  **Connectivity Check:** Execute a simple query to verify the connection (see code below).
4.  **Environment Validation:** Ensure the agent is explicitly pointing to `braintree.Environment.Sandbox` to prevent accidental production calls.

```python
import braintree

gateway = braintree.BraintreeGateway(
    braintree.Configuration(
        braintree.Environment.Sandbox,
        merchant_id="your_merchant_id",
        public_key="your_public_key",
        private_key="your_private_key"
    )
)

# Connection validation
try:
    # Attempt to fetch a non-existent customer to test API reachability
    gateway.customer.find("ping")
except braintree.exceptions.NotFoundError:
    print("Connection Successful: Gateway is reachable.")
```

---

## 5. Integration Example

This Python example demonstrates an agent creating a customer and charging a "nonce" (a temporary payment token generated on the client-side).

```python
import braintree

# Initialize Gateway
gateway = braintree.BraintreeGateway(
    braintree.Configuration(
        braintree.Environment.Sandbox,
        merchant_id="use_your_id",
        public_key="use_your_public_key",
        private_key="use_your_private_key"
    )
)

def process_agent_payment(amount, payment_nonce, customer_email):
    # 1. Create/Update Customer and Charge in one call
    result = gateway.transaction.sale({
        "amount": str(amount),
        "payment_method_nonce": payment_nonce,
        "options": {
            "submit_for_settlement": True, # Immediate capture
            "store_in_vault_on_success": True # Save for future agent use
        },
        "customer": {
            "email": customer_email
        }
    })

    if result.is_success:
        return {
            "status": "success",
            "transaction_id": result.transaction.id,
            "last_4": result.transaction.credit_card_details.last_4
        }
    else:
        # Agent should handle specific error codes (e.g., 2001: Insufficient Funds)
        return {
            "status": "failed",
            "errors": [e.code for e in result.errors.deep_errors]
        }
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **P50 Latency** | 185ms | Standard for transaction authorization. |
| **P95 Latency** | 420ms | Spikes during complex fraud checks (Kount/3DS). |
| **P99 Latency** | 720ms | Occurs during downstream bank gateway timeouts. |
| **Rate Limits** | Variable | Braintree does not publish hard limits but throttles on aggressive polling. |
| **Uptime Target** | 99.9% | Backed by PayPal's global infrastructure. |
| **Idempotency** | Supported | Use `order_id` to prevent duplicate charges. |

---

## 7. Agent-Native Notes

*   **Idempotency:** Braintree uses the `order_id` field for idempotency. If an agent retries a `sale()` call with an existing `order_id` within a 30-day window, Braintree will reject the second attempt to prevent double-charging.
*   **Retry Behavior:** Agents should safely retry on `5xx` status codes or `ConnectionError`. Do **not** retry on `422 Unprocessable Entity` without modifying the payload, as this indicates validation failure.
*   **Error Codes → Agent Decisions:**
    *   `2001 (Insufficient Funds)`: Agent should notify the user to update payment.
    *   `2007 (No Account)`: Agent should flag the payment method as dead and request a new one.
    *   `3000 (Gateway Rejected)`: Usually a fraud trigger; agent should escalate to human review.
*   **Schema Stability:** The GraphQL schema is versioned and highly stable. Mutations rarely change, making it safe for long-running autonomous agents.
*   **Cost-per-operation:** $0.00 for API calls; standard transaction fees (approx. 2.9%) apply only on successful `sale()` or `settle()` operations.
*   **Vaulting for Autonomy:** Agents should always use `store_in_vault_on_success`. This allows the agent to trigger future payments using a `token` rather than handling sensitive card data, maintaining PCI compliance.
*   **Partial Settles:** Agents can perform `void()` if a transaction hasn't settled yet, or `refund()` if it has. The agent must check `transaction.status` to decide which method to call.

---

## 8. Rhumb Context: Why Braintree Scores 5.44 (L2)

Braintree’s **5.44 score** reflects a service that is technically excellent but gated by significant real-world friction:

1.  **Execution Autonomy (6.5)** — The API is highly predictable. The SDKs handle the heavy lifting of encryption and signature verification, allowing agents to focus on logic. The presence of a robust GraphQL schema allows agents to introspect data structures easily. However, the lack of a "dry-run" flag for production (separate from the sandbox) prevents safe final-stage verification.

2.  **Access Readiness (4.3)** — This is the primary drag on the score. While the sandbox is "self-serve," moving an agent to production requires a full merchant application, including manual document submission and credit checks. This prevents "instant-on" capabilities for autonomous agents spinning up new sub-merchants.

3.  **Agent Autonomy (5.33)** — Braintree provides the tools for high autonomy (Vaulting, Subscriptions, Webhooks), but the agent is often limited by the underlying financial rules (e.g., AVS mismatches, 3D Secure challenges) that frequently require human intervention.

**Bottom line:** Braintree is a Tier-2 service because it provides a world-class programmatic interface for payments but remains tethered to traditional, slow-moving banking onboarding processes. It is an excellent choice for agents operating within a pre-established corporate entity, but less ideal for "pop-up" or fully autonomous economic actors.

**Competitor context:** **Stripe (8.2)** scores significantly higher due to its "Connect" architecture which allows for more automated sub-account onboarding. **Adyen (5.1)** scores lower for agents due to its even stricter enterprise-only focus and more complex integration requirements. For agents requiring PayPal/Venmo native support, Braintree is the superior choice over Stripe despite the lower score.
