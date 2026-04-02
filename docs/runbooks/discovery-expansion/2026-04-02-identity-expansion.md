# Discovery expansion — identity

Date: 2026-04-02
Owner: Pedro / Keel runtime review loop

## Why this category

Live public category counts still show **`identity`** at only **4 providers**.

That is too thin for a category agents hit constantly:
- user lookup before action
- organization / membership inspection
- invitation and lifecycle checks
- session / auth-state debugging
- permission-aware workflow routing

Rhumb already had some OSS and infrastructure-leaning identity coverage (`fusionauth`, `keycloak`, `ory`, `supertokens`), but it was missing several of the highest-demand commercial identity surfaces that developers actually choose between.

## Added services

### 1. Auth0
- Slug: `auth0`
- Score: **8.85**
- Execution: **8.95**
- Access readiness: **8.70**
- Why it made the cut:
  - category-defining CIAM platform with rich Management API coverage
  - strong user, org, role, MFA, and admin workflow relevance

### 2. Clerk
- Slug: `clerk`
- Score: **8.75**
- Execution: **8.85**
- Access readiness: **8.60**
- Why it made the cut:
  - explicit Backend API with clean user / org / membership primitives
  - excellent fit for read-first agent workflows inside modern SaaS apps

### 3. Stytch
- Slug: `stytch`
- Score: **8.60**
- Execution: **8.75**
- Access readiness: **8.40**
- Why it made the cut:
  - strong B2B identity and session model
  - direct API relevance for user/session/org inspection workflows

### 4. Descope
- Slug: `descope`
- Score: **8.45**
- Execution: **8.55**
- Access readiness: **8.30**
- Why it made the cut:
  - meaningful enterprise CIAM relevance
  - useful APIs for users, tenants, roles, SSO, and lifecycle operations

### 5. Kinde
- Slug: `kinde`
- Score: **8.20**
- Execution: **8.25**
- Access readiness: **8.15**
- Why it made the cut:
  - credible modern auth platform with user/org/permission APIs
  - important category depth because many startup and mid-market teams now evaluate it alongside Clerk/Auth0/Stytch

## Phase 0 capability assessment

All five additions expose accessible APIs and are viable Resolve candidates.

### Strongest candidates for Resolve capability addition
1. **Clerk**
2. **Auth0**
3. **Stytch**
4. **Descope**

### Candidate capability shapes
- `identity.user.get`
- `identity.user.list`
- `identity.organization.get`
- `identity.organization.members.list`
- `identity.session.get`
- `identity.invitation.list`

### Best initial Phase 0 wedge
The cleanest first move is:
- `identity.user.get`
- `identity.user.list`
- `identity.organization.members.list`

Why:
- these are high-frequency, read-first operational checks
- they help agents answer "who is this user / what org are they in / what membership state applies?" before any write action
- they are safer and more portable than identity mutations, MFA enrollment changes, or role writes
- **Clerk** is the best first provider target because its Backend API exposes these primitives directly on a stable developer-facing surface with less tenant-domain complexity than Auth0

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0148_identity_expansion.sql`

## Verdict

Identity is still an obvious gap in the live catalog. This batch adds five major API-backed identity providers and sharpens the next honest Resolve wedge around **read-first user / org / membership inspection**, with **Clerk** as the best first implementation target.
