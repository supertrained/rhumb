# Discovery expansion — feature flags II

Date: 2026-03-30
Owner: Pedro / Keel runtime review loop

## Why this category

`feature-flags` is still underrepresented relative to how often agents need to read rollout state before acting, gate risky automation behind staged releases, and inspect config safely without mutating production behavior.

The category already had strong leaders, but it was still too shallow for a serious trust/discovery surface. The honest move here was not to add random long-tail APIs; it was to deepen a practical operator category with more real flag/config vendors that have accessible admin surfaces.

## Added services

### 1. DevCycle
- Slug: `devcycle`
- Score: **8.15**
- Execution: **8.30**
- Access readiness: **7.95**
- Why it made the cut:
  - modern API-first feature/config model
  - clear environment and variable surface
  - strongest new fit for normalized `feature_flag.list` and `feature_flag.read`

### 2. Prefab
- Slug: `prefab-cloud`
- Score: **8.00**
- Execution: **8.15**
- Access readiness: **7.80**
- Why it made the cut:
  - practical operator-facing config + flag posture
  - strong read-first value for agents that need rollout/context awareness before taking action

### 3. Flipt
- Slug: `flipt`
- Score: **7.90**
- Execution: **8.05**
- Access readiness: **7.65**
- Why it made the cut:
  - explicit namespaces, flags, segments, and evaluation APIs
  - self-hosted/open-source-friendly angle adds real catalog breadth for agent operators

### 4. FeatBit
- Slug: `featbit`
- Score: **7.75**
- Execution: **7.90**
- Access readiness: **7.55**
- Why it made the cut:
  - credible admin surface for targeting and variations
  - good additional depth for rollout-aware automation workflows

### 5. Harness Feature Management & Experimentation
- Slug: `harness-feature-management`
- Score: **7.65**
- Execution: **7.85**
- Access readiness: **7.40**
- Why it made the cut:
  - enterprise release-control relevance
  - real flag + experimentation surface, even if broader platform complexity makes it a noisier normalization target

## Phase 0 capability assessment

All five additions expose accessible admin/config APIs and are viable Phase 0 candidates.

### Strongest candidates for Resolve capability addition
1. **DevCycle**
2. **Prefab**
3. **Flipt**

### Candidate capability shapes
- `feature_flag.list`
- `feature_flag.read`
- `feature_flag.evaluate`
- `config.read`

### Best initial Phase 0 wedge
The cleanest next wedge remains:
- `feature_flag.list`
- `feature_flag.read`

Why:
- read-first surfaces are safer than mutating rollout rules
- agents get immediate operational value from rollout awareness
- normalized list/read contracts are easier to verify across providers than write-heavy change APIs

### Best first new provider target
**DevCycle** is the best first new provider target because its API posture is explicit, modern, and easier to normalize than the broader Harness surface or the more self-hosted-open-source deployment variability in Flipt.

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0125_feature_flags_expansion_ii.sql`

## Verdict

Feature flags / rollout control is now deeper and more credible as an agent-operator category, and the next honest Resolve wedge remains a read-first flag surface rather than jumping straight into mutation-heavy rollout writes.
