# Phase A acceptance (locked)

Re-verified live with curl at **2026-09-09T21:17:04Z**. Production is still the pre-deploy baseline. This PR is propose-only.

## Done-when

1. Public-truth pipeline feeds site chips, `llms.txt`, agent-caps, and README. Kill `1038 / 415 / 16 / 92` drift. Before/after vs live API (`services≈999`, `capabilities≈435`, `callable≈28–29`, `categories≈87`).
2. Root `/agent-capabilities.json` is 200 or redirects to `.well-known`. Keep both in sync.
3. #40: search `email sending` / `send email` / `email API for agents` each returns ≥3 plausible email providers. Alternatives non-empty where data exists.
4. #42: Twilio (and ≥1 other) failures are non-empty **or** honest unknown — not silent `[]`.
5. Billing health degrades when the outbox is stale beyond the published SLO. Propose public wallet/outbox exposure options. Do not expand exposure.
6. CI/Makefile aligned to `packages/astro-web`. Harness green enough; document baseline.
7. PRs against `main` with evidence.

Hard fences: no OpenClaw; do not merge/rebase/continue #59; propose-only deploys.

## Live production (before deploy)

| Check | Live evidence |
| --- | --- |
| Counters | `GET /v1/services?limit=1` → **999**; `/v1/capabilities?limit=1` → **435**; `/v1/proxy/stats` → callable **28** / registered **29**; `/v1/leaderboard` → **87** |
| Site drift | `rhumb.dev/` still contains `1,038 scored services` and `16 callable providers`. `/llms.txt` still contains `1,038`, `415`, `16 callable`. `/.well-known/agent-capabilities.json` coverage is `1038 / 415 / 92 / 16`. `/docs` and `/about` still show `1,038`. |
| Agent-caps path | `GET https://rhumb.dev/agent-capabilities.json` → **404**. Well-known → **200** (stale numbers). |
| #40 search | `email sending` → 1 row (`aws-ses-v3`). `send email` → 1 row (`google-workspace-api`). `email API for agents` → **0**. |
| Alternatives | `GET /v1/services/{slug}/alternatives` → **404**. `GET /v1/services/{slug}` alternatives **are** populated (sendgrid/resend/postmark/mailgun/stripe/twilio each return 5 peers). |
| #42 failures | Twilio `failure_modes: []` with no `coverage`/`honesty`. Sendgrid/postmark/mailgun/aws-ses-v3 also silent empty. Stripe has 3 modes. Resend has 2. |
| Billing | `status: operational` with `event_outbox_pending_count: 202`, `oldest_pending_age_seconds: 8353672` (~97 days), plus public `settlement_wallet_eth_balance: "0.010000"`. |

## After this PR (code + generated surfaces; needs Tom deploy)

| Check | After |
| --- | --- |
| Counters in repo | `public-truth-counts.ts` fetchedAt `2026-09-09T21:03:39Z`: 999 / 435 / 28 / 29 / 87. Generator rewrites README, MCP README, `llms.txt`, all three agent-caps JSON files. |
| Agent-caps | Astro `public/agent-capabilities.json` + redirect `/agent-capabilities.json` → `/.well-known/`. Byte-aligned with root JSON. |
| #40 | Token search unit tests: each query recalls ≥3 email providers (`sendgrid`, `resend`, `postmark`, `mailgun`, `aws-ses-v3`). |
| Alternatives | Dedicated `/v1/services/{slug}/alternatives` returns the same scored peers as service detail. |
| #42 | Twilio catalog (≥4 modes) + `coverage`/`honesty`. Stripe stays non-empty from live rows. Empty others become `coverage: unresearched` with an honesty string, not silent `[]`. |
| Billing | Same live outbox (202 / ~97d) becomes `degraded`. Exact ETH balance removed. SLO: pending > 25 or age > 6h. |
| CI | `public-truth` and `astro-web-build` green. `api-test` now installs; pytest **3093 passed / 58 failed** on `def7cc23` (Phase A files not in the fail list). `cli-test` black wrap on `find.py` fixed in the follow-up. |

## Curl used

```bash
curl -sS https://api.rhumb.dev/v1/services?limit=1
curl -sS https://api.rhumb.dev/v1/capabilities?limit=1
curl -sS https://api.rhumb.dev/v1/proxy/stats
curl -sS https://api.rhumb.dev/v1/leaderboard
curl -sS -G https://api.rhumb.dev/v1/search --data-urlencode 'q=email sending'
curl -sS https://api.rhumb.dev/v1/services/twilio/failures
curl -sS https://api.rhumb.dev/v1/services/sendgrid
curl -sS https://api.rhumb.dev/v1/billing/health
curl -sSI https://rhumb.dev/agent-capabilities.json
```
