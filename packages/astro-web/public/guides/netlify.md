# Netlify — Agent-Native Service Guide

> **AN Score:** 6.22 · **Tier:** L3 · **Category:** Deployment & Hosting

---

## 1. Synopsis
Netlify is a comprehensive Jamstack platform that automates the deployment, hosting, and scaling of modern web projects. For agents, Netlify serves as the primary "output stage" for code-generation workflows—allowing an agent to not only write code but also provision infrastructure, manage DNS, and deploy live production URLs. It provides a robust REST API that covers the entire lifecycle from site creation to serverless function management. The "Starter" free tier is exceptionally generous for agents, offering 100GB of bandwidth and 300 build minutes per month, making it an ideal sandbox for autonomous web development and documentation hosting.

---

## 2. Connection Methods

### REST API
The primary interface for agents is the Netlify REST API (`https://api.netlify.com/api/v1`). It is a mature, resource-oriented API that supports JSON for all request and response bodies. Agents can manage sites, deploys, environment variables, and forms through standard HTTP verbs.

### SDKs
Netlify maintains an official JavaScript/TypeScript SDK (`netlify` on npm) which is the recommended path for agents operating in Node.js environments. There is also an official Go library (`open-api`) for system-level integrations. While Python does not have an official first-party SDK, the API is simple enough that standard `httpx` or `requests` implementations are reliable.

### MCP (Model Context Protocol)
Netlify is a frequent target for MCP server implementations. These servers allow agents to "browse" sites, check build statuses, and trigger new deploys directly through a standardized tool interface, reducing the need for the agent to generate raw API calls.

### Webhooks
Netlify supports outgoing webhooks for critical lifecycle events: `deploy_building`, `deploy_created`, `deploy_failed`, and `form_submission`. Agents should register webhook listeners to move from polling-based status checks to event-driven state transitions.

### Auth Flows
Agents typically authenticate using a **Personal Access Token (PAT)**, which can be generated in the Netlify UI under User Settings. For multi-user applications where the agent acts on behalf of a user, Netlify supports standard OAuth2 flows. Tokens should be passed in the `Authorization: Bearer <TOKEN>` header.

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **Site** | `POST /sites` | Creates a new site container for deployments. |
| **Deploy** | `POST /sites/{site_id}/deploys` | Uploads files or triggers a build from a linked repository. |
| **Build** | `POST /builds/{build_id}/stop` | Manages active build processes to save minutes. |
| **Env Var** | `PATCH /accounts/{acc_id}/env` | Manages site-specific or account-wide environment variables. |
| **Form** | `GET /sites/{site_id}/forms` | Retrieves data submitted via Netlify Forms. |
| **Function** | `GET /sites/{site_id}/functions` | Lists serverless functions deployed to the site. |
| **Domain** | `POST /dns_zones` | Configures custom domains and managed DNS records. |

---

## 4. Setup Guide

### For Humans
1. Create a Netlify account at app.netlify.com.
2. Navigate to **User Settings > Applications > Personal access tokens**.
3. Click **Generate new token** and give it a descriptive name (e.g., "Agent-Deploy-Service").
4. Copy the token immediately; it will not be shown again.
5. Create a "Team" if you intend for the agent to manage shared resources.
6. Note your **Account ID** (slug) from the Team Settings URL.

### For Agents
1. **Validate Connection:** Perform a `GET /user` request to verify the PAT and retrieve the agent's identity.
2. **Identify Context:** List available sites or accounts to ensure the token has the necessary scopes.
3. **Connection Test:**
```javascript
const NetlifyAPI = require('netlify');
const client = new NetlifyAPI('YOUR_ACCESS_TOKEN');

async function validate() {
  const user = await client.getCurrentUser();
  console.log(`Connected as: ${user.email}`);
  const sites = await client.listSites();
  return sites.length >= 0;
}
```

---

## 5. Integration Example

This example demonstrates an agent creating a new site and performing a "ZIP deploy" (uploading a pre-built folder).

```javascript
const NetlifyAPI = require('netlify');
const fs = require('fs');

async function deployWebAsset(token, folderPath, siteName) {
  const client = new NetlifyAPI(token);

  // 1. Create the site container
  const site = await client.createSite({
    body: { name: siteName }
  });

  console.log(`Site created: ${site.admin_url}`);

  // 2. Deploy the folder (automatically handled as a ZIP by the SDK)
  const deploy = await client.deploy(site.id, folderPath, {
    message: 'Agent-initiated deployment',
    statusCb: (event) => console.log(`Deploy Status: ${event.phase}`)
  });

  // 3. Confirm deployment
  if (deploy.state === 'ready') {
    return {
      url: deploy.ssl_url || deploy.url,
      logs: deploy.deploy_ssl_url
    };
  } else {
    throw new Error(`Deployment failed with state: ${deploy.state}`);
  }
}
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **P50 Latency** | 120ms | Standard API metadata operations. |
| **P95 Latency** | 280ms | Complex queries or small file uploads. |
| **P99 Latency** | 460ms | Large batch operations or cold starts. |
| **Rate Limit** | 3 requests/sec | Per-user rate limit; generous but needs backoff. |
| **Build Time** | 1m - 5m | Highly dependent on build script complexity. |
| **Global CDN** | < 50ms | Edge propagation speed for new deploys. |

---

## 7. Agent-Native Notes

*   **Idempotency:** Netlify does not support a native `Idempotency-Key` header. Agents should use `listSites` to check for existing site names before calling `createSite` to avoid 422 errors on name collisions.
*   **Retry Behavior:** Use exponential backoff for `429 Too Many Requests`. The API returns a `X-RateLimit-Reset` header indicating when the window clears.
*   **Error Codes:** 
    *   `401`: Token expired or invalid. 
    *   `422`: Site name already taken or invalid configuration.
    *   `404`: Site or Deploy ID no longer exists.
*   **Schema Stability:** The v1 API is extremely stable. Netlify rarely introduces breaking changes, opting for new endpoints instead.
*   **Cost-per-operation:** Site creation and metadata updates are free. Build minutes and bandwidth are the primary cost drivers. Agents should be programmed to `stopBuild` if a logic error is detected mid-run.
*   **Atomic Deploys:** Deploys are atomic. A failed upload does not overwrite the "live" version of a site, providing a built-in safety net for autonomous updates.
*   **Polling vs. Webhooks:** For long-running builds, agents should prefer webhooks. If polling, check the `state` field of the Deploy object every 10 seconds.

---

## 8. Rhumb Context: Why Netlify Scores 6.22 (L3)

Netlify's **6.22 score** positions it as a "Ready" service for agent integration, offering high reliability for deployment workflows but with some friction in fine-grained access control:

1. **Execution Autonomy (7.1)** — The API surface is nearly 100% complete, allowing agents to perform any action a human can in the UI. The "ZIP deploy" feature is particularly agent-friendly as it skips the need for a Git intermediary. However, the streaming nature of build logs can be difficult for LLMs to parse without significant pre-processing.

2. **Access Readiness (5.2)** — This is the primary drag on the score. While PATs are easy to generate, Netlify lacks granular "scoped tokens" (e.g., a token that can only deploy to Site A but not Site B). This creates a "all-or-nothing" security risk for agents with account-level access.

3. **Agent Autonomy (6.33)** — The platform excels at self-healing and atomic rollbacks. If an agent deploys a breaking change, the previous version remains live until the new one is fully "Ready." The usage-based billing is agent-compatible, but the lack of programmatic spending limits (hard caps) requires agents to monitor their own "Build Minutes" consumption via the API.

**Bottom line:** Netlify is the premier choice for agents tasked with "building and shipping" web applications. It provides the most straightforward path from a local folder of HTML/JS to a global production URL. While security scoping requires caution, the API's reliability makes it a Tier-1 deployment target.

**Competitor context:** **Vercel (6.45)** scores slightly higher due to better integrated "Preview URL" logic and more granular deployment tokens. **AWS Amplify (4.1)** scores significantly lower due to the extreme complexity of IAM and the overhead of the AWS SDK, which often confuses autonomous agents.
