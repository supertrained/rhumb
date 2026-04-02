# Discovery expansion — authorization II

Date: 2026-04-02
Owner: Pedro / Keel runtime review loop

## Why this category

Live production still shows **`authorization`** as thin relative to how often agents and operators need it.

Why that matters:
- real agent workflows increasingly need **permission checks** before acting on behalf of a user or service
- multi-tenant tools often require **resource visibility / list filtering** rather than simple yes-no auth
- authorization is one of the cleanest read-first control planes to normalize honestly before attempting broader policy mutation or admin writes

So the honest Mission 2 move was to deepen **authorization** instead of adding another novelty category.

## Added services

### 1. AuthZed
- Slug: `authzed`
- Score: **8.55**
- Execution: **8.70**
- Access readiness: **8.25**
- Why it made the cut:
  - explicit permission-check and relationship-graph APIs
  - strategically important because Zanzibar-style authorization is becoming a default design pattern for serious multi-tenant software

### 2. SpiceDB
- Slug: `spicedb`
- Score: **8.40**
- Execution: **8.55**
- Access readiness: **7.95**
- Why it made the cut:
  - important self-hosted counterpart to AuthZed
  - strong fit for infrastructure-heavy and security-conscious teams that want direct control of the auth graph

### 3. Oso Cloud
- Slug: `oso-cloud`
- Score: **8.30**
- Execution: **8.45**
- Access readiness: **8.05**
- Why it made the cut:
  - clear policy-backed access-check surface
  - strong practical fit for SaaS teams that need application authorization with list filtering and relation-aware checks

### 4. Aserto
- Slug: `aserto`
- Score: **8.20**
- Execution: **8.35**
- Access readiness: **7.95**
- Why it made the cut:
  - credible authorization decision platform with policy APIs and directory context
  - meaningful category depth beyond the first-wave providers already in the catalog

### 5. Styra DAS
- Slug: `styra-das`
- Score: **8.10**
- Execution: **8.25**
- Access readiness: **7.80**
- Why it made the cut:
  - important enterprise policy-control-plane coverage for OPA-heavy environments
  - helps Rhumb represent real policy-backed authorization stacks, not only app-level hosted authz vendors

## Phase 0 capability assessment

All five additions expose accessible APIs and are viable Resolve candidates.

### Strongest candidates for Resolve capability addition
1. **AuthZed**
2. **Oso Cloud**
3. **Aserto**
4. **SpiceDB**

### Candidate capability shapes
- `authz.check`
- `authz.list_resources`
- `authz.list_subjects`
- `policy.evaluate`

### Best initial Phase 0 wedge
The cleanest first move is:
- `authz.check`

Why:
- it is the most universal read-first primitive across the category
- it lets agents verify access before acting, which is safer than attempting writes first
- it is easier to normalize honestly than relationship mutation, schema writes, or policy deployment
- **AuthZed** is the best first provider target because hosted permission checks and relationship semantics map directly to a normalized authorization-check lane while still representing an important real-world architectural pattern

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0149_authorization_expansion_ii.sql`

## Verdict

Authorization is still underrepresented for a category this central to safe agent behavior. This batch adds five credible API-backed providers and sharpens the next honest Resolve wedge around **`authz.check`**, with **AuthZed** as the best first implementation target.
