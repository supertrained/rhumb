BEGIN;

-- Migration 0108: Push-notifications discovery expansion (2026-03-28)
-- Rationale: push-notifications is still underrepresented in the live catalog
-- despite being a high-demand operational surface for mobile products,
-- transactional messaging, lifecycle workflows, and agent-triggered customer
-- outreach. Add five providers spanning enterprise mobile engagement,
-- transactional push, developer-first delivery, and the dominant platform push rail.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'airship',
    'Airship',
    'push-notifications',
    'Enterprise mobile engagement and push-notification platform with APIs for push sends, audience targeting, channels, tags, automation, experiments, and notification orchestration.',
    'https://www.airship.com/docs/api/ua/',
    'go.urbanairship.com'
  ),
  (
    'firebase-cloud-messaging',
    'Firebase Cloud Messaging',
    'push-notifications',
    'Google push-delivery platform for Android, iOS, and web with HTTP v1 API support for topic, token, and condition-based message delivery at very large scale.',
    'https://firebase.google.com/docs/reference/fcm/rest',
    'fcm.googleapis.com'
  ),
  (
    'batch',
    'Batch',
    'push-notifications',
    'Customer engagement and transactional push platform with APIs for targeted push sends, campaigns, user targeting, and 1-to-1 notification workflows.',
    'https://doc.batch.com/developer/api/mep/transactional/send',
    'api.batch.com'
  ),
  (
    'pusher-beams',
    'Pusher Beams',
    'push-notifications',
    'Developer-friendly push-notification service from Pusher with publish APIs for interests, authenticated users, and mobile push delivery workflows.',
    'https://pusher.com/docs/beams/reference/publish-api/',
    'pushnotifications.pusher.com'
  ),
  (
    'pushwoosh',
    'Pushwoosh',
    'push-notifications',
    'Cross-platform push and customer-engagement platform with API coverage for message creation, segmentation, scheduling, and mobile lifecycle messaging.',
    'https://docs.pushwoosh.com/platform-docs/api-reference-messages/create-message',
    'cp.pushwoosh.com'
  )
ON CONFLICT (slug) DO NOTHING;

INSERT INTO scores (
  service_slug,
  aggregate_recommendation_score,
  execution_score,
  access_readiness_score,
  confidence,
  tier,
  tier_label,
  probe_metadata,
  calculated_at
)
VALUES
  (
    'airship',
    8.20,
    8.35,
    7.95,
    0.65,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-28","category_rationale":"push-notifications expansion","notes":"Best immediate Phase 0 candidate in the batch. Airship exposes a mature push API with clear audience and send primitives that map well to push_notification.send plus segment-aware delivery workflows."}'::jsonb,
    now()
  ),
  (
    'firebase-cloud-messaging',
    8.10,
    8.25,
    7.80,
    0.67,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-28","category_rationale":"push-notifications expansion","notes":"Strategically critical coverage because FCM is the default push rail for a huge share of modern mobile stacks. Auth and project setup are heavier than the cleanest SaaS entrants, but the HTTP v1 send surface is very real and broadly useful."}'::jsonb,
    now()
  ),
  (
    'batch',
    7.95,
    8.05,
    7.75,
    0.61,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-28","category_rationale":"push-notifications expansion","notes":"Strong transactional push fit with explicit 1-to-1 send docs and operator-friendly user-targeted delivery semantics. Good near-term candidate once push send primitives are prioritized."}'::jsonb,
    now()
  ),
  (
    'pusher-beams',
    7.80,
    7.95,
    7.45,
    0.58,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-28","category_rationale":"push-notifications expansion","notes":"Developer-friendly publish API with clean interest and user targeting concepts. Slightly lower access readiness because instance-specific domains and app setup shape the integration path, but still a strong catalog addition."}'::jsonb,
    now()
  ),
  (
    'pushwoosh',
    7.70,
    7.85,
    7.40,
    0.56,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-28","category_rationale":"push-notifications expansion","notes":"Important cross-platform push vendor with message creation and segmentation APIs. Public docs are more product-heavy than Airship or FCM, which makes it a weaker first Resolve target but still worthwhile discovery coverage."}'::jsonb,
    now()
  );

COMMIT;
