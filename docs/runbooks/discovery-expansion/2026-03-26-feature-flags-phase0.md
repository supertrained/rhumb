# Discovery expansion — feature flags / experimentation

Date: 2026-03-26
Owner: Pedro / Keel runtime review loop

## Why this category

Feature-flag and experimentation control is a high-demand agent category:
- agents often need to read rollout state before acting
- internal operator agents need safe staged-release controls
- experimentation / config APIs are a practical bridge between operations, product, and growth workflows

The public catalog only had 5 providers in `feature-flags`, which is underweighted relative to how often agents need rollout awareness and config control.

## Added services

### 1. LaunchDarkly
- Slug: `launchdarkly`
- Score: **7.95**
- Execution: **8.20**
- Access readiness: **7.70**
- Why it made the cut:
  - strongest enterprise admin API in the batch
  - mature project/environment/flag/change-history surface
  - direct fit for future `feature_flag.list`, `feature_flag.read`, and `feature_flag.update` capabilities

### 2. Statsig
- Slug: `statsig`
- Score: **7.70**
- Execution: **7.95**
- Access readiness: **7.45**
- Why it made the cut:
  - strong gates/configs/experiments model
  - modern API-first posture
  - good overlap with rollout automation and experiment inspection workflows

### 3. Unleash
- Slug: `unleash`
- Score: **7.45**
- Execution: **7.65**
- Access readiness: **7.20**
- Why it made the cut:
  - open-source-friendly and well-aligned with self-hosted/operator-heavy teams
  - useful admin API surface for flags, variants, segments, and strategies

### 4. ConfigCat
- Slug: `configcat`
- Score: **7.20**
- Execution: **7.40**
- Access readiness: **7.00**
- Why it made the cut:
  - clean hosted API and practical rollout/config primitives
  - good SMB/midmarket fit for agent-managed rollout automation

### 5. Split
- Slug: `split`
- Score: **7.05**
- Execution: **7.25**
- Access readiness: **6.85**
- Why it made the cut:
  - established feature delivery + experimentation surface
  - still relevant, though docs/DX feel less sharp than LaunchDarkly or Statsig

## Phase 0 capability assessment

All 5 added providers expose accessible admin APIs and are viable Phase 0 candidates.

### Strongest candidates for Resolve capability addition
1. **LaunchDarkly**
2. **Statsig**
3. **Unleash**

### Candidate capability shapes
- `feature_flag.list`
- `feature_flag.read`
- `feature_flag.update`
- `experiment.list`
- `experiment.read`

### Best initial Phase 0 wedge
The cleanest normalized starting point is likely:
- `feature_flag.list`
- `feature_flag.read`

Why:
- read-only surfaces are safer than mutating rollout changes
- easy to compare direct provider output vs normalized Rhumb output
- useful to agents immediately for rollout awareness and change safety

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0097_feature_flags_expansion.sql`

## Verdict

Feature flags / experimentation is now materially better represented in Discover, and at least three of the new additions are good candidates for the next Phase 0 capability expansion when the callable review lane frees up.
