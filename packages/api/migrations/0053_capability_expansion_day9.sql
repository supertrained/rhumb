-- Migration 0053: Capability expansion Day 9
-- 10 new capabilities across 4 domains: phone, calendar, url, social
-- Running total: ~165 capabilities, ~535 mappings

BEGIN;

-- ============================================================
-- NEW CAPABILITIES
-- ============================================================
INSERT INTO capabilities (id, domain, description, status) VALUES
  -- Phone (3)
  ('phone.validate',    'phone',    'Validate a phone number format and carrier lookup',  'active'),
  ('phone.lookup',      'phone',    'Look up carrier, line type, and location for a number', 'active'),
  ('phone.send_otp',    'phone',    'Send a one-time passcode via SMS for verification', 'active'),
  -- Calendar (2)
  ('calendar.create_event',        'calendar', 'Create a calendar event with attendees and details', 'active'),
  ('calendar.check_availability',  'calendar', 'Check free/busy availability for one or more users', 'active'),
  -- URL utilities (2)
  ('url.shorten',  'url', 'Shorten a long URL to a compact link',  'active'),
  ('url.expand',   'url', 'Expand a short URL to its destination', 'active'),
  -- Social / identity (3)
  ('social.get_profile',  'social', 'Fetch a public profile from a social platform', 'active'),
  ('social.post',         'social', 'Post content to a social platform',             'active'),
  ('social.search',       'social', 'Search posts or accounts on a social platform', 'active')
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- PROVIDER MAPPINGS
-- ============================================================

-- phone.validate
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('phone.validate', 'twilio',      '{byo}', 'api_key', 'GET /v2/PhoneNumbers/{number}',     'Twilio Lookup. ~$0.01/lookup.'),
  ('phone.validate', 'numverify',   '{byo}', 'api_key', 'GET /api/validate',                 'NumVerify. 100 free/mo.'),
  ('phone.validate', 'telesign',    '{byo}', 'api_key', 'POST /v1/phoneid/standard/{number}','TeleSign PhoneID.'),
  ('phone.validate', 'vonage',      '{byo}', 'api_key', 'GET /ni/basic/json',                'Vonage Number Insight.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- phone.lookup
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('phone.lookup', 'twilio',    '{byo}', 'api_key', 'GET /v2/PhoneNumbers/{number}?Fields=carrier', 'Carrier + line type.'),
  ('phone.lookup', 'numverify', '{byo}', 'api_key', 'GET /api/validate',                            'Carrier, country, line type.'),
  ('phone.lookup', 'vonage',    '{byo}', 'api_key', 'GET /ni/advanced/json',                        'Advanced lookup with roaming info.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- phone.send_otp
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('phone.send_otp', 'twilio',  '{byo}', 'api_key', 'POST /v2/Services/{sid}/Verifications', 'Twilio Verify. $0.05/verification.'),
  ('phone.send_otp', 'vonage',  '{byo}', 'api_key', 'POST /verify/v2/verifications',         'Vonage Verify.'),
  ('phone.send_otp', 'telesign','{byo}', 'api_key', 'POST /v1/verify/sms',                   'TeleSign SMS verify.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- calendar.create_event
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('calendar.create_event', 'google-calendar',    '{byo}', 'oauth2', 'POST /calendar/v3/calendars/{calendarId}/events', 'Google Calendar API.'),
  ('calendar.create_event', 'microsoft-calendar', '{byo}', 'oauth2', 'POST /v1.0/me/events',                            'Microsoft Graph Calendar.'),
  ('calendar.create_event', 'nylas',              '{byo}', 'api_key','POST /v3/grants/{id}/events',                     'Nylas unified calendar API. Free tier available.'),
  ('calendar.create_event', 'cal-com',            '{byo}', 'api_key','POST /v1/bookings',                               'Cal.com booking creation.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- calendar.check_availability
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('calendar.check_availability', 'google-calendar',    '{byo}', 'oauth2', 'POST /calendar/v3/freeBusy',     'Google free/busy query.'),
  ('calendar.check_availability', 'microsoft-calendar', '{byo}', 'oauth2', 'POST /v1.0/me/calendar/getSchedule', 'Microsoft Graph schedule.'),
  ('calendar.check_availability', 'nylas',              '{byo}', 'api_key','GET /v3/grants/{id}/events',     'Query events to infer availability.'),
  ('calendar.check_availability', 'cal-com',            '{byo}', 'api_key','GET /v1/availability',           'Cal.com slot availability.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- url.shorten
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('url.shorten', 'bitly',     '{byo}', 'api_key', 'POST /v4/shorten',       'Bitly. 1K links/mo free.'),
  ('url.shorten', 'tinyurl',   '{byo}', 'api_key', 'POST /api/v1/create',    'TinyURL API.'),
  ('url.shorten', 'rebrandly', '{byo}', 'api_key', 'POST /v1/links',         'Custom domain short links. 500/mo free.'),
  ('url.shorten', 'dub',       '{byo}', 'api_key', 'POST /api/v1/links',     'Open-source, 25 links/mo free.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- url.expand
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('url.expand', 'bitly',     '{byo}', 'api_key', 'GET /v4/bitlinks/{id}',  'Bitly link details.'),
  ('url.expand', 'rebrandly', '{byo}', 'api_key', 'GET /v1/links/{id}',     'Rebrandly link details.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- social.get_profile
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('social.get_profile', 'twitter',   '{byo}', 'oauth2',  'GET /2/users/by/username/{username}', 'X/Twitter API v2.'),
  ('social.get_profile', 'linkedin',  '{byo}', 'oauth2',  'GET /v2/me',                          'LinkedIn Profile API.'),
  ('social.get_profile', 'github',    '{byo}', 'api_key', 'GET /users/{username}',               'GitHub public profile.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- social.post
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('social.post', 'twitter',  '{byo}', 'oauth2', 'POST /2/tweets',           'X/Twitter post tweet.'),
  ('social.post', 'linkedin', '{byo}', 'oauth2', 'POST /v2/ugcPosts',        'LinkedIn share/post.'),
  ('social.post', 'buffer',   '{byo}', 'api_key','POST /1/updates/create.json', 'Buffer multi-platform scheduling.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- social.search
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('social.search', 'twitter', '{byo}', 'oauth2',  'GET /2/tweets/search/recent', 'X/Twitter recent search.'),
  ('social.search', 'reddit',  '{byo}', 'oauth2',  'GET /search.json',            'Reddit public search.'),
  ('social.search', 'github',  '{byo}', 'api_key', 'GET /search/repositories',    'GitHub code/repo search.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- ============================================================
-- Totals: 10 new capabilities, ~34 new mappings
-- Running total: ~165 capabilities, ~535 mappings
-- ============================================================

COMMIT;
