# Twitter API — Agent-Native Service Guide

> **AN Score:** 4.2 · **Tier:** L2 · **Category:** Social Media & Communication

---

## 1. Synopsis
The Twitter (X) API v2 provides programmatic access to the world's largest real-time conversational dataset. For agents, it serves as both a high-frequency sensor for trend detection and a broadcast medium for autonomous personas. However, the service has become significantly more hostile to agents since 2023. The Free tier is essentially a "write-only" sandbox limited to 1,500 posts per month. To read any data, agents require the Basic tier ($100/mo), which carries tight rate limits (e.g., 10,000 tweets per month). For production-scale agents, the Pro tier ($5,000/mo) is usually the entry point. While the v2 REST API is well-structured, the high cost-per-operation and restrictive access model make it a "Developing" (L2) service for autonomous systems.

---

## 2. Connection Methods

### REST API
The primary interface is the Twitter API v2 RESTful service. It uses JSON for both requests and responses. Most endpoints follow a predictable pattern: `https://api.twitter.com/2/tweets` or `https://api.twitter.com/2/users`. Note that media uploads still largely rely on the legacy v1.1 endpoints (`upload.twitter.com/1.1/media/upload.json`), which adds complexity for agents handling multi-modal content.

### SDKs
For Python-based agents, **Tweepy** remains the industry standard, offering a clean wrapper around v2 endpoints. For Node.js/TypeScript agents, the official **twitter-api-sdk** is the recommended choice as it provides full type safety for the v2 schema, which is critical for preventing runtime parsing errors in autonomous loops.

### MCP (Model Context Protocol)
There is currently no official MCP server for Twitter. Agent operators typically implement custom tools or use community-maintained wrappers to expose Twitter primitives to LLMs.

### Webhooks
Twitter offers the **Account Activity API**, allowing agents to receive real-time events (DMs, mentions, likes). However, this is largely gated behind Enterprise-level agreements, forcing most L2 agents to rely on expensive polling strategies which quickly exhaust rate limits.

### Auth Flows
Twitter supports **OAuth 1.0a** (User Context) and **OAuth 2.0** (App-only or Authorization Code with PKCE). Agents typically use OAuth 2.0 App-only for read tasks and OAuth 2.0 PKCE for acting on behalf of a specific bot account.

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **Post Tweet** | `POST /2/tweets` | Creates a new tweet or thread. Supports media IDs and polls. |
| **Recent Search** | `GET /2/tweets/search/recent` | Returns tweets from the last 7 days matching a query. |
| **User Lookup** | `GET /2/users/by/username/:username` | Resolves a handle to a persistent numerical User ID. |
| **Tweet Timelines** | `GET /2/users/:id/tweets` | Retrieves the most recent tweets posted by a specific user. |
| **Media Upload** | `POST /1.1/media/upload.json` | Uploads images/video (required before posting a tweet). |
| **Manage Likes** | `POST /2/users/:id/likes` | Allows an agent to like or unlike a specific tweet. |
| **Followers** | `GET /2/users/:id/followers` | Returns a list of users following the specified account. |

---

## 4. Setup Guide

### For Humans
1.  Sign up for a **Twitter Developer Account** at [developer.twitter.com](https://developer.twitter.com).
2.  Create a **Project** and an associated **App** within the Developer Portal.
3.  Navigate to **User authentication settings** and enable OAuth 2.0 (select "Web App, Automated App or Bot").
4.  Generate your **API Key and Secret**, and **Access Token and Secret**.
5.  Subscribe to a paid tier (Basic/Pro) if your agent needs to read data or search.
6.  Set your **App Permissions** (Read/Write/Direct Message) based on the agent's requirements.

### For Agents
1.  **Environment Sync:** Load `TWITTER_API_KEY`, `TWITTER_API_SECRET`, `TWITTER_ACCESS_TOKEN`, and `TWITTER_ACCESS_SECRET`.
2.  **Auth Validation:** Execute a `GET /2/users/me` call to verify credentials and scope permissions.
3.  **Rate Limit Discovery:** Agents should query the `x-rate-limit-remaining` header after the first call to calibrate polling frequency.
4.  **Connectivity Test:**
```python
import tweepy

client = tweepy.Client(bearer_token="YOUR_BEARER_TOKEN")
# Validate connection by fetching the agent's own profile
me = client.get_me()
if me.data:
    print(f"Agent authenticated as: {me.data.username}")
```

---

## 5. Integration Example

This example demonstrates an agent posting a status update using the `tweepy` library.

```python
import tweepy

# Initialize the client with OAuth 1.0a for Write access
client = tweepy.Client(
    consumer_key="REDACTED",
    consumer_secret="REDACTED",
    access_token="REDACTED",
    access_token_secret="REDACTED"
)

try:
    # Post a tweet
    response = client.create_tweet(
        text="Autonomous agent update: Task sequence complete. [Rhumb L2 Service Test]"
    )
    
    if response.data:
        tweet_id = response.data['id']
        print(f"Success! Tweet ID: {tweet_id}")
    
except tweepy.TweepyException as e:
    # Agent decision logic: If 429, back off. If 403, check permissions.
    print(f"Agent Execution Error: {e}")
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **P50 Latency** | 220ms | Standard for single Tweet lookups. |
| **P95 Latency** | 520ms | Common during peak global traffic or complex search queries. |
| **P99 Latency** | 950ms | Occurs during media processing or backend timeouts. |
| **Rate Limit Window** | 15 Minutes | Limits are reset every 15 minutes, not sliding. |
| **Max Payload** | 512KB | Maximum size for a standard POST request (excluding media). |

---

## 7. Agent-Native Notes

*   **Idempotency:** Twitter does **not** support native idempotency keys (like Stripe). Agents must maintain a local state of "Last Tweet ID" or "Last Action Hash" to prevent duplicate posts during retries.
*   **Retry Behavior:** Always implement exponential backoff. Twitter is aggressive with 429 (Too Many Requests) responses. Agents should parse the `x-rate-limit-reset` header to determine exactly how long to sleep.
*   **Error Codes:** 
    *   `403 Forbidden`: Usually means the agent is trying to perform an action not allowed by its tier (e.g., reading on a Free account).
    *   `429 Too Many Requests`: Trigger immediate backoff; persistent 429s can lead to app suspension.
*   **Schema Stability:** v2 is stable, but Twitter frequently changes which fields are "premium" vs "standard," which can break agent parsing if fields suddenly return as null.
*   **Cost-per-operation:** Extremely high. On the Basic tier ($100/mo for 10k reads), every `GET` request costs approximately $0.01. Agents should be architected to batch lookups where possible.
*   **Media Complexity:** Posting an image requires a v1.1 upload followed by a v2 tweet creation. This two-step process is a common failure point for agents.
*   **Text Constraints:** Agents must be programmed with a hard 280-character limit check before calling the API to avoid "Tweet too long" errors.

---

## 8. Rhumb Context: Why Twitter API Scores 4.2 (L2)

Twitter’s **4.2 score** reflects a high-quality technical interface overshadowed by extreme access friction and a restrictive economic model:

1. **Execution Autonomy (5.5)** — The v2 API is modern, uses clean JSON, and provides comprehensive error messages. However, the split between v1.1 (media) and v2 (tweets) creates "integration debt" for agents. The lack of native idempotency is a significant drawback for autonomous systems that must ensure they don't spam the same content during a network retry.

2. **Access Readiness (2.8)** — This is the service's weakest dimension. The $100/mo entry price for basic "read" capabilities is a massive barrier for experimental or multi-agent swarms. The "Free" tier is a misnomer for agents, as it lacks the search and timeline capabilities required for any meaningful autonomy. Setup requires manual approval and human-in-the-loop credit card entry.

3. **Agent Autonomy (4.0)** — While the API is robust, it lacks agent-centric features like long-polling or affordable webhooks. Agents are forced into inefficient polling cycles that are both expensive and slow. The absence of RBAC (Role-Based Access Control) means an agent with "Write" access has total control, increasing the governance risk for operators.

**Bottom line:** Twitter is a "Tier 2" service for agents. It is technically capable but economically and operationally restrictive. It is best used as a high-value broadcast channel rather than a primary data source for autonomous reasoning.

**Competitor context:** **Bluesky (AT Protocol)** scores significantly higher (7.2) due to its open, free-to-access API and decentralized nature which is inherently more agent-friendly. **Mastodon** (6.8) also beats Twitter on access readiness, though it lacks the global unified dataset that makes Twitter valuable.
