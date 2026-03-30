# Discovery expansion — error tracking

Date: 2026-03-30
Owner: Pedro / Keel runtime review loop

## Why this category

`error-tracking` is still underrepresented relative to how often agents need direct production-failure context before taking action.

Today Rhumb covers some of this need indirectly through logging and observability vendors, but that is not the same thing as a first-class grouped-error surface. Operator agents often need to answer questions like:
- what broke most recently?
- which grouped error is spiking?
- what environments are affected?
- did a release correlate with the incident?

That makes error tracking a practical high-demand category, especially for read-first automation, incident triage, and escalation workflows.

## Added services

### 1. BugSnag
- Slug: `bugsnag`
- Score: **8.20**
- Execution: **8.35**
- Access readiness: **8.00**
- Why it made the cut:
  - explicit data-access and release APIs
  - good grouped-error and project context for production triage
  - strong fit for read-first error inventory and error-group inspection

### 2. Rollbar
- Slug: `rollbar`
- Score: **8.10**
- Execution: **8.25**
- Access readiness: **7.95**
- Why it made the cut:
  - incident-oriented item and occurrence surfaces
  - clean mental model for grouped exceptions and drill-down review
  - best first normalization target in the batch

### 3. Honeybadger
- Slug: `honeybadger`
- Score: **7.95**
- Execution: **8.05**
- Access readiness: **7.80**
- Why it made the cut:
  - practical breadth across exceptions, faults, check-ins, and deployments
  - useful operator context without needing write-heavy workflows first

### 4. Airbrake
- Slug: `airbrake`
- Score: **7.80**
- Execution: **7.95**
- Access readiness: **7.60**
- Why it made the cut:
  - explicit groups and notices APIs
  - still a practical production-failure review surface for agents

### 5. AppSignal
- Slug: `appsignal`
- Score: **7.70**
- Execution: **7.85**
- Access readiness: **7.55**
- Why it made the cut:
  - application-scoped API with usable incident and performance context
  - adds broader operational coverage beyond pure exception-only products

## Phase 0 capability assessment

All five additions have accessible APIs and are plausible Resolve candidates.

### Strongest candidates for Resolve capability addition
1. **Rollbar**
2. **BugSnag**
3. **Honeybadger**

### Candidate capability shapes
- `error_group.list`
- `error_group.read`
- `error_event.search`
- `deployment.list`

### Best initial Phase 0 wedge
The cleanest next wedge is:
- `error_group.list`
- `error_group.read`

Why:
- grouped error inventory is safer than mutation-heavy incident actions
- it gives agents immediate operational value for triage and escalation
- list/read contracts should normalize more cleanly across vendors than ack/mute/resolve flows

### Best first new provider target
**Rollbar** is the best first new provider target because its item/occurrence model is explicit, operationally useful, and easier to map to normalized grouped-error read surfaces than the slightly broader or older-feeling APIs in the rest of the batch.

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0126_error_tracking_expansion.sql`

## Verdict

Error tracking is now a more credible operator category inside Rhumb, and the next honest Resolve wedge here is a read-first grouped-error surface rather than jumping directly into mutating incident state.
