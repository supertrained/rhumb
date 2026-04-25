# DC90 DEV.to Draft — Why Per-Call Pricing Needs Explainable Routes

Date: 2026-04-25
Owner: Beacon
Prepared by: Pedro
Source pack: `docs/DC90-RESOLVE-CONTENT-MEASUREMENT-PACK-2026-04-25.md`
Canonical source page: `https://rhumb.dev/resolve/per-call-pricing`
Publication state: **internal draft; not published; Keel review required before external use**

## Publication packet

- **DEV.to title:** Why per-call pricing needs explainable routes
- **Canonical URL:** `https://rhumb.dev/resolve/per-call-pricing`
- **Tags:** `ai`, `api`, `agents`, `mcp`
- **Description / excerpt:** If an agent can spend money on external APIs, the route has to be explainable before execution: provider path, credential rail, estimated cost, and constraints.
- **Series / campaign:** DC90 controlled Resolve content floor
- **Publish rule:** Do not publish from this file until Keel clears final pricing / neutrality wording. Do not syndicate as a wave.

## DEV.to-ready markdown

````markdown
---
title: Why per-call pricing needs explainable routes
published: false
description: If an agent can spend money on external APIs, the route has to be explainable before execution: provider path, credential rail, estimated cost, and constraints.
tags: ai, api, agents, mcp
canonical_url: https://rhumb.dev/resolve/per-call-pricing
---

The hard part of agent API access is not only whether the call can be made.

It is whether the agent should be allowed to spend money on that route without surprising the operator.

For humans, a bad API choice is usually a bug report or an invoice problem. For agents, the decision can happen inside a loop: discover a tool, choose a provider, attach credentials, execute, repeat. If pricing is only visible after the call, the control point arrived too late.

Per-call pricing needs an explainable preflight.

## Discovery should stay separate from execution

Rhumb splits the job into two parts:

- **Index ranks** services so agents and operators can compare what exists.
- **Resolve routes** supported capabilities into governed calls.

Discovery, scoring, and browsing are free. Execution is different. When an agent runs a supported capability through Resolve, the call can have provider cost, credential-mode economics, wallet funding, or account billing attached to it.

Those should not be hidden behind one vague “tool call succeeded” message.

Before spend, the agent should know:

- what supported capability path is being used;
- which provider path is likely to execute;
- what credential rail applies;
- what the estimated cost is;
- and which explicit constraints shaped the route.

## Cost is a route constraint, not a quality score

This part matters.

A cheaper provider is not automatically better. A higher-ranked provider is not automatically the right route for every call. Resolve should treat cost as one execution factor among others, not as a secret rewrite of service quality.

The route can be constrained by things like:

- a pinned provider path;
- an allow list;
- a deny list;
- a max-cost ceiling;
- credential mode;
- provider availability / circuit state;
- and latency proxy.

AN Score remains a quality prior. Estimated cost can change the route when the operator asks for a ceiling or when the execution rail makes cost material. It should not become pay-to-rank by another name.

## The rail changes the economics

Most repeat production traffic should start with a governed API key on `X-Rhumb-Key`.

That is the boring default on purpose: the operator has an account, funding / billing is explicit, and the agent can check the route and estimate before execution.

Other rails exist for different jobs:

- **Wallet-prefund** is for wallet-first agents that still need repeat throughput.
- **x402 per-call** is for zero-signup, request-level payment authorization.
- **BYOK** is for workflows that must use the operator's provider account.
- **Agent Vault** is for encrypted, agent-scoped provider credentials injected at execution time.

Those are not interchangeable packaging labels. They change who owns the upstream credential, where spend lands, and what the route explanation has to disclose.

## What the agent needs before execution

A useful per-call system should answer the uncomfortable questions before the request spends money:

1. Is this capability supported for execution, or is it only discoverable?
2. Which provider path will Resolve use if the call proceeds?
3. What credential boundary is being used?
4. What is the estimated cost?
5. Did a pin, allow list, deny list, or max-cost ceiling affect the route?
6. What receipt or explanation will exist after the call?

That is the difference between “the model called an API” and governed execution.

## The boundary

Resolve does not make every indexed service executable.

Discovery breadth is wider than callable coverage. Rhumb is intentionally clearer about that boundary because cost controls only matter when the execution surface is honest.

The model is simple:

**Index ranks. Resolve routes.**

Read the per-call pricing explainer:

https://rhumb.dev/resolve/per-call-pricing
````

## Claim-safety checklist

- [x] No universal execution claim.
- [x] No anonymous execution claim.
- [x] No AI-visibility / MEO / retrieval improvement claim.
- [x] No highest-scoring-provider claim.
- [x] No stale or hard-coded callable/service/capability counts included.
- [x] Pricing language uses **estimated cost** and route constraints, not guaranteed final invoice language.
- [x] x402 described only as a zero-signup / request-level payment rail, not the default repeat-traffic story.
- [x] Governed `X-Rhumb-Key` described as the repeat production default.
- [x] Cost is explicitly separated from AN Score quality and neutrality.
- [x] Canonical URL points to the owned per-call pricing page.

## Required review

Keel must review this draft before external publication because it makes pricing / neutrality claims. Helm review is only required if code snippets, live estimates, or receipt examples are added.
