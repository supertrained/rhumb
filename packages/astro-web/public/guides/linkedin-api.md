# LinkedIn API — Agent-Native Service Guide

> **AN Score:** 3.78 · **Tier:** L2 · **Category:** Social Media & Communication

---

## 1. Synopsis
LinkedIn API provides programmatic access to the world’s largest professional network, enabling agents to manage professional identities, publish content, and analyze engagement. For agents, LinkedIn is the primary surface for B2B "thought leadership" automation, recruiting workflows, and organizational brand management. However, it is a highly restrictive ecosystem. Unlike developer-first platforms, LinkedIn requires manual application approval for most meaningful scopes (like the Marketing Developer Platform). There is no true "free tier" for scale; access is granted based on use-case approval. For agents, this means a high "human-in-the-loop" setup cost before any autonomous operations can begin. Once authorized, the API offers structured access to posts, ads, and profile data.

---

## 2. Connection Methods

### REST API
LinkedIn primarily uses a RESTful API architecture. While there have been moves toward a unified Version 2 (v2), the legacy of different API versions for different products (Marketing vs. Learning vs. Sales Navigator) persists. Most agent-relevant actions, such as posting content or retrieving profile data, are handled via the `/v2/` or `/rest/` endpoints using JSON payloads.

### SDKs
LinkedIn provides official SDKs for Python and JavaScript, though they are often criticized for lagging behind the REST documentation. Most production-grade agents use standard HTTP clients (like `httpx` or `axios`) to interact directly with the REST endpoints to ensure compatibility with the latest versioned headers (`LinkedIn-Version: 202401`).

### MCP
There is currently no official Model Context Protocol (MCP) server provided by LinkedIn. Agents must rely on custom-built wrappers or third-party integrations (like LangChain community tools) to bridge the gap between LLM reasoning and LinkedIn execution.

### Webhooks
LinkedIn supports webhooks (Callback APIs) for specific events, such as lead generation form submissions or organization mentions. However, these are not "self-serve" and often require the app to be part of a specific partner program to receive real-time events.

### Auth Flows
LinkedIn uses OAuth 2.0 exclusively. Agents typically require "Three-Legged OAuth" (Authorization Code Flow) because actions are performed on behalf of a specific user or organization. For long-running agents, "Refresh Tokens" are critical but are only available to apps that have been specifically approved for them, adding significant friction to autonomous persistence.

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **Profile** | `GET /v2/me` | Retrieves the authenticated member's basic profile (URN, name, photo). |
| **UGC Post** | `POST /v2/ugcPosts` | The primary method for agents to publish articles, images, or short-form posts. |
| **Organization** | `GET /v2/organizations/{id}` | Retrieves metadata for a company page the agent has permission to manage. |
| **Ad Analytics** | `GET /v2/adAnalyticsV2` | Fetches performance metrics (impressions, clicks) for marketing agents. |
| **Image Upload** | `POST /v2/assets?action=registerUpload` | A multi-step process to register, upload, and verify media before posting. |
| **Comment** | `POST /v2/socialActions/{urn}/comments` | Allows agents to reply to or initiate conversations on existing posts. |

---

## 4. Setup Guide

### For Humans
1.  Navigate to the [LinkedIn Developer Portal](https://www.linkedin.com/developers/).
2.  Create a New App and verify it by linking it to a valid LinkedIn Company Page.
3.  Select the "Products" tab and request access to "Share on LinkedIn" and "Sign In with LinkedIn."
4.  If building a marketing agent, apply for the "Marketing Developer Platform" (requires a manual review process).
5.  Configure your Redirect URIs in the "Auth" tab.
6.  Generate your Client ID and Client Secret.
7.  Manually perform the first OAuth handshake to obtain an Access Token and (if approved) a Refresh Token.

### For Agents
1.  **Token Validation:** The agent must first verify the token's expiration and scope using the `/v2/me` endpoint.
2.  **URN Discovery:** Agents should resolve the user's URN (Unique Resource Name) immediately, as all subsequent actions require it.
3.  **Scope Check:** Attempt a low-stakes GET request to ensure the required scopes (e.g., `w_member_social`) are active.
4.  **Connection Validation Code (Python):**

```python
import requests

def validate_linkedin_connection(token):
    headers = {
        'Authorization': f'Bearer {token}',
        'X-Restli-Protocol-Version': '2.0.0'
    }
    response = requests.get('https://api.linkedin.com/v2/me', headers=headers)
    if response.status_code == 200:
        print(f"Connected as: {response.json().get('localizedFirstName')}")
        return True
    return False
```

---

## 5. Integration Example

The following Python example demonstrates an agent creating a text-based post (UGC Post) on behalf of a user.

```python
import requests

def post_to_linkedin(access_token, author_urn, message):
    url = "https://api.linkedin.com/v2/ugcPosts"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    
    post_data = {
        "author": f"urn:li:person:{author_urn}",
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {
                    "text": message
                },
                "shareMediaCategory": "NONE"
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        }
    }

    response = requests.post(url, headers=headers, json=post_data)
    
    if response.status_code == 201:
        return response.json().get('id')
    else:
        raise Exception(f"Post failed: {response.status_code} - {response.text}")

# Usage: post_to_linkedin("TOKEN", "abc12345", "Hello from my autonomous agent!")
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **P50 Latency** | 250ms | Standard for simple GET requests like `/me`. |
| **P95 Latency** | 580ms | Common during media upload registration or complex queries. |
| **P99 Latency** | 1000ms | Occurs during peak hours or for large organizational data pulls. |
| **Rate Limits** | Varies | Tiered by "Application" and "User." Typically 100k requests/day for basic. |
| **Uptime** | 99.9% | High reliability, but sensitive to platform-wide outages. |

---

## 7. Agent-Native Notes

*   **Idempotency:** LinkedIn does not support a native `Idempotency-Key` header for UGC posts. Agents must implement local state tracking (e.g., hash the content) to prevent accidental double-posting during retry loops.
*   **Retry Behavior:** Use exponential backoff for `429 Too Many Requests`. For `500` or `503` errors, LinkedIn usually recovers within 2-5 seconds.
*   **Error Codes:** A `403 Forbidden` often indicates an expired token or a missing "Product" approval in the developer portal, requiring human intervention. A `401 Unauthorized` should trigger a token refresh flow.
*   **Schema Stability:** LinkedIn is currently transitioning to "Versioned APIs" (e.g., `202401`). Agents should explicitly pin the version in the headers to avoid breaking changes.
*   **Cost-per-operation:** Free for standard developer usage, but high-volume marketing or "People Search" APIs require enterprise contracts that can cost thousands per month.
*   **Complex Assets:** Uploading an image is a 3-step process (Register -> Upload -> Verify). Agents need a state machine to handle these transitions or the post will fail.
*   **URN Persistence:** LinkedIn uses URNs (e.g., `urn:li:person:123`) rather than simple integers. Agents must be designed to parse and store these strings exactly.

---

## 8. Rhumb Context: Why LinkedIn API Scores 3.78 (L2)

LinkedIn’s **3.78 score** reflects a powerful professional dataset locked behind an outdated, human-centric gatekeeping model:

1.  **Execution Autonomy (5.2)** — Once an agent has a token, the REST API is relatively predictable. The platform supports structured JSON and versioned headers, allowing agents to execute posts and queries without much ambiguity. However, the lack of idempotency keys for write operations forces agents to carry more "logic weight" for safety.

2.  **Access Readiness (2.6)** — This is the primary drag on the score. LinkedIn is not "agent-startable." A human must create a company page, link an app, and manually apply for "Products." The approval process for the Marketing API can take weeks and is often rejected without specific business justifications. This "Sales-Led" access model is the antithesis of agent-native infrastructure.

3.  **Agent Autonomy (2.67)** — The absence of programmatic billing, the difficulty of obtaining long-lived refresh tokens without partner status, and the lack of a comprehensive webhook system for all events make it hard for agents to run truly "lights-out." Agents are often relegated to being "assistants" that require a human to fix auth issues every 60 days.

**Bottom line:** LinkedIn is a Tier-2 service for agents. It is unavoidable for professional social workflows, but the integration friction is high. It is a "walled garden" that treats programmatic access as a privilege for partners rather than a utility for developers.

**Competitor context:** Compared to **Twitter/X API (4.1)**, LinkedIn is more stable but harder to access. Compared to **Meta Graph API (4.5)**, LinkedIn’s developer portal is less intuitive and more restrictive regarding which scopes a "standard" app can use. For agents, LinkedIn is a high-effort, high-reward integration.
