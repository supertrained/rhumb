# Heroku — Agent-Native Service Guide

> **AN Score:** 5.26 · **Tier:** L2 · **Category:** Deployment & Hosting

---

## 1. Synopsis
Heroku is a pioneer Platform-as-a-Service (PaaS) that enables agents to deploy, manage, and scale applications without managing underlying infrastructure. For autonomous agents, Heroku provides a programmatic interface to the entire application lifecycle: provisioning databases, scaling compute (dynos), managing environment variables, and triggering builds from source code. While Heroku famously discontinued its free tier in late 2022, its "Platform API v3" remains one of the most stable and well-documented deployment APIs available. Agents use Heroku to "spawn" child services or deploy code they have generated, making it a foundational tool for self-replicating or self-healing agentic systems. It is now part of the Salesforce ecosystem, requiring a verified credit card for all operations.

---

## 2. Connection Methods

### REST API
The **Heroku Platform API v3** is the primary interface for agents. It is a strictly modeled REST API that uses JSON for serialization and requires the `Accept: application/vnd.heroku+json; version=3` header. The API is highly predictable, following standard HTTP verbs and status codes. It supports advanced features like range headers for pagination and caching via ETags.

### SDKs
Heroku provides official support for the Platform API via the **Heroku CLI**, which agents can wrap in shell executions. For native language integration, the most reliable options are:
*   **Node.js:** `heroku-client` (Official)
*   **Ruby:** `platform-api` (Official)
*   **Python:** While there is no current official SDK, the community-maintained `heroku3` library is the standard, though many agent operators prefer raw `requests` calls to the v3 API for better error handling.

### MCP (Model Context Protocol)
There is currently no official Heroku MCP server. Agents typically interact via the CLI or by using a custom tool definition that wraps the REST API.

### Webhooks
Heroku supports **App Webhooks**, allowing agents to receive real-time notifications for events such as build updates, release completions, and dyno state changes. This is critical for agents that need to wait for a deployment to finish before performing post-deployment verification.

### Auth Flows
Authentication is handled via **API Keys** (Long-lived tokens). Agents should use the `Authorization: Bearer <TOKEN>` header. For enterprise environments, OAuth 2.0 flows are available to grant agents scoped access to specific teams or apps.

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **App** | `POST /apps` | Creates a new application instance with a unique name and region. |
| **Dyno** | `PATCH /apps/{id}/formation` | Scales compute resources (web, worker) up or down. |
| **Build** | `POST /apps/{id}/builds` | Triggers a new deployment using a source URL (tarball). |
| **Config Var** | `PATCH /apps/{id}/config-vars` | Updates environment variables (e.g., API keys for child agents). |
| **Add-on** | `POST /apps/{id}/addons` | Provisions managed services like Heroku Postgres or Redis. |
| **Log Session** | `POST /apps/{id}/log-sessions` | Generates a temporary URL to stream application logs for debugging. |
| **Release** | `GET /apps/{id}/releases` | Lists the history of deployments and allows for rollbacks. |

---

## 4. Setup Guide

### For Humans
1.  Create a Heroku account at [heroku.com](https://www.heroku.com).
2.  Navigate to **Account Settings** > **Billing** and add a valid credit card (required for all API usage).
3.  Go to **Account Settings** > **API Key** and click "Reveal" to copy your token.
4.  Install the Heroku CLI locally to verify permissions: `heroku auth:token`.
5.  Create a "Team" if the agent needs to operate within a shared governance structure.

### For Agents
1.  **Environment Setup:** Store the `HEROKU_API_KEY` in a secure vault or environment variable.
2.  **Header Configuration:** Ensure the agent is configured to send `Accept: application/vnd.heroku+json; version=3`.
3.  **Connection Validation:** Execute a GET request to the account endpoint to verify the key and retrieve the account ID.
4.  **Verification Code (Python):**
```python
import requests

headers = {
    "Authorization": "Bearer YOUR_API_KEY",
    "Accept": "application/vnd.heroku+json; version=3"
}
resp = requests.get("https://api.heroku.com/account", headers=headers)
if resp.status_code == 200:
    print(f"Connected: {resp.json()['email']}")
```

---

## 5. Integration Example

This Python example demonstrates an agent creating a new app and setting a configuration variable.

```python
import requests
import json

API_URL = "https://api.heroku.com"
HEADERS = {
    "Authorization": "Bearer <HEROKU_API_KEY>",
    "Accept": "application/vnd.heroku+json; version=3",
    "Content-Type": "application/json"
}

def provision_agent_service(app_name):
    # 1. Create the App
    app_data = {"name": app_name, "region": "us"}
    create_res = requests.post(f"{API_URL}/apps", 
                               headers=HEADERS, 
                               data=json.dumps(app_data))
    
    if create_res.status_code != 201:
        return f"Error: {create_res.json().get('message')}"

    # 2. Set Config Vars (e.g., Database URL or API Keys)
    config_data = {"DATABASE_URL": "postgres://...", "AGENT_MODE": "active"}
    config_res = requests.patch(f"{API_URL}/apps/{app_name}/config-vars", 
                                headers=HEADERS, 
                                data=json.dumps(config_data))
    
    return config_res.json()

# Usage
result = provision_agent_service("autonomous-sub-service-42")
print(result)
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **P50 Latency** | 180ms | Standard API metadata operations. |
| **P95 Latency** | 420ms | Complex operations like provisioning add-ons. |
| **P99 Latency** | 720ms | Peak load or cross-region app creation. |
| **Rate Limit** | 1,200 requests/hour | Per account; resets hourly. |
| **Build Time** | 2-5 minutes | Varies significantly by language and dependencies. |
| **Provisioning Speed** | ~30 seconds | Time from `POST /apps` to DNS availability. |

---

## 7. Agent-Native Notes

*   **Idempotency:** Heroku v3 does not natively support an `Idempotency-Key` header for all endpoints. Agents should implement "Check-Then-Act" patterns, such as checking if an app name exists before attempting creation.
*   **Retry Behavior:** Use exponential backoff for `429 Too Many Requests`. The API provides a `Retry-After` header which agents should parse to optimize their queue.
*   **Error Codes:** A `422 Unprocessable Entity` usually indicates a naming conflict or invalid region. Agents should be programmed to retry `422` app-creation errors with a modified name string (e.g., adding a random suffix).
*   **Schema Stability:** The v3 API is exceptionally stable. Agents can rely on the JSON structure not changing unexpectedly, making it safer for long-running autonomous workflows than newer, faster-moving PaaS providers.
*   **Cost-per-operation:** While the API calls are free, every provisioned resource incurs cost. Agents must be equipped with "cleanup" logic (`DELETE /apps/{id}`) to avoid runaway billing.
*   **Log Streaming:** Agents can programmatically consume logs via `log-sessions`. This allows an agent to "self-debug" by feeding its own crash logs back into its context window.
*   **Slug Management:** Heroku uses "Slugs" (compressed pre-packaged copies of your app). Agents can manage deployments by manipulating slug IDs, which is faster than full git-based builds.

---

## 8. Rhumb Context: Why Heroku Scores 5.26 (L2)

Heroku’s **5.26 score** reflects a mature, stable platform that is increasingly hindered by legacy friction and a "human-first" billing model:

1. **Execution Autonomy (6.1)** — The Platform API v3 is robust and allows for near-total control of the stack. The ability to manage add-ons and config vars programmatically is excellent. However, the lack of native idempotency keys across all mutations requires agents to write more complex wrapper logic to ensure they don't double-provision expensive resources.

2. **Access Readiness (4.3)** — This is Heroku’s weakest dimension. The total removal of the free tier means agents cannot perform "dry runs" or validate integration paths without immediate financial commitment. Furthermore, the Salesforce-integrated billing system often triggers manual verification or "CAPTCHA" hurdles during account setup, which are hostile to autonomous agent bootstrapping.

3. **Agent Autonomy (5.33)** — Heroku provides excellent observability through webhooks and log sessions, allowing agents to monitor their own health. However, the 1,200 request-per-hour rate limit is relatively low for high-frequency agent fleets, and the lack of a modern MCP or first-party Python SDK forces developers to rely on community tools of varying quality.

**Bottom line:** Heroku is a reliable "Tier 2" choice for agents that need a stable, long-term home for production services. Its API is the industry standard for PaaS, but the high barrier to entry (paid-only) and legacy rate limits make it less attractive for experimental or highly-dynamic agent swarms.

**Competitor context:** **Railway (7.2)** and **Render (6.8)** score higher due to more generous free tiers and more modern, developer-friendly CLI/API interfaces. **Fly.io (6.4)** offers better global distribution but suffers from more frequent API breaking changes compared to Heroku’s rock-solid v3 stability.
