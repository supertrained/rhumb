# Discovery expansion — push-notifications

Date: 2026-03-31
Owner: Pedro / Keel runtime review loop

## Why this category

Live production still shows **`push-notifications`** at only **4** providers:
- `expo-notifications`
- `gotify`
- `ntfy`
- `pushover`

That is too thin for a category agents need constantly for:
- incident alerts
- approval requests
- workflow completion notifications
- mobile user re-engagement
- background-job status reporting
- delivery of important operational messages outside chat and email

So the honest Mission 2 move was to deepen **push-notifications** with larger commercial and infrastructure-grade APIs instead of adding another shallow fringe category.

## Added services

### 1. OneSignal
- Slug: `onesignal`
- Score: **8.40**
- Execution: **8.50**
- Access readiness: **8.20**
- Why it made the cut:
  - explicit REST API for push sends, templates, users, aliases, segments, and delivery controls
  - strongest clean Phase 0 candidate for a unified notification send primitive

### 2. Firebase Cloud Messaging
- Slug: `firebase-cloud-messaging`
- Score: **8.30**
- Execution: **8.40**
- Access readiness: **8.05**
- Why it made the cut:
  - foundational global push rail with strong device, topic, and condition targeting
  - strategically important because many agent products already sit on Firebase-backed mobile surfaces

### 3. Amazon SNS
- Slug: `amazon-sns`
- Score: **8.20**
- Execution: **8.30**
- Access readiness: **8.00**
- Why it made the cut:
  - broad publish and fanout surface spanning mobile push and server-side notification workflows
  - useful bridge between push-notification and event-driven agent infrastructure

### 4. Airship
- Slug: `airship`
- Score: **8.10**
- Execution: **8.20**
- Access readiness: **7.90**
- Why it made the cut:
  - strong enterprise push, audience, schedule, and template surface
  - good category depth for higher-control commercial delivery workflows

### 5. Pushwoosh
- Slug: `pushwoosh`
- Score: **8.00**
- Execution: **8.10**
- Access readiness: **7.85**
- Why it made the cut:
  - practical commercial API for transactional pushes, applications, devices, and segments
  - good second-wave normalization target once the first push-send wedge is proven

## Phase 0 capability assessment

All five additions expose accessible APIs and are viable Resolve candidates.

### Strongest candidates for Resolve capability addition
1. **OneSignal**
2. **Firebase Cloud Messaging**
3. **Amazon SNS**
4. **Airship**

### Candidate capability shapes
- `notification.push.send`
- `notification.template.send`
- `notification.topic.publish`
- `device.register`
- `audience.segment.list`

### Best initial Phase 0 wedge
The cleanest first move is:
- `notification.push.send`

Why:
- it is the universal primitive across almost every provider in the category
- it supports both operator alerts and product-facing user notifications
- it is easier to normalize than templates, audience graphs, or device lifecycle management
- **OneSignal** is the best first provider target because its create-message API is explicit, mature, and shaped well for a straightforward provider-native execution config

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0139_push_notifications_expansion.sql`

## Verdict

Push-notifications remains underrepresented in live production. This batch adds five more real API-backed providers and sharpens the next honest Resolve wedge around **notification.push.send**, with **OneSignal** as the cleanest first implementation target.
