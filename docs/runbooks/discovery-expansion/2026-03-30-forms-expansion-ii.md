# Discovery expansion — forms II

Date: 2026-03-30
Owner: Pedro / Keel runtime review loop

## Why this category

Forms is still a thin but high-demand category in the live catalog.

Even after earlier expansion work in-repo, the live catalog is still shallow relative to how often agents need:
- intake and lead-capture flows
- support and ops request collection
- onboarding and approval handoffs
- static-site / headless submission endpoints
- structured form-response ingestion into CRM, databases, and automations

This is also an especially good category to keep expanding because Rhumb already has a useful normalized foothold: `forms.collect` exists today. That means discovery depth here can feed a real Resolve extension lane instead of staying purely editorial.

## Added services

### 1. Formspree
- Slug: `formspree`
- Score: **8.10**
- Execution: **8.20**
- Access readiness: **7.95**
- Why it made the cut:
  - strongest immediate Phase 0 candidate in the batch
  - very clear developer-facing submission contract
  - broad relevance across static sites, lightweight apps, and operator intake flows

### 2. Basin
- Slug: `basin`
- Score: **8.00**
- Execution: **8.10**
- Access readiness: **7.85**
- Why it made the cut:
  - real REST API plus webhooks, spam protection, and file-upload support
  - strong operational fit for request collection and downstream automation

### 3. Forminit
- Slug: `forminit`
- Score: **7.90**
- Execution: **8.00**
- Access readiness: **7.75**
- Why it made the cut:
  - headless form-backend posture broadens the category beyond builder-first SaaS
  - structured submission / block model is relevant for agent-shaped intake pipelines

### 4. Formcarry
- Slug: `formcarry`
- Score: **7.70**
- Execution: **7.80**
- Access readiness: **7.60**
- Why it made the cut:
  - simple hosted endpoint model is useful for lightweight collection workflows
  - adds practical long-tail coverage for developer-managed forms

### 5. Web3Forms
- Slug: `web3forms`
- Score: **7.55**
- Execution: **7.60**
- Access readiness: **7.50**
- Why it made the cut:
  - very low-friction API-first submission surface
  - useful category depth for static-site and simple intake use cases

## Phase 0 capability assessment

### Services with accessible APIs
All five added services expose developer-usable submission surfaces or documented APIs.

Strongest near-term Resolve targets:
1. **Formspree**
2. **Basin**
3. **Forminit**

### Candidate capability shapes
- `forms.collect`
- `submission.list`
- `form.get`

### Best initial Phase 0 wedge
The cleanest first move is still to extend **existing** `forms.collect` coverage beyond the current provider lane.

Why:
- Rhumb already has the primitive, so this is an extension rather than a new invented abstraction
- these providers map naturally to submission / collection semantics
- read-first follow-ons like `submission.list` are safer than mutating form definitions
- this category has immediate operator value for intake, support, CRM routing, and workflow automation

**Best first provider target: `formspree`**
- clearest developer-facing submission contract in the batch
- strong fit for lightweight universal form collection
- broadest likely demand across both technical and non-technical operators

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0122_forms_expansion_ii.sql`

## Verdict

Forms still deserves more depth than the live catalog currently shows. This batch adds five more developer-usable providers, broadens the category beyond visual form builders into headless submission backends, and sharpens the next honest Resolve wedge around **`forms.collect` + read-first submission retrieval**.
