# Slack — Agent-Native Service Guide

> **AN Score:** 7.2 · **Tier:** L3 · **Category:** Team Communication & Notifications

---

## 1. Synopsis

Slack is the dominant team communication platform, providing channels, direct messages, threads, and integrations. For agents, Slack serves primarily as an output channel — posting notifications, alerts, reports, and interactive messages. The platform also supports input via slash commands, events API (reacting to messages), and workflow automation. Slack's Block Kit provides rich, interactive message formatting. Free tier: 90-day message history, 10 integrations. Pro: $8.75/user/month with unlimited history and integrations.

---

## 2. Connection Methods

### REST API (Web API)
- **Base URL:** `https://slack.com/api`
- **Auth:** Bearer token (`Authorization: Bearer xoxb-...` for bot tokens, `xoxp-...` for user tokens)
- **Content-Type:** `application/json` (for most methods) or `application/x-www-form-urlencoded`
- **Rate Limits:** Tier-based per method (Tier 1: 1 req/min, Tier 2: 20 req/min, Tier 3: 50 req/min, Tier 4: 100+ req/min)
- **Docs:** https://api.slack.com/methods

### SDKs
- **Python:** `pip install slack-sdk` — official Slack SDK
- **JavaScript/Node:** `npm install @slack/web-api` — official
- **Go:** `go get github.com/slack-go/slack` — community, well-maintained
- **Java:** `implementation("com.slack.api:slack-api-client:...")` — official

### MCP
- Community MCP servers for Slack exist (check MCP registry)
- Slack's Bolt framework can be adapted for MCP-style tool serving

### Webhooks
- **Incoming Webhooks:** Simple POST to a webhook URL to send messages (no API setup needed)
- **Events API:** Real-time events via HTTP POST to your endpoint
- **Socket Mode:** WebSocket connection for events (no public URL needed)
- **Slash Commands:** Custom commands that trigger HTTP requests to your endpoint

### Auth Flows
- **Bot Token (`xoxb-`):** For Slack Apps installed to a workspace
- **User Token (`xoxp-`):** Acts on behalf of a user (more permissions, more restrictions)
- **OAuth 2.0:** For distributing apps to multiple workspaces
- **Incoming Webhook URL:** No token needed — just POST to the URL

---

## 3. Key Primitives

| Primitive | Method | Description |
|-----------|--------|-------------|
| `chat.postMessage` | `POST /api/chat.postMessage` | Send a message to a channel or DM |
| `chat.update` | `POST /api/chat.update` | Edit an existing message |
| `chat.delete` | `POST /api/chat.delete` | Delete a message |
| `conversations.list` | `GET /api/conversations.list` | List channels the bot is in |
| `reactions.add` | `POST /api/reactions.add` | Add an emoji reaction to a message |
| `files.upload` | `POST /api/files.upload` | Upload a file to a channel |
| `views.open` | `POST /api/views.open` | Open a modal (interactive UI) |

---

## 4. Setup Guide

### For Humans
1. Go to https://api.slack.com/apps → **Create New App**
2. Choose **From scratch**, name it (e.g., "Rhumb Agent"), select workspace
3. Navigate to **OAuth & Permissions** → Add bot token scopes:
   - `chat:write` — send messages
   - `channels:read` — list channels
   - `reactions:write` — add reactions
   - `files:write` — upload files
4. Click **Install to Workspace** → Authorize
5. Copy the **Bot User OAuth Token** (`xoxb-...`)
6. Invite the bot to channels: `/invite @YourBotName` in each channel

### For Agents
1. **Credential retrieval:** Pull `SLACK_BOT_TOKEN` from secure store
2. **Connection validation:**
   ```bash
   curl -s https://slack.com/api/auth.test \
     -H "Authorization: Bearer $SLACK_BOT_TOKEN" | jq '.ok, .user'
   # Should return true and bot username
   ```
3. **Channel discovery:** List channels the bot can access:
   ```bash
   curl -s "https://slack.com/api/conversations.list?types=public_channel&limit=100" \
     -H "Authorization: Bearer $SLACK_BOT_TOKEN" | jq '.channels[] | {id, name}'
   ```
4. **Error handling:** All responses have `"ok": true/false`. On `"ok": false`, check `"error"` field. Common: `channel_not_found`, `not_in_channel`, `invalid_auth`, `ratelimited`.
5. **Fallback:** On rate limit, respect `Retry-After` header. On `not_in_channel`, the bot needs to be invited. Use Incoming Webhooks as a zero-auth fallback for simple notifications.

---

## 5. Integration Example

```python
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import os

# Credential setup
client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])

# Send a simple message
try:
    result = client.chat_postMessage(
        channel="#engineering",
        text="🚀 Deployment complete: rhumb.dev v2.1.0 is live.",
        unfurl_links=False
    )
    print(f"Message sent: {result['ts']}")
except SlackApiError as e:
    print(f"Error: {e.response['error']}")

# Send a rich Block Kit message
blocks = [
    {
        "type": "header",
        "text": {"type": "plain_text", "text": "📊 Weekly Agent Report"}
    },
    {
        "type": "section",
        "fields": [
            {"type": "mrkdwn", "text": "*Tasks Completed:*\n142"},
            {"type": "mrkdwn", "text": "*Success Rate:*\n98.2%"},
            {"type": "mrkdwn", "text": "*Avg Latency:*\n230ms"},
            {"type": "mrkdwn", "text": "*Cost:*\n$12.40"}
        ]
    },
    {
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "View Dashboard"},
                "url": "https://rhumb.dev/dashboard"
            }
        ]
    }
]

client.chat_postMessage(
    channel="#engineering",
    text="Weekly Agent Report",  # Fallback for notifications
    blocks=blocks
)

# Send a threaded reply
original_ts = result["ts"]
client.chat_postMessage(
    channel="#engineering",
    thread_ts=original_ts,
    text="Details: 23 invoices generated, 89 tickets resolved, 30 deployments."
)

# Add a reaction
client.reactions_add(
    channel="#engineering",
    name="white_check_mark",
    timestamp=original_ts
)
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| **Latency (P50)** | ~200ms | chat.postMessage |
| **Latency (P95)** | ~500ms | File uploads, complex Block Kit messages |
| **Latency (P99)** | ~1.5s | Under heavy workspace load |
| **Uptime** | 99.9%+ | Check https://status.slack.com |
| **Rate Limits** | Varies by method | Tier 1: 1/min, Tier 2: 20/min, Tier 3: 50/min, Tier 4: 100+/min |
| **Free Tier** | 90-day history, 10 integrations | Pro: $8.75/user/mo, unlimited |

---

## 7. Agent-Native Notes

- **Idempotency:** Messages are NOT idempotent — posting twice creates two messages. Agents must track message timestamps (`ts`) to avoid duplicates. Use `chat.update` to modify existing messages instead of posting new ones. Pattern: post a "processing..." message, then update it with results.
- **Retry behavior:** On `ratelimited` error, respect `Retry-After` header (in seconds). On `channel_not_found`, verify channel ID. On `not_in_channel`, invite the bot first. On `invalid_auth`, re-check token.
- **Error codes → agent decisions:** `ratelimited` → queue and retry after delay. `channel_not_found` → channel was deleted or ID is wrong, update channel cache. `not_in_channel` → post to a different channel or request invitation. `msg_too_long` → truncate or split message (limit: 40,000 characters).
- **Schema stability:** Slack's Web API is stable with good backward compatibility. Methods are versioned. Block Kit evolves additively. MTBBC is good for core messaging endpoints.
- **Cost-per-operation:** No per-API-call cost. Workspace plan-based pricing. Agent routing: Slack is the default for team notifications and interactive workflows. For simple alerts, Incoming Webhooks are zero-cost to set up.
- **Block Kit:** Use Block Kit for structured messages. Slack's Block Kit Builder (https://app.slack.com/block-kit-builder) helps design layouts. Agents should format output using blocks rather than plain text for better readability.
- **Rate limit tiers:** Know your method's tier. `chat.postMessage` is Tier 4+ (generous). `conversations.list` is Tier 2 (20/min). `reactions.add` is Tier 3 (50/min). Plan agent behavior around these limits.
- **Threading:** Use `thread_ts` to keep conversations organized. Agents should thread follow-up messages to avoid channel noise. Set `reply_broadcast=True` to also post the reply to the channel.
- **Incoming Webhooks:** For fire-and-forget notifications, use Incoming Webhooks — no SDK needed, just a POST request. Simplest integration pattern for agent notifications.

---

## 8. Rhumb Context: Why Slack Scores 7.2 (L3)

Slack's **7.2 score** reflects a strong notification and human-in-the-loop channel that wasn't designed for autonomous agent operation:

1. **Execution Autonomy (7.0)** — `chat.postMessage` is the workhorse — but messages aren't idempotent and rate limits are method-specific (Tier 1 methods at 1 req/min create real constraints). Agents must track message timestamps (`ts`) to avoid duplicate posts, and use `chat.update` to modify in-place rather than reposting. The `ok/error` response pattern is clean, but error strings like `not_in_channel` require agent-side channel management that other platforms handle automatically.

2. **Access Readiness (6.8)** — App setup is the highest-friction onboarding in this guide set: create app → configure scopes → install to workspace → invite bot to channels. Each step is manual. Incoming Webhooks bypass most of this friction for output-only agents, but any interactive or input-reading pattern requires the full OAuth app setup. The free tier's 10-integration limit also constrains multi-workspace agent deployments.

3. **Agent Autonomy (7.7)** — Block Kit enables rich interactive messages (buttons, modals, dropdowns) that allow agents to surface decisions to humans and collect responses — this is a genuine strength for human-in-the-loop workflows. The Events API + Socket Mode lets agents react to messages without a public URL. Threading keeps agent output organized in high-traffic channels. The platform's human-centric design actually works in favor of agents that need to escalate to humans.

**Bottom line:** Slack earns its score as the premier human-agent communication layer, not as an autonomous execution platform. Use Slack for: agent status reporting, escalation notifications, and human-in-the-loop approval workflows. For purely programmatic messaging between agent systems, use a lower-friction channel. The Incoming Webhooks pattern is the right starting point for most agent notification use cases.

**Competitor context:** Microsoft Teams (6.5) scores lower due to more complex API setup and weaker Block Kit equivalent. Discord (6.8) is better for developer communities but lacks Slack's enterprise workspace integration and Block Kit richness. Slack remains the default for B2B and internal team notification workflows.
