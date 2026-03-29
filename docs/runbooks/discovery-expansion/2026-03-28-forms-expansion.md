# Discovery expansion — forms

Date: 2026-03-28
Owner: Pedro / Keel runtime review loop

## Why this category

Forms are a high-demand operational category for agents, but Rhumb's current discovery surface is still thin.

I pulled current category counts from the live service catalog and found:
- `forms`: **5** providers
- versus much deeper adjacent operating categories like `crm` (**13**), `customer-support` (**17**), `email` (**34**), and `productivity` (**37**)

That gap matters because agents routinely need form systems for:
- lead capture and qualification
- onboarding and intake workflows
- support and ops request collection
- approvals, checklists, and internal process handoffs
- structured response ingestion into CRM, databases, and automations

There is also already a useful normalized foothold in the product: `forms.collect` exists today for Fillout. That means expanding the provider catalog here is not just discovery theater — it opens a realistic near-term Phase 0 extension lane.

## Added services

### 1. Formstack
- Slug: `formstack`
- Score: **8.20**
- Execution: **8.35**
- Access readiness: **8.05**
- Why it made the cut:
  - strong forms + submissions API posture
  - broad operational relevance for intake, lead capture, and workflow collection
  - clearest immediate Phase 0 candidate in the batch

### 2. Wufoo
- Slug: `wufoo`
- Score: **7.95**
- Execution: **8.05**
- Access readiness: **7.85**
- Why it made the cut:
  - straightforward forms/entries API with durable read-first collection patterns
  - credible extension target for `forms.collect`

### 3. Cognito Forms
- Slug: `cognito-forms`
- Score: **7.85**
- Execution: **7.95**
- Access readiness: **7.75**
- Why it made the cut:
  - strong business-form and structured-entry posture
  - useful for operational workflows that go beyond simple lead forms

### 4. Formsite
- Slug: `formsite`
- Score: **7.65**
- Execution: **7.75**
- Access readiness: **7.55**
- Why it made the cut:
  - practical forms/results API surface for intake and back-office workflows
  - broadens the category without depending on a single modern SaaS aesthetic

## Phase 0 capability assessment

### Services with accessible APIs
All four added services expose developer-accessible APIs.

The strongest Resolve candidates are:
1. **Formstack**
2. **Wufoo**
3. **Cognito Forms**

Formsite is still useful, but it is a weaker first normalization target than Formstack or Wufoo.

### Candidate capability shapes
- `forms.collect`
- `form.list`
- `form.get`
- `submission.list`

### Best initial Phase 0 wedge
The cleanest first move is:
- extend **existing** `forms.collect` coverage beyond Fillout
- optionally add `form.list` as a read-first discovery primitive

Why:
- `forms.collect` already exists in the product, so this is an incremental extension rather than a brand-new invented abstraction
- read-first submission retrieval is safer than mutating form definitions
- it has immediate value for agents ingesting intake data into CRM, support, and internal workflows
- **Formstack** looks like the best first implementation target because its forms/submissions surface is broad without being tied to a single niche workflow

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0114_forms_expansion.sql`

## Verdict

Forms are still underweight relative to operator demand. This batch improves the discovery surface materially, and **Formstack is now the clearest next Phase 0 candidate** for extending `forms.collect` beyond the current single-provider lane.
