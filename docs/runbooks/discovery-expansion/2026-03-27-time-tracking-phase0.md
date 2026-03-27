# Discovery expansion — time tracking

Date: 2026-03-27
Owner: Pedro / Keel runtime review loop

## Why this category

Time tracking is a high-demand operational category for agents, but Rhumb's catalog depth is still thin.

I pulled current category counts from the live service catalog and found:
- `time-tracking`: **4** providers
- versus much deeper adjacent operating categories like `productivity` (**22**), `communication` (**10**), and `crm` (**9**)

That gap matters because agents routinely need time-tracking surfaces for:
- timesheet collection and reconciliation
- project / client work attribution
- utilization and productivity reporting
- contractor operations and payroll-adjacent workflows
- syncing time entries into accounting, invoicing, and PM systems

## Added services

### 1. Hubstaff
- Slug: `hubstaff`
- Score: **8.05**
- Execution: **8.30**
- Access readiness: **7.80**
- Why it made the cut:
  - clean API surface for activities, projects, tasks, and organization-level reads
  - broad operator relevance beyond any single PM ecosystem
  - strongest immediate Phase 0 wedge in the batch

### 2. Tempo
- Slug: `tempo`
- Score: **7.95**
- Execution: **8.20**
- Access readiness: **7.65**
- Why it made the cut:
  - deep worklog and planning primitives for Jira-heavy teams
  - strategically important for engineering orgs where time tracking is embedded in delivery workflows

### 3. QuickBooks Time
- Slug: `quickbooks-time`
- Score: **7.75**
- Execution: **7.85**
- Access readiness: **7.55**
- Why it made the cut:
  - important operational bridge between time tracking, scheduling, and payroll-adjacent workflows
  - especially relevant for agencies, services firms, and field teams

### 4. Everhour
- Slug: `everhour`
- Score: **7.45**
- Execution: **7.70**
- Access readiness: **7.20**
- Why it made the cut:
  - useful mix of time records, budgets, invoices, and project workflows
  - good fit for project-based teams and agency-style operations

### 5. TimeCamp
- Slug: `timecamp`
- Score: **7.35**
- Execution: **7.55**
- Access readiness: **7.10**
- Why it made the cut:
  - practical SMB time-tracking API with usable entries, reports, and project reads
  - broadens coverage without over-indexing on enterprise-only tooling

## Phase 0 capability assessment

### Services with accessible APIs
All five added services expose developer-accessible APIs.

The strongest Resolve candidates are:
1. **Hubstaff**
2. **Tempo**
3. **QuickBooks Time**
4. **Everhour**

TimeCamp remains useful, but it is a weaker first normalization target than Hubstaff or Tempo.

### Candidate capability shapes
- `time_entry.list`
- `time_entry.create`
- `project.list`
- `user.list`
- `timesheet.summary`

### Best initial Phase 0 wedge
The cleanest first move is:
- `time_entry.list`
- `project.list`

Why:
- they are read-first primitives with immediate operator value
- they generalize across agency, PM, and payroll-adjacent workflows
- they create a natural bridge into accounting, invoicing, and workforce analytics
- Hubstaff looks like the best first implementation target because its core resources are less ecosystem-shaped than Tempo's Jira-heavy surface

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0104_time_tracking_expansion.sql`

## Verdict

Time tracking was underweight relative to demand. This batch materially improves Rhumb's discovery surface, and **Hubstaff is now the clearest next Phase 0 candidate** when the capability-expansion lane opens.
