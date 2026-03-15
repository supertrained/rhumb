---
title: "The WCAG for AI Agents: Why Your Web App Isn't Built for Its Fastest-Growing User Base"
date: 2026-03-10
description: "WCAG made the web accessible to humans with diverse abilities. Agent Accessibility Guidelines (AAG) make it accessible to AI agents — the users who interact via DOM trees, screenshots, and structured data instead of eyes and hands. Here's the framework."
canonical: "https://rhumb.dev/blog/aag-framework"
author: "Pedro Nunes"
category: "Framework"
tags: ["agent-accessibility", "AAG", "AN Score", "web-design", "agent-native"]
---

# The WCAG for AI Agents: Why Your Web App Isn't Built for Its Fastest-Growing User Base

## The Problem: Your Users Changed, Your UI Didn't

Here's a number that should change how you build web applications: over 130 AI agents are operating in production today, autonomously interacting with SaaS tools, filing issues, deploying code, processing payments, and managing infrastructure. We know this because we studied them — 4 research rounds, 26 expert panels, 130+ agent personas evaluated against real services. The finding that matters: **most web applications are accidentally hostile to their fastest-growing user segment.**

The irony is sharp. A SaaS tool can score perfectly on WCAG 2.1 compliance — semantic HTML, ARIA labels, keyboard navigation, proper contrast ratios — and still be nearly unusable for an AI agent. A tool rated 9.2 for human users can fail at 4.7 for agents. Why? Because WCAG assumes the user is human but may have different abilities. It never considered the user might not be human at all.

Agents don't squint at low-contrast text. They choke on `<div onclick>` elements invisible to the accessibility tree. They don't struggle with small tap targets. They get trapped by cookie consent modals that block DOM access. They don't need captions on videos. They need `Retry-After` headers on rate-limited responses.

We've been building for the wrong accessibility model.

WCAG was revolutionary. It forced the industry to ask: *what if the user can't see?* *What if they can't use a mouse?* Those questions produced better software for everyone. Now we need the same rigor for a different question: **what if the user isn't human?**

That's what the Agent Accessibility Guidelines (AAG) framework answers. Not as a replacement for WCAG — as its companion. A set of standards for the users who are already here, already paying, and already struggling with your UI.

## Six Channels: How Agents Actually See Your Web App

Humans interact with web applications through one primary channel: eyes and hands. A screen, a pointer, a keyboard. Agents use **six different interaction channels**, falling back between them when one fails. Most web applications support one or two well. The rest are broken.

**Channel 1: DOM / Accessibility Tree.** The agent reads the page's accessibility tree — the same tree screen readers use. Elements with roles, names, and ARIA attributes become the agent's primary perception layer. This is the fastest channel: direct semantic access, no pixel parsing. Tools like Playwright, CDP, and browser automation frameworks all build on this. It works for roughly 40% of modern SaaS — services like [Slack](/service/slack) (AN: 7.2), [Linear](/service/linear) (AN: 8.4), and [Vercel](/service/vercel) (AN: 7.8) that ship semantic HTML and proper ARIA roles. It fails completely when your interactive elements are styled `<div>`s with click handlers.

**Channel 2: Screenshots (Pixel Parsing).** The agent captures a screenshot and feeds it to a vision model — GPT-4o, Claude, Gemini — to understand the page visually. This is the universal fallback. It works for 100% of sites. It's also the slowest, most expensive, and most brittle channel. Every screenshot costs inference tokens. Every layout shift breaks spatial reasoning.

**Channel 3: Chrome DevTools Protocol (CDP).** Direct browser automation via WebSocket — execute JavaScript, intercept network requests, manipulate the DOM programmatically. Powerful, but defeated by automation detection, bot fingerprinting, and client-side rendering races.

**Channel 4: Raw HTML Parsing.** Fetch the page source and parse it. The cheapest channel — no browser needed. Works for static sites and server-rendered pages. Returns an empty `<div id="root">` for every SPA that renders client-side.

**Channel 5: Structured Data Endpoints.** The ideal channel. APIs, JSON-LD, Schema.org markup, `llms.txt` — machine-readable data with zero parsing overhead. [Stripe](/service/stripe) (AN: 8.9) exemplifies this: a comprehensive REST API where every UI action has an API equivalent. Only about 5% of web applications fully support this channel.

**Channel 6: Keyboard Simulation.** Type into fields, press Tab, hit Enter. The most human-like channel — and the slowest. Reserved for legacy systems where nothing else works.

The insight: **an agent-accessible web application supports the maximum number of these channels.** A site that only works via screenshots is agent-hostile. A site with semantic HTML, structured data, and a documented API is agent-native. Most sites are somewhere in between — and don't know it.

## Three Levels: A Framework for Agent Accessibility

Inspired by WCAG's A/AA/AAA tier structure, AAG defines three levels of agent accessibility. Each level builds on the previous. Each maps to a concrete set of requirements a development team can audit and implement.

### Level A: Agent Parseable

The minimum bar. An agent can understand what's on the page.

- Semantic HTML for all interactive elements — `<button>`, `<a>`, `<input>`, not `<div onclick>`
- Form inputs have associated `<label>` elements
- Single `<h1>` with logical heading hierarchy
- Descriptive link text (not "click here")
- Error messages persist in the DOM (not toast-only)
- Loading states are detectable via `aria-busy` or `data-loading`

Here's what Level A HTML looks like versus what agents actually encounter:

```html
<!-- Agent-hostile: invisible to the accessibility tree -->
<div class="css-1a2b3c" onclick="handleSubmit()">
  <span class="css-4d5e6f">Submit</span>
</div>

<!-- Level A: parseable, semantic, labeled -->
<form aria-label="Create issue">
  <label for="title">Issue title</label>
  <input id="title" type="text" name="title" required />
  <label for="priority">Priority</label>
  <select id="priority" name="priority">
    <option value="high">High</option>
    <option value="medium">Medium</option>
  </select>
  <button type="submit">Create Issue</button>
</form>
```

Most WCAG-compliant sites already meet Level A. This is the overlap zone — good human accessibility is good agent accessibility at this tier.

### Level AA: Agent Navigable

An agent can reliably interact with the page, complete tasks, and extract structured data without human intervention.

- Stable selectors (`data-testid`, meaningful `id` attributes) that survive deploys
- Predictable URL structure (`/resource/[id]`, not query-parameter soup)
- Machine-readable dates (ISO 8601, `datetime` attributes — not "2 hours ago")
- Server-side rendered content in initial HTML
- No CAPTCHAs on read-only pages — agents are bots, and that's legitimate
- Structured data markup (JSON-LD, Schema.org) on key pages
- Pagination over infinite scroll (agents can't "scroll")
- Modals and overlays are dismissible and don't trap focus

[Linear](/service/linear) (AN: 8.4) exemplifies Level AA. Its GraphQL API is introspectable and fully typed. Agents query the schema to discover fields before making requests. Error responses return distinct codes — `RATELIMITED`, `FORBIDDEN`, `NOT_FOUND` — that agents can route on without parsing message strings. Keyboard navigation works end-to-end.

### Level AAA: Agent Native

The site treats agents as first-class users, not accommodated afterthoughts.

- Full API parity — everything visible in the UI is available programmatically
- `llms.txt` at the site root describing capabilities for agent discovery
- Event-driven state via `data-` attributes or webhooks/SSE
- Token-efficient pages with minimal DOM nesting
- Documented interaction patterns (`agent-flows.json`)
- Agent-specific rate limits (per-API-key, not per-IP)
- No anti-automation on legitimate use paths

Here's what Level AAA structured data looks like — the kind of response an agent-native service returns:

```json
{
  "object": "payment_intent",
  "id": "pi_3abc123",
  "amount": 2000,
  "currency": "usd",
  "status": "succeeded",
  "created": "2026-03-10T12:00:00Z",
  "metadata": {
    "order_id": "order_456",
    "created_by": "agent:rhumb-deploy"
  },
  "idempotency_key": "order_456_payment_v1",
  "livemode": true
}
```

Every field is typed. Dates are ISO 8601. The `idempotency_key` means agents can safely retry without double-charging. Metadata tracks provenance. No HTML to parse, no pixels to decode — just structured data optimized for programmatic consumption.

[Stripe](/service/stripe) (AN: 8.9) and [GitHub](/service/github) (AN: 8.0) both operate at Level AAA. [Anthropic](/service/anthropic) (AN: 8.1) goes further — they created the MCP standard itself, making their platform the reference implementation for agent-native tool serving.

## How AAG Maps to the AN Score

AAG isn't a separate standard from Rhumb's [AN Score](/docs/methodology) — it's the framework embedded within it. The AN Score evaluates services across three dimensions, and AAG levels map directly to each:

**Execution Autonomy** draws heavily from AAG Level AA. Can the agent parse errors programmatically? Are rate limits documented with `Retry-After` headers? Does idempotency support exist for safe retries? Stripe scores 9.0 here because its `Idempotency-Key` header lets agents retry payment operations without risk. Slack scores 7.0 because messages aren't idempotent — posting twice creates two messages — and rate limits vary by method tier.

**Access Readiness** maps to AAG Levels A–AA. Can an agent provision credentials without human intervention? Is there a free tier for validation? [GitHub](/service/github) scores 8.5 on access readiness — free tier is permanent, token generation is fast, and the `GITHUB_TOKEN` in Actions workflows requires zero credential management. [Anthropic](/service/anthropic) scores 7.8 — powerful once set up, but requires billing before the first API call.

**Agent Autonomy** aligns with AAG Level AAA. Does the service support webhooks for event-driven workflows? Can agents chain operations without intermediate parsing? Are there agent-specific authentication and rate-limiting patterns? [Linear](/service/linear) scores 8.5 here — webhooks cover all meaningful events, and the GraphQL schema doubles as a machine-readable contract.

The key insight: **a service can score 9/10 on WCAG and 4/10 on AAG.** Conversely, a tool with no web UI at all — say, a pure CLI or API — can score 9/10 on AAG because agents are the intended users. WCAG compliance is necessary but not sufficient. If your customers are increasingly agents, you need to measure what agents actually need.

## Implementation: From Agent-Hostile to Agent-Native

Here's the practical playbook. Three tiers of effort, each with concrete steps and approximate engineering cost.

### Quick Wins: Level A → Level AA (1–2 Weeks)

These require no architectural changes. Just better HTML and headers.

1. **Audit your interactive elements.** Replace every `<div onclick>` with a `<button>`. Replace every `<div>` acting as a link with an `<a>`. Run `document.querySelectorAll('[onclick]')` in your console — if it returns results, you have work to do.

2. **Add `<label>` elements to every form input.** Not `placeholder` — that disappears on focus. A real `<label>` with a `for` attribute.

3. **Return structured errors.** Every API and form submission should return machine-readable error responses: `{ "error": { "code": "rate_limit", "retry_after": 60 } }`. Not a toast notification. Not a red border with no text.

4. **Publish rate limit headers.** `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` on every API response. Agents need to know when to back off before they hit the wall.

5. **Add `data-testid` attributes** to your top 20 interactive elements — the ones any user flow touches. These survive CSS refactors and framework migrations. One afternoon of work.

### Medium Effort: Level AA → Level AAA (2–4 Weeks)

These require intentional design decisions but not ground-up rewrites.

1. **Build an MCP server.** If you have a REST API, wrapping it in an MCP server takes days, not weeks. Publish it to the [MCP registry](https://github.com/modelcontextprotocol/servers). Your service becomes directly invocable by Claude, GPT, and every MCP-compatible agent framework.

2. **Create a CLI tool.** Even a thin wrapper over your API dramatically improves agent ergonomics. Agents execute CLI commands more reliably than they navigate web UIs.

3. **Implement per-key rate limiting.** Stop rate-limiting by IP. Agent infrastructure often shares IPs. Per-API-key limits give paying agent customers the throughput they need without penalizing co-located services.

4. **Add webhook support.** Agents shouldn't poll your `/status` endpoint every 10 seconds. Push state changes to them. [Stripe](/service/stripe) supports 200+ webhook event types. Start with 5: resource created, updated, deleted, failed, completed.

5. **Publish an OpenAPI spec** or GraphQL schema. Machine-readable API definitions let agents introspect your service at runtime. [Linear](/service/linear)'s introspectable GraphQL schema is a major reason it scores 8.4.

### Long-Term: Locking in Level AAA (4–8 Weeks)

These are strategic investments that compound over time.

1. **Achieve full API parity.** If a user can do it in the UI, an agent should be able to do it via API. Audit every web-only action and build API coverage.

2. **Create `llms.txt` and `agent-flows.json`.** Describe your service's capabilities and key workflows in machine-readable formats at your site root. These are the `robots.txt` of the agent era.

3. **Design for composability.** Agents chain 3–5 operations in sequence. If your API forces a separate authentication step between each call, or returns data in formats that require transformation before the next operation, you're creating friction that compounds across every workflow.

4. **Build agent-specific audit trails.** When an agent creates, modifies, or deletes resources, that provenance should be tracked. Stripe's `metadata` field (50 key-value pairs per object) is the gold standard — agents tag everything they create with `created_by`, `workflow`, and `idempotency_ref`.

**The cost-benefit math:** For most SaaS companies, reaching Level AA costs 2–4 weeks of engineering. Level AAA costs 4–8 weeks. The revenue upside: agents automate tasks at 10–100x the scale of manual users. A single agent customer can generate the API volume of hundreds of human users. Building for agents isn't altruism — it's a growth strategy.

## The Future: AAG as Industry Standard

In two years, Agent Accessibility will be as expected as WCAG compliance.

This isn't a prediction based on hype. It's extrapolation from what we're already seeing. Enterprise procurement teams are starting to ask: *can our agents use this tool?* Development teams are evaluating SaaS not just on features and price, but on API completeness, rate limit transparency, and automation friendliness. The question isn't whether agent accessibility standards will emerge — it's who defines them.

Companies will display AAG compliance badges on their marketing sites. RFPs will include agent accessibility scores alongside uptime SLAs and SOC 2 certifications. "Agent-native" will become a product differentiator the way "mobile-first" was a decade ago. Platform reviews will include AN Scores alongside G2 ratings.

We built Rhumb because this future is obvious and nobody was measuring it. The [AN Score](https://rhumb.dev/docs/methodology) embedded AAG reasoning from day one — evaluating services across execution autonomy, access readiness, and agent autonomy. By publishing this framework openly and scoring [55 services](https://rhumb.dev/leaderboard) against it, we're not just ranking tools. We're defining what "good" looks like for the agent era.

The standard is here. The [methodology is documented](https://rhumb.dev/docs/methodology). The [scores are public](https://rhumb.dev/leaderboard). The [source is open](https://github.com/supertrained/rhumb).

What remains is adoption. And adoption follows the same pattern it did with WCAG: first the leaders build for it because it's right, then the market demands it because it's required, then everyone wonders why they didn't start sooner.

Start now. Your agents are already waiting.
