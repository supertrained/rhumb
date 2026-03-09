# BUILD-PLAN.md — Rhumb Master Execution Plan

> Pedro's autonomous build roadmap. Work units, phases, agent assignments, dependencies.
> Updated: 2026-03-03
> Status: ACTIVE — executing from Round 1

---

## Philosophy

Build for the model 6 months from now, not today's limitations (Boris Cherny).
Ship Discover first, architect Access in parallel (panel consensus).
Don't over-scaffold — latent demand over new habits.
Every friction I hit is a Rhumb data point (dogfood loop).

---

## Phase 0: Foundation (Week 1) — Pedro solo + sub-agents
*Goal: Strategy crystallized, methodology locked, namespace secured, repo scaffolded.*

### Work Unit 0.1: Strategy Doc ← CURRENT
- **Owner:** Pedro (direct write, not delegated)
- **Output:** `STRATEGY.md`
- **Inputs:** Panel synthesis, MEMORY.md, PRINCIPLES.md, brain-dump-grok.md
- **Why first:** Every build decision references this. Can't delegate without it.
- **Round:** CB Round 1

### Work Unit 0.2: AN Score Spec v0.1
- **Owner:** Pedro (direct write)
- **Output:** `AN-SCORE-SPEC.md`
- **Inputs:** Panel synthesis (especially Felix/Zoe agent dimensions), research corpus
- **Includes:** 10 agent-specific dimensions, contextual explanation generation, failure mode taxonomy, certification tiers, anti-gaming framework, probe methodology
- **Round:** CB Round 2

### Work Unit 0.3: Namespace Execution
- **Owner:** Pedro (self-serve) → Tom (for payment/legal)
- **Tasks:**
  - [ ] Draft npm support request for "rhumb" claim (unpublished since 2015)
  - [ ] Draft PyPI registration (check if self-serve or needs Tom)
  - [ ] Draft trademark filing packet (IC 009 + IC 042) with exact forms/strings
  - [ ] Produce one-pager for Tom with all above
- **Output:** `NAMESPACE-PACKET.md`
- **Round:** CB Round 1 (alongside strategy)

### Work Unit 0.4: GitHub Repo + Scaffold
- **Owner:** Codex sub-agent
- **Tasks:**
  - [ ] Create `rhumb` repo (or repurpose rhumb-workspace)
  - [ ] Monorepo structure: `/packages/cli`, `/packages/api`, `/packages/web`, `/packages/shared`
  - [ ] FastAPI scaffold in `/packages/api`
  - [ ] Next.js 15 scaffold in `/packages/web`
  - [ ] CLI scaffold in `/packages/cli` (Python, Click or Typer)
  - [ ] Supabase schema v0 (services, scores, probes, users)
  - [ ] CI/CD: GitHub Actions (lint, type-check, test)
  - [ ] AGENTS.md for coding agents (repo conventions, architecture decisions)
- **Depends on:** WU 0.1 (strategy informs architecture), WU 0.2 (AN Score informs data model)
- **Round:** CB Round 3

---

## Phase 1: Discover MVP (Weeks 2-4) — Agent swarm
*Goal: `rhumb find` works. AN Score for top 50 tools. CLI published.*

### Work Unit 1.1: AN Score Engine
- **Owner:** Codex sub-agent
- **Description:** Core scoring computation from AN-SCORE-SPEC.md
- **Tasks:**
  - [ ] Data model: Service, Dimension, Score, Evidence, Probe
  - [ ] Scoring algorithm: weighted dimensions → composite score
  - [ ] Contextual explanation generator (one-sentence summaries)
  - [ ] Failure mode classifier
  - [ ] Confidence scoring based on evidence freshness
  - [ ] API endpoints: `POST /score`, `GET /services/{id}/score`
- **Tech:** FastAPI, Supabase, Claude Sonnet (for explanation generation)
- **Tests:** Unit + integration, mock probe data
- **Round:** CB Round 4

### Work Unit 1.2: Probe Infrastructure v0
- **Owner:** Codex sub-agent
- **Description:** Automated testing of MCP servers / API endpoints
- **Tasks:**
  - [ ] Probe runner: HTTP health, auth flow testing, schema capture
  - [ ] Schema fingerprinting (structural + semantic comparison)
  - [ ] Rate limit detection (progressive backoff testing)
  - [ ] Error response analysis (parsability, retry-after headers)
  - [ ] Latency measurement (P50/P95/P99 distribution)
  - [ ] Results stored in Supabase with timestamps
  - [ ] Cron scheduler: adaptive intervals (popular tools more frequent)
- **Tech:** Python async (httpx), Supabase, Redis (probe queue)
- **Depends on:** WU 0.4 (repo scaffold)
- **Round:** CB Round 5

### Work Unit 1.3: Tester Agent Fleet v0
- **Owner:** Pedro (architecture) + Codex (implementation)
- **Description:** Automated agents that run standardized test batteries against tools
- **Tasks:**
  - [ ] Define test battery format (YAML/JSON test specs)
  - [ ] Agent harness: runs test battery, captures results
  - [ ] Varied configurations: different auth methods, rate limits, error scenarios
  - [ ] Score 20 initial services → validate AN Score methodology
  - [ ] Output: scored dataset for hand-verification
- **Depends on:** WU 1.1 (scoring engine), WU 1.2 (probe infra)
- **Round:** CB Round 6

### Work Unit 1.4: CLI — `rhumb find`
- **Owner:** Codex sub-agent
- **Description:** Agent-callable CLI for tool discovery
- **Tasks:**
  - [ ] `rhumb find <query>` — semantic search, returns ranked results with AN Scores
  - [ ] `rhumb score <service>` — detailed AN Score breakdown
  - [ ] `rhumb chart <service>` — service profile
  - [ ] Output formats: human-readable (default), JSON (--json), MCP-compatible
  - [ ] No auth required for basic lookups (free tier)
  - [ ] Share-worthy output formatting (like Lighthouse scores)
- **Tech:** Python (Typer), httpx for API calls
- **Depends on:** WU 1.1 (scoring API)
- **Round:** CB Round 7

### Work Unit 1.5: Web — Service Pages + Leaderboard
- **Owner:** Claude Code sub-agent
- **Description:** Public web presence — SEO/MEO surface
- **Tasks:**
  - [ ] Service profile pages (AN Score, breakdown, explanation, failure modes, "tested X min ago")
  - [ ] Category leaderboard pages (top 50 by category)
  - [ ] Homepage with search + hero leaderboard
  - [ ] llms.txt for machine discovery
  - [ ] Schema.org structured data on every page
  - [ ] Mobile responsive, Lighthouse > 90
- **Tech:** Next.js 15, Tailwind 4, Tremor (charts)
- **Depends on:** WU 1.1 (scoring API), WU 1.3 (scored data to display)
- **Round:** CB Round 8

### Work Unit 1.6: MCP Server — Directory as Tool
- **Owner:** Codex sub-agent
- **Description:** Rhumb itself as an MCP server agents can install
- **Tasks:**
  - [ ] MCP server implementation (stdio transport)
  - [ ] Tools: `find_tools`, `get_score`, `get_alternatives`, `get_failure_modes`
  - [ ] Semantic search over service index
  - [ ] Agent-optimized response format (minimal tokens, structured)
  - [ ] Installation instructions for major frameworks
- **Depends on:** WU 1.1, WU 1.4 (validated through CLI first)
- **Round:** CB Round 9

### Work Unit 1.7: Initial 50 Service Dataset
- **Owner:** Pedro (curation) + Tester Fleet (scoring)
- **Description:** Hand-curated list of 50 services, fully scored
- **Tasks:**
  - [ ] Select 50 services across 8-10 categories (prioritize what operators actually use)
  - [ ] Run tester fleet against all 50
  - [ ] Hand-verify scores for top 20 (validate methodology)
  - [ ] Write contextual explanations for each
  - [ ] Publish leaderboard (pre-launch distribution play)
- **Categories:** Email, CRM, Payments, Calendar, Analytics, Content, Social, DevOps, Search, Auth
- **Depends on:** WU 1.3 (tester fleet)
- **Round:** CB Round 10

---

## Phase 2: Access Architecture (Weeks 4-8) — Parallel track
*Goal: Proxy prototype proven at sub-10ms. Agent identity system. Billing pipeline.*

### Work Unit 2.1: Proxy Core
- **Owner:** Codex sub-agent
- **Description:** Minimal viable proxy — single connection point, pass-through
- **Tasks:**
  - [ ] Proxy router: single API key → fan out to provider APIs
  - [ ] Connection pooling (maintain warm connections to top providers)
  - [ ] Latency measurement + logging
  - [ ] Circuit breaker (fail-open with fallback signal to agent)
  - [ ] Target: sub-10ms overhead on proxied calls
- **Tech:** FastAPI, httpx (async), Redis (connection pool state)
- **Round:** CB Round 11

### Work Unit 2.2: Agent Identity System
- **Owner:** Codex sub-agent
- **Description:** Each agent gets own identity, rate limits, tokens
- **Tasks:**
  - [ ] Agent registration: operator creates agent identities
  - [ ] Per-agent API keys + rate limits
  - [ ] Usage tracking per agent (not just per operator)
  - [ ] Access control: which services each agent can reach
- **Depends on:** WU 2.1 (proxy core)
- **Round:** CB Round 12

### Work Unit 2.3: Metering + Billing Pipeline
- **Owner:** Codex sub-agent
- **Description:** Usage tracking, spend caps, billing
- **Tasks:**
  - [ ] Call metering: count, latency, success/fail per agent per service
  - [ ] Spend caps + alerts (runaway agent loop protection)
  - [ ] Billing aggregation (consolidated invoice)
  - [ ] Stripe integration for payment
  - [ ] Free tier: 1,000 proxy calls/month
- **Depends on:** WU 2.1, WU 2.2
- **Round:** CB Round 13

### Work Unit 2.4: Schema Change Detection
- **Owner:** Codex sub-agent
- **Description:** The #1 unsolved problem ($2.1K–$45M losses cited)
- **Tasks:**
  - [ ] Schema capture on every proxied call
  - [ ] Structural diff engine (field additions, removals, type changes)
  - [ ] Semantic diff layer (renamed fields, moved data)
  - [ ] Alert pipeline: webhook + email + in-app
  - [ ] Feed schema changes back into AN Score freshness
- **Depends on:** WU 2.1 (proxied calls for data capture)
- **Round:** CB Round 14

---

## Phase 3: Launch & GTM (Weeks 6-10)
*Goal: 50 operators using Discover. 10 on proxy beta. Provider engagement started.*

### Work Unit 3.1: Pre-Launch Leaderboard
- **Owner:** Pedro (content) + Claude Code (web)
- **Description:** Top 50 tools by category — shareable, arguable, drives Twitter
- **Output:** Web pages + social cards + API endpoint
- **Depends on:** WU 1.7 (scored dataset)

### Work Unit 3.2: "Tool Autopsy" Content Series
- **Owner:** Pedro (writing) + Tester Fleet (data)
- **Description:** Public teardowns of tool categories. "We tested 12 Salesforce MCP servers. 3 work."
- **Format:** Blog posts + Twitter threads
- **Depends on:** WU 1.7 (scored data)

### Work Unit 3.3: AN Score v2 — New Dimensions (THIS WEEK)
- **Owner:** Pedro (research + spec) + Codex sub-agent (implementation)
- **Description:** Add three new scoring dimensions informed by Levie analysis + Tom's direction
- **Tasks:**
  - [ ] **Payment Autonomy dimension** — Can agents pay for this tool? API-based signup, consumption billing, agent wallets, x402/crypto support
  - [ ] **Governance Readiness dimension** — Audit trails for agent actions, agent-specific ACLs, data residency, retention compliance
  - [ ] **Web Agent Accessibility dimension** — AAG levels (A/AA/AAA) from our AAG framework, scoring tool dashboards/admin panels
  - [ ] Research agent payment primitives: x402 protocol, Stripe agent wallets, Coinbase Commerce, crypto micropayments, whatever else exists
  - [ ] Re-score 50 services against new dimensions
  - [ ] Update AN Score spec and methodology docs
- **Depends on:** WU 1.7 (scored dataset), AAG v0.1 (complete)
- **Output:** Updated scores, new dimension documentation, payment primitives research

### Work Unit 3.4: AAG Blog + Content SEO (THIS WEEK)
- **Owner:** Pedro (writing) + Claude Code (web implementation)
- **Description:** Publish AAG as SEO-optimized blog content. "The WCAG for AI Agents."
- **Tasks:**
  - [ ] Adapt AAG spec into publishable blog post with examples
  - [ ] "Payments for Agents" Tool Autopsy — who actually lets agents pay?
  - [ ] Add structured data / schema.org markup for SEO
  - [ ] Internal linking from leaderboard → blog → methodology
- **Depends on:** WU 3.2 (blog infrastructure), AAG v0.1 (complete)
- **Format:** Blog posts optimized for "agent accessibility" / "agent-native tools" / "AI agent payments" keywords

### Work Unit 3.5: Usage Analytics Stub (THIS WEEK)
- **Owner:** Pedro (direct) or Codex sub-agent
- **Description:** Log every MCP/CLI query to Supabase. Surface patterns. Required before provider outreach.
- **Tasks:**
  - [ ] Supabase table: `query_logs` (timestamp, tool_queried, query_type, constraints, source)
  - [ ] Instrument MCP server + CLI to log queries
  - [ ] Basic dashboard: what are agents searching for?
  - [ ] Surface emergent demand signals (tools searched but not indexed)
- **Depends on:** Supabase (provisioned), MCP server (WU 1.6)
- **Output:** Live query logging, basic analytics, emergent capability discovery loop

### Work Unit 3.6: Provider Outreach v0 (WEEK 3 — after analytics + DNS)
- **Owner:** Pedro → Tom (when external comms needed)
- **Description:** Score providers publicly → notify → self-serve improvements
- **Prerequisites:** DNS live, usage analytics running, 2+ blog posts published
- **Tasks:**
  - [ ] Provider dashboard: queries, failure modes, competitor comparison
  - [ ] "Claim your listing" flow
  - [ ] Certification badge assets (L1/L2/L3)
  - [ ] Email templates for provider notification (spec at docs/WU-3.3-PROVIDER-OUTREACH.md)
  - [ ] Reference Levie article in outreach: "Aaron Levie says if agents can't sign up, you're dead to them. Here's your score."
- **Depends on:** WU 3.5 (usage analytics), DNS resolution, WU 3.4 (content credibility)

### Work Unit 3.7: Community Seeding (WEEK 3)
- **Owner:** Pedro → Tom (for public posts under Tom's name)
- **Tasks:**
  - [ ] Discord communities: OpenClaw, LangChain, CrewAI, AutoGen
  - [ ] Twitter/X presence (Rhumb account) — 1-2 posts/day cadence
  - [ ] Hacker News launch post
  - [ ] 10 white-glove beta users (personal outreach)
- **Depends on:** WU 1.4 (working CLI), WU 1.5 (web presence), WU 3.4 (content)

---

## Agent Routing (from SWARM.md, refined)

| Task Type | Agent | Model | Why |
|-----------|-------|-------|-----|
| Strategy, specs, product writing | Pedro (direct) | Opus 4.6 | Needs full product context |
| Backend (FastAPI, scoring, probes) | Codex sub-agent | Codex 5.3 xhigh | Best reasoning across codebase |
| Frontend (Next.js, Tailwind, Tremor) | Claude Code sub-agent | Sonnet 4.6 | Faster at frontend patterns |
| CLI (Python, Typer) | Codex sub-agent | Codex 5.3 xhigh | Complex arg parsing, output formatting |
| Content (llms.txt, profiles, docs) | Claude Code sub-agent | Sonnet 4.6 | Good at structured content |
| Probes & monitoring | Codex sub-agent | Codex 5.3 xhigh | Reliability-critical |
| Tests | Codex sub-agent | Codex 5.3 xhigh | Thorough edge case coverage |
| Design specs → implementation | Gemini → Claude Code | Mixed | Gemini generates spec, CC implements |

## Parallel Execution Strategy

```
Week 1:  [Phase 0 — Pedro solo: Strategy + AN Score Spec + Namespace]
Week 2:  [WU 0.4: Scaffold] ──→ [WU 1.1: AN Score Engine]
Week 3:  [WU 1.2: Probes] + [WU 1.4: CLI (in parallel)]
Week 4:  [WU 1.3: Tester Fleet] + [WU 1.5: Web (in parallel)]
Week 5:  [WU 1.6: MCP Server] + [WU 1.7: Score 50 Services] + [WU 2.1: Proxy Core (starts)]
Week 6:  [WU 2.2: Agent Identity] + [WU 3.1: Leaderboard Launch]
Week 7:  [WU 2.3: Billing] + [WU 3.2: Tool Autopsies]
Week 8:  [WU 2.4: Schema Detection] + [WU 3.3: Provider Outreach]
```

Max 2 coding agents in parallel (quality > parallelism).
Pedro is always active on product/strategy work alongside coding agents.

## Definition of Done (per Work Unit)

### Technical Gates
- [ ] PR created, branch synced to main
- [ ] CI passing (lint, types, unit, integration)
- [ ] Code review by at least 1 additional AI model
- [ ] Screenshots included (if UI changes)

### Product Gates
- [ ] Serves the flywheel (Discover → Access → Build → validates AN Score)
- [ ] Maintains AN Score neutrality
- [ ] Follows founding principles
- [ ] Documented in llms.txt / machine-readable format (if public-facing)

## Dogfood Log Integration

Every friction I hit while building = data point for Rhumb:
- Tool discovery friction → Discover signal
- Credential management friction → Access signal
- Missing primitive → Build signal

Track in `memory/working/dogfood-log.md`.

## Escalation to Tom

| Situation | Action |
|-----------|--------|
| Spending money | Ask Tom |
| External comms as Tom | Ask Tom |
| Architecture uncertainty | Decide, document, inform Tom |
| Neutrality decision | Ask Tom |
| Everything else | Decide and ship |

---

*This plan is alive. Update it as rounds reveal reality.*
