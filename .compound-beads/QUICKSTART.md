# Quick Start - Rhumb

> **Last Updated:** 2026-03-19T06:43:00-07:00
> **Current Round:** 26 IN_PROGRESS. Phase A complete (WU-A1–A4 shipped). Phase B partially complete: WU-B5 pricing contract + pricing page shipped. Homepage rewrite shipped (hero, blog content, three-path, x402 callout). Security/BYOK blog shipped. `api.rhumb.dev` live with TLS. `/glossary` shipped as the next unblocked trust/activation surface while signup remains OAuth-blocked. Next blocking slice: WU-B1 signup flow once OAuth creds exist.
> **Status:** 23 blog posts across 4 formats. 9 comparisons, 4 autopsies, 2 guides. Homepage fully panel-informed. x402 zero-signup path live. `/v1/pricing` + `/pricing` now live. Launch timing Tom-gated.

## What's Live NOW
- **Site:** https://rhumb.dev — 23 blog posts, 9 comparisons, 4 autopsies, 2 guides, /compare + /autopsy landing pages, /quickstart, /glossary, hero: "Most APIs weren't built for agents"
- **API:** https://api.rhumb.dev/v1 (canonical) | fallback: https://rhumb-api-production-f173.up.railway.app/v1
- **MCP:** `npx rhumb-mcp@0.7.0` → x402 payment flow live for agents
- **Data:** 212 services, 103 capabilities, 30 domains, 249 mappings, 6 bundles
- **Reviews:** 1054 (168 runtime-backed, 15.9% — stats FROZEN until >20%)
- **Payment:** Stripe prepaid + x402 USDC both live. Health: operational.
- **Credentials:** 3 modes (BYO, Rhumb-managed, Agent Vault) all work E2E

## Content Series

### Comparison Series (9 pages, all cross-linked)
| Category | URL | Winner | Score Range |
|----------|-----|--------|-------------|
| Payments | /blog/stripe-vs-square-vs-paypal | Stripe (8.1) | 4.9–8.1 |
| Email | /blog/resend-vs-sendgrid-vs-postmark | Resend (7.8) | 5.5–7.8 |
| CRM | /blog/hubspot-vs-salesforce-vs-pipedrive | None (all <6.0) | 4.6–5.7 |
| Auth | /blog/auth0-vs-clerk-vs-firebase-auth | Clerk (7.4) | 5.7–7.4 |
| Analytics | /blog/posthog-vs-mixpanel-vs-amplitude | PostHog (6.9) | 5.8–6.9 |
| Databases | /blog/supabase-vs-planetscale-vs-neon | Too close (7.2–7.6) | 7.2–7.6 |
| Messaging | /blog/twilio-vs-vonage-vs-plivo | Twilio (8.0) | 6.4–8.0 |
| Project Mgmt | /blog/linear-vs-jira-vs-asana | Linear (7.5) | 7.0–7.5 |
| AI / LLM | /blog/anthropic-vs-openai-vs-google-ai | Anthropic (8.4) | 6.3–8.4 |

### Autopsy Series (4 pages, cross-linked)
| Tool | URL | Score | Key Finding |
|------|-----|-------|-------------|
| HubSpot | /blog/hubspot-api-autopsy | 4.6 | Cross-hub API inconsistency, OAuth maze |
| Salesforce | /blog/salesforce-api-autopsy | 4.8 | Governance 10.0 / autonomy 2.0 split |
| Twilio | /blog/twilio-api-autopsy | 8.0 | What agent-native almost looks like |
| Shopify | /blog/shopify-api-autopsy | 7.8 | GraphQL bet agents must navigate |

## Launch Gates — ALL CLEAR ✅
1. ✅ Technical completeness
2. ✅ Proxy maturity (P50 overhead 4.1ms)
3. ✅ Primitive-product roadmap
4. ✅ Review quality floor (504 reviews, 105 runtime-backed at closure)

Launch timing remains **Tom-gated**.

## Agent Discoverability (LIVE)
- `rhumb.dev/llms.txt` — enhanced with x402 flow, 3 auth paths, pricing, all content
- `rhumb.dev/.well-known/agent-capabilities.json` — full agent manifest (16 tools, pricing, auth)
- JSON-LD SoftwareApplication schema on all pages
- Agent meta tags (ai:capabilities, ai:activation, ai:payment-protocol, ai:signup-required)
- Full activation work plan: `docs/ACTIVATION-WORK-PLAN-2026-03-18.md`

## Blockers
- Signup / dashboard remain the main activation gap. Pricing contract is now live at `/v1/pricing` + `/pricing`; remaining policy cleanup is volume tiers + token expansion.
- ~11 API keys for Keel — Tom-gated
- WU-1.1 legal + WU-1.8 mainnet — Tom-gated

## Infrastructure
- **Vercel:** Auto-deploy from GitHub
- **Railway:** `rhumb-api-production-f173.up.railway.app`
- **Supabase:** 11+ tables, session pooler
- **npm:** `rhumb-mcp@0.7.0` (x402 payment flow live for agents)
- **Analytics:** GA4, Clarity, GSC verified
- **Repo:** `supertrained/rhumb` (product), `tomdmeredith/rhumb-workspace` (workspace)
