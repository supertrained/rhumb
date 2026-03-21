-- Migration 0054: Capability expansion Day 10
-- 10 new capabilities across 4 domains: weather, tax, dns, crypto
-- Continues the daily cadence (~165 → ~175 total capabilities)

BEGIN;

-- ============================================================
-- NEW CAPABILITIES
-- ============================================================
INSERT INTO capabilities (id, domain, description, status) VALUES
  -- Weather (3)
  ('weather.current',   'weather', 'Get current weather conditions for a location',          'active'),
  ('weather.forecast',  'weather', 'Get multi-day weather forecast for a location',           'active'),
  ('weather.historical','weather', 'Retrieve historical weather data for a date and location','active'),
  -- Tax (2)
  ('tax.calculate',     'tax',     'Calculate sales tax or VAT for a transaction',            'active'),
  ('tax.validate_vat',  'tax',     'Validate a VAT number and retrieve business details',     'active'),
  -- DNS (2)
  ('dns.lookup',        'dns',     'Resolve a domain name to IP addresses',                   'active'),
  ('dns.whois',         'dns',     'Retrieve WHOIS registration data for a domain',           'active'),
  -- Crypto / blockchain (3)
  ('crypto.get_price',  'crypto',  'Get current price of a cryptocurrency',                   'active'),
  ('crypto.get_rates',  'crypto',  'Get exchange rates for multiple crypto assets',           'active'),
  ('crypto.verify_address', 'crypto', 'Validate a crypto wallet address format and checksum','active')
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- PROVIDER MAPPINGS
-- ============================================================

-- weather.current
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('weather.current', 'openweather',   '{byo}', 'api_key', 'GET /data/2.5/weather',         'Free: 1K calls/day. Current conditions.'),
  ('weather.current', 'weatherapi',    '{byo}', 'api_key', 'GET /v1/current.json',           'Free: 1M calls/mo. Rich data.'),
  ('weather.current', 'tomorrow-io',   '{byo}', 'api_key', 'GET /v4/weather/realtime',       'Free: 500 calls/day. Hyperlocal.'),
  ('weather.current', 'open-meteo',    '{byo}', 'none',    'GET /v1/forecast',               'Free, no API key required. Open data.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- weather.forecast
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('weather.forecast', 'openweather',  '{byo}', 'api_key', 'GET /data/2.5/forecast',         '5-day/3-hour forecast.'),
  ('weather.forecast', 'weatherapi',   '{byo}', 'api_key', 'GET /v1/forecast.json',           'Up to 14 days.'),
  ('weather.forecast', 'tomorrow-io',  '{byo}', 'api_key', 'GET /v4/weather/forecast',        'Hourly/daily forecast.'),
  ('weather.forecast', 'open-meteo',   '{byo}', 'none',    'GET /v1/forecast',                'Free, no key, 7-day forecast.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- weather.historical
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('weather.historical', 'open-meteo',   '{byo}', 'none',    'GET /v1/archive',               'Free historical data API.'),
  ('weather.historical', 'openweather',  '{byo}', 'api_key', 'GET /data/3.0/onecall/timemachine', 'Historical onecall (paid).'),
  ('weather.historical', 'weatherapi',   '{byo}', 'api_key', 'GET /v1/history.json',           'History up to 365 days back.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- tax.calculate
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('tax.calculate', 'taxjar',     '{byo}', 'api_key', 'POST /v2/taxes',          'SmartCalcs API. 50 free test transactions/mo.'),
  ('tax.calculate', 'avatax',     '{byo}', 'api_key', 'POST /api/v2/transactions/create', 'Avalara AvaTax. Sandbox available.'),
  ('tax.calculate', 'stripe-tax', '{byo}', 'api_key', 'Stripe Tax calculation',  'Built into Stripe Checkout/Invoicing.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- tax.validate_vat
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('tax.validate_vat', 'vatcheckapi',   '{byo}', 'api_key', 'GET /vatcheck/{vat}',         'EU VAT validation. 100 free/mo.'),
  ('tax.validate_vat', 'abstractapi',   '{byo}', 'api_key', 'GET /?api_key={key}&vat_number={vat}', 'Abstract VAT API. 500 free/mo.'),
  ('tax.validate_vat', 'taxjar',        '{byo}', 'api_key', 'GET /v2/validations',          'EU VAT validation endpoint.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- dns.lookup
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('dns.lookup', 'cloudflare-dns', '{byo}', 'none',    'GET /dns-query?name={domain}&type={type}', 'Free DoH endpoint, no key needed.'),
  ('dns.lookup', 'google-dns',     '{byo}', 'none',    'GET /resolve?name={domain}&type={type}',   'Free Google DoH, no key needed.'),
  ('dns.lookup', 'abstractapi',    '{byo}', 'api_key', 'GET /?api_key={key}&domain={domain}',       'IP geolocation + DNS data.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- dns.whois
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('dns.whois', 'whoisxml',    '{byo}', 'api_key', 'GET /whoisserver/WhoisService', 'WHOIS + parsed registrar data. 500 free/mo.'),
  ('dns.whois', 'abstractapi', '{byo}', 'api_key', 'GET /api/whois',                '200 free WHOIS lookups/mo.'),
  ('dns.whois', 'domainr',     '{byo}', 'api_key', 'GET /v2/status',                'Domain availability + registrar info.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- crypto.get_price
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('crypto.get_price', 'coingecko',  '{byo}', 'api_key', 'GET /api/v3/simple/price',          'Free tier: 30 calls/min. 10K+ coins.'),
  ('crypto.get_price', 'coinbase',   '{byo}', 'none',    'GET /v2/prices/{pair}/spot',         'Public endpoint, no key needed.'),
  ('crypto.get_price', 'cryptocompare', '{byo}', 'api_key', 'GET /data/price',                 '100K calls/mo free.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- crypto.get_rates
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('crypto.get_rates', 'coingecko',  '{byo}', 'api_key', 'GET /api/v3/simple/price',          'Multi-coin, multi-currency rates.'),
  ('crypto.get_rates', 'cryptocompare', '{byo}', 'api_key', 'GET /data/pricemultifull',        'Full rate data with metadata.'),
  ('crypto.get_rates', 'coinbase',   '{byo}', 'none',    'GET /v2/exchange-rates',             'Public exchange rates endpoint.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- crypto.verify_address
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('crypto.verify_address', 'blockcypher', '{byo}', 'api_key', 'GET /v1/{coin}/{chain}/addrs/{address}', 'Multi-chain address verification.'),
  ('crypto.verify_address', 'chaingateway', '{byo}', 'api_key', 'POST /v2/address/validate',             'EVM-compatible address validation.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- ============================================================
-- Totals: 10 new capabilities, ~36 new mappings
-- Running total: ~175 capabilities, ~571 mappings
-- ============================================================

COMMIT;
