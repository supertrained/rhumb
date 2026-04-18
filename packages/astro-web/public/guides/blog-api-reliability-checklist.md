---
title: "Before Your Agent Calls an API at 3am: A Reliability Checklist"
description: "A practical pre-flight checklist for agent integrations, focused on the five failure modes that actually wake operators up."
canonical_url: "https://rhumb.dev/blog/api-reliability-checklist"
---

# Before Your Agent Calls an API at 3am: A Reliability Checklist

You're in bed. Your agent is running. It calls a payment API to complete a transaction, gets a 500 back, retries three times, and creates three duplicate charges. By the time you check Slack in the morning, three users have filed disputes.

This isn't hypothetical. It's the failure mode developers hit when they treat agent integrations the same as human integrations.

**The core problem:** APIs are built for developers who can read error messages, click "Retry," and handle edge cases manually. Agents can't do any of that. They need APIs that communicate failures clearly, handle concurrent calls predictably, and allow credentials to be managed programmatically.

Most APIs don't.

---

## The 5 Questions That Separate "Works" from "Works at 3am"

We've scored 650+ APIs across 20 dimensions for agent-nativeness. When we look at what actually causes production failures in agent deployments, five questions account for most of the operational pain.

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

Your agent doesn't read documentation at runtime. It parses the response. If the response doesn't tell it why the call failed, the agent will either retry blindly, risking duplicates, or give up silently, risking data loss.

**AN Score dimension:** Error Signal Quality. Top-scoring APIs return structured, parseable errors with enough context for an agent to decide whether to retry, abort, or escalate.

---

### Question 2: Can the agent send the same request twice without breaking things?

Look for idempotency support in the API docs. Search for `Idempotency-Key`, request IDs, or duplicate-prevention guidance.

**Green flag:** `Idempotency-Key` support on POST requests. The API deduplicates on its end.

**Red flag:** No idempotency support. POST requests are fire-and-forget with no duplicate prevention.

Why it matters: agents retry on timeouts. Networks drop packets. If a call completes on the server but the response never arrives, your agent will retry. Without idempotency, that retry creates a second resource, a second charge, a second email, or a second record.

The most reliable APIs make idempotency boring. You provide a unique key, they handle the rest.

---

### Question 3: When the API rate-limits you, does it tell you when to retry?

Look at the API's documentation for rate limits. Specifically, does a 429 response include a `Retry-After` header or equivalent?

**Green flag:**

```
HTTP 429 Too Many Requests
Retry-After: 30
X-RateLimit-Reset: 1711670400
```

**Red flag:** HTTP 429 with no headers indicating when it's safe to retry.

An agent that hits a rate limit without guidance will either hammer the API on a fixed interval or implement exponential backoff with no ceiling. The first risks getting your key banned. The second means the agent might wait ten minutes when five seconds would have worked.

---

### Question 4: Can the agent get credentials without a human?

Check the API's authentication setup flow. Specifically, can API keys be created, rotated, and scoped programmatically?

**Green flag:** dashboard API key generation as a bounded human setup step, API key auth for all important endpoints, no browser-only consent loop required for routine execution.

**Red flag:** OAuth 2.0 as the only practical auth path, browser-based consent as a runtime dependency, MFA or SMS verification on key creation, or IP allowlisting without a sane operator path.

This is the one that kills you at 3am. If your agent needs to refresh credentials and it requires a human to click "Authorize" in a browser, the task hangs indefinitely.

---

### Question 5: Does the API return deterministic errors for the same input?

This one is harder to test upfront, but look for it in community threads and issue trackers.

**Green flag:** the same bad input always returns the same error code. Pagination is cursor-based, not offset-based.

**Red flag:** offset-based pagination, 500s for edge cases that should be 400s, or repeated mentions of the API being flaky under load.

An agent building a workflow model will retry 400s differently than 500s. If the API mislabels client errors as server errors, your agent will retry indefinitely on something that was never going to succeed.

---

## Scoring the APIs You're Evaluating

The five questions above map to real signal in the [AN Score framework](https://rhumb.dev/blog/how-to-evaluate-apis-for-agents). When Rhumb scores an API, it is systematically measuring these same failure modes across 20 dimensions.

**What to look for:**

| Score Range | What it means for agents |
| --- | --- |
| 8.0–10.0 | Production-grade. Handles edge cases. Safe for unsupervised operation. |
| 6.0–7.9 | Works with careful integration. Add explicit retry logic and error handling. |
| Below 6.0 | High maintenance burden. Expect to babysit this integration. |

Current baselines on common categories:

- **Payment APIs:** Stripe still sets the bar on retry safety and operator clarity.
- **Email APIs:** Resend and Postmark stay cleaner than the average legacy platform.
- **Storage and infrastructure:** the big clouds score well overall, but provider-specific quirks still matter.

Browse the full leaderboard at [rhumb.dev/leaderboard](https://rhumb.dev/leaderboard), sorted by AN Score and filterable by category.

---

## One More Thing: Test the Sandbox First

Before putting any API into a production agent loop, run your agent against the sandbox or test environment with explicit error injection:

1. Send a request that should 400. Does the agent handle it correctly?
2. Simulate a timeout. Does the agent retry, and how many times?
3. Send the same idempotent request twice. Does it create one resource or two?
4. Exhaust the rate limit. Does the agent back off or hammer?

If the API doesn't have a sandbox, treat it as a yellow flag. You're testing in production.

---

## TL;DR

Five questions before your agent calls an API:

1. **Error clarity:** does it return structured, parseable errors?
2. **Idempotency:** can it safely handle retry without creating duplicates?
3. **Rate-limit guidance:** does it tell you when to retry?
4. **Credential autonomy:** can the agent manage auth without a human?
5. **Deterministic behavior:** same input, same output, every time?

APIs that pass all five are built for agents. APIs that fail two or more will cost you sleep.

*Rhumb scores 650+ APIs on 20 dimensions for agent-nativeness. Free to search and browse at [rhumb.dev](https://rhumb.dev). No signup required for the first 10 tool calls.*
