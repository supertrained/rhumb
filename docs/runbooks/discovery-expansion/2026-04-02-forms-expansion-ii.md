# Discovery expansion — forms II

Date: 2026-04-02
Owner: Pedro / Keel runtime review loop

## Why this category

Live production still shows **`forms`** at only **5 providers**.

That is too thin for a category agents hit constantly:
- lead capture and intake monitoring before CRM or enrichment actions
- onboarding, support, and operations workflows that depend on structured submissions
- form-response retrieval before downstream automation, approvals, or document generation
- submission-health checks when a business runs critical front-door workflows through forms
- lightweight operational systems where the form tool is effectively the application database

Rhumb already had first-wave forms coverage (`fillout`, `involve-me`, `jotform`, `tally`, `typeform`), but it was still missing several widely used API-backed form builders.

## Added services

### 1. Formstack
- Slug: `formstack`
- Score: **8.45**
- Execution: **8.55**
- Access readiness: **8.20**
- Why it made the cut:
  - mature API around forms, submissions, and workflow-heavy intake use cases
  - strong operational relevance for back-office, onboarding, and approvals-driven workflows

### 2. Cognito Forms
- Slug: `cognito-forms`
- Score: **8.20**
- Execution: **8.25**
- Access readiness: **8.10**
- Why it made the cut:
  - strong structured-entry and workflow orientation rather than pure marketing capture
  - practical fit for teams using forms as real operational intake systems

### 3. Zoho Forms
- Slug: `zoho-forms`
- Score: **8.15**
- Execution: **8.20**
- Access readiness: **8.00**
- Why it made the cut:
  - meaningful installed-base relevance inside SMB and ops-heavy Zoho environments
  - credible API-backed path for form metadata and submission retrieval

### 4. Formsite
- Slug: `formsite`
- Score: **8.00**
- Execution: **8.05**
- Access readiness: **7.95**
- Why it made the cut:
  - still-active operational form surface with API-backed result retrieval and reporting
  - useful long-tail coverage for teams running established form-driven processes

### 5. Wufoo
- Slug: `wufoo`
- Score: **7.85**
- Execution: **7.80**
- Access readiness: **7.95**
- Why it made the cut:
  - legacy but still relevant installed base in the wild
  - API-backed entry retrieval makes it worth catalog coverage even if it is not the strongest first execution target

## Phase 0 capability assessment

These additions sharpen a clean read-first forms wedge.

### Strongest candidates for Resolve capability addition
1. **Formstack**
2. **Cognito Forms**
3. **Zoho Forms**

### Candidate capability shapes
- `form.get`
- `form.list`
- `form.responses.list`
- `form.response.get`
- `submission.count`

### Best initial Phase 0 wedge
The cleanest first move is:
- `form.get`
- `form.responses.list`
- `form.response.get`

Why:
- these are read-first primitives with obvious operational value
- they let agents inspect intake state honestly before mutating downstream systems
- they are easier to normalize than form creation, branching logic edits, or automation-rule writes
- **Formstack** is the best first provider target because its API surface around forms and submissions is mature, operationally useful, and maps cleanly onto a normalized submission-inspection lane

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0151_forms_expansion_ii.sql`

## Verdict

Forms is still underrepresented for a category that frequently acts as the front door to revenue, support, onboarding, and internal workflows. This batch adds five credible API-backed providers and sharpens the next honest Resolve wedge around **read-first form and submission inspection**, with **Formstack** as the best first implementation target.
