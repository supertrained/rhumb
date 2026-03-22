-- Migration 0058: Capability expansion Day 14
-- 8 new capabilities across 3 domains: timezone, qr, unit
-- Running total: ~211 capabilities, ~670 mappings

BEGIN;

-- ============================================================
-- NEW CAPABILITIES
-- ============================================================
INSERT INTO capabilities (id, domain, description, status) VALUES
  -- Timezone (3)
  ('timezone.convert',   'timezone', 'Convert a datetime from one timezone to another',          'active'),
  ('timezone.get_info',  'timezone', 'Get timezone details, UTC offset, and DST status for a zone','active'),
  ('timezone.list',      'timezone', 'List all IANA timezone identifiers',                        'active'),
  -- QR code (2)
  ('qr.generate',  'qr', 'Generate a QR code image from a URL or text payload', 'active'),
  ('qr.decode',    'qr', 'Decode a QR code image to extract its payload',       'active'),
  -- Unit conversion (3)
  ('unit.convert',         'unit', 'Convert a value between compatible units (length, weight, temp, etc.)', 'active'),
  ('unit.list_categories', 'unit', 'List available unit categories and unit names',                         'active'),
  ('unit.parse',           'unit', 'Parse a human-readable measurement string into value + unit',           'active')
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- PROVIDER MAPPINGS
-- ============================================================

-- timezone.convert
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('timezone.convert', 'timezonedb',   '{byo}', 'api_key', 'GET /v2.1/convert-time-zone', '100K requests/mo free.'),
  ('timezone.convert', 'worldtimeapi', '{byo}', 'none',    'GET /api/timezone/{zone}',    'No auth required; rate-limited.'),
  ('timezone.convert', 'google-tz',    '{byo}', 'api_key', 'GET /maps/api/timezone/json', 'Google Time Zone API; billed per request after free quota.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- timezone.get_info
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('timezone.get_info', 'timezonedb',   '{byo}', 'api_key', 'GET /v2.1/get-time-zone',    '100K requests/mo free.'),
  ('timezone.get_info', 'worldtimeapi', '{byo}', 'none',    'GET /api/timezone/{zone}',   'No auth required.'),
  ('timezone.get_info', 'ipinfo',       '{byo,rhumb_managed}', 'bearer_token', 'GET /lite/{ip}', 'PROXY-CALLABLE — timezone included in IPinfo IP response.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- timezone.list
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('timezone.list', 'worldtimeapi', '{byo}', 'none',    'GET /api/timezone', 'Full list of supported zones.'),
  ('timezone.list', 'timezonedb',   '{byo}', 'api_key', 'GET /v2.1/list-time-zone', 'Returns all zones with UTC offset.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- qr.generate
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('qr.generate', 'qrserver',       '{byo}', 'none',    'GET /v1/create-qr-code/?data={payload}', 'No auth required. Free.'),
  ('qr.generate', 'qr-code-monkey', '{byo}', 'api_key', 'POST /api/qr',                           '250 QR/day free.'),
  ('qr.generate', 'goqr',           '{byo}', 'none',    'GET /api/qr.png?data={payload}',         'No auth required. Free public API.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- qr.decode
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('qr.decode', 'qrserver', '{byo}', 'none',    'POST /v1/read-qr-code/', 'No auth required. Free.'),
  ('qr.decode', 'zxing',    '{byo}', 'none',    'GET /w/decode?u={image_url}',   'Google ZXing online decoder. No auth.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- unit.convert
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('unit.convert', 'unitconverter-io', '{byo}', 'api_key', 'GET /api/convert',      'Free tier available.'),
  ('unit.convert', 'convertapi',       '{byo}', 'api_key', 'POST /convert/{from}/to/{to}', '1,500 seconds free. Covers docs, units, images.'),
  ('unit.convert', 'free-unit-api',    '{byo}', 'none',    'GET /convert',          'Open API, no auth required.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- unit.list_categories
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('unit.list_categories', 'unitconverter-io', '{byo}', 'api_key', 'GET /api/categories', 'Returns all conversion categories.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- unit.parse
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('unit.parse', 'unitconverter-io', '{byo}', 'api_key', 'GET /api/parse', 'Parses natural language measurement strings.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- ============================================================
-- Note: timezone.get_info via ipinfo is rhumb_managed
-- (IPinfo credential already live and verified on proxy)
-- Adds 1 more rhumb_managed mapping to the executable count
-- ============================================================

COMMIT;
