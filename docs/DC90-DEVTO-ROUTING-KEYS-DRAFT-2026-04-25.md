# DC90 DEV.to Draft — Route by Task Fit, Not Leaderboard Purity

Date: 2026-04-25
Owner: Beacon
Prepared by: Pedro
Source pack: `docs/DC90-RESOLVE-CONTENT-MEASUREMENT-PACK-2026-04-25.md`
Canonical source pages: `https://rhumb.dev/resolve/routing` and `https://rhumb.dev/resolve/keys`
Publication state: **internal draft; not published; Keel review required before external use**

## Publication packet

- **DEV.to title:** Route by task fit, not leaderboard purity
- **Canonical URL:** `https://rhumb.dev/resolve/routing`
- **Tags:** `ai`, `api`, `agents`, `mcp`
- **Description / excerpt:** A global service score is useful, but execution needs more context: supported capability path, credential boundary, route factors, and explicit constraints.
- **Series / campaign:** DC90 controlled Resolve content floor
- **Publish rule:** Do not publish from this file until Keel clears final route-factor / credential wording. Do not syndicate as a wave.

## DEV.to-ready markdown

````markdown
---
title: Route by task fit, not leaderboard purity
published: false
description: A global service score is useful, but execution needs more context: supported capability path, credential boundary, route factors, and explicit constraints.
tags: ai, api, agents, mcp
canonical_url: https://rhumb.dev/resolve/routing
---

A leaderboard can tell an agent what looks good in general.

It cannot, by itself, decide what should execute right now.

That distinction matters once an agent is allowed to call external APIs. The agent is no longer just researching a service. It is choosing a route, crossing a credential boundary, and possibly spending money.

For execution, global rank is not enough.

The better rule is:

**Route by task fit, not leaderboard purity.**

## Ranking and routing are different jobs

Rhumb splits the system into two jobs:

- **Index ranks** services so agents and operators can compare the field.
- **Resolve routes** supported capabilities into governed calls.

The score is still important. AN Score is a quality prior: a signal about how agent-compatible a service is before this particular call happens.

But a real execution route also has to answer questions a leaderboard does not know:

- Does this provider support the requested capability path?
- Is that route callable through Resolve today?
- Which credential mode applies?
- Is the provider path available?
- What is the estimated cost?
- Did the operator pin, allow, deny, or cap anything?

Those are route questions, not ranking questions.

## Start with the supported capability path

Before Resolve can choose a provider, it has to narrow the candidate set.

If the agent asks for `search.query`, Resolve should consider supported provider paths mapped to web search. If the agent asks for extraction, the candidate set is different. A high-scoring service outside the requested capability path should not win just because it is high-scoring globally.

That is the first difference between routing and leaderboard order.

A good route starts with the job.

## Then explain the factors

For a supported capability call, Resolve uses route factors such as:

- AN Score;
- provider availability / circuit state;
- estimated cost;
- latency proxy;
- credential mode;
- explicit constraints like provider pins, allow lists, deny lists, and max-cost ceilings.

That list is intentionally concrete.

It avoids vague “AI picked the best tool” language. If an agent is about to execute through an external provider, the operator should be able to see which material factors shaped the selected path.

## Keys can change the right route

Credential mode is not an implementation detail.

It changes what can safely execute.

For repeat Rhumb-managed execution, the governed API key on `X-Rhumb-Key` is the default boring path. The operator has an account or funded balance, and the agent can resolve, estimate, execute, and inspect receipts without copying provider keys into prompts.

BYOK is different. Use it when the workflow has to touch the operator's own provider account or workspace.

Agent Vault is different again. Use it when credentials should be encrypted, scoped to an agent, and injected at execution time.

x402 has a separate job: zero-signup, request-level payment authorization. It is useful when per-call payment matters more than repeat throughput.

Those rails should not be blurred together. A route that is right under Rhumb-managed credentials may not be right under BYOK or Agent Vault, and vice versa.

## Explicit control still matters

Best-fit routing should not remove direct agent control.

Sometimes the agent wants Resolve to choose the supported provider path. Sometimes the workflow already knows the provider it wants, and the right move is to pin it explicitly.

Both modes should be first-class:

- default routing when the agent wants Resolve to choose among supported routes;
- provider pinning when the agent or operator already knows the right supported path;
- allow / deny / max-cost constraints when policy should narrow the answer.

The important part is that the route explanation should make the choice visible.

## What the receipt should preserve

A useful route or receipt should not only say “success.”

It should preserve the selected provider path and the material factors around it: capability, route strategy, credential mode, estimated cost, policy checks, and why other candidate paths were ineligible when that matters.

That is how execution becomes governable instead of magical.

The agent can still move fast. The operator does not have to accept a black box.

## The boundary

Resolve does not make every indexed service executable.

Discovery breadth is wider than callable coverage. Rhumb is deliberately clear about that boundary because routing claims only matter when the execution surface is honest.

The model is simple:

**Index ranks. Resolve routes.**

Read the routing explainer:

https://rhumb.dev/resolve/routing

Read the key-management explainer:

https://rhumb.dev/resolve/keys
````

## Claim-safety checklist

- [x] No universal execution claim.
- [x] No anonymous execution claim.
- [x] No AI-visibility / MEO / retrieval improvement claim.
- [x] No highest-scoring-provider claim.
- [x] No stale or hard-coded callable/service/capability counts included.
- [x] Routing begins from supported capability path, not generic intent or raw leaderboard order.
- [x] Route factors match the current public route-explanation language: AN Score, availability / circuit state, estimated cost, latency proxy, credential mode, and explicit constraints.
- [x] Explicit constraints are enumerated as pin / allow / deny / max-cost ceiling.
- [x] Credential rails preserve current public truth: governed `X-Rhumb-Key` for repeat Rhumb-managed execution, BYOK / Agent Vault for operator-owned credentials, x402 for zero-signup request-level payment.
- [x] Discovery breadth is explicitly separated from callable coverage.
- [x] Canonical URL points to the owned routing page, with `/resolve/keys` as supporting source.

## Required review

Keel must review this draft before external publication because it makes route-factor and claim-parity assertions. Helm review is only required if code snippets, live receipt examples, or executable estimate examples are added.
