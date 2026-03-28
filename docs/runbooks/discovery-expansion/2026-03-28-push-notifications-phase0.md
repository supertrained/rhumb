# Discovery expansion — push notifications

Date: 2026-03-28
Owner: Pedro / Keel runtime review loop

## Why this category

Push notifications are a high-demand operational category for agents, but Rhumb's live catalog depth was still thin.

Current live category counts before this batch:
- `push-notifications`: **5** providers
- versus adjacent categories like `notifications`: **9**, `calendar`: **11**, `workflow-automation`: **12**, and `communication`: **30**

That gap matters because agent workflows increasingly need push rails for:
- transactional delivery to mobile users
- lifecycle nudges and re-engagement
- alerts that need stronger attention than email alone
- product-ops and growth experiments
- bridging backend workflows into mobile surfaces

## Added services

### 1. Airship
- Slug: `airship`
- Score: **8.20**
- Execution: **8.35**
- Access readiness: **7.95**
- Why it made the cut:
  - mature push API with strong audience, channel, and send semantics
  - reads like the cleanest first Resolve wedge in the category
  - important enterprise anchor for mobile engagement workflows

### 2. Firebase Cloud Messaging
- Slug: `firebase-cloud-messaging`
- Score: **8.10**
- Execution: **8.25**
- Access readiness: **7.80**
- Why it made the cut:
  - dominant platform push rail across Android and a huge amount of mobile infrastructure
  - strategically necessary catalog coverage even if auth is heavier than the SaaS-first entrants

### 3. Batch
- Slug: `batch`
- Score: **7.95**
- Execution: **8.05**
- Access readiness: **7.75**
- Why it made the cut:
  - explicit transactional push API with clear 1-to-1 delivery semantics
  - good operator fit for user-targeted notification workflows

### 4. Pusher Beams
- Slug: `pusher-beams`
- Score: **7.80**
- Execution: **7.95**
- Access readiness: **7.45**
- Why it made the cut:
  - straightforward publish API for interests and authenticated users
  - strong developer-first push surface that complements the more enterprise products in the batch

### 5. Pushwoosh
- Slug: `pushwoosh`
- Score: **7.70**
- Execution: **7.85**
- Access readiness: **7.40**
- Why it made the cut:
  - real cross-platform push vendor with message creation and segmentation APIs
  - broadens market coverage beyond the very top-tier incumbents

## Phase 0 capability assessment

### Services with accessible APIs
All five added services expose accessible API surfaces.

The strongest Resolve candidates are:
1. **Airship**
2. **Batch**
3. **Firebase Cloud Messaging**

Pusher Beams is also plausible. Pushwoosh is valuable discovery coverage now, but a weaker first normalization target than Airship or Batch.

### Candidate capability shapes
- `push_notification.send`
- `push_notification.send_to_user`
- `push_topic.publish`
- `push_audience.segment`
- `device_registration.create`

### Best initial Phase 0 wedge
The cleanest first move is:
- `push_notification.send`
- `push_topic.publish`

Why:
- they are immediately valuable and easy to explain to operators
- they map cleanly onto real provider APIs without needing a full campaign abstraction first
- they create a bridge from workflow / alert systems into mobile user delivery
- Airship looks like the best first implementation target because its push API is mature and audience semantics are already explicit

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0108_push_notifications_expansion.sql`

## Verdict

Push notifications were underweight relative to demand. This batch materially improves Rhumb's discovery surface, and **Airship is now the clearest next Phase 0 candidate** if the team wants to deepen notification delivery beyond catalog coverage.
