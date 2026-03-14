# Which SSO Gives Your Agent the Most Power?

*An empirical ranking of identity providers as agent bootstrap primitives.*

---

## The question nobody's asking yet

When a human developer picks a new tool, signup takes 90 seconds. Email, password, maybe verify a link, done.

When an *agent* needs to pick up a new tool — sign up, get credentials, validate them, and start making real API calls — the experience ranges from "completely autonomous" to "impossible without a human in the loop."

We know this because we just tried it. Across 23 developer tools, with a real automated browser, a real GitHub session, and zero human intervention unless absolutely required.

The results surprised us.

---

## The ranking

### 🥇 GitHub OAuth — The Agent's Strongest Passport

**Tools unlocked autonomously:** 8 out of 23  
**Success pattern:** One-click authorize → land in dashboard → find API keys → validate  
**Typical time to working credential:** Under 3 minutes

GitHub OAuth is the single most powerful identity an agent can hold. Here's why:

1. **Session reuse.** Once an agent has a live GitHub session, every tool that accepts GitHub OAuth becomes a one-click authorization away from access. No email verification. No password creation. No CAPTCHA.

2. **Identity carries weight.** GitHub profiles are real — repos, commit history, org membership. Tools trust them more than throwaway emails.

3. **Coverage is broad.** Among modern developer SaaS, GitHub OAuth is the most commonly offered social login. In our batch: Upstash, Netlify, Together AI, Cohere, Turso, Clerk, Algolia, and PostHog all accepted it.

**What we found in practice:**

| Tool | Bootstrap result | Notes |
|------|-----------------|-------|
| Upstash | ✅ Clean | GitHub → Clerk-powered auth → keys on first page |
| Netlify | ✅ Clean | GitHub → dashboard → PAT in settings |
| Together AI | ✅ Clean | GitHub → dashboard → API key creation |
| Cohere | ✅ With friction | GitHub → 3-step onboarding wizard → trial key |
| Algolia | ✅ With friction | GitHub → onboarding questions → API keys in settings |
| Clerk | ✅ Confusing | GitHub → app creation → keys embedded in payload, not a dedicated page |
| Turso | ✅ Confusing | GitHub → dashboard → best path was headless CLI, not web UI |
| PostHog | ✅ With friction | GitHub → multiple credential surfaces, had to find the right one |

**The pattern:** GitHub OAuth almost never fails at the *authorization* step. When friction appears, it's in what happens *after* auth — onboarding wizards, buried settings pages, or non-obvious credential types.

---

### 🥈 Google Account — Powerful but Bounded

**Tools unlocked:** Varies — strong for Google ecosystem, weaker for general dev tools  
**Key distinction:** Google sessions involve a *human identity boundary* that GitHub sessions don't

Google account session reuse is technically powerful. Firebase Console, GCP, and the broader Google ecosystem are immediately accessible if a Google session exists.

But there's a catch that GitHub doesn't have: **Google accounts tend to be personal.** Creating Firebase projects or GCP resources under someone's Google account feels different from authorizing a GitHub OAuth app. The identity boundary is higher.

**Our finding:** Firebase Console was already authenticated under an existing Google session. The *technical* path to creating a project and getting an API key was clear. But the *identity* path — "should an agent be creating GCP projects under a human's personal Google account?" — stopped us.

GitHub OAuth creates *new* accounts tied to the agent's GitHub identity. Google session reuse operates *within* an existing human's account. That's a meaningful difference for autonomous agents.

---

### 🥉 Email/Password — The Default That Blocks Agents

**Tools blocked:** Mistral, DeepSeek  
**Why it fails:** No social auth means the agent must create a net-new account from scratch

Email-only signup isn't inherently hostile to agents, but it introduces friction at every step:

- Need a valid email address
- Need to create and store a password
- Usually need to verify the email
- Sometimes need to complete a profile

For tools like Mistral and DeepSeek, the login page shows *only* email/password fields. No GitHub button. No Google button. No SSO. An agent without existing credentials simply cannot proceed.

**The real cost:** It's not that email signup is hard. It's that it's *manual*. Every email-only tool requires a human to do the initial bootstrap. At scale — across dozens of tools — that human time adds up fast.

---

### 🏚️ Enterprise SSO / Okta — The Agent Wall

**Tools blocked:** Sentry  
**Why it fails:** Designed to keep unauthorized access out. Agents are, by definition, unauthorized.

Enterprise SSO is the hardest wall an agent can hit. Even when a tool offers GitHub OAuth, the enterprise configuration can redirect through Okta, requiring organizational approval that no agent can provide.

**What happened with Sentry:** GitHub sign-in was offered. We clicked it. It authorized through GitHub successfully. Then it redirected to an Okta wall that required enterprise credentials. Dead end.

This isn't a flaw in Sentry's design — it's working as intended. But from an agent's perspective, it's an absolute blocker. No workaround exists without human intervention.

---

### ⚠️ Hosted Auth Providers — The Wild Card

**Observed:** Clerk (clean), Stytch (fragile)

Modern tools increasingly delegate authentication to hosted providers like Clerk or Stytch. These add a layer of indirection that can either help or hurt agent bootstrap:

**Clerk-powered flows** (e.g., Upstash): Clean. The OAuth handoff works, sessions persist, and the agent lands in an authenticated dashboard.

**Stytch-powered flows** (e.g., Groq): Fragile. The OAuth authorization completed successfully at GitHub's end, but the post-auth session didn't persist in the automated browser. The agent completed login and still wasn't logged in.

**The lesson:** The auth *provider* matters as much as the auth *method*. Two tools offering "GitHub OAuth" can have radically different agent experiences depending on who handles the session after the OAuth callback.

---

## The passport power ranking

| Rank | Identity type | Agent autonomy | Coverage | Key risk |
|------|--------------|----------------|----------|----------|
| 🥇 | GitHub OAuth | High | Broad (modern dev tools) | Post-auth onboarding friction |
| 🥈 | Google Account | Medium | Strong (Google ecosystem) | Human identity boundary |
| 🥉 | Email/Password | Low | Universal | Requires human for every new tool |
| 🏚️ | Enterprise SSO | None | Enterprise tools | Designed to block agents |

---

## What this means for tool builders

If you want agents to be able to adopt your tool without a human in the loop:

1. **Offer GitHub OAuth.** It's the single highest-leverage thing you can do for agent accessibility.
2. **Make API keys findable.** After auth, the path to a working credential should be obvious and short. Don't bury it behind onboarding wizards.
3. **Don't require onboarding completion before key access.** Let agents skip the tutorial.
4. **If you use a hosted auth provider, test the agent path.** OAuth can authorize successfully and still fail at session handoff.
5. **Publish your auth requirements in machine-readable format.** An agent shouldn't have to *try* signing up to discover you're email-only.

---

## What this means for agent operators

If you're running agents that need to adopt new tools:

1. **GitHub is your strongest passport.** Invest in a clean GitHub identity for your agent fleet.
2. **Batch the human-gated signups.** Don't do them one at a time. Group the email-only and CAPTCHA-blocked tools into a single human session.
3. **Prefer the strongest credential type.** Personal API keys > project tokens > public keys. The first thing that works isn't always the best thing to use.
4. **Test session persistence.** Just because OAuth authorized doesn't mean the session will stick in your agent's browser.

---

## Methodology

These findings come from Rhumb's launch-batch credential sprint: 23 developer tools, tested with a real automated browser (Playwright via CDP), a real GitHub session (Supertrained org), and a strict validation rule — no credential is "acquired" until a real API endpoint returns a valid response.

The full structured dataset is available at [`/access-audit/launch-batch.json`](/access-audit/launch-batch.json).

---

*This is part of Rhumb's [Access Audit](https://rhumb.dev/methodology) — an ongoing assessment of how easy it is for agents to discover, adopt, and stay operational on developer tools.*
