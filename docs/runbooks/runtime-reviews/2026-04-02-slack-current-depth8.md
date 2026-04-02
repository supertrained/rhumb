# Runtime review — Slack current depth 8

**Date:** 2026-04-02
**Owner:** Pedro / Keel runtime review loop

## Why Slack

Fresh public callable coverage showed Slack as the **sole weakest** callable provider before the pass:
- claim-safe runtime-backed depth: **7**
- freshest evidence: `2026-04-01T11:13:49Z`

That made Slack the clean next WU-T4 lane instead of reopening dogfood or Google AI from stale fallback logic.

## Pass shape

### Rhumb route
- Endpoint: `POST /v1/proxy/`
- Service: `slack`
- Upstream path: `POST /api/auth.test`
- Temp org: `org_runtime_review_slack_20260402t183733z`
- Temp agent: `cb012bb3-6e92-40c6-93f1-1621da26f1b8`
- Explicit Slack access grant: `22eed792-8014-4783-9568-42aff5b23d46`

### Direct control
- Endpoint: `POST https://slack.com/api/auth.test`
- Auth: direct Slack bot token

## Compared fields

Safe read-only parity check on:
- `ok`
- `url`
- `team`
- `team_id`
- `user`
- `user_id`
- `bot_id`
- `is_enterprise_install`

## Result

### Rhumb proxy
- HTTP status: `200`
- Upstream status: `200`
- Workspace: `TeamSuper`
- Workspace URL: `https://team-super-ai.slack.com/`
- Team ID: `T08HGQD6FGW`
- User: `cordelia`
- User ID: `U0AECQMK5FG`
- Bot ID: `B0AEESDJ1CJ`
- Enterprise install: `false`

### Direct Slack control
- HTTP status: `200`
- Returned the exact same normalized identity fields

### Verdict
- **PASS**
- Managed/direct parity: **exact**

## Published trust rows
- Evidence: `a73ca778-4f68-40e8-a334-cf29e13ade58`
- Review: `5b62a497-9097-4ed0-817a-4e395cc56ca5`

## Coverage impact

Pre-pass callable audit:
- artifact: `artifacts/callable-review-coverage-2026-04-02-pre-slack-current-pass-from-cron.json`
- Slack runtime-backed depth: **7**
- Weakest bucket: **Slack only**

Post-pass callable audit:
- artifact: `artifacts/callable-review-coverage-2026-04-02-post-slack-current-pass-from-cron.json`
- Slack runtime-backed depth: **7 → 8**
- New weakest bucket at depth **8**:
  - `slack`
  - `stripe`
  - `twilio`

## Artifacts
- Runtime pass: `artifacts/runtime-review-pass-20260402T183733Z-slack-depth8.json`
- Publication: `artifacts/runtime-review-publication-2026-04-02-slack-depth8.json`
- Pre-pass coverage: `artifacts/callable-review-coverage-2026-04-02-pre-slack-current-pass-from-cron.json`
- Post-pass coverage: `artifacts/callable-review-coverage-2026-04-02-post-slack-current-pass-from-cron.json`
- Helper script: `scripts/runtime_review_slack_depth8_20260402.py`

## Next target

After this pass, the weakest callable bucket is no longer Slack-only.

The next freshness-ordered weakest provider is **Stripe**:
- depth: `8`
- freshest evidence before Slack rerun: `2026-04-02T10:50:35Z`

Twilio is also in the weakest bucket, but its freshest evidence (`2026-04-02T14:49:29Z`) is newer than Stripe.
