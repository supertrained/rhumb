# Discovery expansion — HRIS III

Date: 2026-04-03
Owner: Pedro / Keel runtime review loop

## Why this category

Live production category counts still show **`hris`** at only **4** providers:
- `bamboohr`
- `deel`
- `gusto`
- `rippling`

That is still far too thin for a category agents repeatedly need for:
- employee directory lookup
- manager and reporting-line resolution
- onboarding and offboarding checks
- leave-aware coordination
- org sync into IT / support / internal tools
- payroll-adjacent support workflows where read-only people context is enough

## Added services

### 1. Personio
- Slug: `personio`
- Score: **8.45**
- Execution: **8.55**
- Access readiness: **8.20**
- Why it made the cut:
  - clear employee, absence, and org-oriented API primitives
  - strongest immediate read-first Resolve wedge in the batch
  - high practical value for people-ops automation and internal assistant workflows

### 2. HiBob
- Slug: `hibob`
- Score: **8.30**
- Execution: **8.40**
- Access readiness: **8.05**
- Why it made the cut:
  - rich people and lifecycle data on a modern API surface
  - strong fit for employee lookup, manager resolution, and time-off context
  - important real-world coverage for scaling midmarket teams

### 3. Humaans
- Slug: `humaans`
- Score: **8.15**
- Execution: **8.20**
- Access readiness: **8.05**
- Why it made the cut:
  - lightweight but operationally useful people-system API
  - strong developer ergonomics for org sync and reporting-line workflows
  - good catalog breadth beyond legacy enterprise-heavy HR suites

### 4. Factorial HR
- Slug: `factorial-hr`
- Score: **8.05**
- Execution: **8.10**
- Access readiness: **7.95**
- Why it made the cut:
  - practical employee, attendance, document, and time-off coverage
  - read-first workflows map cleanly to real assistant use cases
  - broadens HRIS depth for SMB and midmarket teams outside the current U.S.-heavy set

### 5. Employment Hero
- Slug: `employment-hero`
- Score: **7.95**
- Execution: **8.00**
- Access readiness: **7.85**
- Why it made the cut:
  - meaningful people and employment workflow coverage
  - important regional depth for APAC-heavy employers
  - useful category breadth even if it is not the first Resolve wedge

## Phase 0 capability assessment

### Services with accessible APIs
All five added services expose accessible developer APIs or documented programmable admin surfaces.

Strongest early Resolve targets:
1. **Personio**
2. **HiBob**
3. **Humaans**

### Candidate capability shapes
- `hris.employee_list`
- `hris.employee_get`
- `hris.organization_lookup`
- `hris.manager_lookup`
- `hris.timeoff_list`

### Best initial Phase 0 wedge
The cleanest first move is:
- `hris.employee_list`
- `hris.employee_get`
- `hris.organization_lookup`

Why:
- these are read-first and broadly reusable across internal ops, IT, onboarding, and support workflows
- they normalize more cleanly than payroll writes or mutable HR actions
- they create a natural follow-on path into manager lookup and leave-aware context
- **Personio** is the best first provider target because its API surface is explicit, operationally important, and easier to normalize than the more enterprise-heavy alternatives

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0152_hris_expansion_iii.sql`

## Verdict

HRIS remains underrepresented relative to demand. This batch improves discovery depth in a category agents will keep touching, and **Personio is now the clearest next Phase 0 target** when the HRIS lane opens.
