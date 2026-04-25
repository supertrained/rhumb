# DC90 DEV.to Draft — Resolve Is Not a Connector Catalog

Date: 2026-04-25
Owner: Beacon
Prepared by: Pedro
Source pack: `docs/DC90-RESOLVE-CONTENT-MEASUREMENT-PACK-2026-04-25.md`
Canonical source page: `https://rhumb.dev/resolve/compare`
Publication state: **internal draft; not published; Keel review required before external use**

## Publication packet

- **DEV.to title:** Resolve is not a connector catalog
- **Canonical URL:** `https://rhumb.dev/resolve/compare`
- **Tags:** `ai`, `api`, `agents`, `mcp`
- **Description / excerpt:** Connector catalogs, tool auth layers, and OAuth plumbing solve real jobs. Resolve is for the different job: helping an agent choose, route, pay, and explain a supported external API call.
- **Series / campaign:** DC90 controlled Resolve content floor
- **Publish rule:** Do not publish from this file until Keel clears final claim wording. Do not syndicate as a wave.

## DEV.to-ready markdown

````markdown
---
title: Resolve is not a connector catalog
published: false
description: Connector catalogs, tool auth layers, and OAuth plumbing solve real jobs. Resolve is for the different job: helping an agent choose, route, pay, and explain a supported external API call.
tags: ai, api, agents, mcp
canonical_url: https://rhumb.dev/resolve/compare
---

A lot of agent infrastructure gets collapsed into one sentence:

> “Give the agent tools.”

That hides three different jobs.

1. **Catalog breadth:** which app actions exist?
2. **Authorization:** which user or workspace is allowed to call them?
3. **Execution routing:** which provider path should this agent trust, pay for, and explain for this call?

Those are adjacent, but they are not the same product.

Composio, Arcade, and Nango point at real needs. Connector catalogs are useful when breadth of app actions is the bottleneck. Tool authorization layers are useful when user-scoped permissioning is the core job. OAuth and sync infrastructure are useful when you are building integrations into your own product.

Rhumb Resolve is built for a narrower execution question:

**When an agent needs a supported external capability, which provider path should it use — and what should the operator know before spend happens?**

## The connector-catalog shape

A connector catalog starts from inventory.

That can be exactly right when your agent needs a broad menu of app actions: create a ticket, read a file, update a CRM record, send a message. In that world, the first question is often “does this tool exist?”

Resolve starts from a different question.

The agent has an intended capability, like web search or extraction. The operator needs to know:

- whether the capability is supported;
- which provider paths are callable through Resolve today;
- what the concrete execution rail looks like;
- what credential boundary applies;
- what Resolve estimates the call will cost;
- and why this route was selected.

That is not just a bigger tool list. It is governed execution.

## What Resolve adds

Rhumb splits the system into two jobs:

- **Index ranks** services so agents and operators can compare the field.
- **Resolve routes** supported capabilities into governed calls.

Resolve does not blindly pick the highest-ranked provider. It first matches the supported capability path, then uses runtime factors like AN Score, availability / circuit state, estimated cost, credential mode, latency proxy, and explicit per-call constraints.

That matters because execution is contextual.

The best global provider for one class of work may not be the best path for a specific call, credential mode, cost ceiling, provider pin, allow list, or deny list. Sometimes the right move is routing by supported capability path and runtime factors. Sometimes the right move is explicit provider pinning.

Resolve keeps both available.

## When Rhumb is the wrong layer

If all you need is one app connection, Rhumb may be overkill.

If your main bottleneck is OAuth plumbing for a product integration, use an OAuth / sync layer. If your main bottleneck is a huge menu of app actions, use a connector catalog. If your main bottleneck is user-scoped tool permissioning, use a tool authorization layer.

Rhumb is the better fit when the hard question is not merely “can my agent call something?”

It is:

- which service should the agent trust for this job;
- which supported provider path is callable now;
- what is the estimated cost;
- which credential boundary is being used;
- and how do I explain the route afterward?

## The boundary

Resolve does not make every indexed service executable.

Discovery breadth is wider than callable coverage. Rhumb currently separates broad service intelligence from the narrower set of supported callable providers, and that boundary is intentional. It is better for an agent to see the truth than to inherit an overstated universal connector promise.

The model is simple:

**Index ranks. Resolve routes.**

Read the comparison page:

https://rhumb.dev/resolve/compare
````

## Claim-safety checklist

- [x] No universal execution claim.
- [x] No anonymous execution claim.
- [x] No AI-visibility / MEO / retrieval improvement claim.
- [x] No highest-scoring-provider claim.
- [x] No stale or hard-coded callable/service/capability counts included.
- [x] Competitor references are job-based, not derogatory or unverifiable.
- [x] Discovery breadth is explicitly separated from callable coverage.
- [x] Canonical URL points to the owned comparison page.

## Keel review notes

- Keel flagged minor copy blockers (cost certainty; avoid broad "operator policy" / "intent-first" routing shorthand; avoid derogatory competitor tone).
- Edits applied: use **estimated cost** wording, enumerate only explicit constraints (pin/allow/deny/cost ceiling), and replace "fake" with "overstated".
- If this draft changes again before external use, re-run Keel review.

## Required review

Keel must review this draft before external publication because it names adjacent vendors and makes competitor-positioning claims. Helm review is not required unless code snippets or live execution examples are added.
