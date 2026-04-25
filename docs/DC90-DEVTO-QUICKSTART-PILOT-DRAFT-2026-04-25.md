# DC90 DEV.to Pilot Draft — Resolve a Web-Search Capability in Three Calls

Date: 2026-04-25
Owner: Beacon
Prepared by: Pedro
Source prep: `docs/DC90-DEVTO-PILOT-PREP-2026-04-25.md`
Publication state: **final Keel review passed after one scope-tightening edit; not published**
Canonical URL: `https://rhumb.dev/quickstart`

## Publication packet

- **DEV.to title:** Resolve a web-search capability in three calls
- **Canonical URL:** `https://rhumb.dev/quickstart`
- **Tags:** `ai`, `api`, `agents`, `mcp`
- **Description / excerpt:** Most agent demos jump from “the model picked a tool” to “the API call worked.” The missing production step is the governed preflight: supported path, concrete rail, cost, and credential boundary before spend.
- **Series / campaign:** DC90 controlled Resolve pilot
- **Publish rule:** Do not publish until Keel clears the final copy below. Do not start a syndication wave from this draft.

## DEV.to-ready markdown

````markdown
---
title: Resolve a web-search capability in three calls
published: false
description: Most agent demos skip the governed preflight: supported path, concrete rail, cost, and credential boundary before spend.
tags: ai, api, agents, mcp
canonical_url: https://rhumb.dev/quickstart
---

Most agent demos skip the uncomfortable part.

They show a model deciding to use a tool, then jump straight to a successful API call. In production, the missing step is usually the whole problem:

- what capability is actually supported;
- which provider path can execute it;
- what the call is likely to cost;
- and what credential boundary applies before the agent spends anything.

Rhumb splits that into two jobs:

- **Index ranks** services so agents and operators can compare what exists.
- **Resolve routes** supported capabilities into governed calls.

For `search.query` (web search), the useful preflight is two open reads and one paid / authorized continuation.

## 1. Resolve the supported provider paths

```bash
API="https://api.rhumb.dev/v1"

curl "${API}/capabilities/search.query/resolve"
```

For `search.query`, this open preflight read shows supported provider paths and routing context. It is a way to ask: “what can Resolve do for this capability before I hand it money or credentials?”

## 2. Estimate the concrete execution rail

```bash
curl "${API}/capabilities/search.query/execute/estimate"
```

The estimate call checks the concrete hosted execution rail before spend.

That matters because `resolve` and `estimate` are answering related but different questions:

- `resolve` shows supported provider paths and routing context.
- `estimate` shows the concrete execution rail available for the call you are about to make.

The estimate is not required to be the first provider listed by `resolve`. Routing for an agent call is not leaderboard purity. It has to account for supported capability path, credential mode, estimated cost, availability / circuit state, latency proxy, and explicit per-call constraints.

## 3. Execute only through a paid or authorized rail

Execution is different. It is not anonymous.

```bash
curl -X POST "${API}/capabilities/search.query/execute" \
  -H "X-Rhumb-Key: rhumb_live_..." \
  -H "Content-Type: application/json" \
  -d '{"body":{"query":"best CRM for seed-stage B2B SaaS","max_results":5}}'
```

For repeat traffic, the normal path is a funded governed `X-Rhumb-Key`. Wallet-prefund or x402 can also be payment rails when zero-signup per-call payment is the point.

The boundary is intentional:

- open discovery and preflight first;
- paid or authorized execution second;
- receipt / explanation path for the actual call.

## What not to overread

This quickstart is scoped to one supported capability: `search.query`.

It does **not** mean every indexed service is executable through Resolve. Discovery breadth is wider than callable coverage. It also does **not** mean agents execute anonymously, or that Resolve blindly picks the highest-ranked provider every time.

The model is simpler than that:

**Index ranks. Resolve routes.**

Start with the public quickstart:

https://rhumb.dev/quickstart
````

## Claim-safety checklist

- [x] No universal execution claim.
- [x] No anonymous execution claim.
- [x] No AI-visibility / MEO / retrieval improvement claim.
- [x] No highest-scoring-provider claim.
- [x] No public callable/service/capability counts included.
- [x] x402 described only as a payment rail, not the default repeat-traffic story.
- [x] Canonical URL points to the public quickstart.
- [x] Scoped explicitly to `search.query`.

## Final Keel review notes

Keel returned **PASS** on 2026-04-25 with one recommended micro-edit to make the `search.query` scope explicit earlier. That edit was applied in the DEV.to-ready markdown: `For \`search.query\` (web search), the useful preflight is two open reads and one paid / authorized continuation.`

Publication is still intentionally not performed from this artifact. The next external action is a controlled DEV.to draft/publish step by Beacon after channel policy / operator-posting conditions are satisfied; do not start a syndication wave.
