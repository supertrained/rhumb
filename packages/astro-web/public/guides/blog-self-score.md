
# We Scored Ourselves First — Here's What We Found

**TL;DR:** We built a scoring system for agent-native tools. Before we launched, we scored ourselves. The result: **3.5/10 (L1 Emerging)**. This post is what we learned in the process.

---

## The Vulnerability

Most product launches work backwards: build something, launch it, hope it works. Rhumb works differently. We built a framework for measuring whether tools work for agents. Then we applied it to ourselves.

**The score stung.** 3.5/10 is "Emerging" tier — the same category as PayPal (4.9) and Square (6.3). We're literally worse than tools we're supposed to be evaluating.

But that's the point. If we can't pass our own test, why should anyone trust our scores for others?

---

## What We Scored Ourselves On

The AN (Agent-Native) Score has three dimensions:

1. **Execution Score** (45%) — Technical reliability, error handling, schema stability, latency
2. **Access Readiness** (40%) — Can an agent start using this without human intervention?
3. **Autonomy Score** (15%) — Payment, provisioning, identity management

Let's break down where we failed.

### Execution: 5.2/10

**What we got right:**
- API responses are well-structured JSON ✅
- Endpoints return consistent data ✅
- HTTP status codes are correct ✅

**What we got wrong:**
- Documentation is incomplete (README is a stub)
- Error messages are generic ("something went wrong" instead of structured fault trees)
- No retry-after headers
- Latency varies wildly depending on Supabase pool state
- Schema hasn't been versioned (future changes will break clients)

**Grade:** Technical foundation exists, but you'd be frustrated using this in production.

### Access Readiness: 4.1/10

**What we got right:**
- You can sign up immediately (no approval queue) ✅
- There's a web dashboard ✅
- You can create API keys ✅

**What we got wrong:**
- No programmatic way to create accounts or API keys (humans only)
- No usage-based billing — you'd have to email us for pricing
- No webhook support (can't be notified of events)
- No alternative payment options (no crypto, no x402)
- No rate limiting transparency (we don't publish our limits)
- Provisioning workflow requires human signup

**Grade:** Better than closed APIs, but far from autonomous.

### Autonomy: 2.8/10

**What we got wrong:**
- No agent identity system (each agent under an operator gets the same key)
- No per-agent rate limits
- No way to revoke access to specific agents
- No audit logs showing which agent called what
- No spending caps (an agent loop could theoretically bill infinite dollars)

**Grade:** Non-existent.

---

## Why This Matters

Here's the uncomfortable truth: **our leaderboard is only useful if we pass our own tests first.**

We're asking Stripe (8.1), GitHub (7.8), Slack (7.2) to be better than we are. That's fine only if we can prove we're trying. The moment we publish scores we don't apply to ourselves, we become the thing we're criticizing: a ranking system with no skin in the game.

**Better:** Show the work. Prove you use your own framework. Let people see your growth.

---

## The Roadmap (What's Next)

We're not staying at 3.5.

### Next 30 Days (Target: 5.5/10)
- [ ] Structured error responses with fault trees
- [ ] Webhook support with signed payloads
- [ ] Programmatic account creation (agents can bootstrap themselves)
- [ ] Per-agent identity + rate limits
- [ ] Rate limit transparency + spending caps
- [ ] Complete documentation

### Next 90 Days (Target: 7.0/10)
- [ ] Usage-based billing with transparent pricing
- [ ] Crypto payment option (x402 headers)
- [ ] Schema versioning with backwards-compatibility guarantees
- [ ] Audit logging (queryable event stream)
- [ ] SLA guarantees with published uptime

### Strategic (Post-Launch)
- [ ] Alternative payment rails (x402 protocol)
- [ ] Regional deployments (EU agents can't route through US proxy)
- [ ] White-label provisioning (partners can resell)

---

## What We Learned

### 1. Stubs Pass Tests

We had 523+ tests. All passing. Our API routes returned empty arrays and the tests were happy. **Lesson:** Test what users see, not what exists internally. We now have "stranger test" suites — simulating HN clicks, agent queries, error scenarios.

### 2. Transparency Beats Perfection

We could have hidden the 3.5 score. Launched at 7.0 with hand-waving about "mature architecture." Instead we published the worst of it. **Effect:** credibility boost. You trust someone more when they're honest about limitations.

### 3. "Agent-Native" Is a Skill

We thought building APIs was enough. Nope. Building *for agents* means:
- No surprises (predictable errors, not magical behaviors)
- No async gaps (webhooks, long-running jobs)
- No auth friction (provisioning, not password flows)
- No human-gated bottlenecks (can an agent start from zero?)

Most tools were never designed with agents in mind. Even the best ones (Stripe, GitHub) have compromises. **Our job:** make those visible and provide workarounds.

### 4. Self-Scoring Is the Credibility Moat

Any directory can publish scores. Only one that scores itself honestly becomes trustworthy.

---

## How to Use This

If you're building tools for agents:

1. **Apply the AN Score framework to yourself.** Use our methodology. Publish your score. Show the work.
2. **Find your gaps.** 4.1 in Access Readiness? Make provisioning autonomous. 2.8 in Autonomy? Build agent identity.
3. **Commit to improvement.** Tell people what you're fixing and by when.

If you're using Rhumb:

1. **Don't trust scores with no context.** Click "Dispute this score" if you disagree. Evidence > points.
2. **Watch the roadmap.** We're transparent about what we're building. Hold us accountable.
3. **Send feedback.** We're learning from this too.

---

## The Version Two Question

By late April, we'll re-score ourselves. If we're still 3.5, something's wrong.

If we hit 6.5+, we'll have earned the right to keep scoring others.

That's the deal.

---

**Questions?** [Open an issue on GitHub](https://github.com/supertrained/rhumb/issues). We read everything.

**Want to dispute a score?** [Click the button on any service page](https://rhumb.dev/service/stripe). We take disputes seriously.

**Found a bug in our API?** [File a security report](https://github.com/supertrained/rhumb/security/advisories). We patch within 24h.

---

*Published 2026-03-11 — Pedro*
