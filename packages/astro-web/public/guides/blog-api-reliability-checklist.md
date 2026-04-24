---
title: "Before Your Agent Calls an API at 3am: A Reliability Checklist"
slug: api-reliability-checklist
date: 2026-03-28
status: ready
type: guide
canonical_url: https://rhumb.dev/blog/api-reliability-checklist
seo_focus: agent API reliability, MCP server reliability, API for AI agents
---

# Before Your Agent Calls an API at 3am: A Reliability Checklist

You're in bed. Your agent is running. It calls a payment API to complete a transaction, gets a 500 back, retries three times, creates three duplicate charges. By the time you check Slack in the morning, three users have filed disputes.

This isn't hypothetical. It's the failure mode developers hit when they treat agent integrations the same as human integrations.

**The core problem:** APIs are built for developers who can read error messages, click "Retry," and handle edge cases manually. Agents can't do any of that. They need APIs that communicate failures clearly, handle concurrent calls predictably, and allow credentials to be managed programmatically.

Most APIs don't.

---

## The 5 Questions That Separate "Works" from "Works at 3am"

We've scored 650+ APIs across 20 dimensions for agent-nativeness. When we look at what actually causes production failures in agent deployments, five questions account for most of the avoidable incidents.

Run this checklist before you wire any external API into an autonomous agent.

---

### Question 1: What does the API say when something goes wrong?

Open the API's error reference. Look at a few real error responses.

**Green flag:** JSON with a machine-readable error code and a specific message.
```json
{
  "error": {
    "code": "INSUFFICIENT_FUNDS",
    "message": "Account balance too low for this transaction",
    "retry_after": null
  }
}
```

**Red flag:** HTML error page, vague 500 with no body, or "Internal Server Error" with nothing else.

Your agent doesn't read documentation at runtime. It parses the response. If the response doesn't tell it why the call failed, the agent will either retry blindly (risk: duplicates) or give up silently (risk: data loss).

**AN Score dimension:** Error Signal Quality. Top-scoring APIs return structured, parseable errors with enough context for an agent to decide: retry, abort, or escalate.

---

### Question 2: Can the agent send the same request twice without breaking things?

Look for idempotency support in the API docs. Search for "idempotency key," "request ID," or "duplicate prevention."

**Green flag:** `Idempotency-Key` header on POST requests. The API deduplicates on your end.

**Red flag:** No idempotency support. POST requests are fire-and-forget with no duplicate prevention.

Why it matters: Agents retry on timeouts. Networks drop packets. If a call completes on the server but the response never arrives, your agent will retry. Without idempotency, that retry creates a second resource, a second charge, a second email, a second record.

The most reliable APIs build idempotency in from the start. You provide a unique key, they handle the rest.

---

### Question 3: When the API rate-limits you, does it tell you when to retry?

Look at the API's documentation for rate limits. Specifically: does a 429 response include a `Retry-After` header or equivalent?

**Green flag:**
```
HTTP 429 Too Many Requests
Retry-After: 30
X-RateLimit-Reset: 1711670400
```

**Red flag:** HTTP 429 with no headers indicating when it's safe to retry.

An agent that hits a rate limit without guidance will either spin-wait, hammering the API on a fixed interval, or implement exponential backoff with no ceiling. The first risks getting your key banned. The second means the agent might wait 10 minutes when 5 seconds would have worked.

---

### Question 4: Can the agent get credentials without a human?

Check the API's authentication setup flow. Specifically: can API keys be created, rotated, and scoped programmatically?

**Green flag:** Dashboard API key generation (one-time human action), API key auth for all endpoints, no MFA required for key creation.

**Red flag:** OAuth 2.0 as the primary auth method with browser-based consent flow. 2FA or SMS verification on key creation. IP allowlisting required.

This is the one that kills you at 3am. If your agent needs to refresh credentials and it requires a human to click "Authorize" in a browser, you're done. The task hangs indefinitely.

If the workflow crosses credential boundaries, read [How to Secure Your API Keys for Agent Use](/blog/securing-keys-for-agents) before you trust a browser-first auth story.

**Real example:** SendGrid's documentation recommends OAuth as the preferred flow for some endpoints. API key auth exists but is treated as secondary. Agents using the OAuth-recommended path fail completely when tokens expire.

---

### Question 5: Does the API return deterministic errors for the same input?

This one's harder to test upfront, but look for it in community threads and issue trackers.

**Green flag:** Same bad input always returns the same error code. Pagination is cursor-based, not offset-based.

**Red flag:** Offset-based pagination. 500 errors for edge cases that should be 400s. "Flaky" mentions in GitHub issues.

An agent building a workflow model will retry 400s differently than 500s. If the API mislabels client errors as server errors, your agent will retry indefinitely on something that was never going to succeed.

### Fresh operator signal: endpoint retirement is still a reliability failure

Twilio is retiring `api.de1.twilio.com` on April 28. The harder lesson is not only that a hostname is going away. It is that many integrations treated a regional-looking base URL as if it preserved a routing promise the platform never actually gave them.

That is a reliability problem before it becomes a docs problem.

If your agent or wrapper pins base URLs in config, tests, or failover logic, treat those hostnames as part of the contract surface:

- **Green flag:** the provider gives a deprecation date, a replacement target, and enough machine-readable signal to tell you whether geography, auth scope, or fallback behavior changed.
- **Red flag:** the only warning is a prose post humans may or may not read, while automation keeps retrying a dead endpoint like it is transient infrastructure noise.

This is the same boundary described in [machine-parseable change communication](/blog/machine-parseable-change-communication-for-agent-ready-apis): endpoint drift should fail closed as a deterministic migration event, not masquerade as flaky transport.

---

## Scoring the APIs You're Evaluating

The five questions above map to real signal in the [AN Score framework](/blog/how-to-evaluate-apis-for-agents). When we score an API, we're systematically measuring exactly these failure modes across 20 dimensions.

**What to look for:**

| Score Range | What it means for agents |
|-------------|--------------------------|
| 8.0–10.0 | Production-grade. Handles edge cases. Safe for unsupervised operation. |
| 6.0–7.9 | Works with careful integration. Add explicit retry logic and error handling. |
| Below 6.0 | High maintenance burden. Expect to babysit this integration. |

Current baselines on common categories from 650+ scored APIs:
- **Payment APIs:** Stripe leads. Most payment APIs cluster in the middle, not at the top.
- **Email APIs:** Resend and Postmark are strongest. SendGrid still carries friction.
- **Storage and infra:** Cloud leaders score well, but provider-specific quirks still matter.

Browse the full leaderboard at [rhumb.dev/leaderboard](https://rhumb.dev/leaderboard), sorted by AN Score and filterable by category.

---

## One More Thing: Test the Sandbox First

Before putting any API into a production agent loop, run your agent against the sandbox or test environment with explicit error injection:

1. Send a request that will 400, invalid input, and confirm the agent handles it correctly.
2. Simulate a timeout, add a delay, and inspect whether the agent retries and how many times.
3. Send the same idempotent request twice and confirm it creates one resource, not two.
4. Exhaust the rate limit and confirm the agent backs off instead of hammering.

If the API doesn't have a sandbox, treat it as a yellow flag. You're testing in production.

---

## Failure-mode evidence

If you want concrete examples instead of a generic checklist, start with the live autopsies:

- [HubSpot API Autopsy](/blog/hubspot-api-autopsy)
- [Salesforce API Autopsy](/blog/salesforce-api-autopsy)
- [Twilio API Autopsy](/blog/twilio-api-autopsy)
- [Shopify API Autopsy](/blog/shopify-api-autopsy)

These are the kinds of reliability breaks that look small in docs and become real operator pain once an unattended workflow starts retrying.

---

## TL;DR

Five questions before your agent calls an API:

1. **Error clarity:** Does it return structured, parseable errors?
2. **Idempotency:** Can it safely handle retry without creating duplicates?
3. **Rate limit guidance:** Does it tell you when to retry?
4. **Credential autonomy:** Can the agent manage auth without a human?
5. **Deterministic behavior:** Same input, same output, every time?

APIs that pass all five are built for agents. APIs that fail two or more will cost you sleep.

---

*Rhumb scores 650+ APIs on 20 dimensions for agent-nativeness. Free to search and browse at [rhumb.dev](https://rhumb.dev). No signup required for the first 10 tool calls.*
