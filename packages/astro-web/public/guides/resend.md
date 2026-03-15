# Resend — Agent-Native Service Guide

> **AN Score:** 8.6 · **Tier:** L4 · **Category:** Email Delivery

---

## 1. Synopsis

Resend is a modern email delivery API built for developers and agents. It replaces legacy SMTP complexity with a clean REST API for sending transactional and marketing emails. Resend's API-first design makes it one of the most agent-friendly communication services available — minimal setup, fast iteration, excellent DX. Built by former Vercel engineers, it emphasizes simplicity and reliability. Free tier: 3,000 emails/month, 100 emails/day. Supports custom domains, React Email templates, and webhook-based delivery tracking.

---

## 2. Connection Methods

### REST API
- **Base URL:** `https://api.resend.com`
- **Auth:** Bearer token (`Authorization: Bearer re_...`)
- **Content-Type:** `application/json`
- **Rate Limits:** 10 requests/sec on free tier; higher on paid plans
- **Docs:** https://resend.com/docs/api-reference

### SDKs
- **Python:** `pip install resend`
- **JavaScript/Node:** `npm install resend`
- **Go:** `go get github.com/resend/resend-go/v2`
- **Ruby, PHP, Elixir** — community-maintained

### MCP
- Check https://github.com/modelcontextprotocol/servers for community MCP servers
- Resend's API simplicity makes raw REST calls equally efficient for agents

### Webhooks
- **Events:** `email.sent`, `email.delivered`, `email.opened`, `email.clicked`, `email.bounced`, `email.complained`
- **Configure:** Dashboard → Webhooks or via API
- **Signature verification:** Svix-based signatures (`svix-id`, `svix-timestamp`, `svix-signature` headers)

### Auth Flows
- **API Keys:** Single bearer token per project
- **Scoped Keys:** Create keys with specific domain or sending permissions
- **No OAuth** — API keys only

---

## 3. Key Primitives

| Primitive | Endpoint | Description |
|-----------|----------|-------------|
| `email.send` | `POST /emails` | Send a single email |
| `email.batch` | `POST /emails/batch` | Send up to 100 emails in one call |
| `email.get` | `GET /emails/{id}` | Retrieve email status and metadata |
| `domains.list` | `GET /domains` | List verified sending domains |
| `domains.verify` | `POST /domains/{id}/verify` | Trigger DNS verification |
| `contacts.create` | `POST /contacts` | Add a contact to an audience |
| `audiences.list` | `GET /audiences` | List audience groups |

---

## 4. Setup Guide

### For Humans
1. Create account at https://resend.com/signup
2. Navigate to **API Keys** → Generate a new key
3. Add a sending domain: **Domains** → Add Domain
4. Configure DNS records (DKIM, SPF, DMARC) as shown in dashboard
5. Wait for verification (usually 1-5 minutes)
6. Send a test email from the dashboard to confirm

### For Agents
1. **Credential retrieval:** Pull API key from secure store (env var `RESEND_API_KEY`)
2. **Connection validation:**
   ```bash
   curl -s https://api.resend.com/domains \
     -H "Authorization: Bearer $RESEND_API_KEY" | jq '.[0].name'
   # Should return your verified domain
   ```
3. **Error handling:** Check HTTP status codes — `422` for validation errors (bad email format, unverified domain), `429` for rate limits, `403` for auth failures
4. **Fallback:** On rate limit, queue emails and retry after `Retry-After` header value. On persistent failure, fall back to SMTP relay if configured.

---

## 5. Integration Example

```python
import resend
import os

# Credential setup
resend.api_key = os.environ["RESEND_API_KEY"]

# Send a single email
result = resend.Emails.send({
    "from": "Pedro <pedro@yourdomain.com>",
    "to": ["recipient@example.com"],
    "subject": "Weekly Agent Report",
    "html": """
        <h2>Weekly Summary</h2>
        <p>Your agent processed <strong>142 tasks</strong> this week.</p>
        <ul>
            <li>Invoices generated: 23</li>
            <li>Support tickets resolved: 89</li>
            <li>Deployments: 30</li>
        </ul>
    """,
    "tags": [
        {"name": "category", "value": "report"},
        {"name": "agent", "value": "rhumb-lead"}
    ]
})
print(f"Email sent: {result['id']}")

# Batch send (up to 100 emails)
batch_result = resend.Emails.send([
    {
        "from": "notifications@yourdomain.com",
        "to": ["user1@example.com"],
        "subject": "Your invoice is ready",
        "html": "<p>Invoice #1001 is attached.</p>"
    },
    {
        "from": "notifications@yourdomain.com",
        "to": ["user2@example.com"],
        "subject": "Your invoice is ready",
        "html": "<p>Invoice #1002 is attached.</p>"
    }
])
print(f"Batch sent: {len(batch_result)} emails")
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| **Latency (P50)** | ~150ms | Email accepted (not delivered) |
| **Latency (P95)** | ~400ms | Under normal load |
| **Delivery Time** | 1-5s typical | Time from API call to inbox arrival |
| **Uptime** | 99.9%+ | Check https://status.resend.com |
| **Rate Limits** | 10 req/sec (free), 100 req/sec (pro) | Burst-friendly within limits |
| **Free Tier** | 3,000 emails/month, 100/day | Sufficient for development and low-volume production |

---

## 7. Agent-Native Notes

- **Idempotency:** Not built-in. Agents must track sent email IDs to avoid duplicates. Use a local dedup cache keyed on `(recipient, subject, timestamp_bucket)`.
- **Retry behavior:** Safe to retry on 500+ errors (Resend deduplicates on their side within a short window). On 429, respect `Retry-After`. On 422, do not retry — fix the request.
- **Error codes → agent decisions:** `422` with `"validation_error"` → check `from` domain is verified, `to` is valid email format. `429` → queue and retry. `403` → API key invalid or revoked, escalate.
- **Schema stability:** Resend's API is stable but young. Pin to current behavior and monitor changelog at https://resend.com/changelog. MTBBC is good for core endpoints.
- **Cost-per-operation:** Free tier: $0. Pro plan: $20/month for 50K emails ($0.0004/email). Enterprise scales further. Very cost-effective for agent email workflows.
- **Tags:** Use `tags` on every email for analytics segmentation. Agents should tag with `agent_id`, `workflow`, and `category` for traceability.
- **React Email:** Resend supports React Email components for template rendering. Agents can dynamically generate HTML or use pre-built templates. Check https://react.email for component library.
- **Batch optimization:** Prefer `POST /emails/batch` over individual sends when delivering to multiple recipients. Reduces API calls and stays within rate limits.

---

## 8. Rhumb Context: Why Resend Scores 8.6 (L4)

Resend's **8.6 score** reflects clean agent-native design:

1. **Execution Autonomy (8.5)** — JSON-native REST API (not SMTP) means agents parse responses deterministically. No socket-level surprises. Error responses are machine-readable (HTTP status + JSON error codes).

2. **Access Readiness (8.7)** — Free tier (3K emails/month, 100/day) lets agents validate the full workflow. Custom domain verification is fast (~5 min). Free tier is genuinely usable for production low-volume use cases.

3. **Agent Autonomy (8.6)** — Webhooks for delivery tracking (`email.delivered`, `email.bounced`, `email.complained`) enable async workflows. Agents can route based on bounce status or engagement signals. Batch API (`/emails/batch`) for high-volume scenarios.

**Bottom line:** Resend is the modern email choice for agents. RESTful design + fast iteration + free tier = lower barrier to agent-native workflows vs. SMTP-based services.

**Competitor context:** SendGrid (7.4) scores lower due to heavier SMTP legacy patterns and more complex webhook setup. Postmark (8.1) is comparable but pricier ($10/mo minimum). Choose Resend for simplicity and cost-efficiency.
