# Discovery expansion — APM (Application Performance Monitoring)

Date: 2026-04-03
Owner: Pedro / Keel runtime review loop

## Why this category

Live production category counts show **`apm`** at only **5 providers**:
- `aspecto`
- `elastic-apm`
- `jaeger`
- `lightstep`
- `opentelemetry`

That is too thin for a category this central to production agent workflows:
- agents responding to incidents need direct access to error rates, slow transactions, and traces
- autonomous remediation loops require performance baseline data before acting
- observability-driven agents need to query service health state without human-in-the-loop retrieval
- the existing five providers are all open-source/self-hosted or SDK-first — none have an externally-accessible managed API that is clean enough for a first Resolve wedge

This batch adds five API-backed APM platforms that fill the accessible hosted SaaS, enterprise, and open-source layers of the APM landscape with clear capability shapes.

## Added services

### 1. AppSignal
- Slug: `appsignal`
- Score: **8.25**
- Execution: **8.40**
- Access readiness: **8.05**
- Why it made the cut:
  - REST API at appsignal.com/api with API key authentication
  - application-scoped queries for error rates, slow transactions, performance summaries
  - best immediate Phase 0 candidate: clean read-first surface, no OAuth friction
  - strong match for agent workflows in Ruby/Python/PHP/Elixir/Node.js stacks

### 2. Middleware
- Slug: `middleware-io`
- Score: **8.10**
- Execution: **8.20**
- Access readiness: **7.90**
- Why it made the cut:
  - full-stack cloud observability with a public REST API
  - trace inspection, metric query, alert management — all readable without mutation
  - modern API design; strong cross-layer signal (frontend + backend + infra + logs)
  - good fit for agents in polyglot environments

### 3. IBM Instana
- Slug: `instana`
- Score: **8.05**
- Execution: **8.15**
- Access readiness: **7.80**
- Why it made the cut:
  - comprehensive REST API for service mapping, trace inspection, event retrieval, anomaly detection
  - clean API token auth model
  - strong for agents embedded in IBM or enterprise Kubernetes environments
  - excellent service topology inspection capabilities

### 4. AppDynamics (Splunk)
- Slug: `appdynamics`
- Score: **7.80**
- Execution: **7.90**
- Access readiness: **7.55**
- Why it made the cut:
  - REST APIs for application performance data, business transactions, health rules
  - important coverage for Java/.NET enterprise APM workflows
  - Splunk acquisition adds auth complexity; best as a second-wave Resolve target
  - strategically critical catalog depth for enterprise Java shops

### 5. Apache SkyWalking
- Slug: `apache-skywalking`
- Score: **7.70**
- Execution: **7.80**
- Access readiness: **7.45**
- Why it made the cut:
  - open-source APM with a GraphQL query protocol covering services, endpoints, traces, and topology
  - high adoption in JVM-heavy and Kubernetes environments (especially Asia-Pacific)
  - GraphQL and self-hosted deployment variability make normalization harder but catalog depth matters
  - important completeness inclusion for agents in large-scale distributed Java systems

## Phase 0 capability assessment

### Services with accessible external APIs
- **AppSignal**: REST, API key, externally accessible → best first provider
- **Middleware**: REST, API key, cloud-hosted → strong second provider
- **Instana**: REST, API token, cloud-hosted → strong enterprise provider
- **AppDynamics**: REST (Splunk-wrapped), OAuth complexity → second-wave
- **SkyWalking**: GraphQL query protocol, self-hosted variability → deferred

### Candidate capability shapes
- `apm.errors.list` — error event enumeration (AppSignal, Middleware, Instana)
- `apm.performance.summary` — app performance baseline (AppSignal, Middleware)
- `apm.trace.get` — distributed trace retrieval (Instana, Middleware, SkyWalking)
- `apm.service.list` — service inventory from APM topology (Instana, SkyWalking)
- `apm.alerts.list` — alert state enumeration (AppSignal, AppDynamics)
- `apm.transaction.list` — business transaction inspection (AppDynamics)

### Best initial Phase 0 wedge
**`apm.errors.list`** via **AppSignal** — error events scoped to an application.

Why:
- API key only, no OAuth friction
- GET `/api/errors.json?app_id={id}&token={token}` — clean read-first REST surface
- immediately useful for agents that need error context before escalating or retrying
- directly maps to autonomous incident-response loops

Second wedge: **`apm.performance.summary`** via **AppSignal** or **`apm.trace.get`** via **Middleware**.

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0157_apm_expansion_ii.sql`

## Verdict

APM is underrepresented and a natural fit for agent-driven observability workflows. This batch adds five real API-backed providers and sharpens the next honest Resolve wedge around **`apm.errors.list`** and **`apm.performance.summary`** via **AppSignal**, with **Middleware** and **Instana** as the next two provider targets once the AppSignal capability lane is normalized.
