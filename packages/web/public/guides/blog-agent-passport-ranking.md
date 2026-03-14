---
title: "Which SSO Gives Agents the Most Power?"
description: "We tried to bootstrap 23 developer tools autonomously. GitHub unlocked 8. Email unlocked 0. Here's the full passport ranking."
date: "2026-03-14"
author: "Pedro"
category: "Access"
---

# Which SSO Gives Agents the Most Power?

We just ran a real experiment: one AI agent, 23 developer tools, zero human help. The goal was simple — sign up, get an API key, validate it against a live endpoint.

The results surprised us. Not because some tools were hard to access — we expected that. What surprised us was how much the **choice of SSO** determined whether an agent could get in at all.

## The experiment

We gave an agent a single GitHub session (already authenticated) and asked it to bootstrap access to 23 services across payments, databases, auth, search, email, compute, and hosting.

No stored passwords. No pre-existing accounts on most services. Just a GitHub identity and a browser.

Here's what happened.

## The ranking

### Tier 1: GitHub — The Agent's Strongest Passport

**Services unlocked: 8 out of 23**

| Service | Bootstrap result | Time to API key | Notes |
|---------|-----------------|-----------------|-------|
| Upstash | ✅ Clean | ~2 min | GitHub → Clerk-powered OAuth → direct key page |
| Netlify | ✅ Clean | ~2 min | GitHub → dashboard → PAT creation |
| Together AI | ✅ Clean | ~3 min | GitHub → dashboard → key creation (read-only until deposit) |
| Algolia | ✅ Clean | ~4 min | GitHub → 3-step onboarding → keys visible on settings |
| Cohere | ✅ Clean | ~5 min | GitHub → onboarding wizard → trial key issued |
| Turso | ✅ Clean | ~5 min | GitHub → dashboard → CLI token handoff |
| Clerk | ✅ Clean | ~3 min | GitHub → app creation → keys in generated payload |
| Resend | ✅ Partial | ~2 min | Needed existing GitHub-linked account |

**Why GitHub works:**
- Collapses signup + email verification + account creation into one step
- Most modern developer SaaS treats GitHub as a first-class identity
- Session reuse means the agent doesn't need to re-authenticate per service
- OAuth scopes are typically minimal (email + profile)

**The pattern:** GitHub is an *identity amplifier*. It doesn't just authenticate — it communicates "this is a developer" in a way that skips friction most signup flows impose.

### Tier 2: Google — Powerful but Boundary-Gated

**Services accessible: 2–3 (with caveats)**

| Service | Bootstrap result | Notes |
|---------|-----------------|-------|
| Firebase | ⚠️ Accessible but identity-bound | Console was logged in; creating projects requires human approval |
| PostHog | ✅ Partial | Google OAuth worked but GitHub was the faster path |

**Why Google is different from GitHub:**
- Google sessions are typically tied to a *person*, not an *agent identity*
- Creating cloud projects, enabling APIs, and managing billing all carry real consequences under a human's account
- An agent using someone else's Google session is borrowing identity, not establishing its own

**The boundary:** GitHub OAuth creates an agent-scoped account. Google OAuth borrows a human's account. That distinction matters.

### Tier 3: Hosted Auth Providers — Mixed Results

**Services using Clerk or Stytch as their auth layer:**

| Auth provider | Service | Result |
|--------------|---------|--------|
| Clerk | Upstash | ✅ Clean — Clerk-powered GitHub OAuth worked perfectly |
| Stytch B2B | Groq | ⚠️ OAuth succeeded, session didn't persist |

**The lesson:** The auth provider matters as much as the SSO method. Clerk's GitHub integration was seamless. Stytch's B2B session management broke the post-auth handoff in an automated browser — the OAuth *worked*, but the session *didn't stick*.

This is a new failure mode that doesn't exist for human users. When the auth provider's session management assumes browser behaviors that automated agents don't replicate, the OAuth "succeeds" but the access still fails.

### Tier 4: Email/Password — The Agent Dead End

**Services requiring email signup: 3**

| Service | Blocker |
|---------|---------|
| Mistral | Email-only login, no social auth at all |
| DeepSeek | Email-only login, no social auth at all |
| Postmark | Email signup with reCAPTCHA |

**Why this is a dead end for agents:**
- Email signup requires either access to a real inbox (another tool dependency) or a pre-created account
- reCAPTCHA is an explicit anti-automation gate
- Password creation introduces state management that agents handle poorly
- No session reuse — every service is a fresh signup

**The irony:** These are developer tools. Their users build APIs. But their onboarding assumes a human with a browser and a memory for passwords.

### Tier 5: Enterprise SSO — The Hard Wall

**Services blocked by enterprise auth: 1**

| Service | Blocker |
|---------|---------|
| Sentry | GitHub OAuth → Okta SSO wall |

**Why enterprise SSO is different:** It's not that Sentry doesn't support GitHub — it does. But the specific organization's configuration routes GitHub sign-in through Okta, which requires enterprise credentials the agent doesn't have.

This is the cleanest example of a *context-dependent* access failure. The same tool might be Tier 1 for one organization and Tier 5 for another, depending on their SSO configuration.

### Special Case: Self-Hosted — No Passport Helps

| Service | Blocker |
|---------|---------|
| Meilisearch | No hosted service; needs a running instance URL |

**The lesson:** For self-hosted tools, the access question isn't "which SSO?" but "does an instance exist?" This is a different category entirely.

## The scorecard

| Identity method | Services unlocked | Success rate | Agent-native? |
|----------------|-------------------|-------------|---------------|
| **GitHub OAuth** | 8 of 10 attempted | **80%** | ✅ Yes |
| **Google OAuth** | 2–3 (with caveats) | ~50% | ⚠️ Partial |
| **Hosted auth (Clerk)** | 1 of 1 | 100% | ✅ Yes |
| **Hosted auth (Stytch)** | 0 of 1 | 0% | ❌ Broken |
| **Email/password** | 0 of 3 | **0%** | ❌ No |
| **Enterprise SSO** | 0 of 1 | 0% | ❌ No |

## What this means for tool builders

If you want agents to be able to use your tool without a human in the loop:

1. **Support GitHub OAuth.** It's the single highest-leverage change you can make for agent accessibility.
2. **Test your auth flow in an automated browser.** If the session doesn't persist after OAuth callback, your tool is broken for agents even though it works for humans.
3. **Put your API keys on a direct settings page.** Onboarding wizards are fine for humans, but agents need a URL they can navigate to directly.
4. **Don't gate signup with reCAPTCHA on the primary path.** Consider rate limiting or email verification instead — both are more agent-compatible.
5. **Separate personal tokens from project tokens.** Agents need the strongest credential available, not a scoped project key that can't access management endpoints.

## What this means for agent operators

If you're running agents that need to access developer tools:

- **GitHub is your strongest passport.** Invest in a clean GitHub identity for your agent fleet.
- **Google is useful but carries identity risk.** Creating projects under a human's Google account isn't the same as an agent having its own access.
- **Expect 20–30% of tools to require human intervention** for initial account creation, even in the developer tool category.
- **Track which tools your agents can bootstrap vs. which ones need a human seed.** That distinction is the real access readiness signal.

## Why we're publishing this

At Rhumb, we score tools on how well they work for agents. But "works for agents" has always been measured *after* authentication — response times, error handling, schema stability.

This experiment made us realize there's a dimension we were underweighting: **can an agent even get in?**

We're now adding bootstrap autonomy as a first-class field on every service page. Not as a judgment ("this tool is bad") but as a fact ("this tool requires human intervention to set up"). Because if your agent can't get an API key without you, that's information worth knowing before you build a dependency on it.

---

*The data behind this post comes from Rhumb's [Access Audit](/access-audit) — a structured dataset of observed access findings across 23 developer tools. Every finding was generated by an actual agent attempting real bootstrap flows, not theoretical analysis.*

*Have access audit data for a tool we haven't covered? [Let us know](https://github.com/supertrained/rhumb/issues).*
