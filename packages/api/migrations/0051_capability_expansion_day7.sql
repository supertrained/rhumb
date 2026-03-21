-- Migration 0051: Capability expansion Day 7
-- 10 new capabilities across 4 domains: translation, image, currency, maps
-- Continues the daily cadence (135 → 145 total capabilities)

BEGIN;

-- ============================================================
-- NEW CAPABILITIES
-- ============================================================
INSERT INTO capabilities (id, domain, description, status) VALUES
  -- Translation (3)
  ('translate.text',            'translation', 'Translate text between languages',                    'active'),
  ('translate.detect_language', 'translation', 'Detect the language of a text string',               'active'),
  ('translate.batch',           'translation', 'Translate multiple strings in a single request',     'active'),
  -- Image processing (3)
  ('image.resize',              'image',       'Resize or crop an image to specified dimensions',    'active'),
  ('image.optimize',            'image',       'Compress/optimize an image for web delivery',        'active'),
  ('image.analyze',             'image',       'Extract labels, objects, or text from an image',     'active'),
  -- Currency / FX (2)
  ('currency.convert',          'currency',    'Convert an amount between two currencies',           'active'),
  ('currency.get_rates',        'currency',    'Fetch current or historical FX rates',               'active'),
  -- Maps / geocoding (2)
  ('maps.geocode',              'maps',        'Convert an address or place name to coordinates',    'active'),
  ('maps.directions',           'maps',        'Get turn-by-turn directions between two points',     'active')
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- PROVIDER MAPPINGS
-- ============================================================

-- translate.text
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('translate.text', 'deepl',            '{byo}', 'api_key', 'POST /v2/translate',             'High-quality neural translation. Free tier: 500K chars/mo.'),
  ('translate.text', 'google-translate', '{byo}', 'api_key', 'POST /language/translate/v2',    'Google Cloud Translation. Pay-per-use.'),
  ('translate.text', 'aws-translate',    '{byo}', 'api_key', 'POST / (AWS SDK)',                'AWS Translate. 2M chars/mo free 12 months.'),
  ('translate.text', 'libretranslate',   '{byo}', 'api_key', 'POST /translate',                'Open-source, self-hostable option.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- translate.detect_language
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('translate.detect_language', 'deepl',            '{byo}', 'api_key', 'POST /v2/translate',          'Language detection bundled with translate call.'),
  ('translate.detect_language', 'google-translate', '{byo}', 'api_key', 'POST /language/translate/v2/detect', 'Dedicated detect endpoint.'),
  ('translate.detect_language', 'aws-translate',    '{byo}', 'api_key', 'AWS Comprehend DetectDominantLanguage', 'Via AWS Comprehend.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- translate.batch
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('translate.batch', 'deepl',            '{byo}', 'api_key', 'POST /v2/translate',          'Up to 50 texts per request.'),
  ('translate.batch', 'google-translate', '{byo}', 'api_key', 'POST /language/translate/v2', 'Array of q= inputs supported.'),
  ('translate.batch', 'aws-translate',    '{byo}', 'api_key', 'StartTextTranslationJob',     'Async batch translation job.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- image.resize
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('image.resize', 'cloudinary', '{byo}', 'api_key', 'GET /image/upload/{transformations}/{public_id}', 'URL-based transforms. Free: 25 monthly credits.'),
  ('image.resize', 'imgix',      '{byo}', 'api_key', 'GET /{path}?w={w}&h={h}',                        'URL parameter transforms.'),
  ('image.resize', 'imagekit',   '{byo}', 'api_key', 'GET /{path}?tr=w-{w},h-{h}',                     'Free: 20GB bandwidth/mo.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- image.optimize
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('image.optimize', 'cloudinary', '{byo}', 'api_key', 'GET /image/upload/q_auto/{public_id}', 'Automatic quality + format selection.'),
  ('image.optimize', 'tinypng',    '{byo}', 'api_key', 'POST /shrink',                         'PNG/JPEG compression. 500 free/mo.'),
  ('image.optimize', 'imagekit',   '{byo}', 'api_key', 'GET /{path}?tr=q-auto',                'Auto quality optimization.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- image.analyze
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('image.analyze', 'google-vision', '{byo}', 'api_key', 'POST /v1/images:annotate',        'Labels, objects, OCR, faces. 1K units/mo free.'),
  ('image.analyze', 'aws-rekognition', '{byo}', 'api_key', 'DetectLabels (AWS SDK)',         '5K images/mo free 12 months.'),
  ('image.analyze', 'cloudinary',   '{byo}', 'api_key', 'GET /image/upload/e_art/{public_id}', 'AI-powered image analysis add-on.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- currency.convert
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('currency.convert', 'exchangerate-api',  '{byo}', 'api_key', 'GET /v6/{key}/pair/{from}/{to}/{amount}', '1,500 requests/mo free.'),
  ('currency.convert', 'openexchangerates', '{byo}', 'api_key', 'GET /api/convert/{amount}/{from}/{to}',   '1K requests/mo free.'),
  ('currency.convert', 'fixer',             '{byo}', 'api_key', 'GET /convert',                            '100 requests/mo free.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- currency.get_rates
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('currency.get_rates', 'exchangerate-api',  '{byo}', 'api_key', 'GET /v6/{key}/latest/{base}',       'All rates against a base currency.'),
  ('currency.get_rates', 'openexchangerates', '{byo}', 'api_key', 'GET /api/latest.json',              '170 currencies.'),
  ('currency.get_rates', 'fixer',             '{byo}', 'api_key', 'GET /latest',                       'ECB-sourced rates.'),
  ('currency.get_rates', 'currencylayer',     '{byo}', 'api_key', 'GET /live',                         '168 currencies, 250 requests/mo free.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- maps.geocode
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('maps.geocode', 'google-maps', '{byo}', 'api_key', 'GET /maps/api/geocode/json',      '200 USD/mo free credit.'),
  ('maps.geocode', 'mapbox',      '{byo}', 'api_key', 'GET /geocoding/v5/mapbox.places/{query}.json', '100K requests/mo free.'),
  ('maps.geocode', 'here-maps',   '{byo}', 'api_key', 'GET /v1/geocode',                 '30K transactions/mo free.'),
  ('maps.geocode', 'opencage',    '{byo}', 'api_key', 'GET /geocode/v1/json',            '2.5K requests/day free.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- maps.directions
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('maps.directions', 'google-maps', '{byo}', 'api_key', 'GET /maps/api/directions/json', '200 USD/mo free credit.'),
  ('maps.directions', 'mapbox',      '{byo}', 'api_key', 'GET /directions/v5/mapbox/{profile}/{coordinates}', '100K requests/mo free.'),
  ('maps.directions', 'here-maps',   '{byo}', 'api_key', 'GET /v8/routes',                'Free tier included.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- ============================================================
-- Totals: 10 new capabilities, ~37 new mappings
-- Running total: ~145 capabilities, ~466 mappings
-- ============================================================

COMMIT;
