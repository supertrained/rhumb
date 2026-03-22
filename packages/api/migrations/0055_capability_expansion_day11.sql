-- Migration 0055: Capability expansion Day 11
-- 10 new capabilities across 4 domains: validate, video, notification, spreadsheet
-- Continues the daily cadence (~175 → ~185 total capabilities)

BEGIN;

-- ============================================================
-- NEW CAPABILITIES
-- ============================================================
INSERT INTO capabilities (id, domain, description, status) VALUES
  -- Validation utilities (3)
  ('validate.email',        'validate',     'Validate email address format, MX records, and deliverability', 'active'),
  ('validate.address',      'validate',     'Validate and normalize a postal address',                       'active'),
  ('validate.vat',          'validate',     'Validate a VAT/tax ID number for a given country',              'active'),
  -- Video processing (3)
  ('video.transcode',       'video',        'Transcode a video file to a different format or resolution',    'active'),
  ('video.thumbnail',       'video',        'Extract a thumbnail image from a video at a given timestamp',   'active'),
  ('video.subtitle',        'video',        'Generate or embed subtitles/captions for a video',              'active'),
  -- Push / in-app notifications (2)
  ('notification.push',     'notification', 'Send a push notification to a mobile device or browser',        'active'),
  ('notification.in_app',   'notification', 'Deliver an in-app notification message to a user',              'active'),
  -- Spreadsheet / tabular data (2)
  ('spreadsheet.read',      'spreadsheet',  'Read rows or ranges from a spreadsheet file',                   'active'),
  ('spreadsheet.write',     'spreadsheet',  'Write or append rows to a spreadsheet file',                    'active')
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- PROVIDER MAPPINGS
-- ============================================================

-- validate.email
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('validate.email', 'zerobounce',    '{byo}', 'api_key', 'GET /v2/validate',                  'Real-time bounce detection. 100 free/mo.'),
  ('validate.email', 'hunter',        '{byo}', 'api_key', 'GET /v2/email-verifier',            'Email verification + deliverability. 25 free/mo.'),
  ('validate.email', 'kickbox',       '{byo}', 'api_key', 'GET /v2/verify',                    'Single email verify. 100 free.'),
  ('validate.email', 'millionverifier','{byo}','api_key', 'GET /api/v3/verify',                'High-volume email verification.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- validate.address
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('validate.address', 'google-maps',  '{byo}', 'api_key', 'POST /v1:validateAddress',         'Address Validation API. Pay-per-use.'),
  ('validate.address', 'smartystreets','{byo}', 'api_key', 'GET /street-address',              'US address validation. 250 free/mo.'),
  ('validate.address', 'lob',          '{byo}', 'api_key', 'POST /v1/us_verifications',        'US + intl address verify. Free test mode.'),
  ('validate.address', 'here-maps',    '{byo}', 'api_key', 'GET /v1/validate',                 'HERE Address Validation API.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- validate.vat
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('validate.vat', 'vatcheckapi',  '{byo}', 'api_key', 'GET /api/v2/vatcheck',              'EU VAT + VIES validation. 100/day free.'),
  ('validate.vat', 'abstractapi',  '{byo}', 'api_key', 'GET /vat/v1/validate',              'VAT validation API. 1K free/mo.'),
  ('validate.vat', 'stripe-tax',   '{byo}', 'api_key', 'POST /v1/tax/calculations',         'Stripe Tax VAT validation via calculation.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- video.transcode
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('video.transcode', 'cloudinary',   '{byo}', 'api_key', 'POST /video/upload',              'Eager transformations at upload. 25 credits/mo free.'),
  ('video.transcode', 'mux',          '{byo}', 'api_key', 'POST /video/v1/assets',           'Streaming + transcoding. Pay-per-minute.'),
  ('video.transcode', 'cloudconvert', '{byo}', 'api_key', 'POST /v2/jobs',                   '25 conversions/day free. 200+ formats.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- video.thumbnail
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('video.thumbnail', 'cloudinary',  '{byo}', 'api_key', 'GET /video/upload/so_{offset}/{id}', 'URL-based video thumbnail extraction.'),
  ('video.thumbnail', 'mux',         '{byo}', 'api_key', 'GET /video/v1/assets/{id}/images',   'Generate thumbnail from uploaded asset.'),
  ('video.thumbnail', 'api.video',   '{byo}', 'api_key', 'GET /videos/{id}/thumbnails',         'api.video thumbnail endpoint.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- video.subtitle
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('video.subtitle', 'deepgram',    '{byo,rhumb_managed}', 'api_key', 'POST /v1/listen?diarize=true', 'PROXY-CALLABLE — live Deepgram credential. STT → SRT output.'),
  ('video.subtitle', 'rev-ai',      '{byo}', 'api_key', 'POST /speechtotext/v1/jobs',        'Caption/subtitle generation. Pay-per-minute.'),
  ('video.subtitle', 'assemblyai',  '{byo}', 'api_key', 'POST /v2/transcript',               'Auto-chapters, SRT export. $0.37/hr.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- notification.push
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('notification.push', 'onesignal',  '{byo}', 'api_key', 'POST /api/v1/notifications',      'Push to iOS/Android/web. Free up to 10K subscribers.'),
  ('notification.push', 'expo',       '{byo}', 'api_key', 'POST /--/api/v2/push/send',        'Expo Push — React Native first. Free.'),
  ('notification.push', 'firebase',   '{byo}', 'api_key', 'POST /v1/projects/{id}/messages:send', 'FCM push via Firebase. Free.'),
  ('notification.push', 'pusher',     '{byo}', 'api_key', 'POST /apps/{id}/events',           'Pusher Beams push. 1K subscribers free.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- notification.in_app
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('notification.in_app', 'onesignal', '{byo}', 'api_key', 'POST /api/v1/notifications',    'In-app messaging alongside push. Free tier.'),
  ('notification.in_app', 'novu',      '{byo}', 'api_key', 'POST /v1/events/trigger',       'Open-source notification infra. 10K events/mo free.'),
  ('notification.in_app', 'courier',   '{byo}', 'api_key', 'POST /send',                    'Multi-channel. 10K notifications/mo free.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- spreadsheet.read
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('spreadsheet.read', 'google-sheets', '{byo}', 'oauth2', 'GET /v4/spreadsheets/{id}/values/{range}', 'Google Sheets API. Free (quota-based).'),
  ('spreadsheet.read', 'airtable',      '{byo}', 'api_key', 'GET /v0/{base}/{table}',                  'Airtable REST API. 1K records/month free.'),
  ('spreadsheet.read', 'smartsheet',    '{byo}', 'api_key', 'GET /sheets/{id}/rows',                   'Smartsheet API. Free trial.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- spreadsheet.write
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('spreadsheet.write', 'google-sheets', '{byo}', 'oauth2', 'PUT /v4/spreadsheets/{id}/values/{range}', 'Google Sheets write/append. Free (quota-based).'),
  ('spreadsheet.write', 'airtable',      '{byo}', 'api_key', 'POST /v0/{base}/{table}',                  'Airtable record creation. Free tier.'),
  ('spreadsheet.write', 'smartsheet',    '{byo}', 'api_key', 'POST /sheets/{id}/rows',                   'Smartsheet row insert.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- ============================================================
-- Totals: 10 new capabilities, ~37 new mappings
-- Running total: ~185 capabilities, ~508 mappings
-- ============================================================

COMMIT;
