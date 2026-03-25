# Discovery expansion — identity verification (2026-03-25)

## Why this category

Identity verification is still underweight relative to market demand.
Current catalog concentration is heavy in AI/devtools, while identity verification is a recurring requirement for fintech, marketplaces, payroll, crypto, travel, and trust/safety products.

At run time, the catalog had only 5 identity-verification services:
- Persona
- Onfido
- Veriff
- Jumio
- Stripe Identity

That is too thin for a category this important.

## Services added

Added 5 services with initial AN scoring:
- Sumsub
- Trulioo
- Shufti Pro
- iDenfy
- Smile Identity

## Initial score posture

All 5 landed in the same practical peer band as the existing identity-verification leaders:
- tier: `L3`
- tier_label: `Ready`
- aggregate score range: `7.1`–`7.4`

This keeps the category internally consistent while leaving room for later runtime verification to move scores up or down.

## Phase 0 Resolve assessment

The strongest existing Resolve fit is **not** creating a new capability, but widening provider coverage on current identity surfaces:
- `identity.verify`
- `identity.check_document`
- `kyc.verify`

Best immediate candidates:
- **Sumsub** — clean developer docs, API-first verification flows, broad KYC/KYB coverage
- **Trulioo** — strong platform API positioning for identity/business verification
- **Smile Identity** — accessible docs and differentiated regional strength for Africa-focused onboarding

## Recommendation

Next Phase 0 pass for this category should:
1. add provider mappings for Sumsub and Trulioo first
2. add Smile Identity immediately after for geographic coverage depth
3. hold Shufti Pro and iDenfy as follow-on additions once the first three are wired cleanly
