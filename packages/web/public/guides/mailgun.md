# Mailgun — Agent-Native Service Guide

> **AN Score:** 5.83 · **Tier:** L3 · **Category:** Email Delivery

---

## 1. Synopsis
Mailgun is a developer-first email delivery platform designed for high-volume transactional and marketing sequences. For autonomous agents, Mailgun serves as a primary communication interface, allowing them to send notifications, execute cold outreach, and ingest incoming user responses via robust inbound routing. Its core strength lies in its powerful webhook system and email validation API, which prevent agents from wasting quota on "dead" addresses. While it offers a Trial plan (5,000 emails for the first month), it transitions to a usage-based "Foundation" plan. Agents value Mailgun for its detailed event logs and the ability to programmatically manage domain reputations, though the initial DNS configuration remains a significant human-in-the-loop hurdle.

---

## 2. Connection Methods

### REST API
Mailgun's primary interface is a mature RESTful API (v3). It follows standard HTTP conventions and uses Basic Authentication, where the username is `api` and the password is your API key. The API is divided into regional base URLs: `api.mailgun.net/v3` for the US and `api.eu.mailgun.net/v3` for the EU. All requests must be made over HTTPS.

### SDKs
Official libraries are maintained for Python (`mailgun-python-sdk`), JavaScript/Node.js (`mailgun.js`), Go, PHP, Ruby, and Java. These SDKs abstract the multipart/form-data requirements for attachments and provide typed interfaces for message construction, which is preferred for agent stability.

### MCP
There is currently no official Model Context Protocol (MCP) server maintained by Mailgun, though community implementations for tools like Claude Desktop often wrap the `messages` and `stats` endpoints to allow agents to "check their inbox" or report on campaign performance.

### Webhooks
Webhooks are the backbone of agent autonomy in Mailgun. Agents can subscribe to events like `delivered`, `opened`, `clicked`, `permanent_fail`, and `temporary_fail`. Mailgun includes a cryptographic signature in every webhook payload (using your API key), allowing agents to autonomously verify the authenticity of the data before triggering downstream logic.

### Auth Flows
Mailgun uses API Key authentication. For agents, it is best practice to use "Domain-specific" keys where possible to limit the blast radius. There is no OAuth2 flow for standard API access; it is strictly a server-to-server integration model.

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **Send Message** | `POST /v3/{domain}/messages` | Sends a plain text or HTML email. Supports templates and variables. |
| **Validate Email** | `GET /v3/address/validate` | Checks if an email address exists and is deliverable to prevent bounces. |
| **List Events** | `GET /v3/{domain}/events` | Queries the history of sent, delivered, or failed messages for a domain. |
| **Inbound Route** | `POST /v3/routes` | Creates a rule to forward incoming emails to a URL (webhook) or another email. |
| **Manage Templates** | `POST /v3/{domain}/templates` | Programmatically creates or updates HTML templates for agent use. |
| **Domain Stats** | `GET /v3/{domain}/stats/total` | Retrieves aggregate metrics on delivery and engagement for a specific domain. |

---

## 4. Setup Guide

### For Humans
1. **Create Account:** Sign up at Mailgun.com and select a plan (Trial or Foundation).
2. **Add Domain:** Navigate to "Sending" > "Domains" and add your sending subdomain (e.g., `mg.yourdomain.com`).
3. **Configure DNS:** Manually add the required SPF, DKIM, and MX records to your DNS provider (e.g., Cloudflare, AWS Route53).
4. **Verify Domain:** Wait for Mailgun to detect the DNS changes and mark the domain as "Active."
5. **Generate API Key:** Go to "Settings" > "API Keys" and copy the "Private API Key."

### For Agents
1. **Validate Credentials:** The agent should perform a `GET /v3/domains` request to ensure the API key is valid and the domain is active.
2. **Check Region:** Ensure the agent is using the correct base URL (US vs. EU) based on the account configuration.
3. **Verify Domain State:** The agent must confirm the `state` of the target domain is `active` before attempting to send messages.
4. **Connection Test (Python):**
```python
import requests

def validate_mailgun(api_key, domain):
    response = requests.get(
        f"https://api.mailgun.net/v3/domains/{domain}",
        auth=("api", api_key)
    )
    if response.status_code == 200 and response.json().get('domain', {}).get('state') == 'active':
        return True
    return False
```

---

## 5. Integration Example

```python
import os
import requests

def agent_send_email(recipient_email, subject, body_text):
    """
    Standard agent implementation for sending a message using 
    Mailgun's REST API with simple error handling.
    """
    MAILGUN_API_KEY = os.getenv("MAILGUN_API_KEY")
    MAILGUN_DOMAIN = os.getenv("MAILGUN_DOMAIN")
    
    response = requests.post(
        f"https://api.mailgun.net/v3/{MAILGUN_DOMAIN}/messages",
        auth=("api", MAILGUN_API_KEY),
        data={
            "from": f"Agent Support <support@{MAILGUN_DOMAIN}>",
            "to": [recipient_email],
            "subject": subject,
            "text": body_text,
            "o:tracking": "yes"
        }
    )

    if response.status_code == 200:
        return response.json().get("id")
    elif response.status_code == 429:
        # Agent decision: trigger backoff and retry
        raise Exception("Rate limit exceeded. Retry in 60s.")
    else:
        # Agent decision: escalate to human or log error
        raise Exception(f"Failed to send: {response.text}")
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **P50 Latency** | 165ms | Standard API response for message queuing. |
| **P95 Latency** | 380ms | Occurs during high-load periods or large attachments. |
| **P99 Latency** | 650ms | Rare spikes, usually related to regional network jitter. |
| **Rate Limits** | Variable | Typically 100 requests per second; varies by plan. |
| **Max Payload** | 25MB | Total message size including attachments. |

---

## 7. Agent-Native Notes

*   **Idempotency:** Mailgun does not support native `Idempotency-Key` headers. Agents should use the `Message-ID` returned from the first successful request to track delivery and avoid duplicate sends during retries.
*   **Retry Behavior:** Agents should implement exponential backoff for `429 Too Many Requests` and `5xx` errors. `400` errors (e.g., "Invalid Address") should be treated as terminal and should trigger a cleanup of the agent's contact list.
*   **Error Codes:** A `401` indicates an expired or incorrect API key. A `403` usually means the domain is disabled or the account has been flagged for a TOS violation.
*   **Schema Stability:** The `/v3/` API has been stable for years. Agents can rely on the JSON response structures for long-term deployments without frequent maintenance.
*   **Cost-per-operation:** On the Foundation plan, costs are approximately $0.0008 per email. High-frequency agents should monitor usage to avoid unexpected overages.
*   **Webhooks for Loops:** Agents should use the `delivered` webhook to confirm the end of a task. If a `permanent_fail` event is received, the agent should autonomously update its internal database to mark that user as "unreachable."
*   **IP Warmup:** For high-volume agents, Mailgun handles IP warmup on managed plans, but agents must be programmed to throttle their own volume initially to protect domain reputation.

---

## 8. Rhumb Context: Why Mailgun Scores 5.83 (L3)

Mailgun's **5.83 score** reflects a service that is highly capable for programmatic use but suffers from significant human-centric bootstrapping requirements:

1. **Execution Autonomy (6.8)** — Mailgun provides clear, actionable error codes and a highly reliable webhook system. The ability for an agent to "close the loop" by listening for bounces or opens is excellent. However, the lack of native idempotency headers requires the agent (or developer) to build custom logic to prevent duplicate emails during network retries.

2. **Access Readiness (4.8)** — This is the primary drag on the score. Mailgun is not "plug-and-play" for a fresh agent. DNS configuration (SPF/DKIM/MX) is a manual process that requires human access to a domain registrar. Unlike some modern services, an agent cannot fully provision its own communication infrastructure from scratch without human intervention.

3. **Agent Autonomy (5.67)** — The API surface is broad, covering everything from message sending to complex inbound routing and template management. The "Email Validation" API is a high-value tool for autonomous agents to maintain data hygiene. Payment is self-serve, but the complexity of plan tiers and the potential for account freezes during "manual reviews" limit its score in fully autonomous environments.

**Bottom line:** Mailgun is a "Ready" (L3) service for agents that have already been bootstrapped with a verified domain. It is the preferred choice for agents that need to handle both outbound delivery and inbound processing at scale.

**Competitor context:** **Postmark (6.2)** scores higher due to superior delivery reputation and simpler pricing, though it is more restrictive on the types of mail allowed. **SendGrid (5.2)** scores lower due to a more complex API and a history of inconsistent delivery performance for new accounts. For agents requiring high-volume automation, Mailgun is the most balanced choice.
