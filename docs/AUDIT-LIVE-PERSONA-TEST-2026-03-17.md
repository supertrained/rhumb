# Live Persona Test Audit — 2026-03-17

> Scope: live site + docs + llms.txt + CLI + API smoke tests from human/operator and agent personas
> Author: Pedro

## Tested personas
1. **Indie developer** — lands on site, searches for a tool, checks docs, tries CLI
2. **Operator evaluating payments** — views pricing, service pages, leaderboard, docs
3. **Agent reading llms.txt** — tries to discover endpoints and tools programmatically
4. **CLI user** — installs/uses `rhumb` locally
5. **MCP/agent integrator** — checks docs for base URL and tool names

## What worked
- Homepage/search/service-page UX is strong and legible
- Search flow returns useful results (`stripe`, `payment`)
- Service pages are genuinely valuable: score, failure modes, freshness, breakdowns
- Production API itself is alive on Railway host and returns real data
- CLI command set is directionally good once pointed at the correct API base URL

## High-signal friction / bugs found

### P0
1. **Public API hostname drift**
   - `api.rhumb.dev` does not resolve
   - `rhumb.dev/v1/...` returns 404
   - Docs and llms.txt were pointing people/agents at dead or ambiguous routes
   - Actual live API: `https://rhumb-api-production-f173.up.railway.app/v1`

2. **CLI first-run failure**
   - `rhumb find stripe` failed with `Connection refused`
   - Root cause: CLI defaulted to `http://localhost:8000/v1`
   - This breaks the first real operator trial

3. **Docs response-shape drift**
   - Docs examples did not match live payloads
   - Some live endpoints return `{ data, error }`, while score returns a raw object
   - This creates parsing failures for humans and agents implementing clients from docs

4. **Pricing/onboarding dead end**
   - Pricing page says: create org + generate API key from dashboard
   - No public dashboard/signup path is exposed on the site
   - High-intent user hits a dead end right at conversion

### P1
5. **Content/detail drift across surfaces**
   - Blog index title drift vs article numbers
   - Docs examples stale vs live data
   - Trust product cannot afford factual drift between pages

6. **Service pages need clearer next-step actions**
   - They explain score/risk well
   - They are weaker on explicit "do this next" conversion paths

7. **Category pages are still mostly raw tables**
   - They need editorial intros for search, context, and better agent parsing

## Fixes started immediately
- Updated docs page source to point at real production API base URL
- Updated llms.txt source to use absolute production API URLs and list capability/billing tools
- Updated CLI config to support `RHUMB_API_BASE_URL` and default to production instead of localhost
- Fixed blog index title drift to match article

## Validation after fixes
- `rhumb find stripe` now works locally against production
- Astro web build passes after the docs/llms changes
- CLI tests pass in the project virtualenv

## Backlog implications
- Public API base URL and docs parity are launch-critical trust fixes
- Pricing/onboarding path needs explicit owner and surface
- Comparison pages + framework onboarding guides are the best next content assets
- Affiliate links belong only on service-guide surfaces with explicit disclosure, never on ranking surfaces
