-- Migration 0074: Capability Expansion Day 30
-- Domains: incident, pos, gift_card, catalog
-- New capabilities: 10
-- New mappings: ~36
-- Cumulative target: ~351 capabilities / ~1219 mappings
-- Milestone: 350-capability target reached

-- ============================================================
-- DOMAIN: incident (Incident Management & On-Call)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('incident.create', 'incident.create', 'incident', 'Create a new incident or alert in an on-call management platform', '{"type":"object","required":["title","severity"],"properties":{"title":{"type":"string"},"severity":{"type":"string","enum":["critical","high","medium","low"]},"description":{"type":"string"},"service":{"type":"string"},"assignee":{"type":"string"},"source":{"type":"string"},"dedup_key":{"type":"string","description":"Deduplication key to prevent duplicate incidents"}}}', '{"type":"object","properties":{"incident_id":{"type":"string"},"status":{"type":"string"},"url":{"type":"string"},"assigned_to":{"type":"string"}}}'),
  ('incident.update', 'incident.update', 'incident', 'Update the status, severity, or assignee of an existing incident', '{"type":"object","required":["incident_id"],"properties":{"incident_id":{"type":"string"},"status":{"type":"string","enum":["acknowledged","investigating","identified","monitoring","resolved"]},"severity":{"type":"string"},"assignee":{"type":"string"},"note":{"type":"string"}}}', '{"type":"object","properties":{"incident_id":{"type":"string"},"status":{"type":"string"},"updated_at":{"type":"string"}}}'),
  ('incident.resolve', 'incident.resolve', 'incident', 'Mark an incident as resolved and optionally add a post-mortem note', '{"type":"object","required":["incident_id"],"properties":{"incident_id":{"type":"string"},"resolution_note":{"type":"string"},"dedup_key":{"type":"string"}}}', '{"type":"object","properties":{"incident_id":{"type":"string"},"resolved_at":{"type":"string"},"duration_sec":{"type":"integer"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- incident.create
  ('incident.create', 'pagerduty', 'byo', 0.005, 8.4, true),
  ('incident.create', 'opsgenie', 'byo', 0.004, 8.1, false),
  ('incident.create', 'grafana-oncall', 'byo', 0.003, 7.8, false),
  ('incident.create', 'victorops', 'byo', 0.005, 7.7, false),
  -- incident.update
  ('incident.update', 'pagerduty', 'byo', 0.004, 8.4, true),
  ('incident.update', 'opsgenie', 'byo', 0.003, 8.1, false),
  ('incident.update', 'grafana-oncall', 'byo', 0.002, 7.8, false),
  -- incident.resolve
  ('incident.resolve', 'pagerduty', 'byo', 0.004, 8.4, true),
  ('incident.resolve', 'opsgenie', 'byo', 0.003, 8.1, false),
  ('incident.resolve', 'grafana-oncall', 'byo', 0.002, 7.8, false),
  ('incident.resolve', 'victorops', 'byo', 0.004, 7.7, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: pos (Point of Sale)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('pos.charge', 'pos.charge', 'pos', 'Process a card-present payment at a point-of-sale terminal', '{"type":"object","required":["amount","currency","terminal_id"],"properties":{"amount":{"type":"integer","description":"Amount in smallest currency unit"},"currency":{"type":"string","default":"USD"},"terminal_id":{"type":"string"},"reference":{"type":"string"},"tip_amount":{"type":"integer"},"metadata":{"type":"object"}}}', '{"type":"object","properties":{"charge_id":{"type":"string"},"status":{"type":"string","enum":["succeeded","pending","failed"]},"receipt_url":{"type":"string"},"card_brand":{"type":"string"},"last4":{"type":"string"}}}'),
  ('pos.get_transaction', 'pos.get_transaction', 'pos', 'Retrieve details of a point-of-sale transaction by ID', '{"type":"object","required":["transaction_id"],"properties":{"transaction_id":{"type":"string"}}}', '{"type":"object","properties":{"transaction_id":{"type":"string"},"amount":{"type":"integer"},"status":{"type":"string"},"terminal_id":{"type":"string"},"created_at":{"type":"string"},"receipt_url":{"type":"string"}}}'),
  ('pos.refund', 'pos.refund', 'pos', 'Issue a full or partial refund for a point-of-sale transaction', '{"type":"object","required":["transaction_id"],"properties":{"transaction_id":{"type":"string"},"amount":{"type":"integer","description":"Partial refund amount; omit for full refund"},"reason":{"type":"string"}}}', '{"type":"object","properties":{"refund_id":{"type":"string"},"status":{"type":"string"},"amount":{"type":"integer"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- pos.charge
  ('pos.charge', 'square', 'byo', 0.005, 8.2, true),
  ('pos.charge', 'stripe-terminal', 'byo', 0.006, 8.3, false),
  ('pos.charge', 'shopify-pos', 'byo', 0.005, 7.9, false),
  -- pos.get_transaction
  ('pos.get_transaction', 'square', 'byo', 0.002, 8.2, true),
  ('pos.get_transaction', 'stripe-terminal', 'byo', 0.002, 8.3, false),
  ('pos.get_transaction', 'shopify-pos', 'byo', 0.002, 7.9, false),
  -- pos.refund
  ('pos.refund', 'square', 'byo', 0.004, 8.2, true),
  ('pos.refund', 'stripe-terminal', 'byo', 0.004, 8.3, false),
  ('pos.refund', 'shopify-pos', 'byo', 0.003, 7.9, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: gift_card (Gift Card Issuance & Redemption)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('gift_card.create', 'gift_card.create', 'gift_card', 'Issue a new gift card with a specified balance', '{"type":"object","required":["amount","currency"],"properties":{"amount":{"type":"integer","description":"Initial balance in smallest currency unit"},"currency":{"type":"string","default":"USD"},"recipient_email":{"type":"string"},"message":{"type":"string"},"expires_at":{"type":"string"}}}', '{"type":"object","properties":{"gift_card_id":{"type":"string"},"code":{"type":"string"},"balance":{"type":"integer"},"url":{"type":"string"}}}'),
  ('gift_card.get_balance', 'gift_card.get_balance', 'gift_card', 'Retrieve the remaining balance of a gift card by code or ID', '{"type":"object","required":["code"],"properties":{"code":{"type":"string"}}}', '{"type":"object","properties":{"gift_card_id":{"type":"string"},"balance":{"type":"integer"},"currency":{"type":"string"},"status":{"type":"string","enum":["active","redeemed","expired","disabled"]}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- gift_card.create
  ('gift_card.create', 'stripe', 'byo', 0.005, 8.3, true),
  ('gift_card.create', 'square', 'byo', 0.004, 8.0, false),
  ('gift_card.create', 'yift', 'byo', 0.006, 7.5, false),
  -- gift_card.get_balance
  ('gift_card.get_balance', 'stripe', 'byo', 0.002, 8.3, true),
  ('gift_card.get_balance', 'square', 'byo', 0.002, 8.0, false),
  ('gift_card.get_balance', 'yift', 'byo', 0.002, 7.5, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: catalog (Product Catalog Management)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('catalog.search_products', 'catalog.search_products', 'catalog', 'Search a product catalog by keyword, category, or attribute filters', '{"type":"object","required":["query"],"properties":{"query":{"type":"string"},"category":{"type":"string"},"attributes":{"type":"object","description":"Key-value attribute filters"},"price_min":{"type":"number"},"price_max":{"type":"number"},"limit":{"type":"integer","default":25}}}', '{"type":"object","properties":{"products":{"type":"array"},"total":{"type":"integer"}}}'),
  ('catalog.get_product', 'catalog.get_product', 'catalog', 'Retrieve full details for a specific product by ID or SKU', '{"type":"object","required":["product_id"],"properties":{"product_id":{"type":"string"},"sku":{"type":"string"}}}', '{"type":"object","properties":{"product_id":{"type":"string"},"title":{"type":"string"},"description":{"type":"string"},"price":{"type":"number"},"sku":{"type":"string"},"attributes":{"type":"object"},"images":{"type":"array"},"in_stock":{"type":"boolean"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- catalog.search_products
  ('catalog.search_products', 'shopify', 'byo', 0.002, 8.1, true),
  ('catalog.search_products', 'salsify', 'byo', 0.005, 7.8, false),
  ('catalog.search_products', 'akeneo', 'byo', 0.005, 7.7, false),
  ('catalog.search_products', 'commercetools', 'byo', 0.004, 8.0, false),
  -- catalog.get_product
  ('catalog.get_product', 'shopify', 'byo', 0.002, 8.1, true),
  ('catalog.get_product', 'salsify', 'byo', 0.003, 7.8, false),
  ('catalog.get_product', 'akeneo', 'byo', 0.003, 7.7, false),
  ('catalog.get_product', 'commercetools', 'byo', 0.003, 8.0, false)
ON CONFLICT (capability_id, provider) DO NOTHING;
