# Runtime review — Slack current depth 10

**Date:** 2026-04-03  
**Owner:** Pedro / Keel runtime review loop

## Why Slack

Fresh public callable coverage showed Slack as the **sole weakest** callable provider before the pass:
- claim-safe runtime-backed depth: **9**
- freshest evidence: `2026-04-02T22:34:39Z`

That made Slack the clean next WU-T4 lane instead of reopening dogfood or Google AI from stale fallback logic.

## Pass shape

### Rhumb route
- Endpoint: `POST /v1/proxy/`
- Service: `slack`
- Upstream path: `POST /api/auth.test`
- Temp org: `org_runtime_review_slack_20260403t104534z`
- Temp agent: `e54d0ec8-374b-48f7-a398-7472bfb01017`
- Explicit Slack access grant: `94ef1e18-7076-4a9c-8984-e2d490a0e69f`

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

### First run truth
- The first fresh-agent run failed honestly on a transient auth propagation race:
  - Rhumb proxy: `401 Invalid or expired Rhumb API key`
  - direct Slack control: `200`
- This was the same class of fresh-key propagation flake already seen on other review rails, but on the execute path rather than estimate.
- I hardened the Slack helper with:
  - `POST_GRANT_PROPAGATION_DELAY_SECONDS = 5`
  - bounded execute retry on the specific transient invalid-key signature

### Passing rerun
#### Rhumb proxy
- HTTP status: `200`
- Workspace: `TeamSuper`
- Workspace URL: `https://team-super-ai.slack.com/`
- Team ID: `T08HGQD6FGW`
- User: `cordelia`
- User ID: `U0AECQMK5FG`
- Bot ID: `B0AEESDJ1CJ`
- Enterprise install: `false`

#### Direct Slack control
- HTTP status: `200`
- Returned the exact same normalized identity fields

#### Verdict
- **PASS**
- Managed/direct parity: **exact**
- Execute attempts on the passing run: **1**

## Published trust rows
- Evidence: `991152b9-afe2-41c7-b6ed-b5f48dfdcca9`
- Review: `7c00dec7-7cee-4c5a-ad77-39a28cd65eaf`

## Coverage impact

Pre-pass callable audit:
- artifact: `artifacts/callable-review-coverage-2026-04-03-pre-slack-current-pass-from-cron-0342.json`
- Slack runtime-backed depth: **9**
- Weakest bucket: **Slack only**

Post-pass callable audit:
- artifact: `artifacts/callable-review-coverage-2026-04-03-post-slack-current-pass-from-cron-0342.json`
- Slack runtime-backed depth: **9 → 10**
- Callable review floor: **10 across all 16 callable providers**
- Weakest bucket is now the full callable set at depth **10**, i.e. there is no remaining sub-10 straggler

## Artifacts
- Runtime pass: `artifacts/runtime-review-pass-20260403T104534Z-slack-depth10.json`
- Publication: `artifacts/runtime-review-publication-2026-04-03-slack-depth10.json`
- Pre-pass coverage: `artifacts/callable-review-coverage-2026-04-03-pre-slack-current-pass-from-cron-0342.json`
- Post-pass coverage: `artifacts/callable-review-coverage-2026-04-03-post-slack-current-pass-from-cron-0342.json`
- Helper script: `scripts/runtime_review_slack_depth10_20260403.py`

## Next target

With Slack lifted out of the last sub-10 bucket, the callable review floor is now **10** everywhere.

If WU-T4 continues as a freshness loop, the next honest target should be chosen from the oldest depth-10 evidence set after a fresh coverage pull. Practical note: PDL already gets separate fix-verification attention, so the next non-PDL freshness target is likely **E2B** unless the live ordering changes.
