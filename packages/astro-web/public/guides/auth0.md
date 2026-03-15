# Auth0 — Agent-Native Service Guide

> **AN Score:** 6.34 · **Tier:** L3 · **Category:** Authentication & Identity

---

## 1. Synopsis
Auth0 is a comprehensive Identity-as-a-Service (IDaaS) platform that provides universal authentication and authorization via SAML, OAuth 2.0, and OIDC. For agents, Auth0 serves as the authoritative source for user identity, permission management (RBAC), and secure machine-to-machine (M2M) communication. Agents utilize the Auth0 Management API to provision users, rotate credentials, and audit security logs programmatically. The service is highly attractive for autonomous systems due to its rigorous governance standards and extensive SDK support. Auth0 offers a generous "Free Forever" tier for up to 7,500 active users, while the Developer tier ($35/mo) unlocks professional features like custom domains and additional social connections.

---

## 2. Connection Methods

### REST API
Auth0 provides two distinct REST APIs. The **Authentication API** handles login, logout, and token exchange. The **Management API (v2)** is the primary interface for agents, allowing for the manipulation of users, organizations, and security settings. All Management API requests require a JWT (JSON Web Token) obtained via the Client Credentials flow.

### SDKs
Auth0 maintains high-quality, production-ready SDKs for all major languages. For agentic workflows, the `auth0-python` and `node-auth0` packages are the gold standard. These SDKs abstract the token management and retry logic, providing a typed interface for the Management API.

### MCP
While there is no official Auth0 MCP (Model Context Protocol) server yet, the community has produced several wrappers that expose the Management API to LLMs. Agents can easily use these to perform tasks like "Find the user with email X and reset their password."

### Webhooks & Log Streams
Auth0 supports event-driven architectures through **Log Streams**. Agents can subscribe to events (e.g., failed logins, password changes) via webhooks, Amazon EventBridge, or Azure Event Grid. This allows agents to trigger security remediation workflows in real-time without polling.

### Auth Flows
Agents typically interact with Auth0 using the **Client Credentials Flow**. The agent is configured as a "Machine to Machine" (M2M) application in the Auth0 dashboard, granted specific scopes (e.g., `read:users`, `update:users`), and uses its Client ID and Secret to request an Access Token from the `/oauth/token` endpoint.

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **Get Access Token** | `POST /oauth/token` | Exchanges client credentials for a Management API JWT. |
| **Create User** | `POST /api/v2/users` | Provisions a new user identity in a specific connection. |
| **Search Users** | `GET /api/v2/users` | Queries users using Lucene syntax (e.g., `email:"*@rhumb.com"`). |
| **Assign Roles** | `POST /api/v2/users/{id}/roles` | Grants specific RBAC roles to a user identity. |
| **Get Logs** | `GET /api/v2/logs` | Retrieves audit logs for security monitoring and event analysis. |
| **Create Client** | `POST /api/v2/clients` | Programmatically creates a new application or agent identity. |
| **Update Org** | `PATCH /api/v2/organizations/{id}` | Modifies organization settings for multi-tenant applications. |

---

## 4. Setup Guide

### For Humans
1.  **Create a Tenant:** Sign up at Auth0 and create a tenant in your preferred region.
2.  **Create an M2M Application:** Navigate to Applications > Applications > Create Application. Select "Machine to Machine."
3.  **Authorize API:** Select the "Auth0 Management API" and choose the required scopes (e.g., `read:users`, `create:users`).
4.  **Capture Credentials:** Copy the Domain, Client ID, and Client Secret.
5.  **Configure Connections:** Ensure at least one database connection is enabled for your new application.

### For Agents
1.  **Initialize Client:** Load credentials from environment variables.
2.  **Fetch Management Token:** Use the Auth0 SDK to request a token for the Management API audience.
3.  **Verify Scopes:** Perform a "WhoAmI" check by attempting to retrieve the agent's own client details.
4.  **Validation Code:**
```python
from auth0.authentication import GetToken
from auth0.management import Auth0

# 1. Get Token
gt = GetToken("YOUR_DOMAIN")
token = gt.client_credentials("CLIENT_ID", "CLIENT_SECRET", "https://YOUR_DOMAIN/api/v2/")
mgmt_token = token['access_token']

# 2. Validate Connection
auth0 = Auth0("YOUR_DOMAIN", mgmt_token)
try:
    auth0.tenants.get_settings()
    print("Connection Verified: Agent has Management API access.")
except Exception as e:
    print(f"Connection Failed: {e}")
```

---

## 5. Integration Example

```python
from auth0.management import Auth0

# Initialize the Auth0 Management API client
# In production, use the GetToken flow to refresh expired tokens
auth0 = Auth0(domain="rhumb-dev.us.auth0.com", token="YOUR_MGMT_API_TOKEN")

def onboard_new_user(email, name, role_id):
    """
    Agentic workflow to provision a user and assign a role.
    """
    # 1. Create the user identity
    user_data = {
        "email": email,
        "name": name,
        "connection": "Username-Password-Authentication",
        "password": "TemporaryPassword123!", # Should be randomized
        "verify_email": True
    }
    
    try:
        new_user = auth0.users.create(user_data)
        user_id = new_user['user_id']
        
        # 2. Assign the requested RBAC role
        auth0.users.add_roles(user_id, {"roles": [role_id]})
        
        return {"status": "success", "user_id": user_id}
    
    except Exception as e:
        # Handle 409 Conflict (User already exists) or 429 Rate Limit
        return {"status": "error", "message": str(e)}
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **P50 Latency** | 135ms | Standard Management API response time. |
| **P95 Latency** | 290ms | Higher during complex user searches or bulk updates. |
| **P99 Latency** | 480ms | Occasional spikes during cross-region token exchange. |
| **Rate Limit** | 2-10 req/sec | Management API limits vary by endpoint and plan. |
| **Uptime SLA** | 99.9% - 99.99% | Enterprise plans offer higher availability guarantees. |

---

## 7. Agent-Native Notes

*   **Idempotency:** Auth0's Management API does not support a native `Idempotency-Key` header. Agents must implement a "Read-then-Write" pattern or catch `409 Conflict` errors when creating resources like users or clients.
*   **Retry Behavior:** Use exponential backoff for `429 Too Many Requests`. Auth0 provides `X-RateLimit-Reset` headers which agents should parse to determine wait times.
*   **Error Codes:** Agents should distinguish between `invalid_body` (schema error - do not retry) and `request_timeout` or `too_many_requests` (transient - retry).
*   **Schema Stability:** Extremely high. Auth0 rarely breaks the Management API v2, making it safe for long-term autonomous integrations.
*   **Cost-per-operation:** Negligible for Management API calls. The primary cost driver is Monthly Active Users (MAU). Agents creating thousands of test users can inadvertently spike costs.
*   **Token Lifecycle:** Access tokens for the Management API typically expire in 24 hours. Agents must handle token expiration by catching `401 Unauthorized` and re-authenticating.
*   **Search Syntax:** The `q` parameter in user searches uses Lucene syntax. Agents must be instructed on proper escaping to avoid injection-like errors in queries.

---

## 8. Rhumb Context: Why Auth0 Scores 6.34 (L3)

Auth0's **6.34 score** reflects its status as a robust, enterprise-grade identity provider that suffers from high configuration friction for autonomous agents:

1. **Execution Autonomy (7.3)** — The Management API is exceptionally well-documented and the SDKs are robust. Auth0 provides clear, machine-readable error codes that allow agents to make logic-based decisions (e.g., differentiating between a missing scope and a missing resource). The structured nature of the RBAC system allows agents to manage permissions with high precision.

2. **Access Readiness (5.0)** — This is Auth0’s weakest dimension. Setting up a tenant, configuring an M2M application, and granting specific scopes requires significant manual overhead in the dashboard. Unlike "developer-first" alternatives, Auth0 does not offer a "one-click" API key generation for agents; it requires navigating a complex OIDC-compliant setup that is difficult for agents to self-bootstrap.

3. **Agent Autonomy (7.0)** — Auth0 scores well here due to its Log Streams and Actions (extensibility). Agents can be programmed to respond to specific identity events (like a user logging in from a new IP) via webhooks. This event-driven capability allows for a high degree of proactive autonomy in security and user management workflows.

**Bottom line:** Auth0 is the mandatory choice for agents operating in enterprise environments where SOC 2, HIPAA, or complex SSO (SAML/OIDC) are required. While the initial setup is cumbersome, the API's reliability and the platform's governance features make it a Tier-1 choice for production systems.

**Competitor context:** **Clerk (7.2)** scores higher on Access Readiness due to its simplified developer experience but lacks the deep Enterprise Governance (9.0) that Auth0 provides. **Stytch (6.8)** offers a more modern API surface for passwordless flows but has a smaller ecosystem of pre-built integrations than Auth0.
