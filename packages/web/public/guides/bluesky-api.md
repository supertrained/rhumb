# Bluesky API — Agent-Native Service Guide

> **AN Score:** 6.2 · **Tier:** L3 · **Category:** Social Media & Communication

---

## 1. Synopsis
The Bluesky API, powered by the AT Protocol (Authenticated Transfer), provides a decentralized infrastructure for social networking. Unlike legacy social platforms that have pivoted toward restrictive, high-cost API tiers, Bluesky offers a transparent, developer-first environment where agents can read, write, and interact with the social graph without gatekeeping. For agents, Bluesky is a primary channel for real-time sentiment analysis, automated content distribution, and autonomous community management. The service is fundamentally free to use, requires no credit card for API access, and supports "App Passwords" to isolate agent credentials from primary account security. It is the gold standard for agents requiring a programmatic social presence without the risk of arbitrary platform de-platforming.

---

## 2. Connection Methods

### REST API (XRPC)
The AT Protocol uses a custom remote procedure call system called XRPC, which is essentially a set of RESTful conventions over HTTP. Every action (query or procedure) is defined by a Lexicon (schema). Endpoints follow a reverse-DNS naming convention (e.g., `com.atproto.server.createSession`). Agents can interact with any Personal Data Server (PDS) or the main Bluesky Relay via standard JSON/HTTP.

### SDKs
The official SDK support is robust, particularly for TypeScript and Python.
- **JavaScript/TypeScript:** `@atproto/api` is the most mature library, providing full type safety for Lexicons.
- **Python:** The `atproto` package (community-maintained but highly recommended) provides an idiomatic way to interact with the protocol, including helper classes for complex objects like "facets" (links and mentions in posts).

### MCP
There is an emerging community-driven Model Context Protocol (MCP) server for Bluesky that allows agents using the Claude Desktop or other MCP-compatible hosts to search posts and interact with the feed directly as a tool-call without writing custom integration logic.

### Auth Flows
Agents should use **App Passwords**. These are generated in the Bluesky UI (Settings > App Passwords) and allow the agent to authenticate as a specific handle (e.g., `agent.bsky.social`) without exposing the master password. This is a critical security primitive for agent autonomy, allowing for easy revocation if the agent's environment is compromised.

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **Authenticate** | `com.atproto.server.createSession` | Exchanges handle and app password for a JWT (access token). |
| **Create Post** | `com.atproto.repo.createRecord` | Publishes a post to the user's repository (collection: `app.bsky.feed.post`). |
| **Get Profile** | `app.bsky.actor.getProfile` | Retrieves detailed metadata for a specific handle or DID. |
| **Search Posts** | `app.bsky.feed.searchPosts` | Queries the global index for specific keywords or hashtags. |
| **Follow User** | `com.atproto.repo.createRecord` | Creates a follow relationship (collection: `app.bsky.graph.follow`). |
| **Get Timeline** | `app.bsky.feed.getTimeline` | Retrieves the authenticated user's "Following" feed. |
| **Delete Record** | `com.atproto.repo.deleteRecord` | Programmatically removes a post, like, or follow by its URI. |

---

## 4. Setup Guide

### For Humans
1. Create a Bluesky account at [bsky.app](https://bsky.app).
2. Navigate to **Settings** > **Advanced** > **App Passwords**.
3. Click **Add App Password**, name it (e.g., "Rhumb-Agent-Alpha"), and copy the generated string.
4. Note your full handle (e.g., `my-agent.bsky.social`).
5. Ensure your email is verified, as some PDS instances limit API throughput for unverified accounts.

### For Agents
1. **Install SDK**: `pip install atproto` or `npm install @atproto/api`.
2. **Environment**: Store `BSKY_HANDLE` and `BSKY_APP_PASSWORD` in secure environment variables.
3. **Initialize Client**: Use the SDK to point to the entryway (usually `https://bsky.social`).
4. **Connection Validation**: Execute a simple profile fetch to confirm the session is active.

```python
from atproto import Client

client = Client()
profile = client.login('my-agent.bsky.social', 'xxxx-xxxx-xxxx-xxxx')
print(f"Agent connected as: {profile.display_name}")
```

---

## 5. Integration Example

This Python example demonstrates an agent-native pattern: authenticating, creating a post with a link (requiring "facets" for the protocol to recognize it), and handling the response.

```python
from atproto import Client, models

def run_agent_broadcast(text, url):
    client = Client()
    # Login using App Password
    client.login('agent.bsky.social', 'your-app-password')
    
    # In ATProto, links must be explicitly defined as 'facets' 
    # for the UI to render them as clickable.
    facets = [
        models.AppBskyRichtextFacet.Main(
            features=[models.AppBskyRichtextFacet.Link(uri=url)],
            index=models.AppBskyRichtextFacet.ByteStartEnd(
                byte_start=text.find(url), 
                byte_end=text.find(url) + len(url)
            )
        )
    ]

    try:
        post = client.send_post(text=text, facets=facets)
        return {"status": "success", "cid": post.cid, "uri": post.uri}
    except Exception as e:
        # Agent decision logic: If 401, re-auth. If 429, backoff.
        return {"status": "error", "message": str(e)}

# Execution
result = run_agent_broadcast("Check out Rhumb: https://rhumb.com", "https://rhumb.com")
print(result)
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **P50 Latency** | 160ms | Standard for simple record creation (Post/Like). |
| **P95 Latency** | 380ms | Typically seen during global search or complex feed fetches. |
| **P99 Latency** | 640ms | Occurs during PDS-to-PDS data synchronization or high load. |
| **Rate Limit** | 3,000 requests / 5 min | Generous limits for post creation and profile reads. |
| **Uptime** | 99.9% | Highly resilient due to decentralized infrastructure. |

---

## 7. Agent-Native Notes

*   **Idempotency**: The API does not natively support idempotency keys. To prevent duplicate posts during retries, agents should store the `CID` (Content Identifier) of successful writes and check their own repository (`com.atproto.repo.listRecords`) before retrying a timed-out request.
*   **Retry Behavior**: Implement exponential backoff for `429 Too Many Requests`. For `503 Service Unavailable`, agents should wait at least 30 seconds, as this usually indicates a PDS migration or temporary relay lag.
*   **Error Codes**: `InvalidRequest` usually means a schema violation (e.g., post too long). `ExpiredToken` should trigger an automatic re-authentication flow using the stored App Password.
*   **Schema Stability**: Bluesky uses Lexicons. These are extremely stable. If a schema changes, it is versioned, ensuring agents don't break when the platform adds new features.
*   **Cost-per-operation**: $0.00. There are currently no per-request charges, making it ideal for high-frequency monitoring agents.
*   **The Firehose**: For advanced autonomy, agents can subscribe to the "Firehose" (WebSocket), receiving every public event on the network in real-time. This allows for sub-second reaction times to global events.
*   **Rich Text**: Agents cannot just send a string with a URL. They must calculate byte offsets for links and mentions (Facets). This requires a more "computationally aware" agent than simple REST services.

---

## 8. Rhumb Context: Why Bluesky API Scores 6.2 (L3)

Bluesky's **6.2 score** reflects its status as the most developer-friendly social protocol, hampered only by its early-stage governance tools:

1. **Execution Autonomy (6.6)** — The Lexicon system provides a machine-readable contract that agents can use to validate their own payloads before sending. Because the protocol is open, agents have high certainty that their "tools" (like posting or following) will function consistently across different PDS providers. The structured nature of the "Facets" system, while complex, ensures that agent-generated content is indistinguishable from human-generated content.

2. **Access Readiness (5.7)** — While the API is free (Payment Autonomy: 9), the setup requires manual generation of App Passwords. There is no "one-click" OAuth flow for headless agents yet that matches the simplicity of modern SaaS. However, once the App Password is set, the friction vanishes. The lack of a credit card requirement makes it the easiest social API for an agent to "boot up" autonomously.

3. **Agent Autonomy (6.33)** — The availability of the real-time Firehose is a massive force multiplier for agent autonomy. An agent can "listen" to the entire network without polling, reducing latency and compute overhead. The primary score drag is Governance (3); there are no built-in audit logs, RBAC for sub-accounts, or enterprise-grade compliance features. It is a "wild west" environment where the agent is responsible for its own logging and safety boundaries.

**Bottom line:** Bluesky is the premier choice for agents requiring social capabilities. It offers the highest "freedom-of-action" for the lowest cost. While it lacks the corporate governance features of a service like LinkedIn or the scale of X, its programmatic transparency makes it far more reliable for autonomous systems.

**Competitor context:** X (Twitter) API (3.4) is significantly lower due to extreme costs ($100/mo minimum for basic write access) and aggressive rate limiting that kills agent autonomy. Mastodon (5.9) is a close competitor but suffers from "fragmentation friction," where an agent must handle different API versions and behaviors across thousands of independent instances. Bluesky provides the best balance of decentralization and API consistency.
