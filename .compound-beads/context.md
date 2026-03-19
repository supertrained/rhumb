# Compound Beads Context — Rhumb

> Portable memory for Pedro. Read at session start. Update as you work.
> **Last cleaned:** 2026-03-19. Historical rounds (R1-R21) archived to `memory/archive/compound-beads-rounds-1-21.md`.

## Current State

### Product
- **Site:** https://rhumb.dev — 23 blog posts, 9 comparisons, 4 autopsies, 2 guides, /compare + /autopsy landing pages, /quickstart, /glossary
- **API:** https://api.rhumb.dev/v1 (canonical) | fallback: https://rhumb-api-production-f173.up.railway.app/v1
- **MCP:** `npx rhumb-mcp@0.7.0` — x402 payment flow live for agents
- **Data:** 212 services, 103 capabilities, 30 domains, 249 mappings, 6 bundles
- **Reviews:** 1054 (168 runtime-backed, 15.9% — below 20%, stats FROZEN)
- **Payment rails:** Stripe prepaid + x402 USDC both live and verified
- **3 credential modes:** BYO, Rhumb-managed, Agent Vault — all work E2E
- **Content formats:** articles (8), comparisons (9), autopsies (4), guides (2)

### Launch
- All 4 hard gates CLEAR (as of 2026-03-14)
- Launch timing remains **Tom-gated**
- Lightning-strike launch plan at `docs/LIGHTNING-STRIKE-LAUNCH.md`

### Comparison Series (9 pages, shipped 2026-03-17/18)
9 pages live, all cross-linked, in nav, in llms.txt:
1. Payments: Stripe vs Square vs PayPal
2. Email: Resend vs SendGrid vs Postmark
3. CRM: HubSpot vs Salesforce vs Pipedrive
4. Auth: Auth0 vs Clerk vs Firebase Auth
5. Analytics: PostHog vs Mixpanel vs Amplitude
6. Databases: Supabase vs PlanetScale vs Neon
7. Messaging: Twilio vs Vonage vs Plivo
8. Project Management: Linear vs Jira vs Asana
9. AI / LLM: Anthropic vs OpenAI vs Google AI

### Autopsy Series (shipped 2026-03-18)
4 pages live, all cross-linked, in nav, in llms.txt:
1. HubSpot (4.6) — 6 failure modes
2. Salesforce (4.8) — 6 failure modes
3. Twilio (8.0) — strengths + friction model
4. Shopify (7.8) — GraphQL analysis

## Round History (Recent)

### Round 24 (cb-r024) — COMPLETE ✅
Tool Autopsy Series. 4 pages + landing page + infrastructure in ~26 min.
Commits: `b1336c6` → `88d527f` → `9bda057` → `02f24e0`.

### Round 23 (cb-r023) — COMPLETE ✅
Content sprint: 6 comparison pages + discoverability infrastructure.

### Round 22 (cb-r022) — COMPLETE ✅
Payment System Phase 0. 7/7 WUs in ~75 min. 96 tests.

### Rounds 1-21 — ALL COMPLETE
Archived to `memory/archive/compound-beads-rounds-1-21.md`.

## Blockers (External)
- No sign-up / dashboard / API key issuance flow — **#1 activation gap**
- WU-1.1 (legal for crypto) — Tom-gated
- WU-1.8-1.9 (mainnet activation) — blocked on legal
- ~11 API keys for Keel — Tom-gated
- Pricing mostly confirmed (free tier 1K/mo, x402 15%, managed 20%). Remaining: volume tiers + token expansion.
- Launch timing — Tom-gated

### Round 25 — COMPLETE ✅
- WU-25.1: Getting Started with Rhumb MCP guide — `/blog/getting-started-mcp` live
- WU-25.2: Messaging comparison (Twilio vs Vonage vs Plivo) — `/blog/twilio-vs-vonage-vs-plivo` live
- WU-25.3: Project Management comparison (Linear vs Jira vs Asana) — `/blog/linear-vs-jira-vs-asana` live
- WU-25.4: Content freshness system — dateModified on all pages + cadence plan

### Round 26 — IN PROGRESS
- WU-26.1: AI/LLM comparison (Anthropic vs OpenAI vs Google AI) — COMPLETE ✅
  - `/blog/anthropic-vs-openai-vs-google-ai` live
- WU-26.2: Expert panels — COMPLETE ✅
  - Homepage marketing panel + auth/payment architecture panel completed
  - Key finding: activation > discovery as current bottleneck
- WU-26.3: Activation MVP Phase A — COMPLETE ✅
  - Homepage rewrite shipped (hero, blog content section, three-path entry, x402 callout)
  - Security/BYOK blog shipped
  - Quickstart shipped
  - llms.txt + agent-capabilities + JSON-LD shipped
  - x402 anonymous auth gate + MCP x402 mode shipped
  - `rhumb-mcp@0.7.0` published
  - `api.rhumb.dev` custom domain live with TLS
- WU-26.4: Activation MVP Phase B — IN PROGRESS
  - WU-B5 pricing contract shipped: `GET /v1/pricing` + public `/pricing` page live (commit `ad45d6f`)
  - `/glossary` shipped as the next unblocked trust/activation surface while signup remains OAuth-blocked
  - Adversarial review immediately surfaced a discoverability gap; glossary is now wired into main nav, mobile nav, and trust page
  - Build/runtime alignment hardened for the Astro/Vercel surface: repo now pins Node 24 via `.nvmrc` + package engines
  - Live verification surfaced two trust-surface bugs and both are now fixed in code: `/quickstart` no longer points REST users at a nonexistent alternatives endpoint, and `/v1/pricing` now has an API-bundled pricing catalog fallback for Docker deploys
  - Remaining: WU-B1 signup flow + WU-B3 dashboard first-run (signup blocked on OAuth credentials)
  - Launch-prep advanced while blocked: shipped `docs/LAUNCH-ASSET-PACK-2026-03-19.md` covering Moltbook copy, channel hooks, and operator-vs-agent launch narrative variants
  - Launch-proof tracker refreshed to current truth: launch copy readiness improved, but social proof remains zero, the lightning audit rerun is now stale, and GitHub public metadata still understates scope (`50+ APIs`)
  - Focused adversarial review caught a live trust-surface claim bug: `/trust` said runtime-backed coverage was over 20% even though current truth is 15.9%; source wording has been corrected in code to remove the false threshold claim
