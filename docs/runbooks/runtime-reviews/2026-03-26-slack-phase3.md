# Phase 3 runtime review — Slack

Date: 2026-03-26
Owner: Pedro / Keel runtime review loop
Priority: Phase 3 callable-provider verification

## Why Slack

Google AI is still not live in the callable inventory, so the next unblocked lane remained callable-provider runtime review depth.

Slack was the cleanest BYOK target because:
- it is already listed as callable in production status
- it exposes a safe, non-mutating auth identity read (`POST /api/auth.test`)
- direct-control parity is easy to verify with the same credential
- it avoids Twilio lookup spend and avoids message-send side effects

## Setup note

The stored launch/dashboard API key was not usable for this verification path.

A fresh check against `POST /v1/admin/agents` with the key currently stored in 1Password returned:
- `401 unauthorized`
- detail: `Invalid or missing admin key.`

Rather than blocking on that stale dashboard key, I used the cleaner Stripe-style pattern instead:
- create a fresh internal runtime-review agent
- grant it **only** Slack access
- run the verification through that scoped agent key

This keeps the runtime proof isolated from launch/dashboard credential drift.

## Test setup

### Rhumb proxy execution
- Endpoint: `POST /v1/proxy/`
- Service: `slack`
- Method/path: `POST /api/auth.test`
- Agent: ephemeral runtime-review agent `b99a88f3-862e-4754-b52e-178c8cebcb62`
- Result target:
  - workspace name + id
  - user name + id
  - bot id

### Direct provider control
- Endpoint: `POST https://slack.com/api/auth.test`
- Auth: direct Slack bearer token
- Result target:
  - workspace name + id
  - user name + id
  - bot id

## Results

### Rhumb proxy
- Result: **succeeded**
- Envelope status: **200**
- Upstream status: **200**
- Response highlights:
  - `team: TeamSuper`
  - `team_id: T08HGQD6FGW`
  - `user: cordelia`
  - `user_id: U0AECQMK5FG`
  - `bot_id: B0AEESDJ1CJ`

### Direct Slack control
- Result: **succeeded**
- HTTP status: **200**
- Response highlights:
  - `team: TeamSuper`
  - `team_id: T08HGQD6FGW`
  - `user: cordelia`
  - `user_id: U0AECQMK5FG`
  - `bot_id: B0AEESDJ1CJ`

### Runtime evidence emitted
Fresh production runtime artifacts were emitted and ingested immediately after the proxy call:
- latency evidence: `88c3e792-6df4-4f23-8233-ab66fe1ca72f`
- credential evidence: `ad10d10f-a347-4871-b87e-97034beee1bf`
- usage summary evidence: `01b3c6bd-dd51-4b3c-983a-eea43354c721`

## Comparison

| Dimension | Rhumb proxy | Direct Slack |
|---|---|---|
| Reachability | Healthy | Healthy |
| Auth path | Rhumb proxy credential injection | Direct Slack bearer token |
| Output | Workspace/user/bot identity returned | Same workspace/user/bot identity returned |
| Side effects | None | None |
| Operator conclusion | Working production Slack proxy path | Provider API healthy |

## Public trust surface update

After the live rerun:
- fresh `runtime_verified` evidence rows were inserted for Slack
- a new published review was created: **"Slack: Phase 3 runtime check passes on safe auth identity read"**
- the review was linked to the fresh evidence in `review_evidence_links`
- `/v1/services/slack/reviews` now shows a new **🟢 Runtime-verified** row at the top

Review id:
- `7efddc9b-d09f-4387-8b00-7c84feead6f2`

Evidence ids:
- `88c3e792-6df4-4f23-8233-ab66fe1ca72f`
- `ad10d10f-a347-4871-b87e-97034beee1bf`
- `01b3c6bd-dd51-4b3c-983a-eea43354c721`

## Phase 3 verdict

**Slack is Phase-3-verified in production.**

The current Slack proxy/auth path cleanly matches direct provider control on a safe read-only check, and the runtime evidence pipeline is still wiring those proofs onto the public trust surface correctly.

## Follow-up

1. Continue the next BYOK runtime review while Google AI remains absent from the live callable inventory.
2. Twilio is now the last active BYOK verification backlog item.
3. Keep the launch/dashboard API key drift in view as a separate bootstrap/ops concern, but do not block runtime-review progress on it.
4. Unstructured still remains blocked on multipart/form-data support.
