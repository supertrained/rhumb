# Work Unit 3.3 — Provider Outreach v0

**Status:** Ready for Kickoff  
**Created:** 2026-03-09  
**Owner:** Pedro (autonomous, pending Tom approval for email sends)  
**Depends on:** WU 1.7 (scored dataset), WU 3.1 (leaderboard live)  
**Timeline:** 1–2 hours (drafting + sending)

---

## Context

Rhumb has publicly scored 50 tools. This creates an opportunity: notify providers of their scores with actionable feedback, drive traffic to the leaderboard, and begin building relationships.

This is v0 — simple, direct, authentic. No "claim your listing" flow yet, no dashboard. Just scores + improvement recommendations + leaderboard link.

**Strategic leverage:**
- Providers who score well want the badge visibility
- Providers who score poorly want to improve (and will iterate if they know the criteria)
- Either way, they visit the leaderboard, test Rhumb's credibility, and can link to their scores

**Go-big principle:** This is day 8 of Rhumb existing. Reaching out to 50 providers is the move that turns a published leaderboard into a provider engagement loop.

---

## Deliverables

### 1. Email Template (Approval-Gated)

Two templates: High scores (L3/L4) and Low scores (L1/L2).

#### Template A: High-Score Notification (L3/L4 — "Ready" or "Native")

```
Subject: Rhumb Agent-Native Scoring: {service_name} scores {score}/10

Hi {contact_name},

I've been building Rhumb — a rating system for how well software tools work with AI agents. This week, I scored 50 services across 10 categories. {service_name} came out strong:

**Rhumb Agent-Native Score: {score}/10 ({tier_label})**

This means agents can use {service_name} reliably. Here's the breakdown:
- **Execution Quality:** {execution_score}/10 — how well the API works in agent hands
- **Access Readiness:** {access_score}/10 — how easy it is for an agent to get started

**Key strengths:** {strength_1}, {strength_2}  
**Room to improve:** {improvement_1}

See the full leaderboard and comparison with peers:
{leaderboard_url}/{category}

No actions needed from you — I thought you'd want to know. If you have questions about the methodology or want to discuss the score, I'm always open to feedback.

Shipping fast,  
Pedro  
Rhumb (rhumb.dev)
```

#### Template B: Low-Score Notification (L2 — "Developing" or lower)

```
Subject: Rhumb Scoring: {service_name} at {score}/10 — here's how to improve

Hi {contact_name},

I built a rating system (Rhumb) for how well software tools work with AI agents. I just scored {service_name}, and I wanted to share the results + specific improvement recommendations.

**Rhumb Agent-Native Score: {score}/10 ({tier_label})**

**Here's why the score is lower than you might expect:**
- **{issue_1}:** {explanation_1}
- **{issue_2}:** {explanation_2}

**To improve to L3 (Ready), focus on:**
1. {improvement_1} — This will immediately unlock agent reliability
2. {improvement_2} — Agents value this highly
3. {improvement_3} — Takes lift but high-impact

These aren't arbitrary — they came from testing {service_name} with real agent patterns.

See how you compare to similar tools:
{leaderboard_url}/{category}

If this resonates and you want to discuss, I'm happy to dive deeper on what agents actually need.

Shipping,  
Pedro  
Rhumb (rhumb.dev)
```

---

### 2. Provider Email List & Scores

**Top 10 (L3+ / "Ready" tier and above):**
1. Stripe (8.3, L4 Native) — stripe@stripe.com
2. Resend (8.1, L4 Native) — hello@resend.com
3. Clerk (7.8, L3 Ready) — support@clerk.com
4. Algolia (7.7, L3 Ready) — support@algolia.com
5. Meilisearch (7.7, L3 Ready) — hello@meilisearch.com
6. PostHog (7.4, L3 Ready) — hey@posthog.com
7. SendGrid (6.8, L3 Ready) — help@sendgrid.com
8. Postmark (7.1, L3 Ready) — support@postmarkapp.com
9. Twilio (7.6, L3 Ready) — support@twilio.com
10. GitHub (8.0, L3 Ready) — support@github.com

**Bottom 5 (L2 / "Developing"):**
1. PayPal (5.2, L2 Developing) — developer-relations@paypal.com
2. Braintree (5.8, L2 Developing) — dev-support@braintreepayments.com
3. Square (6.0, L2 Developing) — developer-support@squareup.com
4. Notion (6.7, L3 Ready *borderline*) — support@notion.com
5. Airtable (6.9, L3 Ready *borderline*) — support@airtable.com

**Note:** Email addresses are placeholders based on public developer contact pages. Before sending, verify via:
- Support pages (e.g., stripe.com/contact/support)
- Developer relations sections
- LinkedIn/Twitter for dev relations leads
- Or use general developer@ or support@ routes as fallback

---

### 3. Outreach Strategy

**Phase 1: Top 10 (Day 1)**
Send Template A to high-scorers. Goal: get them to visit, celebrate the score, maybe link from their site.

**Phase 2: Bottom 5 (Day 2)**
Send Template B to low-scorers. Goal: show we're credible, specific feedback drives legitimacy, they iterate to improve.

**Why this order:** High-scorers are quick wins (positive messaging, drives engagement). Low-scorers build trust (actionable feedback, shows we're not just giving praise).

---

## Implementation Checklist

- [ ] **Verify email addresses** — Check current developer contact pages for all 50 services (spot check top 10 + bottom 5)
- [ ] **Populate templates** — Fill in {service_name}, {score}, {tier_label}, {explanation_1}, etc. from dataset
- [ ] **Tom review & approval** — Send templates + email list to Tom for sign-off
- [ ] **SendGrid setup** (if automating) — Create campaign, test email, schedule sends
- [ ] **Manual sends** (if low-volume) — Send via Gmail with personal email, track opens/replies
- [ ] **Log responses** — Track replies, note any "please fix this" requests for product backlog
- [ ] **Post to Twitter** — Share launch: "Scored 50 tools. Emailing providers their AN Scores. Who do you think improved?"

---

## Success Metrics

**Immediate (Week 1):**
- 80%+ email delivery rate (no bounces)
- 20%+ open rate (industry avg is 15%)
- 5+ providers click through to leaderboard

**Follow-up (Week 2–4):**
- 2+ providers respond with questions/feedback
- 1+ provider links to their score from their docs
- Visits to `/leaderboard` increase 3x
- 1+ provider starts iterating to improve score

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Emails flagged as spam | Use existing email accounts (Pedro's Gmail), not SendGrid at first. Keep subject lines authentic. |
| Provider responds negatively | Respond thoughtfully. Explain methodology. This is day 8 — expectations are learning mode. |
| Email addresses stale | Spot-check 10 before sending 50. Fall back to general support@ if dev contact not found. |
| Low engagement | Expect low. This is cold outreach to strangers. Success is 1–2 strong responses. |
| Tom wants different messaging | Easy to adjust. Have templates approved before sending. |

---

## Tom Approval Gate

**Before sending any emails, need Tom to review:**
1. Template A (high-score)
2. Template B (low-score)
3. Email list (providers + addresses)
4. Timing + cadence

**Tom can:**
- Edit templates (tone, framing, offers)
- Add/remove providers from list
- Approve voice (is this authentically Rhumb/Pedro?)
- Advise on follow-up strategy

---

## Next Steps

**Immediate (this session):**
1. ✅ Create this spec
2. ⏳ Share with Tom for review
3. ⏳ Get approval + template edits
4. ⏳ Verify 5 email addresses as sanity check
5. ⏳ Begin sends (manual or SendGrid)

**Follow-up:**
- Log any responses in `memory/working/outreach-responses.md`
- Use feedback to refine provider strategy for Round 4

---

*Version 0.1 — Pedro, 2026-03-09*
