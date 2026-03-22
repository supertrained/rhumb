-- Migration 0063: Capability expansion Day 19
-- 10 new capabilities across 4 domains: shipping, receipt, agent, network
-- Continues cadence toward 250+ capabilities

BEGIN;

-- ============================================================
-- NEW CAPABILITIES
-- ============================================================
INSERT INTO capabilities (id, domain, description, status) VALUES
  -- Shipping / logistics (3)
  ('shipping.track',          'shipping', 'Track a package by carrier and tracking number',         'active'),
  ('shipping.get_rates',      'shipping', 'Get shipping rates for a given package and destination', 'active'),
  ('shipping.create_label',   'shipping', 'Purchase and generate a shipping label',                 'active'),
  -- Receipt / invoice parsing (2)
  ('receipt.parse',           'receipt',  'Extract line items, totals, and metadata from a receipt or invoice', 'active'),
  ('receipt.extract_data',    'receipt',  'Extract structured data fields from a scanned document',            'active'),
  -- Agent / orchestration meta-capabilities (3)
  ('agent.spawn',             'agent',    'Create and start a new autonomous agent run',            'active'),
  ('agent.get_status',        'agent',    'Check the status or output of a running agent',          'active'),
  ('agent.send_message',      'agent',    'Send a message or instruction to an active agent',       'active'),
  -- Network / DNS utilities (2)
  ('network.dns_lookup',      'network',  'Resolve a domain to IP addresses (A/AAAA/MX/TXT)',       'active'),
  ('network.whois',           'network',  'Look up WHOIS registration data for a domain or IP',     'active')
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- PROVIDER MAPPINGS
-- ============================================================

-- shipping.track
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('shipping.track', 'easypost',    '{byo}', 'api_key', 'GET /v2/trackers/{id}',                          'EasyPost: 70+ carriers. Free tier available.'),
  ('shipping.track', 'shippo',      '{byo}', 'api_key', 'GET /v1/tracks/{carrier}/{tracking_number}',     'Shippo: 85+ carriers. Pay-per-label.'),
  ('shipping.track', 'aftership',   '{byo}', 'api_key', 'GET /v4/trackings/{slug}/{tracking_number}',     'AfterShip: 900+ carriers. 100 trackings/mo free.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- shipping.get_rates
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('shipping.get_rates', 'easypost',     '{byo}', 'api_key', 'POST /v2/shipments',                    'Returns rates from multiple carriers in one call.'),
  ('shipping.get_rates', 'shippo',       '{byo}', 'api_key', 'POST /v1/shipments',                    'Shippo multi-carrier rate quotes.'),
  ('shipping.get_rates', 'shipstation',  '{byo}', 'api_key', 'POST /shipments/getrates',              'ShipStation rate quotes. Free tier: 50 shipments/mo.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- shipping.create_label
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('shipping.create_label', 'easypost',  '{byo}', 'api_key', 'POST /v2/shipments/{id}/buy',           'Purchase label from selected rate.'),
  ('shipping.create_label', 'shippo',    '{byo}', 'api_key', 'POST /v1/transactions',                 'Buy label; returns PDF/ZPL.'),
  ('shipping.create_label', 'shipstation','{byo}','api_key', 'POST /orders/createlabelfororder',      'Create label for existing order.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- receipt.parse
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('receipt.parse', 'mindee',       '{byo}', 'api_key', 'POST /v1/products/mindee/expense_receipts/v5/predict', 'Mindee: receipt parser. 250 pages/mo free.'),
  ('receipt.parse', 'veryfi',       '{byo}', 'api_key', 'POST /api/v8/partner/{client_id}/documents/',           'Veryfi: line-item extraction. 100 docs/mo free.'),
  ('receipt.parse', 'unstructured', '{byo,rhumb_managed}', 'api_key', 'POST /general/v0/general',    'PROXY-CALLABLE — live Unstructured credential. General document parsing.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- receipt.extract_data
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('receipt.extract_data', 'mindee',       '{byo}', 'api_key', 'POST /v1/products/mindee/financial_document/v1/predict', 'Financial document extraction.'),
  ('receipt.extract_data', 'aws-textract', '{byo}', 'api_key', 'DetectDocumentText / AnalyzeExpense (AWS SDK)',           'AWS Textract: 1K pages/mo free 3 months.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- agent.spawn
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('agent.spawn', 'e2b',        '{byo,rhumb_managed}', 'api_key', 'POST /sandboxes',       'PROXY-CALLABLE — live E2B credential. Spawn a code sandbox as an agent execution env.'),
  ('agent.spawn', 'modal',      '{byo}', 'api_key', 'POST /v1/runs',                       'Modal: serverless GPU/CPU function runs.'),
  ('agent.spawn', 'inngest',    '{byo}', 'api_key', 'POST /e/{event_key}',                 'Inngest: event-driven durable functions.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- agent.get_status
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('agent.get_status', 'e2b',    '{byo,rhumb_managed}', 'api_key', 'GET /sandboxes/{id}',  'PROXY-CALLABLE — live E2B credential.'),
  ('agent.get_status', 'modal',  '{byo}', 'api_key', 'GET /v1/runs/{id}',                  'Check run status and output.'),
  ('agent.get_status', 'inngest','{byo}', 'api_key', 'GET /v1/runs/{run_id}',              'Poll run state.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- agent.send_message
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('agent.send_message', 'inngest', '{byo}', 'api_key', 'POST /e/{event_key}',             'Send an event to a running workflow step.'),
  ('agent.send_message', 'temporal','{byo}', 'api_key', 'POST /api/v1/namespaces/{ns}/workflows/{id}/signal', 'Send signal to active Temporal workflow.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- network.dns_lookup
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('network.dns_lookup', 'cloudflare',  '{byo}', 'api_key', 'GET /client/v4/zones/{id}/dns_records',     'Cloudflare DNS records API.'),
  ('network.dns_lookup', 'google-dns',  '{byo}', 'api_key', 'GET /resolve?name={host}&type={type}',      'Google DNS-over-HTTPS. No auth required.'),
  ('network.dns_lookup', 'ipinfo',      '{byo,rhumb_managed}', 'bearer_token', 'GET /{ip}/json',         'PROXY-CALLABLE — live IPinfo credential. Reverse DNS + PTR via IP lookup.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- network.whois
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('network.whois', 'whoisxml',  '{byo}', 'api_key', 'GET /whoisserver/WhoisService?domainName={d}', 'WhoisXML: 500 queries/mo free.'),
  ('network.whois', 'ipinfo',    '{byo,rhumb_managed}', 'bearer_token', 'GET /{ip}/json',             'PROXY-CALLABLE — live IPinfo credential. ASN + org for IP-based WHOIS.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- ============================================================
-- Totals: 10 new capabilities, ~32 new provider mappings
-- Running total: ~241 capabilities, ~821 mappings
-- ============================================================

COMMIT;
