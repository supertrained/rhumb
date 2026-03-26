# Discovery Expansion — Notifications category

Date: 2026-03-26
Operator: Pedro / Keel runtime loop
Status: completed

## Why this category

`notifications` is still underrepresented in the live catalog despite being a core agent workflow primitive. Agents constantly need to trigger transactional, cross-channel, and in-product notifications, but the catalog only had two notification-centric providers before this pass.

## Services added

| Service | Slug | Score | Tier | Notes |
|---|---|---:|---|---|
| Knock | `knock` | 7.7 | Ready | Cross-channel workflow builder with recipients, schedules, and API-triggered notification runs |
| Novu | `novu` | 7.4 | Ready | Open-core notification infrastructure with subscriber model and direct server-side API |
| SuprSend | `suprsend` | 7.2 | Ready | Omni-channel HTTPS notification API with workflow abstraction and vendor routing |
| MagicBell | `magicbell` | 6.9 | Ready | Notification inbox + delivery API with batching, OpenAPI, and recipient-targeted notifications |

## Scoring approach

These additions were scored from official docs, authentication posture, API shape, and likely normalization fit for agent workflows.

Key signals used:
- **Knock** — documented REST API at `https://api.knock.app/v1`, bearer-auth secret keys, workflow/recipient/channel abstraction, schedules and broadcasts
- **Novu** — documented server-side API at `https://api.novu.co/v1`, `Authorization: ApiKey ...`, subscriber and multi-channel provider model
- **SuprSend** — omni-channel HTTPS API plus workflow-oriented control plane for vendor routing and notification orchestration
- **MagicBell** — REST API v2 at `https://api.magicbell.com/v2`, bulk notification support, OpenAPI, and explicit rate-limit/idempotency docs

Probe metadata recorded as:
- runner: `pedro-manual-docs`
- evidence types: docs / auth / API surface
- freshness: 24 hours

## Phase 0 Resolve assessment

This category is a strong candidate for a future capability family like:
- `notification.send`
- `notification.broadcast`
- `notification.schedule`

Likely normalized params:
- `workflow` or `template`
- `recipient` / `recipients`
- `data`
- optional `channels`
- optional `schedule_at`

Strongest Phase 0 candidates from this batch:
1. **Knock** — best overall fit for workflow-triggered cross-channel notifications
2. **Novu** — clean server-side API with explicit multi-channel mental model
3. **SuprSend** — strong orchestration story for vendor abstraction and omni-channel triggering

## Operator view

Notifications is the right expansion lane because it is:
- a high-frequency operational need for agents
- easy to explain in capability terms
- commercially relevant across SaaS, ops, and product workflows
- likely to benefit from a single normalized send/broadcast contract later