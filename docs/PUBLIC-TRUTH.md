# Public truth pipeline

Single source for the public coverage counts that marketing, docs, MCP, and agent-caps must not invent.

## Live counters used (2026-09-09 audit, re-fetched by this branch)

| Counter | Endpoint | Live value |
| --- | --- | --- |
| Services | `GET https://api.rhumb.dev/v1/services?limit=1` → `data.total` | 999 |
| Capabilities | `GET https://api.rhumb.dev/v1/capabilities?limit=1` → `data.total` | 435 |
| Callable providers | `GET https://api.rhumb.dev/v1/proxy/stats` → `data.services_callable` | 28 |
| Registered providers | `GET https://api.rhumb.dev/v1/proxy/stats` → `data.services_registered` | 29 |
| Leaderboard categories | `GET https://api.rhumb.dev/v1/leaderboard` → `data.total` | 87 |

Do not hand-edit those numbers in copy. Refresh them from the live API.

## Source of truth

`packages/astro-web/src/lib/public-truth-counts.ts` holds the committed counters and the fetch timestamp.

`packages/astro-web/src/lib/public-truth.ts` derives labels and summaries from that file. Homepage chips, About/Docs/Resolve/Capabilities copy, and generated machine surfaces read those labels.

## How to regenerate

```bash
# Refresh counts from the live public API, then rewrite generated surfaces
python3 scripts/generate_agent_capabilities.py --from-live --write

# Or, from the Makefile
make public-truth

# CI / local drift check (does not hit the live API)
python3 scripts/generate_agent_capabilities.py --check
```

`--from-live` reads `RHUMB_API_BASE` or `--api-base` (default `https://api.rhumb.dev/v1`).

## Surfaces the generator writes

- `README.md` managed product + MCP tool blocks, plus the visibility-map callable count
- `packages/mcp/README.md` coverage sentence + tool surface
- `llms.txt` and `packages/web/public/llms.txt`
- `agent-capabilities.json`
- `packages/astro-web/public/agent-capabilities.json` (root path on Vercel)
- `packages/astro-web/public/.well-known/agent-capabilities.json`

Astro also redirects `/agent-capabilities.json` → `/.well-known/agent-capabilities.json`.

Runtime pages (`index`, `about`, `docs`, `capabilities`, `resolve`, `search`, `llms.txt.ts`) interpolate `PUBLIC_TRUTH` at build time.

## Billing health SLO

`GET /v1/billing/health` is `degraded` when the durable event outbox exceeds either published SLO:

- pending count > 25
- oldest pending age > 6 hours

Those thresholds live in `packages/api/services/payment_health.py` as `OUTBOX_PENDING_COUNT_SLO` and `OUTBOX_OLDEST_PENDING_AGE_SLO_SECONDS`. The public payload no longer includes the settlement wallet ETH balance.

## Index honesty

- Search tokenizes natural queries (`email sending`, `send email`, `email API for agents`) instead of requiring the whole phrase as a substring. See issue #40.
- Empty `GET /v1/services/{slug}/failures` is a coverage gap (`coverage: unresearched`), not a clean bill of health. Twilio falls back to the published research catalog in `packages/shared/failure-mode-catalog.json` until migration `0165_twilio_failure_modes_seed.sql` is applied. See issue #42.

## Deploy notes for Tom

Propose-only. This branch does **not** production-deploy.

1. Merge this PR (leave #59 / `pp-vnext-foundation` untouched).
2. Deploy API so search tokenization, billing SLO, and failure honesty/catalog go live.
3. Apply `packages/api/migrations/0165_twilio_failure_modes_seed.sql` on production Supabase so the website's direct Supabase read also has Twilio rows.
4. Deploy Vercel `packages/astro-web` so homepage/docs/llms/agent-caps counts and `/agent-capabilities.json` match.
5. Re-run `python3 scripts/generate_agent_capabilities.py --from-live --write` if live totals move before the next marketing pass.

## Boundary

PR #59 (Resolve launch catalog) is out of scope and was not rebased, merged, or continued.
