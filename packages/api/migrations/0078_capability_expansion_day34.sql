-- Migration 0078: Capability Expansion Day 34
-- Domains: affiliate, news, data_warehouse, certificate
-- New capabilities: 10
-- New mappings: ~37
-- Cumulative target: ~391 capabilities / ~1368 mappings

-- ============================================================
-- DOMAIN: affiliate (Affiliate & Partner Program Management)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('affiliate.create_link', 'affiliate.create_link', 'affiliate', 'Generate a trackable affiliate referral link for a partner', '{"type":"object","required":["partner_id","destination_url"],"properties":{"partner_id":{"type":"string"},"destination_url":{"type":"string"},"campaign":{"type":"string"},"sub_id":{"type":"string","description":"Custom tracking sub-ID"},"expires_at":{"type":"string"}}}', '{"type":"object","properties":{"link_id":{"type":"string"},"tracking_url":{"type":"string"},"short_url":{"type":"string"}}}'),
  ('affiliate.get_stats', 'affiliate.get_stats', 'affiliate', 'Retrieve clicks, conversions, and revenue attribution for an affiliate partner', '{"type":"object","required":["partner_id"],"properties":{"partner_id":{"type":"string"},"date_from":{"type":"string"},"date_to":{"type":"string"},"campaign":{"type":"string"}}}', '{"type":"object","properties":{"clicks":{"type":"integer"},"conversions":{"type":"integer"},"revenue":{"type":"number"},"conversion_rate":{"type":"number"},"currency":{"type":"string"}}}'),
  ('affiliate.get_commissions', 'affiliate.get_commissions', 'affiliate', 'List pending or paid commission payouts for an affiliate partner', '{"type":"object","required":["partner_id"],"properties":{"partner_id":{"type":"string"},"status":{"type":"string","enum":["pending","approved","paid","rejected"]},"limit":{"type":"integer","default":25}}}', '{"type":"object","properties":{"commissions":{"type":"array"},"total_pending":{"type":"number"},"total_paid":{"type":"number"},"currency":{"type":"string"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- affiliate.create_link
  ('affiliate.create_link', 'impact', 'byo', 0.004, 8.2, true),
  ('affiliate.create_link', 'partnerstack', 'byo', 0.004, 8.0, false),
  ('affiliate.create_link', 'rewardful', 'byo', 0.003, 7.7, false),
  ('affiliate.create_link', 'shareasale', 'byo', 0.004, 7.5, false),
  -- affiliate.get_stats
  ('affiliate.get_stats', 'impact', 'byo', 0.005, 8.2, true),
  ('affiliate.get_stats', 'partnerstack', 'byo', 0.005, 8.0, false),
  ('affiliate.get_stats', 'rewardful', 'byo', 0.003, 7.7, false),
  -- affiliate.get_commissions
  ('affiliate.get_commissions', 'impact', 'byo', 0.004, 8.2, true),
  ('affiliate.get_commissions', 'partnerstack', 'byo', 0.004, 8.0, false),
  ('affiliate.get_commissions', 'rewardful', 'byo', 0.003, 7.7, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: news (News Search & Headlines)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('news.search', 'news.search', 'news', 'Search news articles by keyword, topic, or source', '{"type":"object","required":["query"],"properties":{"query":{"type":"string"},"sources":{"type":"array"},"language":{"type":"string","default":"en"},"date_from":{"type":"string"},"date_to":{"type":"string"},"sort_by":{"type":"string","enum":["relevancy","popularity","publishedAt"],"default":"relevancy"},"limit":{"type":"integer","default":20}}}', '{"type":"object","properties":{"articles":{"type":"array"},"total":{"type":"integer"}}}'),
  ('news.get_headlines', 'news.get_headlines', 'news', 'Retrieve top headlines for a country, category, or source', '{"type":"object","properties":{"country":{"type":"string","description":"ISO-3166 2-letter code"},"category":{"type":"string","enum":["business","entertainment","health","science","sports","technology","general"]},"source":{"type":"string"},"limit":{"type":"integer","default":10}}}', '{"type":"object","properties":{"articles":{"type":"array"},"total":{"type":"integer"},"fetched_at":{"type":"string"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- news.search
  ('news.search', 'newsapi', 'byo', 0.004, 8.0, true),
  ('news.search', 'bing-news', 'byo', 0.005, 7.9, false),
  ('news.search', 'guardian', 'byo', 0.002, 7.7, false),
  ('news.search', 'nyt', 'byo', 0.003, 7.8, false),
  -- news.get_headlines
  ('news.get_headlines', 'newsapi', 'byo', 0.003, 8.0, true),
  ('news.get_headlines', 'bing-news', 'byo', 0.004, 7.9, false),
  ('news.get_headlines', 'guardian', 'byo', 0.002, 7.7, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: data_warehouse (Analytical Query & Job Execution)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('data_warehouse.query', 'data_warehouse.query', 'data_warehouse', 'Execute an analytical SQL query against a data warehouse', '{"type":"object","required":["connection_id","sql"],"properties":{"connection_id":{"type":"string"},"sql":{"type":"string"},"params":{"type":"array"},"max_bytes_billed":{"type":"integer"},"timeout_sec":{"type":"integer","default":120}}}', '{"type":"object","properties":{"rows":{"type":"array"},"row_count":{"type":"integer"},"bytes_processed":{"type":"integer"},"cost_usd":{"type":"number"},"duration_ms":{"type":"integer"}}}'),
  ('data_warehouse.run_job', 'data_warehouse.run_job', 'data_warehouse', 'Submit an async transformation or export job and return a job handle', '{"type":"object","required":["connection_id","job_type","config"],"properties":{"connection_id":{"type":"string"},"job_type":{"type":"string","enum":["transform","export","copy"]},"config":{"type":"object"},"schedule":{"type":"string","description":"Cron expression for recurring jobs"}}}', '{"type":"object","properties":{"job_id":{"type":"string"},"status":{"type":"string","enum":["queued","running","succeeded","failed"]},"started_at":{"type":"string"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- data_warehouse.query
  ('data_warehouse.query', 'bigquery', 'byo', 0.010, 8.4, true),
  ('data_warehouse.query', 'snowflake', 'byo', 0.012, 8.3, false),
  ('data_warehouse.query', 'redshift', 'byo', 0.010, 8.1, false),
  ('data_warehouse.query', 'databricks', 'byo', 0.015, 8.2, false),
  -- data_warehouse.run_job
  ('data_warehouse.run_job', 'bigquery', 'byo', 0.015, 8.4, true),
  ('data_warehouse.run_job', 'snowflake', 'byo', 0.018, 8.3, false),
  ('data_warehouse.run_job', 'databricks', 'byo', 0.020, 8.2, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: certificate (TLS/SSL Certificate Lifecycle)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('certificate.issue', 'certificate.issue', 'certificate', 'Issue or renew a TLS/SSL certificate for one or more domains', '{"type":"object","required":["domains"],"properties":{"domains":{"type":"array","items":{"type":"string"}},"validation_method":{"type":"string","enum":["dns","http","email"],"default":"dns"},"certificate_type":{"type":"string","enum":["dv","ov","ev"],"default":"dv"},"validity_days":{"type":"integer","default":90}}}', '{"type":"object","properties":{"certificate_id":{"type":"string"},"status":{"type":"string","enum":["pending_validation","issued","failed"]},"expires_at":{"type":"string"},"pem":{"type":"string","description":"PEM-encoded certificate when status is issued"}}}'),
  ('certificate.get_status', 'certificate.get_status', 'certificate', 'Check the current status and expiry of an issued certificate', '{"type":"object","required":["certificate_id"],"properties":{"certificate_id":{"type":"string"},"domain":{"type":"string"}}}', '{"type":"object","properties":{"certificate_id":{"type":"string"},"status":{"type":"string"},"domains":{"type":"array"},"issued_at":{"type":"string"},"expires_at":{"type":"string"},"days_remaining":{"type":"integer"}}}'),
  ('certificate.revoke', 'certificate.revoke', 'certificate', 'Revoke an issued TLS/SSL certificate', '{"type":"object","required":["certificate_id"],"properties":{"certificate_id":{"type":"string"},"reason":{"type":"string","enum":["key_compromise","ca_compromise","affiliation_changed","superseded","cessation_of_operation","unspecified"],"default":"unspecified"}}}', '{"type":"object","properties":{"certificate_id":{"type":"string"},"revoked_at":{"type":"string"},"status":{"type":"string"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- certificate.issue
  ('certificate.issue', 'digicert', 'byo', 0.020, 8.3, true),
  ('certificate.issue', 'aws-acm', 'byo', 0.005, 8.2, false),
  ('certificate.issue', 'sectigo', 'byo', 0.015, 8.0, false),
  ('certificate.issue', 'zerossl', 'byo', 0.005, 7.7, false),
  -- certificate.get_status
  ('certificate.get_status', 'digicert', 'byo', 0.005, 8.3, true),
  ('certificate.get_status', 'aws-acm', 'byo', 0.002, 8.2, false),
  ('certificate.get_status', 'sectigo', 'byo', 0.004, 8.0, false),
  -- certificate.revoke
  ('certificate.revoke', 'digicert', 'byo', 0.010, 8.3, true),
  ('certificate.revoke', 'aws-acm', 'byo', 0.004, 8.2, false),
  ('certificate.revoke', 'zerossl', 'byo', 0.003, 7.7, false)
ON CONFLICT (capability_id, provider) DO NOTHING;
