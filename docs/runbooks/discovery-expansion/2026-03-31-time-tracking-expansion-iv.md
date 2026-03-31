# Discovery expansion — time-tracking IV

Date: 2026-03-31
Owner: Pedro / Keel runtime review loop

## Why this category

Live production still shows `time-tracking` at only **4** providers:
- `clockify`
- `harvest`
- `toggl`
- `toggl-api`

That remains too thin for a category agents repeatedly need for:
- listing and creating time entries
- starting and stopping timers
- reading project/client allocations
- building timesheet summaries for operators and finance teams
- reconciling time data with project management, payroll, and invoicing systems
- running productivity and utilization workflows across teams

So the honest Mission 2 move was to deepen **time-tracking** again instead of inventing a net-new shallow category.

## Added services

### 1. Time Doctor
- Slug: `timedoctor`
- Score: **8.15**
- Execution: **8.20**
- Access readiness: **8.05**
- Why it made the cut:
  - strong worklog, project, user, and attendance API surface
  - high operator relevance for team productivity and reporting workflows

### 2. Kimai
- Slug: `kimai`
- Score: **8.10**
- Execution: **8.20**
- Access readiness: **7.95**
- Why it made the cut:
  - clean REST API with explicit timesheet, customer, project, and activity primitives
  - clearest technical Phase 0 candidate in the batch

### 3. Jibble
- Slug: `jibble`
- Score: **7.95**
- Execution: **8.05**
- Access readiness: **7.80**
- Why it made the cut:
  - useful attendance + timesheet crossover for operational workflows
  - practical fit for shift-aware time-entry reads and approvals

### 4. RescueTime
- Slug: `rescuetime`
- Score: **7.85**
- Execution: **7.70**
- Access readiness: **8.05**
- Why it made the cut:
  - strong read-first productivity analytics surface
  - useful for daily summaries, focus reports, and operator coaching workflows

### 5. Timeular
- Slug: `timeular`
- Score: **7.75**
- Execution: **7.85**
- Access readiness: **7.60**
- Why it made the cut:
  - explicit activity and time-entry APIs
  - good additional commercial timer-platform depth for the catalog

## Phase 0 capability assessment

All five additions expose accessible APIs and are viable Resolve candidates.

### Strongest candidates for Resolve capability addition
1. **Kimai**
2. **Time Doctor**
3. **Jibble**
4. **Timeular**

### Candidate capability shapes
- `time.entries.list`
- `time.entries.create`
- `timer.start`
- `timer.stop`
- `project.list`
- `activity.list`

### Best initial Phase 0 wedge
The cleanest first move is:
- `time.entries.list`
- `time.entries.create`
- `timer.start`
- `timer.stop`

Why:
- these are the most common cross-provider time-tracking primitives
- they normalize well before heavier payroll or screenshot features
- they support agent workflows around utilization, reporting, billing, and operational summaries
- **Kimai** is the best first provider target because the API is explicit, REST-shaped, and lighter-weight than the more operationally loaded commercial suites

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0137_time_tracking_expansion_iv.sql`

## Verdict

Time-tracking is still underrepresented in live production. This batch adds five more real API-backed providers and sharpens the next honest Resolve wedge around **time entries + timers**, with **Kimai** as the cleanest first implementation target.
