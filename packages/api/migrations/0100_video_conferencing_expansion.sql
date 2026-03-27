BEGIN;

-- Migration 0100: Video-conferencing discovery expansion (2026-03-26)
-- Rationale: video conferencing is a high-demand operational category for agents,
-- but the catalog still lacks breadth across enterprise meeting suites and
-- programmable video infrastructure. Add 4 API-first providers with initial scoring.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'webex-meetings',
    'Webex Meetings',
    'video-conferencing',
    'Cisco Webex meetings API for listing, creating, updating, and deleting scheduled meetings and related conferencing objects.',
    'https://developer.webex.com/meeting/docs/api/v1/meetings',
    'webexapis.com'
  ),
  (
    'vonage-video',
    'Vonage Video',
    'video-conferencing',
    'Programmable video platform for sessions, tokens, archives, broadcasts, and embedded real-time communication workflows.',
    'https://developer.vonage.com/en/video/overview',
    'video.api.vonage.com'
  ),
  (
    'amazon-chime-sdk',
    'Amazon Chime SDK',
    'video-conferencing',
    'AWS real-time communications stack for audio, video, screen sharing, messaging, and media pipelines inside custom applications.',
    'https://docs.aws.amazon.com/chime-sdk/latest/dg/what-is-chime-sdk.html',
    'service.chime.aws.amazon.com'
  ),
  (
    'stream-video',
    'Stream Video',
    'video-conferencing',
    'API-first in-app video and audio platform for call creation, participant management, moderation, recording, and product-native calling.',
    'https://getstream.io/video/docs/api/',
    'video.stream-io-api.com'
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
    'webex-meetings',
    7.85,
    8.10,
    7.55,
    0.58,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-26","category_rationale":"video-conferencing expansion","notes":"Best immediate Phase 0 candidate in the batch. Meetings API maps directly to normalized meeting.list/create/update/cancel flows and has clear enterprise scheduling value for agents."}'::jsonb,
    now()
  ),
  (
    'vonage-video',
    7.55,
    7.95,
    7.05,
    0.56,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-26","category_rationale":"video-conferencing expansion","notes":"Strong programmable video/session surface with session, token, archive, and broadcast primitives. Attractive later Resolve target for meeting/session orchestration and recording controls."}'::jsonb,
    now()
  ),
  (
    'amazon-chime-sdk',
    7.20,
    7.70,
    6.65,
    0.54,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-26","category_rationale":"video-conferencing expansion","notes":"High-power communications infrastructure with broad real-time media scope, but more infra-heavy and AWS-shaped than first-wave normalized conferencing capabilities."}'::jsonb,
    now()
  ),
  (
    'stream-video',
    7.60,
    7.90,
    7.20,
    0.56,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-26","category_rationale":"video-conferencing expansion","notes":"Modern API-first product video platform with strong developer ergonomics and good fit for call/session orchestration, moderation, and recording workflows once conferencing primitives are normalized."}'::jsonb,
    now()
  );

COMMIT;
