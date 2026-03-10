# Lemon Squeezy — Agent-Native Service Guide

> **AN Score:** 6.56 · **Tier:** L3 · **Category:** Payments & Billing

---

## 1. Synopsis
Lemon Squeezy is a Merchant of Record (MoR) platform designed for selling digital products, subscriptions, and software licenses. For autonomous agents, Lemon Squeezy is a high-utility service because it offloads the complexities of global sales tax (VAT), compliance, and invoicing. Agents can programmatically generate checkout links, manage subscriptions, and validate license keys without human intervention. Unlike standard payment gateways, Lemon Squeezy handles the "legal" transaction, meaning agents don't need to manage tax nexus logic. There is no monthly platform fee; instead, it operates on a pay-as-you-go model (typically 5% + 50¢ per transaction), making it ideal for low-volume or experimental agentic services.

---

## 2. Connection Methods

### REST API
Lemon Squeezy provides a robust REST API built on the **JSON:API** specification. This is a significant advantage for agents, as the response structure is highly predictable and standardized. Every resource includes `id`, `type`, and `attributes` blocks, which simplifies parsing logic across different endpoints. The API is accessible at `https://api.lemonsqueezy.com/v1/`.

### SDKs
The official primary library is the **Lemon Squeezy JavaScript SDK** (`@lemonsqueezy/lemonsqueezy.js`), which is fully typed and supports both Node.js and edge environments. While no official Python SDK exists, the JSON:API structure makes standard libraries like `httpx` or `requests` highly effective. Community-maintained Python packages are available but should be vetted for specific agentic use cases.

### Webhooks
For agents, webhooks are the primary method for handling asynchronous events like `order_created`, `subscription_created`, and `subscription_payment_failed`. Lemon Squeezy supports signing secrets (HMAC SHA256) to allow agents to verify that incoming events originated from the platform.

### Auth Flows
Authentication is handled via **API Keys** (Bearer Tokens). Agents should store these as environment variables (`LEMON_SQUEEZY_API_KEY`). Keys are generated in the Lemon Squeezy Dashboard under Settings > API. Note that keys are store-specific or account-wide depending on the permissions granted during generation.

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **Store** | `GET /v1/stores` | The top-level entity representing a business unit. Agents need the Store ID for most operations. |
| **Product** | `GET /v1/products` | Represents a sellable item (e.g., "Agent Subscription"). |
| **Variant** | `GET /v1/variants` | Specific versions of a product (e.g., Monthly vs. Yearly pricing). |
| **Checkout** | `POST /v1/checkouts` | Generates a hosted payment URL. Critical for agents to hand off to users. |
| **Subscription** | `GET /v1/subscriptions` | Manages recurring billing cycles and status (active, cancelled, on_trial). |
| **Order** | `GET /v1/orders` | Represents a completed transaction record. |
| **License Key** | `POST /v1/license-keys/validate` | Validates a user's license for software/agent access. |

---

## 4. Setup Guide

### For Humans
1. Create an account at [lemonsqueezy.com](https://www.lemonsqueezy.com/).
2. Complete the "Store Setup" wizard (requires business details for MoR compliance).
3. Create at least one **Product** and a corresponding **Variant** (price).
4. Navigate to **Settings > API** and generate a new API Key.
5. Copy the **Store ID** found in the URL or via the API to use in your agent configuration.

### For Agents
1. **Initialize Environment:** Ensure `LEMON_SQUEEZY_API_KEY` is present in the environment.
2. **Identity Verification:** Call the "Me" endpoint to verify connectivity and retrieve account details.
3. **Store Discovery:** Query available stores to find the active `store_id`.
4. **Validation Code:**
```python
import httpx
import os

headers = {
    "Accept": "application/vnd.api+json",
    "Content-Type": "application/vnd.api+json",
    "Authorization": f"Bearer {os.environ['LEMON_SQUEEZY_API_KEY']}"
}

with httpx.Client() as client:
    resp = client.get("https://api.lemonsqueezy.com/v1/users/me", headers=headers)
    if resp.status_code == 200:
        print(f"Connected: {resp.json()['data']['attributes']['name']}")
```

---

## 5. Integration Example

This example demonstrates an agent generating a unique checkout link for a specific customer using the official JavaScript SDK.

```javascript
import { lemonSqueezySetup, createCheckout } from "@lemonsqueezy/lemonsqueezy.js";

// 1. Initialize with API Key
lemonSqueezySetup({ apiKey: process.env.LEMON_SQUEEZY_API_KEY });

async function generateAgentCheckout(storeId, variantId, userEmail) {
  try {
    // 2. Programmatically create a checkout session
    const { data, error } = await createCheckout(storeId, variantId, {
      checkoutData: {
        email: userEmail,
        custom: {
          agent_session_id: "agent_12345" // Pass metadata for tracking
        }
      },
      productOptions: {
        redirectUrl: "https://your-agent-app.com/success",
      }
    });

    if (error) throw new Error(error.message);

    // 3. Return the hosted checkout URL to the agent for delivery
    return data.data.attributes.url;
  } catch (err) {
    console.error("Agent Checkout Error:", err.message);
    return null;
  }
}
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **Latency P50** | 105ms | Fast enough for real-time chat-to-checkout flows. |
| **Latency P95** | 240ms | Occasional spikes during complex JSON:API resource inclusion. |
| **Latency P99** | 400ms | Rare; usually during peak global traffic or reporting queries. |
| **Rate Limit** | 500 requests / min | Shared across all endpoints; sufficient for most agent fleets. |
| **Uptime** | 99.9%+ | Highly stable infrastructure. |

---

## 7. Agent-Native Notes

*   **Idempotency:** Lemon Squeezy does not support a dedicated `Idempotency-Key` header. Agents must implement client-side checks (e.g., verifying if a checkout with a specific `custom` metadata ID already exists) before retrying `POST` requests.
*   **Retry Behavior:** Use exponential backoff for `429 Too Many Requests`. For `5xx` errors, retries are safe for `GET` requests but require caution on `POST /v1/checkouts` to avoid duplicate link generation.
*   **Error Codes:** Errors follow the JSON:API format. Agents should look for the `code` and `detail` fields within the `errors` array. Specifically, `422 Unprocessable Entity` usually indicates a schema mismatch or missing required field.
*   **Schema Stability:** The use of JSON:API makes the schema extremely stable. Lemon Squeezy rarely makes breaking changes, preferring to add new optional attributes.
*   **Cost-per-operation:** Zero API call cost. Revenue is only shared upon successful transaction (5% + 50¢). This makes it "free" for agents to poll for status or manage metadata.
*   **Metadata Limit:** Use the `custom` object in checkouts to store agent-specific state. This metadata persists through to the `Order` and `Subscription` objects, enabling agents to maintain context across the entire lifecycle.
*   **No Test Mode Toggle:** Unlike Stripe, Lemon Squeezy uses a "Test Mode" flag on individual stores. Agents must be programmed to recognize if they are interacting with a `test` store versus a `live` store via the `mode` attribute.

---

## 8. Rhumb Context: Why Lemon Squeezy Scores 6.56 (L3)

Lemon Squeezy’s **6.56 score** reflects its position as a highly accessible, developer-friendly Merchant of Record that falls just short of the "Autonomous Tier" (L4) due to governance and idempotency gaps:

1. **Execution Autonomy (7.5)** — The JSON:API implementation is a major win for agents. It provides a strict, predictable contract that allows LLMs to generate valid requests with high confidence. The ability to bundle custom metadata through the entire payment lifecycle allows agents to maintain state without an external database.

2. **Access Readiness (5.7)** — While the API is easy to use, the "Merchant of Record" model introduces human friction. Stores must be manually approved for payouts, and the lack of a robust "Test Mode" that mirrors production exactly (without creating a separate store environment) adds complexity to agent testing pipelines.

3. **Agent Autonomy (6.0)** — The platform lacks built-in idempotency headers, forcing agent developers to write custom "check-before-act" logic. However, the comprehensive webhook system and the inclusion of tax/compliance handling mean the agent can operate globally without needing a "Human-in-the-Loop" for fiscal logic.

**Bottom line:** Lemon Squeezy is the best choice for agents that need to sell things globally without the overhead of managing sales tax. It is more agent-friendly than legacy providers but requires careful handling of retries due to the lack of native idempotency.

**Competitor context:** **Stripe (7.2)** scores higher on execution autonomy due to superior idempotency and "Test Mode" features, but requires significantly more configuration for global tax. **Paddle (6.1)** offers a similar MoR model but has a more fragmented API history that is slightly harder for agents to navigate compared to Lemon Squeezy’s clean JSON:API structure.
