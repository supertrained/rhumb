# WU 3.4 — Community Seeding & Hard Launch
## Phase 3: GTM & Launch

**Objective:** Drive user discovery + agent adoption through community presence + HN launch. Target: 50+ Discover users, 10+ proxy beta sign-ups.

**Acceptance Criteria:**
- ✅ Hacker News launch post live (250+ points, top 10 for day)
- ✅ Discord seeds in 4 communities (OpenClaw, LangChain, CrewAI, AutoGen)
- ✅ Twitter posting cadence started (2-3 posts/day for 3 days around launch)
- ✅ 10 white-glove beta invites sent to hand-selected operators
- ✅ Feedback loop established (monitoring mentions, DMs, email)

**Dependencies:** WU 1.5 (web presence) ✅, WU 1.4 (CLI) ✅

**Timeline:** 3-4 hours (single-operator execution)

---

## Execution Plan (No Sub-Agents)

This is direct operator work — writing, outreach, and monitoring. No code changes required.

### Slice A: HN Launch Post (30 min)

**Goal:** Write and launch the Hacker News post

**What to post:**
- Title: "Show HN: Agent-native tool scoring — 50 APIs ranked on execution (not docs)"
- Lead: Direct, specific, controversial
- Body: 
  - Opening hook: "Most tools are built for humans. We scored them for AI agents."
  - Data: Stripe 8.3 (L4) vs PayPal 5.2 (L2) — biggest spread in payments
  - Why it matters: "Error ergonomics, idempotency, retry safety — not features"
  - What we built: leaderboard + scoring engine + CLI tool
  - Link to: https://rhumb-orcin.vercel.app/leaderboard/payments (or rhumb.dev once DNS propagates)
  - Call to action: "Try the CLI: `pip install rhumb && rhumb find payment`"
- Length: ~500 words (long enough for substance, short enough for reading)
- Timing: Post at 10 AM PT Monday = 1 PM ET (peak HN traffic)

**Action:**
1. Compose post in a text editor
2. Submit to HN under `@pedrorhumb` account
3. Monitor for first 2 hours (respond to comments, answer questions)
4. Screenshot top comments for Twitter amplification

**Success metric:** 100+ points in first 2h, top 30 by end of day

---

### Slice B: Discord Community Seeds (45 min)

**Goal:** Introduce Rhumb to 4 target communities

**Communities:**
1. **OpenClaw Discord** (Pedro's home community — highest trust)
   - Channel: #general or #announcements
   - Message: "Built a live scoring system for agent tools. 50 services ranked on execution. First results: Stripe (8.3), PayPal (5.2). Biggest gap is error ergonomics. Free leaderboard: https://rhumb-orcin.vercel.app/leaderboard"
   - Tone: Matter-of-fact, data-first, no hype

2. **LangChain Discord** (~30K members)
   - Channel: #integrations or #general (check pinned rules first)
   - Message: "Launched an agent-native scoring index. Ranked payment APIs, auth, devops, search, and more on how well agents can use them (not humans). Data-first approach — open leaderboard, CLI tool. https://rhumb-orcin.vercel.app"
   - Tone: Technical, specific, humble

3. **CrewAI Discord** (~10K members)
   - Similar message, tailored for CrewAI use cases
   - Highlight: "Schema detection, latency distribution, error ergonomics — dimensions that matter for agents"

4. **AutoGen Discord** (~5K members)
   - Same core message
   - Highlight: "Tool discovery primitive for agent systems"

**Action:**
1. Join each Discord (if not already member)
2. Read community rules/pinned messages (respect channels)
3. Post message (once per community, don't spam)
4. Monitor for responses (answer questions within 1h)
5. Don't hard-sell — let data speak

**Success metric:** 5+ meaningful conversations started, 20+ clicks to leaderboard

---

### Slice C: Twitter/X Posting Cadence (1h)

**Goal:** Amplify via @pedrorhumb with 3-day launch blitz

**Timeline:**
- **Day 1 (HN launch day):** 2 posts
  - Post 1 (10 AM PT): "Scored 50 developer tools on how well they work for AI agents, not humans. Leaderboard live. Pay attention to the gaps. https://rhumb-orcin.vercel.app/leaderboard"
  - Post 2 (2 PM PT): Link to Tool Autopsy blog post (payments) or HN discussion

- **Day 2:** 2 posts
  - Post 1: Category deep-dive (e.g., "Auth APIs ranked: Clerk (7.8), Firebase Auth (6.7), Auth0 (6.6). The gap? OAuth state token security.")
  - Post 2: CLI usage post ("CLI tool for finding the right tool: `rhumb find payment` + constraints, returns scores + failure modes")

- **Day 3:** 1-2 posts
  - Recap + highlight any viral signal from HN
  - Link to community feedback or notable quotes

**Tone:** Data-first, specific observations, no hype language
**Goal:** 10K impressions, 200+ clicks to leaderboard in 3 days

---

### Slice D: White-Glove Beta Invites (45 min)

**Goal:** Personal outreach to 10 hand-selected operators

**Target personas:**
- AI automation consultants ($200+/hr WTP)
- Agent framework builders (LangChain, CrewAI, AutoGen integrations)
- Founders with agent products (FelixCraft, etc.)
- Published researchers on agent systems (Shunyu Yao, others)

**Outreach:**
- Medium: Email or Twitter DM (depends on relationship)
- Message template:
  ```
  Hi [Name],

  Built something I think you'll find useful: live scoring of developer tools on how well they work for AI agents (not humans).

  Biggest insight: error ergonomics and idempotency matter 10x more than feature count.

  Currently scoring 50 services across 10 categories. Free CLI tool:
  ```bash
  pip install rhumb && rhumb find payment
  ```

  Open leaderboard: https://rhumb-orcin.vercel.app/leaderboard

  Would love feedback on scoring dimensions and missing tools.

  — Pedro
  ```
- Goal: 10 accepts within 48h, 3-5 sharing with their networks

**Identified targets** (from prior context):
1. Alden Morris (warm mention, ICP match)
2. Felix/Zoe (agents from research panels)
3. Nat Eliason (Tom connection, potential advisor)
4. David Park (Twilio playbook mentioned)
5. Priya Kapoor (composability layer insight)
6. Omar Al-Rashid (regulatory researcher)
7. [LangChain maintainer]
8. [CrewAI maintainer]
9. [AutoGen contributor]
10. [Published agent researcher]

**Action:**
1. List 10 targets with emails/handles
2. Personalize each invite (1-2 sentence context why I'm reaching out)
3. Send over 2h (don't mass-mail same time)
4. Expect: 30-40% accept rate (3-4 beta users)
5. Monitor responses, set up calls with interested parties

---

### Slice E: Feedback Loop (30 min)

**Goal:** Monitor signals and iterate

**What to track:**
- HN discussion (comments, questions, criticism)
- Twitter mentions (@pedrorhumb, #agent-tools, #rhumb)
- Discord DMs (from community seeds)
- Email replies (from beta invites)
- Slack mentions (OpenClaw, others)
- GitHub issues (if any)

**Action:**
1. Set up IFTTT/monitoring for mentions
2. Answer HN comments within 1h (build reputation)
3. Respond to DMs personally (beta users, potential users)
4. Capture feedback in `memory/working/launch-feedback.md`
5. Identify top 3 user requests for next iteration

**Success metric:** 20+ substantive comments, 5+ beta sign-ups, 1+ feature requests surfaced

---

## Success Metrics

**Quantitative:**
- HN post: 150+ points, top 20
- Twitter: 5K impressions, 300+ clicks
- Discord: 15+ community members engaged
- Beta: 10+ invites sent, 3-5 accepts
- Leaderboard traffic: 500+ users from launch day

**Qualitative:**
- Users understand the AN Score thesis (not just "ranking tools")
- Feedback surfaces real pain points (what dimensions we missed, what tools to add)
- Beta users begin asking about Access layer (provisioning proxy)

---

## Post-Execution

If launch successful:
- Respond to all feedback within 24h
- Publish launch recap post (lessons learned)
- Begin WU 3.3 (provider engagement) based on community feedback
- Monitor for viral coefficient (are users sharing with their networks?)
