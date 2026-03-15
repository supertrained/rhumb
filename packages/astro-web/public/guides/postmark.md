# Postmark — Agent-Native Service Guide

> **AN Score:** 6.76 · **Tier:** L3 · **Category:** Email Delivery

---

## 1. Synopsis
Postmark is a high-reliability email delivery service focused exclusively on transactional messaging (password resets, notifications, and alerts) rather than bulk marketing. For autonomous agents, Postmark serves as a critical bridge to the human world, providing a programmatic way to send status updates, report findings, or request human-in-the-loop intervention. Its primary value lies in its strict deliverability standards and "Server Token" architecture, which allows agents to be scoped to specific messaging environments. Postmark offers a free tier of 100 emails per month, making it accessible for low-volume agent testing, though its rigorous domain verification process is a prerequisite for production use.

---

## 2. Connection Methods

### REST API
Postmark's primary interface is a developer-centric REST API. It uses JSON for both requests and responses. The API is organized around "Servers"—logical containers that group emails, templates, and stats. Unlike many legacy providers, Postmark’s API is highly predictable, using standard HTTP verbs and consistent resource nesting.

### SDKs
Official libraries are maintained for all major agent runtime environments:
*   **Python:** `postmarker` (Community recommended) or `postmark` (Official)
*   **Node.js:** `postmark` (Official)
*   **Other:** Ruby, PHP, .NET, and Go.

### MCP (Model Context Protocol)
While no official MCP server is maintained by Postmark, the service's strict REST structure makes it a primary candidate for community-built MCP implementations. Agents can easily wrap the `/email` endpoint as a tool definition.

### Webhooks
Postmark provides robust webhooks for lifecycle events: `Delivery`, `Bounce`, `SpamComplaint`, `Open`, and `Click`. This is essential for agents that need to "close the loop"—for example, an agent can automatically retry an alternative contact method if a `Bounce` webhook is received.

### Auth Flows
Postmark uses two types of API tokens:
1.  **Server Tokens:** Used for sending emails and managing resources within a specific server. These are ideal for agents, as they provide a limited "blast radius."
2.  **Account Tokens:** Used for high-level management (creating new servers, managing billing). Agents should rarely, if ever, be granted Account Tokens.

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **Send Email** | `POST /email` | Sends a single transactional email using a Server Token. |
| **Send Batch** | `POST /email/batch` | Sends up to 500 emails in a single API call to reduce latency. |
| **Send with Template** | `POST /email/withTemplate` | Populates a pre-defined Postmark template with dynamic JSON data. |
| **Get Delivery Stats** | `GET /deliverystats` | Retrieves an overview of bounces, spam complaints, and sent counts. |
| **Search Outbound** | `GET /messages/outbound` | Queries the history of sent messages (useful for agent state audits). |
| **Manage Bounces** | `GET /bounces/<id>` | Retrieves detailed diagnostic information for a specific failed delivery. |
| **Activate Bounce** | `PUT /bounces/<id>/activate` | Re-enables a suppressed email address after a hard bounce (use with caution). |

---

## 4. Setup Guide

### For Humans
1.  **Create Account:** Sign up at [postmarkapp.com](https://postmarkapp.com).
2.  **Verify Domain:** Add your sending domain and complete the DKIM/SPF setup via your DNS provider. This is mandatory for deliverability.
3.  **Create a Server:** In the dashboard, create a new "Server" (e.g., "Agent-Notifications-Prod").
4.  **Get Server Token:** Navigate to the "API Tokens" tab of your new server and copy the Server API token.
5.  **Verify Sender:** Add a "Signature" (the email address the agent will send from) and verify it via the confirmation email.

### For Agents
1.  **Secure Token:** Store the Server Token in an environment variable (`POSTMARK_SERVER_TOKEN`).
2.  **Validate Connection:** Perform a lightweight GET request to the delivery stats endpoint to ensure the token is valid and the server is active.
3.  **Check Sender:** Verify the `From` address matches a verified Sender Signature.
4.  **Test Send:** Execute a test send to a known internal address before entering autonomous loops.

```python
import requests

# Connection validation for agents
def validate_postmark(token):
    headers = {"X-Postmark-Server-Token": token, "Accept": "application/json"}
    response = requests.get("https://api.postmarkapp.com/deliverystats", headers=headers)
    return response.status_code == 200
```

---

## 5. Integration Example

This example uses the official Node.js SDK to send a templated notification.

```javascript
const postmark = require("postmark");

// Initialize the client with a Server Token
const client = new postmark.ServerClient(process.env.POSTMARK_SERVER_TOKEN);

async function notifyUser(userEmail, taskDetails) {
  try {
    const response = await client.sendEmailWithTemplate({
      "From": "agent@yourdomain.com",
      "To": userEmail,
      "TemplateAlias": "task-completed-notification",
      "TemplateModel": {
        "user_name": "Human Operator",
        "task_name": taskDetails.name,
        "completion_time": new Date().toISOString(),
        "result_summary": taskDetails.summary
      }
    });

    // Postmark returns a 'ErrorCode' of 0 for success
    if (response.ErrorCode === 0) {
      console.log(`Message sent successfully: ${response.MessageID}`);
    }
  } catch (error) {
    // Agent-specific error handling
    if (error.code === 406) {
      console.error("Recipient is inactive/suppressed. Agent should flag this record.");
    } else if (error.code === 429) {
      console.error("Rate limit hit. Agent should back off and retry.");
    } else {
      console.error(`Postmark API Error: ${error.message}`);
    }
  }
}
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **P50 Latency** | 110ms | Extremely responsive for single transactional sends. |
| **P95 Latency** | 260ms | Stable even during peak global traffic. |
| **P99 Latency** | 420ms | Occasional spikes usually related to large batch processing. |
| **Rate Limits** | 500 req/10s | Standard limit; can be increased for high-volume accounts. |
| **Uptime** | 99.9% | Public status page available at status.postmarkapp.com. |

---

## 7. Agent-Native Notes

*   **Idempotency:** Postmark does not natively support an `Idempotency-Key` header. Agents must implement their own tracking (e.g., storing the `MessageID` in a local DB) to prevent duplicate sends during retries.
*   **Retry Behavior:** Agents should automatically retry on 5xx errors and 429 (Rate Limit). Do **not** retry on 401 (Unauthorized) or 422 (Unprocessable Entity).
*   **Error Codes → Agent Decisions:** 
    *   `ErrorCode: 406` (Inactive Recipient): The agent should stop attempting to email this user and notify the system admin.
    *   `ErrorCode: 300` (Invalid Email): The agent should validate its input data source for typos.
*   **Schema Stability:** Postmark’s API is famously stable. Breaking changes are rare, making it safe for agents with long-term autonomous deployments.
*   **Cost-per-operation:** Fixed pricing per email. Agents can accurately predict costs based on the number of planned interactions.
*   **Template Logic:** Using `TemplateAlias` instead of raw HTML/Text is highly recommended for agents. This separates the "message content" (managed by humans/designers) from the "data payload" (managed by the agent).
*   **Zero-Marketing Policy:** Agents must not use Postmark for cold outreach. Postmark’s automated systems will suspend accounts that trigger high spam complaints, effectively "killing" the agent's communication channel.

---

## 8. Rhumb Context: Why Postmark Scores 6.76 (L3)

Postmark's **6.76 score** reflects its status as a highly reliable, "ready" service that is slightly held back by the manual friction inherent in email infrastructure:

1. **Execution Autonomy (7.7)** — The API is exceptionally well-structured. Error codes are granular and actionable, allowing agents to distinguish between a temporary network issue and a permanent recipient suppression without human intervention. The batch API allows for efficient resource management.

2. **Access Readiness (5.6)** — This is the primary bottleneck. Postmark requires manual domain verification (DKIM/SPF) and often a manual review of the first sending server. An agent cannot "self-provision" a fully functional Postmark account from scratch without a human interacting with DNS records.

3. **Agent Autonomy (7.0)** — Postmark's webhook system is best-in-class. It allows agents to build sophisticated reactive loops (e.g., "if email bounces, try sending a Slack message instead"). The separation of Server Tokens provides a strong governance model for multi-agent systems.

**Bottom line:** Postmark is the gold standard for agents that require high-integrity communication with humans. While the initial setup requires human DNS configuration, the operational phase is highly autonomous and predictable.

**Competitor context:** **Resend (7.2)** scores higher on Access Readiness due to a more modern developer onboarding experience and lower initial friction. **SendGrid (5.4)** scores lower due to a more complex API surface, inconsistent error reporting, and a higher frequency of deliverability issues that require human troubleshooting.
