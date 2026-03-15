# Square — Agent-Native Service Guide

> **AN Score:** 6.27 · **Tier:** L3 · **Category:** Payments & Billing

---

## 1. Synopsis
Square provides a comprehensive commerce platform that allows agents to programmatically handle the entire lifecycle of a transaction, from inventory management to final settlement. For agents, Square is the bridge between digital logic and physical commerce, offering robust APIs for processing payments, managing customer profiles, and synchronizing catalogs across online and brick-and-mortar locations. Its primary value to autonomous systems is its unified data model—an agent can create an order, apply a discount from a loyalty program, and process a payment through a single API ecosystem. Square offers a self-serve developer tier with no monthly platform fees; costs are strictly transaction-based (typically 2.9% + 30¢ for online payments), making it low-risk for agent experimentation.

---

## 2. Connection Methods

### REST API
Square’s primary interface is a mature REST API that follows standard HTTP conventions. It uses JSON for request and response bodies. The API is versioned via a mandatory `Square-Version` header (e.g., `2023-12-13`), ensuring that agents can rely on schema stability even as Square updates its platform.

### SDKs
Square maintains high-quality, idiomatic SDKs for Python, Node.js, Ruby, Java, PHP, and .NET. These SDKs are the recommended path for agents as they include built-in models for complex objects like `Money` (which prevents floating-point errors by using minor units) and automated handling of the `idempotency_key` requirement.

### Webhooks
For agents performing long-running or asynchronous tasks, Square's Webhooks are essential. Agents can subscribe to events such as `payment.updated`, `order.created`, or `inventory.count.updated`. Square supports webhook signatures (HMAC-SHA256) to allow agents to verify that incoming notifications are authentic.

### Auth Flows
Square supports two primary authentication methods:
*   **Personal Access Tokens (PATs):** Used for agents acting on behalf of the developer's own account. This is the fastest path for "single-merchant" agents.
*   **OAuth 2.0:** Required for agents that provide services to multiple Square merchants. It uses a standard authorization code grant flow with specific scopes (e.g., `PAYMENTS_WRITE`, `CUSTOMERS_READ`).

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **Payment** | `POST /v2/payments` | The core transaction entity. Converts a source (token/card) into a movement of funds. |
| **Order** | `POST /v2/orders` | A line-item breakdown of a sale, including taxes, discounts, and fulfillment details. |
| **Customer** | `POST /v2/customers` | A profile for CRM, allowing agents to track lifetime value and store cards-on-file. |
| **Catalog** | `GET /v2/catalog/list` | The source of truth for items, variations, and pricing that an agent can sell. |
| **Location** | `GET /v2/locations` | Identifies the physical or logical business unit where a transaction occurs. |
| **Invoice** | `POST /v2/invoices` | Allows an agent to request payment via an emailed link rather than immediate checkout. |
| **Refund** | `POST /v2/refunds` | Reverses a previous payment, either partially or in full. |

---

## 4. Setup Guide

### For Humans
1.  Log in to the [Square Developer Dashboard](https://developer.squareup.com/apps).
2.  Click "Create an Application" and give it a name.
3.  Navigate to **Production Settings** to retrieve your `Application ID` and `Personal Access Token`.
4.  Set your **Square Version** to the latest stable release to ensure documentation alignment.
5.  In the **Locations** tab, identify the `Location ID` you wish the agent to operate within.
6.  (Optional) Setup a Sandbox application for risk-free agent testing.

### For Agents
1.  **Environment Sync:** Load the `SQUARE_ACCESS_TOKEN` and `SQUARE_LOCATION_ID` into the environment.
2.  **SDK Initialization:** Instantiate the client using the production or sandbox environment flag.
3.  **Connection Discovery:** Call the `/v2/locations` endpoint to verify connectivity and retrieve the specific location's currency settings.
4.  **Capability Check:** Perform a `GET /v2/catalog/info` to ensure the agent has read access to the merchant's inventory.
5.  **Validation Code (Python):**
```python
from square.client import Client
import os

client = Client(access_token=os.environ['SQUARE_ACCESS_TOKEN'], environment='production')
res = client.locations.list_locations()

if res.is_success():
    print(f"Connected to Square. Active Location: {res.body['locations'][0]['name']}")
else:
    raise Exception(f"Connection failed: {res.errors}")
```

---

## 5. Integration Example

This script demonstrates an agent autonomously creating a payment for a specific amount.

```python
import uuid
from square.client import Client

# Initialize client
client = Client(
    access_token='YOUR_ACCESS_TOKEN',
    environment='production'
)

# Agents must generate a unique idempotency key for every mutation
idempotency_key = str(uuid.uuid4())

# Payment request body
create_payment_request = {
    "source_id": "cnon:card-nonce-ok", # In production, this is a real token from Web Payments SDK
    "idempotency_key": idempotency_key,
    "amount_money": {
        "amount": 1000, # $10.00
        "currency": "USD"
    },
    "note": "Agent-initiated replenishment order"
}

# Execute payment
result = client.payments.create_payment(create_payment_request)

if result.is_success():
    payment_id = result.body['payment']['id']
    status = result.body['payment']['status']
    print(f"Success: Payment {payment_id} is {status}")
elif result.is_error():
    # Agent logic for handling errors
    for error in result.errors:
        print(f"Error: {error['category']} - {error['code']}: {error['detail']}")
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **P50 Latency** | 140ms | Standard for simple GET requests (Locations, Catalog). |
| **P95 Latency** | 310ms | Common for POST operations involving external card networks. |
| **P99 Latency** | 520ms | Occurs during high-concurrency periods or complex Order/Payment chains. |
| **Rate Limits** | ~2 QPS | Default limit is conservative; varies by endpoint. Check headers for `RateLimit-*`. |
| **Uptime** | 99.9% + | High availability, though downstream bank outages can affect P99. |

---

## 7. Agent-Native Notes

*   **Idempotency:** Square strictly enforces idempotency for all `POST` requests. Agents **must** generate and store a `idempotency_key` (typically a UUID) to safely retry requests without double-charging.
*   **Retry behavior:** Square returns specific 5xx errors for transient issues. Agents should implement exponential backoff only for 5xx and `429 Too Many Requests`.
*   **Error codes → agent decisions:** Square categorizes errors. `CATEGORY_PAYMENT_METHOD_ERROR` should trigger the agent to stop and notify the human for a new payment method, while `CATEGORY_API_ERROR` suggests a bug in the agent's request construction.
*   **Schema stability:** Square is highly disciplined with versioning. Using a fixed `Square-Version` header prevents the agent's parsing logic from breaking during platform updates.
*   **Cost-per-operation:** While API calls are free, `POST /v2/payments` results in financial charges. Agents should be governed by "spending limits" or "human-in-the-loop" thresholds for high-value transactions.
*   **Money Representation:** Square uses integers for currency (cents). Agents must be programmed to avoid floating-point math (e.g., using `1000` for `$10.00`) to prevent reconciliation errors.
*   **Sandbox Parity:** Square provides a robust Sandbox environment. Agents can be fully validated using "fake" card nonces (e.g., `cnon:card-nonce-ok`) before touching real capital.

---

## 8. Rhumb Context: Why Square Scores 6.27 (L3)

Square’s **6.27 score** reflects a powerful, developer-centric platform that is slightly hampered by the inherent friction of financial compliance and a "merchant-first" rather than "agent-first" onboarding flow:

1. **Execution Autonomy (7.3)** — Square excels here. The mandatory use of idempotency keys is a foundational "agent-native" feature, allowing autonomous systems to recover from network failures without financial risk. The error categorization is granular, enabling agents to distinguish between a "card declined" (business logic) and a "timeout" (infrastructure).

2. **Access Readiness (5.2)** — This is the primary drag on the score. While the developer account is self-serve, moving from Sandbox to Production requires "Know Your Customer" (KYC) verification, which involves human intervention. Unlike a pure software API (like Linear), an agent cannot "fully" spin up a new Square instance in seconds without a human providing tax IDs and bank details.

3. **Agent Autonomy (6.0)** — Square’s SDKs provide excellent abstractions, but the platform lacks a first-class "Agent" role in its IAM. Currently, agents must use Merchant-level OAuth or PATs, which grants broad permissions. More granular, "agent-scoped" permissions would raise this score. However, the robust webhook system allows agents to maintain state effectively without polling.

**Bottom line:** Square is the premier choice for agents that need to interact with physical commerce or provide a "Point of Sale" capability. Its strict adherence to idempotency and typed SDKs makes it safer for autonomous execution than many younger fintech APIs.

**Competitor context:** Stripe (7.1) scores higher due to its superior developer documentation, more flexible "Connect" architecture for complex marketplaces, and a slightly more "API-first" approach to sandbox testing. However, for agents managing actual retail hardware or local business inventory, Square remains the superior integration.
