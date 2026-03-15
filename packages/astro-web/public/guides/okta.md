# Okta — Agent-Native Service Guide

> **AN Score:** 5.69 · **Tier:** L3 · **Category:** Authentication & Identity

---

## 1. Synopsis
Okta is the enterprise-standard Identity and Access Management (IAM) platform. For agents, Okta acts as the central control plane for organizational access, enabling programmatic user provisioning, group management, and security auditing. Agents use Okta to automate onboarding/offboarding workflows, enforce Zero Trust policies, and monitor system logs for anomalous behavior. The service is critical for "Agentic Ops" where a machine must manage human or service identities. While the Okta Developer Edition provides a generous free tier (up to 15,000 Monthly Active Users), the platform is fundamentally enterprise-first. Agents will encounter complex configuration dashboards and sales-heavy pricing models when moving beyond basic development into production environments.

---

## 2. Connection Methods

### REST API
Okta’s primary interface is a comprehensive REST API. The API is versioned (currently `/api/v1`) and follows predictable resource-oriented patterns. It supports a wide array of operations from identity management to policy configuration. Most agentic use cases will interact with the Users, Groups, and Logs endpoints.

### SDKs
Okta maintains high-quality, production-ready SDKs for major languages. For agents, the **Python (`okta`)** and **Node.js (`@okta/okta-sdk-nodejs`)** libraries are the most relevant. These SDKs handle back-off logic, collection pagination, and type validation, which significantly reduces the logic an agent must implement to handle complex identity objects.

### Auth Flows
Agents should utilize **OAuth 2.0 Client Credentials** (Machine-to-Machine) flows for autonomous operation. This involves creating a "Service App" in the Okta Admin Console, generating a public/private key pair (JWT-based), and requesting scoped tokens. For simpler scripts, an **API Token** (SSWS header) can be used, though it inherits the full permissions of the user who generated it, which is less secure for autonomous agents than scoped OAuth.

### Webhooks (Event Hooks)
Okta provides "Event Hooks" to push real-time notifications to agents. This is the preferred method for event-driven agents (e.g., an agent that triggers a "Welcome" workflow the moment a user is created). Event Hooks require a publicly accessible HTTPS endpoint and support HMAC signatures for verification.

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **User** | `/api/v1/users` | The core identity object containing profile data, status, and credentials. |
| **Group** | `/api/v1/groups` | Containers for users used to manage bulk permissions and application assignments. |
| **Log Event** | `/api/v1/logs` | The System Log; a read-only stream of all recorded events in the Okta org. |
| **Application** | `/api/v1/apps` | Represents a service (like Slack or AWS) that users can be assigned to. |
| **Factor** | `/api/v1/users/{id}/factors` | MFA methods (SMS, TOTP, Okta Verify) associated with a specific user. |
| **Policy** | `/api/v1/policies` | Rules governing sign-on behavior, MFA requirements, and password complexity. |

---

## 4. Setup Guide

### For Humans
1.  Sign up for an [Okta Developer Account](https://developer.okta.com/signup/).
2.  Navigate to **Applications > Applications** in the Admin Console.
3.  Click **Create App Integration** and select **API Services**.
4.  Under **General Settings**, note your Client ID and generate/upload a Public Key for JWT authentication.
5.  Go to the **Okta API Scopes** tab and grant specific scopes (e.g., `okta.users.manage`, `okta.groups.read`).
6.  Navigate to **Security > API** to find your Org URL (e.g., `https://dev-12345.okta.com`).

### For Agents
1.  **Initialize Client:** Load the Org URL and private key from secure environment variables.
2.  **Request Token:** Exchange the signed JWT for an access token via the `/oauth2/v1/token` endpoint.
3.  **Validate Connectivity:** Perform a "WhoAmI" check by querying the current service app's details.
4.  **Test Scope:** Attempt to list a single user to verify the `okta.users.read` scope is active.

```python
# Validation check for an agent
import asyncio
from okta.client import Client as OktaClient

async def validate():
    config = {'orgUrl': 'https://dev-123.okta.com', 'token': 'SSWS_TOKEN'}
    client = OktaClient(config)
    users, resp, err = await client.list_users()
    if not err:
        print(f"Connection Valid: Found {len(users)} users.")
```

---

## 5. Integration Example

This Python example demonstrates an agent creating a new user and assigning them to a specific group, a common onboarding task.

```python
import asyncio
from okta.client import Client as OktaClient

async def onboard_user(email, first_name, last_name, group_id):
    # Configuration using an API Token (SSWS)
    config = {
        'orgUrl': 'https://dev-your-org.okta.com',
        'token': '00u...' # Replace with secure token
    }
    client = OktaClient(config)

    # 1. Define the user profile
    user_body = {
        "profile": {
            "firstName": first_name,
            "lastName": last_name,
            "email": email,
            "login": email
        }
    }

    # 2. Create the user (activate=True)
    user, resp, err = await client.create_user(user_body, query_params={'activate': 'true'})
    
    if err:
        print(f"Error creating user: {err}")
        return

    # 3. Add user to the specified group
    resp, err = await client.add_user_to_group(group_id, user.id)
    
    if not err:
        print(f"Successfully onboarded {email} to group {group_id}")

# Run the task
# asyncio.run(onboard_user("agent.test@example.com", "Agent", "Smith", "00g..."))
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **P50 Latency** | 170ms | Standard for metadata lookups and single-user fetches. |
| **P95 Latency** | 400ms | Observed during complex searches or group membership expansions. |
| **P99 Latency** | 700ms | Typically occurs during heavy System Log queries or batch updates. |
| **Rate Limits** | Variable | Tier-based. Standard is ~2,000 requests/min per endpoint. |
| **Uptime** | 99.99% | Enterprise-grade reliability; status available at trust.okta.com. |

---

## 7. Agent-Native Notes

*   **Idempotency:** Okta does not support a global `Idempotency-Key` header. However, for user creation, agents should check for existing logins (`/api/v1/users?q={email}`) before attempting a POST to avoid 400 "User already exists" errors.
*   **Retry Behavior:** Okta returns a `429 Too Many Requests` when limits are hit. Agents **must** respect the `X-Rate-Limit-Reset` header, which provides the Unix timestamp for when the limit resets.
*   **Error Codes:** Use the `errorCode` field in the JSON body (e.g., `E0000001` for internal errors, `E0000060` for invalid tokens). Agents should retry on `E0000001` but escalate on `E0000006` (Invalid password).
*   **Schema Stability:** Extremely high. Okta rarely makes breaking changes to the `/v1` surface. Custom user attributes are supported but require the agent to fetch the schema (`/api/v1/meta/schemas/user/default`) to understand the structure.
*   **Cost-per-operation:** Zero for the Developer tier. For Enterprise, costs are calculated per-user, not per-API-call, making it highly economical for high-frequency agent operations on a fixed user base.
*   **Auditability:** Every action an agent takes via the API is logged with the agent's Client ID. This provides a perfect 10/10 governance trail for compliance-heavy industries.
*   **Pagination:** Okta uses `Link` headers for cursor-based pagination. Agents must parse the `next` relation rather than calculating offsets.

---

## 8. Rhumb Context: Why Okta Scores 5.69 (L3)

Okta’s **5.69 score** reflects its status as a robust but high-friction enterprise tool. It is "Ready" for agents but requires significant setup effort.

1.  **Execution Autonomy (6.8)** — The API is granular and supports sophisticated M2M flows. The presence of well-documented SDKs allows agents to navigate complex objects with ease. However, the lack of native idempotency keys on all POST actions prevents a higher score.

2.  **Access Readiness (4.2)** — This is Okta's weakest area for agents. The onboarding process is designed for human IT admins, involving multi-step dashboard configurations, OIDC dance, and scope assignments. There is no "one-click" API key for agents; the barrier to entry is high.

3.  **Agent Autonomy (6.33)** — Okta excels in providing the "environment" for agents. With Event Hooks and the System Log API, agents can be fully aware of their surroundings. The high Governance score (10) ensures that agents can operate in regulated environments without manual oversight.

**Bottom line:** Okta is the mandatory choice for agents operating in corporate environments. While the setup friction is high (4.2), the resulting governance and reliability (10) make it the only viable option for enterprise-scale identity automation.

**Competitor context:** **Auth0** (now owned by Okta) offers a better developer experience but is increasingly merged into the Okta ecosystem. **Clerk** (7.2) and **WorkOS** (6.8) score higher on Access Readiness for simpler SaaS use cases, but they lack the deep Governance and Policy depth that gives Okta its L3 "Enterprise Ready" status.
