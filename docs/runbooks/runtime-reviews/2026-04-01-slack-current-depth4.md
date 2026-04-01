# Runtime Review — Slack depth 3→4

**Date:** 2026-04-01
**Owner:** Pedro / Keel runtime review loop

## Why Slack

Fresh callable audit showed weakest claim-safe depth **3** across 4 providers: `slack`, `github`, `twilio`, `algolia`. Slack was the stalest by freshest runtime evidence timestamp.

## Pass Details

- **Endpoint:** POST /api/auth.test (safe read, no side effects)
- **Previous depth-3 passes:** all used auth.test with 3 parity fields (team, user, bot_id)
- **This pass:** expanded parity surface to 8 fields

### Expanded Parity Fields
1. `ok` — API success flag
2. `url` — workspace URL
3. `team` — workspace name
4. `team_id` — workspace ID
5. `user` — bot user name
6. `user_id` — bot user ID
7. `bot_id` — bot ID
8. `is_enterprise_install` — enterprise grid flag

### Temp Agent
- Org: `org_rhumb_internal`
- Agent: `74e3ec81-7b56-467a-9987-e9d36eaca34b`
- Granted explicit `slack` service access
- Disabled after pass

### Managed vs Direct Results

| Field | Managed | Direct | Match |
|---|---|---|---|
| ok | true | true | ✅ |
| url | https://team-super-ai.slack.com/ | https://team-super-ai.slack.com/ | ✅ |
| team | TeamSuper | TeamSuper | ✅ |
| team_id | T08HGQD6FGW | T08HGQD6FGW | ✅ |
| user | cordelia | cordelia | ✅ |
| user_id | U0AECQMK5FG | U0AECQMK5FG | ✅ |
| bot_id | B0AEESDJ1CJ | B0AEESDJ1CJ | ✅ |
| is_enterprise_install | false | false | ✅ |

**Parity: PASS** — all 8 fields matched exactly.

## Published Trust Rows
- Evidence: `70d5e53a-df6b-4286-b518-60df96b02448`
- Review: `8c65fd24-dddf-4454-b6ca-c98ecadc55cc`

## Coverage Impact
- Slack claim-safe runtime-backed reviews: **3 → 4**
- Callable review floor stayed: **3**
- Weakest bucket shrank: **4 → 3** (github, twilio, algolia)

## Artifacts
- Runtime pass: `artifacts/runtime-review-pass-20260401T111246Z-slack-depth4.json`
- Pre-pass audit: `artifacts/callable-review-coverage-2026-04-01-pre-slack-depth4.json`
- Post-pass audit: `artifacts/callable-review-coverage-2026-04-01-post-slack-depth4.json`
- Helper script: `scripts/runtime_review_slack_depth4_20260401.py`

## Proxy Observation
During this pass, discovered that the Slack Web API proxy only works for parameterless endpoints (like `auth.test`). Endpoints requiring parameters (like `users.info?user=...` or `team.info`) fail because the proxy sends JSON body but Slack expects `application/x-www-form-urlencoded`. This is a known proxy limitation, not a depth-4 blocker.

## Next Target
Next stalest in the weakest depth-3 bucket is `github` (freshest evidence: 2026-04-01T00:23:34Z).
