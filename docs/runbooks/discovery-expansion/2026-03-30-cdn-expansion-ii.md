# Discovery expansion — CDN II

Date: 2026-03-30
Owner: Pedro / Keel runtime review loop

## Why this category

`cdn` is still underrepresented relative to how often operator agents need to inspect edge-delivery infrastructure before acting.

Current production catalog coverage was only **5 CDN services** before this pass, which is too thin for a category that agents routinely touch for:
- zone / property inventory
- cache invalidation
- origin and delivery-path inspection
- edge rollout checks after deploys
- delivery troubleshooting during incidents

That makes CDN a practical high-demand operator category, especially for read-first infrastructure checks with a clean follow-on mutation wedge.

## Added services

### 1. Gcore CDN
- Slug: `gcore`
- Score: **8.20**
- Execution: **8.35**
- Access readiness: **8.00**
- Why it made the cut:
  - modern API posture for CDN resources and purge operations
  - clear fit for normalized zone inventory and cache control
  - best first Phase 0 target in the batch

### 2. Akamai
- Slug: `akamai`
- Score: **8.10**
- Execution: **8.15**
- Access readiness: **7.85**
- Why it made the cut:
  - category heavyweight with real enterprise CDN depth
  - strong property, config, invalidation, and reporting surfaces
  - important catalog credibility even if auth/product complexity is higher

### 3. CDN77
- Slug: `cdn77`
- Score: **7.95**
- Execution: **8.05**
- Access readiness: **7.75**
- Why it made the cut:
  - practical customer API for zones, purge, and analytics
  - strong mid-market CDN operator fit

### 4. CacheFly
- Slug: `cachefly`
- Score: **7.75**
- Execution: **7.85**
- Access readiness: **7.55**
- Why it made the cut:
  - credible cache-control and service-management API surface
  - useful category depth for delivery-path operations

### 5. CDNSUN
- Slug: `cdnsun`
- Score: **7.60**
- Execution: **7.70**
- Access readiness: **7.45**
- Why it made the cut:
  - pull-zone, storage-zone, and invalidation APIs map well to edge-ops workflows
  - expands long-tail CDN coverage beyond the usual hyperscaler/default choices

## Phase 0 capability assessment

All five additions have accessible APIs and are plausible Resolve candidates.

### Strongest candidates for Resolve capability addition
1. **Gcore CDN**
2. **CDN77**
3. **Akamai**

### Candidate capability shapes
- `cdn.zone.list`
- `cdn.zone.read`
- `cache.purge`
- `cdn.analytics.read`

### Best initial Phase 0 wedge
The cleanest next wedge is:
- `cdn.zone.list`
- `cdn.zone.read`

Why:
- zone/property inventory is read-first and safer than mutation-heavy edge actions
- it gives agents immediate value for delivery-path checks and deploy verification
- list/read normalization is cleaner across vendors than jumping directly into purge semantics

### Best first new provider target
**Gcore CDN** is the best first new provider target because its API posture is modern, explicit, and operationally useful without the heavier enterprise auth and product-surface complexity that comes with Akamai.

### Best follow-on mutation wedge
Once read-first parity is proven, the next honest follow-on is **`cache.purge`**.

That is the highest-leverage write action in the category, but it should come *after* read-first zone normalization so agents can target the right resource boundaries safely.

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0127_cdn_expansion_ii.sql`

## Verdict

CDN is now a more credible operator category inside Rhumb, and the next honest Resolve wedge here is read-first zone inventory followed by tightly-scoped cache purge rather than jumping immediately into broader edge configuration writes.
