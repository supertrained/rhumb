-- Migration 0067: Capability Expansion Day 23
-- Domains: contract, inventory, compliance, referral
-- New capabilities: 10
-- New mappings: ~36
-- Cumulative target: ~281 capabilities / ~963 mappings

-- ============================================================
-- DOMAIN: contract (Contract & Document Signing)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('contract.create', 'contract.create', 'contract', 'Create a contract or agreement document from a template or raw content', '{"type":"object","required":["title"],"properties":{"title":{"type":"string"},"template_id":{"type":"string"},"fields":{"type":"object","description":"Template field values"},"content":{"type":"string","description":"Raw document content (HTML or markdown) if no template"}}}', '{"type":"object","properties":{"contract_id":{"type":"string"},"status":{"type":"string"},"edit_url":{"type":"string"}}}'),
  ('contract.send', 'contract.send', 'contract', 'Send a contract to one or more signers for electronic signature', '{"type":"object","required":["contract_id","signers"],"properties":{"contract_id":{"type":"string"},"signers":{"type":"array","items":{"type":"object","required":["email","name"],"properties":{"email":{"type":"string"},"name":{"type":"string"},"role":{"type":"string"}}}},"message":{"type":"string"},"expiry_days":{"type":"integer","default":30}}}', '{"type":"object","properties":{"envelope_id":{"type":"string"},"status":{"type":"string"},"signing_urls":{"type":"array"}}}'),
  ('contract.get_status', 'contract.get_status', 'contract', 'Get the current status and signer completion state of a contract', '{"type":"object","required":["contract_id"],"properties":{"contract_id":{"type":"string"}}}', '{"type":"object","properties":{"contract_id":{"type":"string"},"status":{"type":"string","enum":["draft","sent","partially_signed","completed","declined","expired"]},"signers":{"type":"array"},"completed_at":{"type":"string"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- contract.create
  ('contract.create', 'docusign', 'byo', 0.010, 8.3, true),
  ('contract.create', 'pandadoc', 'byo', 0.008, 8.0, false),
  ('contract.create', 'hellosign', 'byo', 0.007, 7.8, false),
  ('contract.create', 'dropbox-sign', 'byo', 0.007, 7.8, false),
  -- contract.send
  ('contract.send', 'docusign', 'byo', 0.015, 8.3, true),
  ('contract.send', 'pandadoc', 'byo', 0.012, 8.0, false),
  ('contract.send', 'hellosign', 'byo', 0.010, 7.8, false),
  ('contract.send', 'dropbox-sign', 'byo', 0.010, 7.8, false),
  -- contract.get_status
  ('contract.get_status', 'docusign', 'byo', 0.003, 8.3, true),
  ('contract.get_status', 'pandadoc', 'byo', 0.003, 8.0, false),
  ('contract.get_status', 'hellosign', 'byo', 0.002, 7.8, false),
  ('contract.get_status', 'dropbox-sign', 'byo', 0.002, 7.8, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: inventory (Inventory & Stock Management)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('inventory.check_stock', 'inventory.check_stock', 'inventory', 'Check current stock levels for one or more SKUs', '{"type":"object","required":["skus"],"properties":{"skus":{"type":"array","items":{"type":"string"}},"location_id":{"type":"string"}}}', '{"type":"object","properties":{"items":{"type":"array","items":{"type":"object","properties":{"sku":{"type":"string"},"quantity":{"type":"integer"},"location":{"type":"string"},"available":{"type":"boolean"}}}}}}'),
  ('inventory.update_quantity', 'inventory.update_quantity', 'inventory', 'Update the quantity of a specific SKU at a location', '{"type":"object","required":["sku","quantity"],"properties":{"sku":{"type":"string"},"quantity":{"type":"integer"},"location_id":{"type":"string"},"reason":{"type":"string","enum":["received","sold","adjustment","returned"]}}}', '{"type":"object","properties":{"sku":{"type":"string"},"new_quantity":{"type":"integer"},"updated_at":{"type":"string"}}}'),
  ('inventory.reserve', 'inventory.reserve', 'inventory', 'Reserve stock for a pending order to prevent overselling', '{"type":"object","required":["sku","quantity","order_id"],"properties":{"sku":{"type":"string"},"quantity":{"type":"integer"},"order_id":{"type":"string"},"ttl_seconds":{"type":"integer","default":900}}}', '{"type":"object","properties":{"reservation_id":{"type":"string"},"reserved_quantity":{"type":"integer"},"expires_at":{"type":"string"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- inventory.check_stock
  ('inventory.check_stock', 'shopify', 'byo', 0.002, 8.0, true),
  ('inventory.check_stock', 'square', 'byo', 0.002, 7.7, false),
  ('inventory.check_stock', 'lightspeed', 'byo', 0.002, 7.4, false),
  ('inventory.check_stock', 'cin7', 'byo', 0.003, 7.2, false),
  -- inventory.update_quantity
  ('inventory.update_quantity', 'shopify', 'byo', 0.003, 8.0, true),
  ('inventory.update_quantity', 'square', 'byo', 0.003, 7.7, false),
  ('inventory.update_quantity', 'cin7', 'byo', 0.003, 7.2, false),
  -- inventory.reserve
  ('inventory.reserve', 'shopify', 'byo', 0.004, 8.0, true),
  ('inventory.reserve', 'square', 'byo', 0.003, 7.7, false),
  ('inventory.reserve', 'lightspeed', 'byo', 0.003, 7.4, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: compliance (Compliance Monitoring & Reporting)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('compliance.check', 'compliance.check', 'compliance', 'Run a compliance check against a framework (SOC2, ISO27001, GDPR, HIPAA)', '{"type":"object","required":["framework"],"properties":{"framework":{"type":"string","enum":["soc2","iso27001","gdpr","hipaa","pci-dss"]},"scope":{"type":"string"}}}', '{"type":"object","properties":{"framework":{"type":"string"},"status":{"type":"string","enum":["compliant","non_compliant","in_progress"]},"passing":{"type":"integer"},"failing":{"type":"integer"},"controls":{"type":"array"}}}'),
  ('compliance.generate_report', 'compliance.generate_report', 'compliance', 'Generate a compliance evidence report for auditors or stakeholders', '{"type":"object","required":["framework"],"properties":{"framework":{"type":"string"},"period_start":{"type":"string"},"period_end":{"type":"string"},"format":{"type":"string","enum":["pdf","json"],"default":"pdf"}}}', '{"type":"object","properties":{"report_id":{"type":"string"},"url":{"type":"string"},"generated_at":{"type":"string"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- compliance.check
  ('compliance.check', 'vanta', 'byo', 0.020, 8.1, true),
  ('compliance.check', 'drata', 'byo', 0.020, 8.0, false),
  ('compliance.check', 'secureframe', 'byo', 0.018, 7.7, false),
  ('compliance.check', 'sprinto', 'byo', 0.015, 7.4, false),
  -- compliance.generate_report
  ('compliance.generate_report', 'vanta', 'byo', 0.030, 8.1, true),
  ('compliance.generate_report', 'drata', 'byo', 0.030, 8.0, false),
  ('compliance.generate_report', 'secureframe', 'byo', 0.025, 7.7, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: referral (Referral & Affiliate Tracking)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('referral.create_link', 'referral.create_link', 'referral', 'Create a unique referral or affiliate tracking link for a participant', '{"type":"object","required":["participant_id"],"properties":{"participant_id":{"type":"string"},"campaign_id":{"type":"string"},"custom_slug":{"type":"string"},"metadata":{"type":"object"}}}', '{"type":"object","properties":{"link_id":{"type":"string"},"url":{"type":"string"},"participant_id":{"type":"string"}}}'),
  ('referral.get_stats', 'referral.get_stats', 'referral', 'Get conversion and reward stats for a referral participant or campaign', '{"type":"object","properties":{"participant_id":{"type":"string"},"campaign_id":{"type":"string"},"date_from":{"type":"string"},"date_to":{"type":"string"}}}', '{"type":"object","properties":{"clicks":{"type":"integer"},"conversions":{"type":"integer"},"pending_rewards":{"type":"number"},"paid_rewards":{"type":"number"},"conversion_rate":{"type":"number"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- referral.create_link
  ('referral.create_link', 'rewardful', 'byo', 0.003, 7.7, true),
  ('referral.create_link', 'partnerstack', 'byo', 0.004, 7.8, false),
  ('referral.create_link', 'tapfiliate', 'byo', 0.003, 7.4, false),
  ('referral.create_link', 'referralhero', 'byo', 0.003, 7.2, false),
  -- referral.get_stats
  ('referral.get_stats', 'rewardful', 'byo', 0.002, 7.7, true),
  ('referral.get_stats', 'partnerstack', 'byo', 0.003, 7.8, false),
  ('referral.get_stats', 'tapfiliate', 'byo', 0.002, 7.4, false)
ON CONFLICT (capability_id, provider) DO NOTHING;
