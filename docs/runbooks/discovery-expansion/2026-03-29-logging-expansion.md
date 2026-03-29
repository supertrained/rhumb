# Discovery expansion — logging

Date: 2026-03-29
Owner: Pedro / Keel runtime review loop

## Why this category

Logging is a high-demand operational category for agents, but Rhumb's live catalog depth is still thin.

I pulled full category counts from the live service catalog with pagination and found:
- `logging`: **6** providers
- versus deeper adjacent operating categories like `monitoring` (**43**) and `devops` (**83**)

That gap matters because agents routinely need logging surfaces for:
- production debugging and root-cause analysis
- incident triage and postmortem support
- support-ticket investigation against real system events
- alert enrichment and anomaly follow-up
- tracing user-impacting failures back to concrete log evidence

## Added services

### 1. Sumo Logic
- Slug: `sumo-logic`
- Score: **8.20**
- Execution: **8.40**
- Access readiness: **8.00**
- Why it made the cut:
  - clean search-job and monitor surfaces for read-first operational work
  - strong portability into a normalized `log.query` lane
  - best immediate Phase 0 wedge in the batch

### 2. Coralogix
- Slug: `coralogix`
- Score: **8.10**
- Execution: **8.30**
- Access readiness: **7.90**
- Why it made the cut:
  - modern observability posture with credible programmable query and alert surfaces
  - strong fit for agents doing incident triage and alert follow-up

### 3. Sematext Logs
- Slug: `sematext-logs`
- Score: **7.95**
- Execution: **8.10**
- Access readiness: **7.80**
- Why it made the cut:
  - practical SMB-to-midmarket logging API surface with search and alerting semantics
  - broadens coverage beyond the biggest enterprise incumbents

### 4. CrowdStrike LogScale
- Slug: `crowdstrike-logscale`
- Score: **7.90**
- Execution: **8.20**
- Access readiness: **7.55**
- Why it made the cut:
  - high-scale query and repository model is useful for serious operational forensics
  - strategically relevant for teams with large-volume log workflows

### 5. Logz.io
- Slug: `logz-io`
- Score: **7.85**
- Execution: **8.05**
- Access readiness: **7.65**
- Why it made the cut:
  - meaningful Elasticsearch-adjacent log workflow coverage
  - useful for agent operators who need search and alert control without rolling their own stack

## Phase 0 capability assessment

### Services with accessible APIs
All five added services expose developer-accessible APIs or documented programmable control surfaces.

The strongest Resolve candidates are:
1. **Sumo Logic**
2. **Coralogix**
3. **Sematext Logs**
4. **Logz.io**

CrowdStrike LogScale is strategically valuable, but it is a heavier first normalization target than Sumo Logic or Coralogix.

### Candidate capability shapes
- `log.query`
- `saved_search.run`
- `alert.list`
- `dataset.list`
- `log.tail_snapshot`

### Best initial Phase 0 wedge
The cleanest first move is:
- `log.query`
- `saved_search.run`

Why:
- they are read-first primitives with immediate operator value
- they generalize across debugging, support, and incident workflows
- they create a natural bridge into alert triage and automated diagnostics
- Sumo Logic looks like the best first implementation target because its search-job API is explicit, operationally important, and easier to normalize than the more ecosystem-shaped alternatives

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0116_logging_expansion.sql`

## Verdict

Logging was underweight relative to demand. This batch materially improves Rhumb's discovery surface, and **Sumo Logic is now the clearest next Phase 0 candidate** when the logging capability lane opens.
