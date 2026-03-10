# Render — Agent-Native Service Guide

> **AN Score:** 6.51 · **Tier:** L3 · **Category:** Deployment & Hosting

---

## 1. Synopsis
Render is a unified cloud platform for hosting full-stack applications, static sites, and managed databases. For agents, Render serves as a programmatic execution environment where they can deploy code, scale services, and manage infrastructure without the complexity of AWS or GCP. Agents primarily use Render to automate the "Build-Deploy-Monitor" loop, often triggering new deployments after code generation or adjusting environment variables dynamically. Render offers a generous free tier for static sites and web services, though free web services "spin down" after 15 minutes of inactivity—a critical behavior for agents to track. The platform is highly accessible for autonomous systems due to its clean REST API and "Blueprints" (Infrastructure-as-Code) feature.

---

## 2. Connection Methods

### REST API
Render provides a standardized REST API (v1) accessible at `https://api.render.com/v1`. It is the primary interface for agents to manage services, deploys, and environment groups. The API uses JSON for all request and response bodies. Agents must be aware that most write operations (like triggering a deploy) return a 201 Created or 202 Accepted status, requiring the agent to poll a status endpoint or wait for a webhook to confirm completion.

### SDKs
Render does not maintain an extensive library of official language-specific SDKs. Instead, it provides an official OpenAPI/Swagger specification, which allows agents to generate their own clients or use standard HTTP libraries like `httpx` (Python) or `axios` (Node.js). There is a community-maintained Go library, but for most agentic workflows, direct REST interaction is the recommended path to ensure compatibility with the latest API features.

### Webhooks
Render supports outgoing webhooks for service events. Agents can register a webhook URL to receive POST requests when a deploy starts, succeeds, or fails. This is the most efficient way for an agent to "close the loop" on a deployment task without constant polling.

### Auth Flows
Authentication is handled via API Keys (Personal Access Tokens). Agents must include the key in the `Authorization: Bearer <TOKEN>` header. For team-based environments, agents should use a dedicated service account key. Render also requires an `ownerId` for many requests, which an agent must first discover by querying the `/owners` endpoint.

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **Service** | `GET /v1/services` | The core resource (Web Service, Private Service, Background Worker). |
| **Deploy** | `POST /v1/services/{id}/deploys` | Triggers a fresh deployment of a specific service. |
| **Job** | `POST /v1/services/{id}/jobs` | Executes a one-off command (e.g., database migrations) in the service environment. |
| **Env Group** | `GET /v1/env-groups` | Manages shared environment variables across multiple services. |
| **Owner** | `GET /v1/owners` | Returns the ID of the user or team, required for resource creation. |
| **Blueprint** | `POST /v1/blueprint-runs` | Deploys a set of resources defined in a `render.yaml` file. |

---

## 4. Setup Guide

### For Humans
1. Create a Render account at [dashboard.render.com](https://dashboard.render.com).
2. Connect your Git provider (GitHub or GitLab) to allow Render to access your repositories.
3. Navigate to **Account Settings** > **API Keys** and generate a new key.
4. Copy the API Key immediately; it will not be shown again.
5. (Optional) Add a payment method to the **Billing** section to avoid free-tier sleep cycles.
6. Create your first service manually to establish a baseline `ownerId` and service configuration.

### For Agents
1. **Discovery:** The agent must first retrieve the `ownerId` using the API key provided.
2. **Validation:** Perform a "Who Am I" check to ensure the token has correct permissions.
3. **Targeting:** List existing services to find the `serviceId` for the target application.
4. **Execution:** Trigger a deploy or update an environment variable.

```python
import httpx

API_KEY = "rnd_..."
headers = {"Authorization": f"Bearer {API_KEY}", "Accept": "application/json"}

with httpx.Client(base_url="https://api.render.com/v1", headers=headers) as client:
    # 1. Validate connection and find Owner ID
    owners = client.get("/owners").json()
    owner_id = owners[0]['owner']['id']
    
    # 2. Verify service access
    services = client.get(f"/services?ownerId={owner_id}").json()
    print(f"Connected to Render. Found {len(services)} services.")
```

---

## 5. Integration Example

This Python example demonstrates an agent triggering a deployment and then polling for the result—a common pattern for automated CI/CD agents.

```python
import httpx
import time

def deploy_and_wait(service_id: str, api_key: str):
    url = f"https://api.render.com/v1/services/{service_id}/deploys"
    headers = {"Authorization": f"Bearer {api_key}"}
    
    with httpx.Client() as client:
        # Trigger the deploy
        response = client.post(url, headers=headers)
        response.raise_for_status()
        deploy_data = response.json()
        deploy_id = deploy_data['id']
        
        # Poll for status
        for _ in range(20):  # 10 minute timeout (30s intervals)
            status_resp = client.get(f"{url}/{deploy_id}", headers=headers)
            status = status_resp.json().get('status')
            
            if status == 'live':
                return "Deployment Successful"
            elif status in ['build_failed', 'canceled', 'deactivated']:
                return f"Deployment Failed: {status}"
            
            time.sleep(30)
        return "Timeout waiting for deployment"

# Usage
# result = deploy_and_wait("srv-c1234567890", "rnd_your_key_here")
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **Latency P50** | 105ms | Rapid response for metadata and list queries. |
| **Latency P95** | 240ms | Slightly higher for complex resource filtering. |
| **Latency P99** | 400ms | Peak latency usually during high-concurrency API bursts. |
| **Rate Limit** | ~1,000 req/min | Generally high, but varies by endpoint; check headers. |
| **Build Time** | 2–10 mins | Dependent on language and cache; not an API latency. |
| **Cold Start** | 30s+ | Applies to Free Tier web services only. |

---

## 7. Agent-Native Notes

*   **Idempotency:** Render's deploy triggers are **not idempotent**. Every `POST` to the `/deploys` endpoint creates a new deployment instance. Agents should check the status of the "last" deploy before triggering a new one to avoid build-queue stacking.
*   **Retry Behavior:** Standard 5xx errors should be retried with exponential backoff. If a 429 (Too Many Requests) is received, the agent must respect the `Retry-After` header.
*   **Error Codes:** Render uses standard HTTP codes. A `400` often indicates a missing `ownerId` or malformed JSON, while a `404` usually means the `serviceId` is incorrect or the agent is querying the wrong owner context.
*   **Schema Stability:** The v1 API is highly stable. Render rarely introduces breaking changes, making it safe for long-term agent integration.
*   **Cost-per-operation:** API calls are free. Cost is incurred by the underlying resources (Services/Databases). Agents must be programmed to recognize "Pro" vs "Free" tiers to manage expectations around spin-down latency.
*   **Environment Injection:** Agents can update environment variables via `PATCH /v1/services/{id}`. Note that this automatically triggers a redeploy unless specified otherwise.
*   **Log Access:** Agents can retrieve logs via `GET /v1/services/{id}/logs`. This is vital for "Self-Healing" agents that need to diagnose why a build failed.

---

## 8. Rhumb Context: Why Render Scores 6.51 (L3)

Render’s **6.51 score** reflects a robust, developer-centric platform that is "Ready" for agents, though it lacks some of the advanced governance features found in enterprise-grade providers.

1. **Execution Autonomy (7.4)** — Render provides a very clean REST interface that maps directly to infrastructure state. The "Blueprint" system (IaC) is particularly agent-friendly, allowing an agent to define a whole stack in a single YAML file and deploy it via API. The distinction between build status and runtime status is clear and actionable.

2. **Access Readiness (5.7)** — While the API is easy to use once connected, there is initial friction in the "Owner ID" discovery process. Agents cannot simply "start" with just a key; they must perform a discovery step to find the team context. Additionally, the Free Tier's 15-minute sleep cycle can confuse simple agents that expect immediate service availability.

3. **Agent Autonomy (6.0)** — Render supports the core "loop" of autonomous DevOps well. However, it lacks granular RBAC (Role-Based Access Control) at the API key level—keys are generally "all or nothing" for a given user/team. The lack of detailed audit logs via API also makes it harder for governance agents to verify "who did what" in a complex multi-agent system.

**Bottom line:** Render is an excellent "middle-ground" service for agents. It is significantly more programmable than legacy PaaS providers but simpler to manage than hyperscalers. It is the ideal target for agents tasked with deploying prototypes, staging environments, or internal tools.

**Competitor context:** **Railway (6.8)** scores slightly higher due to its more aggressive "everything is an API" philosophy and slightly lower friction in project initialization. **Heroku (5.2)** scores lower due to its aging API surface and the removal of its free tier, which prevents low-cost agent experimentation.
