# Compound Beads Context — Rhumb

> Portable memory for Pedro. Read at session start. Update as you work.
> **Last cleaned:** 2026-03-19. Historical rounds (R1-R21) archived to `memory/archive/compound-beads-rounds-1-21.md`.

## Current State

### 2026-04-08 AUD-18 Snapshot
- Primary lane is still `AUD-18`, not callable freshness and not `AUD-3` recovery.
- DB read-first is proven enough, including hosted `agent_vault` and the signed `rhdbv1` bridge proof (`rhumb/artifacts/aud18-db-read-agent-vault-signed-token-proof-20260408T120733Z.json`).
- First hosted S3 proof bundle is also green enough (`rhumb/artifacts/aud18-s3-hosted-proof-20260408T2315Z-public-aws.json`).
- The next bounded AUD-18 rail is now locked as **Zendesk ticket read-first**. Decision: `docs/specs/AUD-18-NEXT-READ-FIRST-RAIL-DECISION-2026-04-08.md`. Contract: `docs/specs/AUD-18-ZENDESK-TICKET-READ-FIRST-CONTRACT-2026-04-08.md`.
- First Zendesk implementation slice is now scaffolded in product code:
  - `packages/api/services/support_connection_registry.py` for env-backed `support_ref` bundle resolution via `RHUMB_SUPPORT_<REF>`
  - `packages/api/routes/support_execute.py` for direct execute handling of `ticket.search`, `ticket.get`, and `ticket.list_comments`
  - `packages/api/services/zendesk_support_executor.py` for bounded Zendesk reads with scope enforcement and public-comments-only defaults
  - `packages/api/routes/capability_execute.py` wired to early-dispatch the support rail
  - `packages/api/routes/capabilities.py` now resolves those three capabilities to the direct Zendesk rail instead of blurring them into generic support mappings
- Focused verification is green for the new slice:
  - `packages/api/tests/test_support_connection_registry.py`
  - `packages/api/tests/test_zendesk_support_executor.py`
  - `packages/api/tests/test_support_execute.py`
  - `packages/api/tests/test_support_capability_registry.py`
  - `packages/api/tests/test_capabilities.py`
- Operator follow-through is sharper now too:
  - `scripts/build_zendesk_support_bundle.py` builds bounded hosted support bundles
  - `scripts/zendesk_read_dogfood.py` now matches shipped denial semantics (`403 support_ticket_scope_denied`, `403 support_internal_comments_denied`) and no longer pretends a fake default ticket id proves scope denial
  - `scripts/audit_support_proof_sources.py` now turns the proof-material discovery pass into a repeatable artifact across shared vault metadata, browser history, and Gmail metadata
  - latest rerun artifact `artifacts/aud18-zendesk-hosted-proof-20260409T0218Z-post-harness-fix.json` still fails honestly because hosted Rhumb does not yet have `RHUMB_SUPPORT_ST_ZD`
  - latest discovery artifact `artifacts/aud18-support-proof-source-audit-20260409T0634Z.json` confirms the blocker is still credential truth: no vault-backed Zendesk / Intercom items, no non-public workspace traces in the `rhumb` browser profile, and only third-party provider support threads in Gmail metadata
- Current honest next step: source bounded Zendesk proof material, set hosted `RHUMB_SUPPORT_ST_ZD`, and rerun the first hosted proof bundle before widening to Intercom or any write/mutate support actions.

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
  - Launch-proof tracker refreshed to current truth: launch copy readiness improved, social proof remains zero, and the lightning audit rerun is now stale
  - Focused adversarial review caught a live trust-surface claim bug: `/trust` said runtime-backed coverage was over 20% even though current truth is 15.9%; source wording was corrected and production now serves the non-numeric claim
  - Blocked-safe launch-prep continued: GitHub public metadata no longer understates scope; the repo description now reflects current public truth (`200+ services`, `100+ capabilities`)
