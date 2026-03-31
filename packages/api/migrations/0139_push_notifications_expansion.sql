BEGIN;

-- Migration 0139: Push-notifications discovery expansion (2026-03-31)
-- Rationale: live production still shows push-notifications as an
-- underrepresented category despite strong operator demand for delivery of
-- alerts, approvals, incident notifications, workflow completions, and mobile
-- user re-engagement across agent-driven systems.
-- Add five API-backed providers that deepen the category around direct push
-- sends, audience targeting, device/token delivery, and notification workflow
-- orchestration.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'onesignal',
    'OneSignal',
    'push-notifications',
    'Customer messaging and push-notification platform with APIs for notifications, segments, templates, users, subscriptions, and delivery analytics across mobile, web, email, and SMS channels.',
    'https://documentation.onesignal.com/reference/create-message',
    'api.onesignal.com'
  ),
  (
    'pushwoosh',
    'Pushwoosh',
    'push-notifications',
    'Push-notification and customer engagement platform with APIs for message sends, segments, devices, applications, transactional pushes, and campaign analytics.',
    'https://docs.pushwoosh.com/developer/api-reference/',
    'api.pushwoosh.com'
  ),
  (
    'airship',
    'Airship',
    'push-notifications',
    'Enterprise push-notification and cross-channel customer engagement platform with APIs for pushes, audiences, schedules, templates, channels, and delivery reporting.',
    'https://docs.airship.com/api/ua/',
    'api.airship.com'
  ),
  (
    'firebase-cloud-messaging',
    'Firebase Cloud Messaging',
    'push-notifications',
    'Google push messaging infrastructure for Android, iOS, and web with APIs for device-targeted sends, topics, conditions, and high-scale delivery through the Firebase HTTP v1 API.',
    'https://firebase.google.com/docs/cloud-messaging',
    'fcm.googleapis.com'
  ),
  (
    'amazon-sns',
    'Amazon SNS',
    'push-notifications',
    'AWS pub-sub and mobile push delivery platform with APIs for publish, topics, platform applications, endpoints, fanout delivery, and notification workflows across mobile and server systems.',
    'https://docs.aws.amazon.com/sns/latest/api/welcome.html',
    'sns.amazonaws.com'
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
    'onesignal',
    8.40,
    8.50,
    8.20,
    0.67,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-31","category_rationale":"push-notifications expansion","notes":"Best immediate Phase 0 candidate in the batch. OneSignal exposes a clean create-message API with explicit audience targeting, templates, user aliases, and delivery controls that map well to notification.push.send and template-backed alert workflows."}'::jsonb,
    now()
  ),
  (
    'firebase-cloud-messaging',
    8.30,
    8.40,
    8.05,
    0.66,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-31","category_rationale":"push-notifications expansion","notes":"Foundational global push rail with strong device, topic, and condition targeting. Excellent long-term Resolve target for notification.push.send, though Google auth setup is slightly heavier than OneSignal for a first pass."}'::jsonb,
    now()
  ),
  (
    'amazon-sns',
    8.20,
    8.30,
    8.00,
    0.64,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-31","category_rationale":"push-notifications expansion","notes":"Useful breadth provider because SNS spans mobile push, pub-sub fanout, and event-driven delivery. Strong fit for agent alerts and topic-based notification workflows, even if its broader AWS surface makes normalization slightly noisier than the cleanest first target."}'::jsonb,
    now()
  ),
  (
    'airship',
    8.10,
    8.20,
    7.90,
    0.62,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-31","category_rationale":"push-notifications expansion","notes":"Enterprise-grade push and audience platform with strong execution potential around pushes, schedules, and templates. Valuable category depth with good future Resolve potential once the simpler cross-provider send primitive is normalized."}'::jsonb,
    now()
  ),
  (
    'pushwoosh',
    8.00,
    8.10,
    7.85,
    0.60,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-31","category_rationale":"push-notifications expansion","notes":"Good commercial push API covering transactional sends, segments, and devices. Solid category depth add and plausible second-wave Resolve target after the first unified notification send wedge is proven."}'::jsonb,
    now()
  )
ON CONFLICT (service_slug) DO UPDATE SET
  aggregate_recommendation_score = EXCLUDED.aggregate_recommendation_score,
  execution_score = EXCLUDED.execution_score,
  access_readiness_score = EXCLUDED.access_readiness_score,
  confidence = EXCLUDED.confidence,
  tier = EXCLUDED.tier,
  tier_label = EXCLUDED.tier_label,
  probe_metadata = EXCLUDED.probe_metadata,
  calculated_at = EXCLUDED.calculated_at;

COMMIT;
