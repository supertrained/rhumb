# Runtime review — Slack current depth 9

**Date:** 2026-04-02
**Owner:** Pedro / Keel runtime review loop

## Why Slack

Fresh public callable coverage showed Slack as the **sole weakest** callable provider before the pass:
- claim-safe runtime-backed depth: **8**
- freshest evidence: `2026-04-02T18:37:40Z`

That made Slack the clean next WU-T4 lane instead of reopening dogfood or Google AI from stale fallback logic.

## Pass shape

### Rhumb route
- Endpoint: `POST /v1/proxy/`
- Service: `slack`
- Upstream path: `POST /api/auth.test`
- Temp org: `org_runtime_review_slack_20260402t223435z`
- Temp agent: `9bff835c-4b88-42fa-ac97-328f4a61daf6`
- Explicit Slack access grant: `80be92c3-afb7-4e12-b9b9-8022a3e67e44`

### Direct control
- Endpoint: `POST https://slack.com/api/auth.test`
- Auth: direct Slack bot token from 1Password item `Slack - TeamSuper Bot Token`

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
- Evidence: `4f59ba6e-0a29-45bb-9258-067d5a403728`
- Review: `c9182d6f-04a9-4169-a64b-fe3c58c79632`

## Coverage impact

Pre-pass callable audit:
- artifact: `artifacts/callable-review-coverage-2026-04-02-pre-slack-current-pass-from-cron-1531.json`
- Slack runtime-backed depth: **8**
- Weakest bucket: **Slack only**

Post-pass callable audit:
- artifact: `artifacts/callable-review-coverage-2026-04-02-post-slack-current-pass-from-cron-1531.json`
- Slack runtime-backed depth: **8 → 9**
- New weakest bucket at depth **9**:
  - `github`
  - `slack`
  - `stripe`
  - `apify`
  - `exa`
  - `replicate`
  - `unstructured`
  - `algolia`
  - `twilio`

## Artifacts
- Runtime pass: `artifacts/runtime-review-pass-20260402T223435Z-slack-depth9.json`
- Publication: `artifacts/runtime-review-publication-2026-04-02-slack-depth9.json`
- Pre-pass coverage: `artifacts/callable-review-coverage-2026-04-02-pre-slack-current-pass-from-cron-1531.json`
- Post-pass coverage: `artifacts/callable-review-coverage-2026-04-02-post-slack-current-pass-from-cron-1531.json`
- Helper script: `scripts/runtime_review_slack_depth9_20260402.py`

## Next target

After this pass, Slack is no longer the sole weakest callable provider.

The next freshness-ordered weakest provider is **Exa**:
- depth: `9`
- freshest evidence before Slack rerun: `2026-03-30T23:08:32Z`
