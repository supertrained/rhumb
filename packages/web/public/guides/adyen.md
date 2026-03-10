# Adyen — Agent-Native Service Guide

> **AN Score:** 6.07 · **Tier:** L3 · **Category:** Payments & Billing

---

## 1. Synopsis
Adyen is an enterprise-grade global payment platform that consolidates gateway, risk management, and acquiring into a single stack. For agents, Adyen is the preferred choice for high-volume, multi-region commerce where regulatory compliance (PCI-DSS, PSD2) and fraud prevention are non-negotiable. Unlike developer-first platforms like Stripe, Adyen is "enterprise-first," requiring significant manual onboarding and KYC before programmatic access is granted. However, once integrated, its API provides deep granularity for payment routing and financial settlement. There is no traditional "free tier"; Adyen operates on a per-transaction fee model with high monthly minimums, making it unsuitable for hobbyist agents but ideal for autonomous procurement systems at scale.

---

## 2. Connection Methods

### REST API
Adyen’s primary interface is a versioned REST API (currently `v71` for Checkout). The API is highly structured and follows a predictable pattern across different modules like Checkout, Payouts, and Management. It uses JSON for payloads and requires specific headers for versioning and authentication.

### SDKs
Adyen maintains robust, official SDKs for Python (`adyen-python-api-library`), JavaScript/Node.js (`@adyen/api-library`), Java, Go, and PHP. These libraries are recommended for agents as they handle the complexities of HMAC signature validation for webhooks and provide type-safe models for complex payment objects.

### Webhooks
For asynchronous payment flows (like 3D Secure or bank transfers), Adyen uses a "Standard Notification" webhook system. Agents must implement an endpoint that can process JSON notifications and return an `[accepted]` string to acknowledge receipt. HMAC signatures are mandatory for security.

### Auth Flows
Authentication is handled via an `X-API-Key` header. Unlike OAuth-based services, Adyen uses long-lived API keys generated in the Customer Area (CA). Each request also typically requires a `MerchantAccount` identifier in the request body, effectively creating a two-factor identification requirement for every programmatic call.

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **Payment Session** | `POST /sessions` | Creates a secure session for checkout, returning a token for the agent to use. |
| **Payment Request** | `POST /payments` | The core primitive to authorize a transaction using stored or provided credentials. |
| **Payment Methods** | `POST /paymentMethods` | Queries available payment options based on amount, currency, and country. |
| **Refund** | `POST /payments/{pspReference}/refunds` | Triggers a full or partial reversal of a previously successful payment. |
| **Capture** | `POST /payments/{pspReference}/captures` | Finalizes a previously authorized payment (standard for "Auth-then-Capture" flows). |
| **Payout** | `POST /payouts` | Programmatically sends funds to a third party (requires specific account roles). |
| **Cancel** | `POST /payments/{pspReference}/cancels` | Voids an authorized transaction before it is captured. |

---

## 4. Setup Guide

### For Humans
1. **Apply for a Test Account:** Visit the Adyen website and request a test account. This usually involves a brief sales contact.
2. **KYC Verification:** Complete the "Know Your Customer" documentation for your legal entity.
3. **Create a Merchant Account:** Within the Adyen Customer Area, set up a specific merchant account for your agent's activity.
4. **Generate API Key:** Navigate to **Developers > API credentials** and generate a new key for your merchant account.
5. **Configure Webhooks:** Set up a Standard Notification URL and generate an HMAC key for validation.

### For Agents
1. **Environment Initialization:** Load the `ADYEN_API_KEY` and `ADYEN_MERCHANT_ACCOUNT` into the agent's secure context.
2. **Library Setup:** Install the official library (e.g., `pip install adyen-python-api-library`).
3. **Connectivity Check:** Execute a call to the `/paymentMethods` endpoint to verify the API key and merchant account mapping.
4. **Validation Code:**
```python
import Adyen
adyen = Adyen.Adyen(api_key="YOUR_API_KEY", platform="test")
result = adyen.checkout.payments_api.payment_methods({
    "merchantAccount": "YOUR_MERCHANT_ACCOUNT",
    "amount": {"currency": "USD", "value": 1000}
})
if result.status_code == 200:
    print("Agent Connection Verified")
```

---

## 5. Integration Example

```python
import Adyen
import uuid

# Initialize Adyen client
adyen = Adyen.Adyen(
    api_key="AQE...your_key...",
    platform="test" # Change to "live" for production
)

def process_agent_payment(amount_cents, currency, payment_method_data):
    # Use a UUID for idempotency to prevent double-charging
    idempotency_key = str(uuid.uuid4())
    
    payment_request = {
        "amount": {"value": amount_cents, "currency": currency},
        "reference": f"agent-ref-{idempotency_key}",
        "paymentMethod": payment_method_data,
        "merchantAccount": "RhumbAgentService_ECOM",
        "returnUrl": "https://your-agent-callback.com/verify",
        "authenticationData": {
            "attemptAuthentication": "always"
        }
    }

    # Execute payment with idempotency header
    try:
        response = adyen.checkout.payments_api.payments(
            payment_request, 
            headers={"Idempotency-Key": idempotency_key}
        )
        return response.message
    except Adyen.AdyenAPIResponseError as e:
        return {"error": e.status_code, "message": str(e)}
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **P50 Latency** | 155ms | Standard for REST API authorization calls. |
| **P95 Latency** | 340ms | Occurs during peak global traffic or complex fraud checks. |
| **P99 Latency** | 580ms | Typically seen in cross-border transactions involving 3rd party banks. |
| **Rate Limits** | Variable | Usually 10-50 requests per second (RPS) depending on account tier. |
| **Uptime SLA** | 99.99% | Enterprise-grade availability. |

---

## 7. Agent-Native Notes

*   **Idempotency:** Adyen supports an `Idempotency-Key` header. Agents **must** use this for all `POST /payments` and `POST /payouts` calls to ensure that retries due to network timeouts do not result in duplicate charges.
*   **Retry Behavior:** If an agent receives a `5xx` error, it is safe to retry with the same idempotency key. If a `422` (Unprocessable Entity) is returned, the agent should examine the `resultCode` (e.g., `Refused`, `Cancelled`) and stop retrying.
*   **Error Codes → Agent Decisions:** Adyen provides granular `refusalReason` strings. Agents should be programmed to distinguish between "hard" declines (e.g., `Expired Card` - do not retry) and "soft" declines (e.g., `Insufficient Funds` - retry after 24 hours).
*   **Schema Stability:** Adyen is highly disciplined with versioning. Using a specific version (e.g., `/v71/`) ensures the agent's parsing logic won't break due to upstream changes.
*   **Cost-per-operation:** Adyen uses a "Blended" or "Interchange++" pricing model. Agents should expect a fixed processing fee (~$0.12) plus a percentage (~0.6% to 3%+) per transaction.
*   **Governance Readiness:** Adyen is a top-tier choice for agents in regulated industries. It provides full RBAC, allowing you to give an agent "view-only" access to transaction logs while denying "payout" capabilities.
*   **Async Complexity:** Many Adyen flows are asynchronous. Agents must be capable of maintaining state while waiting for a webhook notification to confirm the final status of a payment.

---

## 8. Rhumb Context: Why Adyen Scores 6.07 (L3)

Adyen’s **6.07 score** reflects a platform that is technically superior for execution but carries high friction for autonomous setup:

1. **Execution Autonomy (7.3)** — Adyen’s API is a masterpiece of deterministic design. The `Idempotency-Key` support and the clarity of `resultCode` allow agents to manage the entire payment lifecycle without human intervention once the account is active. The high score here is earned by the reliability of the "Auth-Capture-Refund" state machine.

2. **Access Readiness (4.7)** — This is Adyen's primary bottleneck. An agent cannot simply "sign up" and start transacting in minutes. The sales-led onboarding, manual KYC, and high minimum volume requirements create a significant barrier to entry compared to self-serve alternatives. This score reflects the "human-in-the-loop" requirement for initial provisioning.

3. **Agent Autonomy (6.0)** — While the API is robust, the platform relies heavily on the "Customer Area" (a web GUI) for advanced configuration like risk rule tuning and webhook setup. While Management APIs are expanding, many "day 2" operations still require a human to log into a dashboard, limiting the agent's ability to fully self-configure.

**Bottom line:** Adyen earns its L3 "Ready" status as the premier infrastructure for enterprise agents. Use Adyen when your agent needs to handle millions of dollars across 50+ countries with maximum regulatory safety. For rapid prototyping or low-volume agents, the access friction is likely too high.

**Competitor context:** **Stripe (8.9)** scores significantly higher due to its 100% self-serve onboarding and superior documentation. **Braintree (5.8)** scores slightly lower than Adyen due to a less modern API structure and slower adoption of the latest web standards. Adyen remains the benchmark for "High-Governance" payment agents.
