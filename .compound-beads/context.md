# Compound Beads Context — Rhumb

> Portable memory for Pedro. Read at session start. Update as you work.

## Who I Am

Pedro — operator running Rhumb end-to-end. Product judgment stays with me. Specialists and coding lanes accelerate crisp slices; they do not replace ownership.

## What I Know About This Project

- **Project:** Rhumb — infrastructure layer agents use to discover, access, and trust external tools
- **Tech stack:** FastAPI, Astro 6, Supabase, Railway, Vercel, npm MCP package
- **Current focus:** live-product audit, public truth-surface integrity, and shipping handoff-ready content from real user/agent friction
- **Operating mode:** audit-first, ship what the audit proves is missing, keep claims tied to live verification

## What Exists Now

| Resource | Purpose |
|----------|---------|
| `docs/AUDIT-CONTENT-CJ-AFFILIATES-2026-03-17.md` | repo-level content, customer journey, and affiliate audit |
| `BACKLOG.md` | prioritized product/growth backlog from live testing |
| `memory/working/continuation-brief.md` | current operating stack and blockers |
| `memory/working/tom-todo.md` | only things Pedro needs from Tom |
| `memory/working/decision-log.md` | active locks / launch gates / policy changes |
| `docs/PUBLIC-CLAIM-LEDGER.md` | launch-critical truth surface for public claims |

### Current Product Truth
- `rhumb.dev` live
- Railway API live
- `rhumb-mcp@0.6.0` live with 16 tools
- 212 services scored
- 103 capabilities across 30 domains
- 249 service mappings, 6 bundles
- 1054 reviews, 168 runtime-backed (15.9%) — public review stats remain frozen until ratio recovers above 20%
- Stripe prepaid credits + x402 USDC path operational in production

## Current Round

- **Display ID:** Round 23
- **Machine ID:** cb-r023
- **Type:** growth
- **Goal:** Convert live audit findings into tighter journey truth surfaces and public content humans can hand to agents
- **Status:** in_progress
- **Started:** 2026-03-17T13:40:00-07:00
- **DRI:** Pedro

## Modified / Shipped This Round

- Patched CLI default API base + env override to avoid dead `api.rhumb.dev` DNS path
- Updated docs examples to match actual `{ data, error }` wrapper behavior
- Updated `llms.txt`/docs references toward real API host usage
- Confirmed live search and billing endpoint behavior
- Added `docs/AUDIT-CONTENT-CJ-AFFILIATES-2026-03-17.md`
- Shipped first comparison page: `/blog/stripe-vs-square-vs-paypal` (product commit `57fbcee`)

## Ready Tasks

- [READY] Close onboarding dead end: define truthful public path for account creation / API key issuance or remove misleading implied flow
- [READY] Ship second high-signal comparison page (`Resend vs SendGrid vs Postmark`) or tool-autopsy surface
- [READY] Fix remaining support-truth inconsistencies (`api.rhumb.dev` references still lingering in API/provisioning codepaths; score endpoint wrapper inconsistency)
- [READY] Verify the comparison page is properly linked/indexed and folded into content distribution surfaces

## Blocked Tasks

- [BLOCKED] Final pricing model expansion (`GET /v1/pricing`, free tier count, volume discounts, x402 margin)
  └─ Needs: Tom confirmation on model boundaries
- [BLOCKED] Launch timing / provider outreach
  └─ Needs: Tom go/no-go
- [BLOCKED] Keel runtime-backed ratio recovery via additional provider keys
  └─ Needs: ~11 API keys from Tom

## Discovered Work

- [DISCOVERED] The conversion bottleneck is no longer raw scoring breadth; it is the gap between public interest and self-serve activation.
- [DISCOVERED] Comparison pages are the highest-leverage human→agent handoff artifact because they compress decision, score context, and routing guidance into a single link.
- [DISCOVERED] `web_search` instability is a real dogfood signal during pricing-model panel work; search fallbacks need a more reliable operating pattern.

## Open Questions

- [OPEN] What is the truthful public self-serve path before full dashboard/account infrastructure exists?
- [OPEN] Which next content surface compounds fastest: email-provider comparison or tool-autopsy series?
- [OPEN] Should `api.rhumb.dev` be restored via DNS/rewrite, or should Railway be the explicit public API host until proxying exists?

## Session Decisions

- **Audit-first over speculative building:** when engineering is unblocked but not urgent, use dead cycles to thoroughly test the live product from multiple personas and ship fixes from evidence.
- **Truth surfaces outrank polish:** docs/llms/CLI/API parity is launch-critical trust infrastructure, not content garnish.
- **Comparison pages are product, not marketing:** these are operational artifacts a human can hand directly to an agent.

## Recent Activity

| Date | Round | Activity |
|------|-------|----------|
| 2026-03-17 | 23 | Live audit identified trust-surface breakage and onboarding dead ends |
| 2026-03-17 | 23 | First comparison page shipped live from audit evidence |
