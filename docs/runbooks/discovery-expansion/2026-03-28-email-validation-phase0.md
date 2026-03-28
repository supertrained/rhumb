# Discovery expansion — email validation Phase 0 shaping

Date: 2026-03-28
Owner: Pedro
Mission: Mission 2 — discovery expansion after runtime verification work

## Why this category

Email validation is still thin in Rhumb relative to how often agents need it for outbound, inbound signup hygiene, CRM cleanup, enrichment pipelines, and workflow guardrails.

Before this batch, Rhumb only had **5** email-validation providers in the live catalog:
- Abstract API
- Hunter.io
- Kickbox
- NeverBounce
- ZeroBounce

That is not enough depth for a category that repeatedly shows up in GTM automation, list hygiene, and anti-garbage-input workflows.

## What I added

Added five services with fresh scoring via migration `0109_email_validation_expansion.sql`:
- `emailable`
- `bouncer`
- `verifalia`
- `debounce`
- `mailboxlayer`

## Why these five

### Emailable
- Clear public API docs
- Straightforward auth
- Obvious single-email verification primitive
- Strongest immediate Phase 0 candidate

### Bouncer
- Explicit real-time + batch + hybrid verification modes
- Good fit for future bulk hygiene workflows
- Strong operational demand signal

### Verifalia
- Mature enterprise vendor with strong API surface
- Good trust anchor for larger list-cleaning workflows
- Slightly heavier job model than Emailable

### DeBounce
- Clean single-check and batch surfaces
- Good catalog breadth for smaller-budget buyers
- Worth tracking for Phase 0 only after stronger operators

### mailboxlayer
- Familiar utility-style API shape
- Easy auth and email-check semantics
- Lower-quality Phase 0 candidate than Emailable or Bouncer, but worthwhile catalog coverage

## Phase 0 assessment

### Best candidate: Emailable

**Why Emailable is the cleanest first execution wedge:**
- single-email validation is obvious and low-risk
- auth is simple
- docs expose a conventional request/response flow
- outputs map cleanly to provider-neutral trust semantics

### Recommended future Resolve shape

Primary wedge:
- `email.verify`

Possible follow-ons:
- `email.batch_verify`
- `email.domain_quality_check`

### Success contract

For Phase 0, success should mean:
- Rhumb submits an email address to the provider
- provider returns a structured validation result
- Rhumb normalizes the minimum stable fields into a provider-neutral surface

Minimum normalized fields:
- `email`
- `deliverability_status`
- `is_disposable`
- `is_role_account`
- `is_free_provider`
- `quality_score`
- `did_you_mean` (when available)
- `provider_used`

### Zero-config truth

**Zero-config = NO** for this category.

These providers still require provider accounts and credits. The value is not signup elimination — it is normalized execution, comparable trust surfaces, and the ability to swap validation vendors without rewriting agent contracts.

## Recommendation

If I take an email-validation provider into Resolve next, it should be:
1. **Emailable** first
2. **Bouncer** second
3. **Verifalia** third

That gives Rhumb a clean lightweight wedge, a batch-oriented operator, and an enterprise-grade anchor in the same category.
