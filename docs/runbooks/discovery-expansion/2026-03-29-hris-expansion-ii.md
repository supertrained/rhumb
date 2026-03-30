# Discovery expansion — HRIS II

Date: 2026-03-29
Owner: Pedro / Keel runtime review loop

## Why this category

HRIS is still underrepresented relative to how often agents need it.

Current live depth before this batch is only **5** providers:
- `bamboohr`
- `deel`
- `gusto`
- `rippling`
- `workday-api`

That is too thin for a category agents repeatedly touch for:
- employee directory lookup
- manager / org-chart resolution
- onboarding and offboarding checks
- payroll-adjacent support workflows
- leave-aware scheduling and coordination
- people-system sync across HR, IT, and internal ops

## Added services

### 1. Paylocity
- Slug: `paylocity`
- Score: **8.20**
- Execution: **8.35**
- Access readiness: **8.00**
- Why it made the cut:
  - concrete employee and company primitives in public docs
  - cleanest immediate read-first Resolve target in the batch
  - strong fit for employee list/get and org-sync workflows

### 2. ADP
- Slug: `adp`
- Score: **8.15**
- Execution: **8.30**
- Access readiness: **7.90**
- Why it made the cut:
  - very high strategic demand across enterprise workforce stacks
  - broad people, org, and payroll-adjacent surface area
  - important category anchor even if Phase 0 access is more enterprise-shaped

### 3. Dayforce
- Slug: `dayforce`
- Score: **8.05**
- Execution: **8.20**
- Access readiness: **7.85**
- Why it made the cut:
  - strong employee, labor, and workforce-management coverage
  - good future path from simple employee lookups into scheduling and workforce workflows

### 4. UKG
- Slug: `ukg`
- Score: **7.95**
- Execution: **8.10**
- Access readiness: **7.75**
- Why it made the cut:
  - meaningful enterprise workforce depth beyond the current HRIS set
  - valuable for labor, schedule, and organization-aware agent workflows

### 5. Zenefits
- Slug: `zenefits`
- Score: **7.85**
- Execution: **7.95**
- Access readiness: **7.75**
- Why it made the cut:
  - practical SMB HR coverage around people, benefits, and org data
  - useful depth for read-heavy internal assistant and ops workflows

## Phase 0 capability assessment

### Services with accessible APIs
All five added services expose accessible APIs, though enterprise auth/provisioning burden varies materially across the batch.

Strongest early Resolve targets:
1. **Paylocity**
2. **ADP**
3. **Dayforce**

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
- these are read-first and broadly reusable across support, IT, onboarding, and operations workflows
- they normalize more cleanly than payroll or write-heavy HR actions
- they create a natural follow-on path into manager lookups, leave data, and workforce scheduling
- **Paylocity** is the best first provider target because its public docs expose the clearest employee/company primitives with less integration overhead than ADP or UKG

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0120_hris_expansion_ii.sql`

## Verdict

HRIS depth is still too thin for a workflow category agents will keep hitting as they move deeper into internal ops and people-system automation. This batch materially improves discovery coverage, and **Paylocity is now the clearest next Phase 0 target** when the HRIS lane opens.
