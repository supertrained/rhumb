-- Migration 0061: Capability expansion Day 17
-- 9 new capabilities across 3 domains: ecommerce, market-data, identity
-- Running total: ~237 capabilities, ~756 mappings

BEGIN;

-- ============================================================
-- NEW CAPABILITIES
-- ============================================================
INSERT INTO capabilities (id, domain, description, status) VALUES
  -- E-commerce (3)
  ('ecommerce.search_products', 'ecommerce', 'Search a product catalog by query or filters',         'active'),
  ('ecommerce.get_product',     'ecommerce', 'Fetch details for a single product by ID or handle',   'active'),
  ('ecommerce.create_order',    'ecommerce', 'Place an order in a store or marketplace',             'active'),
  -- Market / financial data (3)
  ('market.get_quote',          'market',    'Get real-time or delayed quote for a stock or asset',  'active'),
  ('market.get_history',        'market',    'Fetch historical OHLCV price data for an asset',       'active'),
  ('market.search_symbols',     'market',    'Search for ticker symbols or financial instruments',   'active'),
  -- Identity / KYC (3)
  ('identity.verify',           'identity',  'Verify a persons identity against document data',      'active'),
  ('identity.check_document',   'identity',  'Analyze and validate an ID document image',            'active'),
  ('identity.lookup',           'identity',  'Look up identity attributes from a phone or email',    'active')
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- PROVIDER MAPPINGS
-- ============================================================

-- ecommerce.search_products
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('ecommerce.search_products', 'shopify',       '{byo}', 'api_key', 'GET /admin/api/2024-01/products.json',         'Shopify Admin API. Requires store-specific OAuth.'),
  ('ecommerce.search_products', 'bigcommerce',   '{byo}', 'api_key', 'GET /v3/catalog/products',                     'BigCommerce REST API.'),
  ('ecommerce.search_products', 'woocommerce',   '{byo}', 'api_key', 'GET /wp-json/wc/v3/products',                  'WooCommerce REST API. Requires store host.'),
  ('ecommerce.search_products', 'algolia',       '{byo,rhumb_managed}', 'api_key', 'POST /{index}/query',            'PROXY-CALLABLE — live Algolia credential. Powers product search.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- ecommerce.get_product
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('ecommerce.get_product', 'shopify',     '{byo}', 'api_key', 'GET /admin/api/2024-01/products/{id}.json', 'Shopify Admin API.'),
  ('ecommerce.get_product', 'bigcommerce', '{byo}', 'api_key', 'GET /v3/catalog/products/{id}',             'BigCommerce REST API.'),
  ('ecommerce.get_product', 'woocommerce', '{byo}', 'api_key', 'GET /wp-json/wc/v3/products/{id}',          'WooCommerce REST API.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- ecommerce.create_order
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('ecommerce.create_order', 'shopify',     '{byo}', 'api_key', 'POST /admin/api/2024-01/orders.json', 'Shopify Admin API.'),
  ('ecommerce.create_order', 'bigcommerce', '{byo}', 'api_key', 'POST /v2/orders',                     'BigCommerce REST API.'),
  ('ecommerce.create_order', 'woocommerce', '{byo}', 'api_key', 'POST /wp-json/wc/v3/orders',          'WooCommerce REST API.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- market.get_quote
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('market.get_quote', 'alpaca',        '{byo}', 'api_key', 'GET /v2/stocks/{symbol}/quotes/latest', 'Alpaca Markets. Free data plan available.'),
  ('market.get_quote', 'polygon-io',    '{byo}', 'api_key', 'GET /v2/last/trade/{symbol}',           'Polygon.io. Free tier: 5 API calls/min.'),
  ('market.get_quote', 'alpha-vantage', '{byo}', 'api_key', 'GET /query?function=GLOBAL_QUOTE',      'Alpha Vantage. Free tier: 25 req/day.'),
  ('market.get_quote', 'finnhub',       '{byo}', 'api_key', 'GET /quote',                            'Finnhub. Free tier: 60 calls/min.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- market.get_history
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('market.get_history', 'alpaca',        '{byo}', 'api_key', 'GET /v2/stocks/{symbol}/bars', 'Bars endpoint. Configurable timeframe.'),
  ('market.get_history', 'polygon-io',    '{byo}', 'api_key', 'GET /v2/aggs/ticker/{symbol}/range/{from}/{to}', 'Aggregates endpoint.'),
  ('market.get_history', 'alpha-vantage', '{byo}', 'api_key', 'GET /query?function=TIME_SERIES_DAILY', 'Daily OHLCV, 20+ years history.'),
  ('market.get_history', 'finnhub',       '{byo}', 'api_key', 'GET /stock/candle',            'OHLCV candles.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- market.search_symbols
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('market.search_symbols', 'polygon-io',    '{byo}', 'api_key', 'GET /v3/reference/tickers', 'Search all supported tickers.'),
  ('market.search_symbols', 'alpha-vantage', '{byo}', 'api_key', 'GET /query?function=SYMBOL_SEARCH', 'Keyword search for symbols.'),
  ('market.search_symbols', 'finnhub',       '{byo}', 'api_key', 'GET /search',               'Symbol + company name search.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- identity.verify
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('identity.verify', 'persona',   '{byo}', 'api_key', 'POST /api/v1/inquiries',       'Persona Identity. Hosted + API flows.'),
  ('identity.verify', 'onfido',    '{byo}', 'api_key', 'POST /v3.6/checks',            'Onfido. Document + biometric checks.'),
  ('identity.verify', 'jumio',     '{byo}', 'api_key', 'POST /api/v1/accounts',        'Jumio. Global ID verification.'),
  ('identity.verify', 'stripe-identity', '{byo}', 'api_key', 'POST /v1/identity/verification_sessions', 'Stripe Identity. Selfie + doc check.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- identity.check_document
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('identity.check_document', 'persona',  '{byo}', 'api_key', 'POST /api/v1/inquiries', 'Document scan + liveness check.'),
  ('identity.check_document', 'onfido',   '{byo}', 'api_key', 'POST /v3.6/documents',   'Document upload + extraction.'),
  ('identity.check_document', 'jumio',    '{byo}', 'api_key', 'POST /api/v1/accounts',  'Netverify document scanning.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- identity.lookup
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('identity.lookup', 'ekata',     '{byo}', 'api_key', 'GET /v2/identity_check', 'Phone + email + address risk signals.'),
  ('identity.lookup', 'data-axle', '{byo}', 'api_key', 'POST /v1/match',         'Consumer identity matching.'),
  ('identity.lookup', 'ipinfo',    '{byo,rhumb_managed}', 'bearer_token', 'GET /lite/{ip}', 'PROXY-CALLABLE — IP-based identity enrichment.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- ============================================================
-- Totals: 9 new capabilities, ~30 new mappings
-- Running total: ~237 capabilities, ~756 mappings
-- ============================================================

COMMIT;
