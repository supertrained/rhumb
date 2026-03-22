-- Migration 0070: Capability Expansion Day 26
-- Domains: wallet, ml, cdn, cdp
-- New capabilities: 10
-- New mappings: ~37
-- Cumulative target: ~311 capabilities / ~1073 mappings

-- ============================================================
-- DOMAIN: wallet (Digital Wallet & Funds Management)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('wallet.create', 'wallet.create', 'wallet', 'Create a digital wallet or stored-value account for a customer', '{"type":"object","required":["customer_id"],"properties":{"customer_id":{"type":"string"},"currency":{"type":"string","default":"USD"},"metadata":{"type":"object"}}}', '{"type":"object","properties":{"wallet_id":{"type":"string"},"balance":{"type":"number"},"currency":{"type":"string"},"status":{"type":"string"}}}'),
  ('wallet.get_balance', 'wallet.get_balance', 'wallet', 'Retrieve the current balance of a digital wallet', '{"type":"object","required":["wallet_id"],"properties":{"wallet_id":{"type":"string"}}}', '{"type":"object","properties":{"wallet_id":{"type":"string"},"balance":{"type":"number"},"currency":{"type":"string"},"pending":{"type":"number"},"updated_at":{"type":"string"}}}'),
  ('wallet.send', 'wallet.send', 'wallet', 'Transfer funds from a wallet to another wallet or external account', '{"type":"object","required":["from_wallet_id","amount"],"properties":{"from_wallet_id":{"type":"string"},"to_wallet_id":{"type":"string"},"to_account":{"type":"string"},"amount":{"type":"number"},"currency":{"type":"string","default":"USD"},"memo":{"type":"string"}}}', '{"type":"object","properties":{"transfer_id":{"type":"string"},"status":{"type":"string"},"new_balance":{"type":"number"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- wallet.create
  ('wallet.create', 'stripe', 'byo', 0.005, 8.4, true),
  ('wallet.create', 'marqeta', 'byo', 0.008, 8.0, false),
  ('wallet.create', 'circle', 'byo', 0.006, 7.8, false),
  -- wallet.get_balance
  ('wallet.get_balance', 'stripe', 'byo', 0.002, 8.4, true),
  ('wallet.get_balance', 'marqeta', 'byo', 0.003, 8.0, false),
  ('wallet.get_balance', 'circle', 'byo', 0.002, 7.8, false),
  ('wallet.get_balance', 'plaid', 'byo', 0.004, 7.9, false),
  -- wallet.send
  ('wallet.send', 'stripe', 'byo', 0.010, 8.4, true),
  ('wallet.send', 'marqeta', 'byo', 0.012, 8.0, false),
  ('wallet.send', 'circle', 'byo', 0.008, 7.8, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: ml (Machine Learning Inference)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('ml.predict', 'ml.predict', 'ml', 'Run inference on a deployed ML model with input features', '{"type":"object","required":["model_id","inputs"],"properties":{"model_id":{"type":"string"},"inputs":{"description":"Input features as object or array depending on model signature"},"version":{"type":"string"}}}', '{"type":"object","properties":{"predictions":{"description":"Model output predictions"},"model_id":{"type":"string"},"latency_ms":{"type":"integer"}}}'),
  ('ml.evaluate', 'ml.evaluate', 'ml', 'Evaluate a model against a labeled dataset and return metrics', '{"type":"object","required":["model_id","dataset_id"],"properties":{"model_id":{"type":"string"},"dataset_id":{"type":"string"},"metrics":{"type":"array","items":{"type":"string"},"default":["accuracy","f1","precision","recall"]}}}', '{"type":"object","properties":{"model_id":{"type":"string"},"metrics":{"type":"object"},"sample_count":{"type":"integer"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- ml.predict
  ('ml.predict', 'aws-sagemaker', 'byo', 0.010, 8.2, true),
  ('ml.predict', 'google-vertex', 'byo', 0.010, 8.1, false),
  ('ml.predict', 'huggingface', 'byo', 0.005, 7.8, false),
  ('ml.predict', 'replicate', 'byo', 0.008, 7.7, false),
  -- ml.evaluate
  ('ml.evaluate', 'aws-sagemaker', 'byo', 0.015, 8.2, true),
  ('ml.evaluate', 'google-vertex', 'byo', 0.015, 8.1, false),
  ('ml.evaluate', 'huggingface', 'byo', 0.010, 7.8, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: cdn (CDN & Edge Cache Management)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('cdn.purge', 'cdn.purge', 'cdn', 'Purge cached assets from a CDN edge by URL or tag', '{"type":"object","properties":{"urls":{"type":"array","items":{"type":"string"},"description":"Specific URLs to purge"},"tags":{"type":"array","items":{"type":"string"},"description":"Cache tags to purge"},"purge_everything":{"type":"boolean","default":false},"zone_id":{"type":"string"}}}', '{"type":"object","properties":{"purged":{"type":"integer"},"status":{"type":"string"},"estimated_ttl_sec":{"type":"integer"}}}'),
  ('cdn.get_stats', 'cdn.get_stats', 'cdn', 'Retrieve CDN traffic and cache hit rate analytics', '{"type":"object","properties":{"zone_id":{"type":"string"},"date_from":{"type":"string"},"date_to":{"type":"string"},"granularity":{"type":"string","enum":["hour","day","week"],"default":"day"}}}', '{"type":"object","properties":{"requests":{"type":"integer"},"bandwidth_gb":{"type":"number"},"cache_hit_rate":{"type":"number"},"top_paths":{"type":"array"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- cdn.purge
  ('cdn.purge', 'cloudflare', 'byo', 0.003, 8.5, true),
  ('cdn.purge', 'fastly', 'byo', 0.004, 8.2, false),
  ('cdn.purge', 'aws-cloudfront', 'byo', 0.005, 8.0, false),
  ('cdn.purge', 'bunny', 'byo', 0.002, 7.6, false),
  -- cdn.get_stats
  ('cdn.get_stats', 'cloudflare', 'byo', 0.003, 8.5, true),
  ('cdn.get_stats', 'fastly', 'byo', 0.003, 8.2, false),
  ('cdn.get_stats', 'aws-cloudfront', 'byo', 0.004, 8.0, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: cdp (Customer Data Platform)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('cdp.identify', 'cdp.identify', 'cdp', 'Identify and upsert a user profile in the customer data platform', '{"type":"object","required":["user_id"],"properties":{"user_id":{"type":"string"},"traits":{"type":"object","description":"User attributes, e.g. name, email, plan, company"},"anonymous_id":{"type":"string"}}}', '{"type":"object","properties":{"profile_id":{"type":"string"},"status":{"type":"string"}}}'),
  ('cdp.track', 'cdp.track', 'cdp', 'Track a named user event with properties for downstream destinations', '{"type":"object","required":["event","user_id"],"properties":{"event":{"type":"string"},"user_id":{"type":"string"},"properties":{"type":"object"},"timestamp":{"type":"string"},"anonymous_id":{"type":"string"}}}', '{"type":"object","properties":{"event_id":{"type":"string"},"status":{"type":"string"}}}'),
  ('cdp.get_profile', 'cdp.get_profile', 'cdp', 'Retrieve a unified customer profile with merged traits and event history', '{"type":"object","required":["user_id"],"properties":{"user_id":{"type":"string"},"include_events":{"type":"boolean","default":false},"event_limit":{"type":"integer","default":20}}}', '{"type":"object","properties":{"profile_id":{"type":"string"},"traits":{"type":"object"},"audiences":{"type":"array"},"last_seen":{"type":"string"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- cdp.identify
  ('cdp.identify', 'segment', 'byo', 0.002, 8.3, true),
  ('cdp.identify', 'rudderstack', 'byo', 0.002, 7.9, false),
  ('cdp.identify', 'mparticle', 'byo', 0.003, 7.8, false),
  ('cdp.identify', 'amplitude', 'byo', 0.002, 7.7, false),
  -- cdp.track
  ('cdp.track', 'segment', 'byo', 0.001, 8.3, true),
  ('cdp.track', 'rudderstack', 'byo', 0.001, 7.9, false),
  ('cdp.track', 'mparticle', 'byo', 0.002, 7.8, false),
  ('cdp.track', 'mixpanel', 'byo', 0.001, 7.7, false),
  -- cdp.get_profile
  ('cdp.get_profile', 'segment', 'byo', 0.004, 8.3, true),
  ('cdp.get_profile', 'rudderstack', 'byo', 0.003, 7.9, false),
  ('cdp.get_profile', 'mparticle', 'byo', 0.004, 7.8, false)
ON CONFLICT (capability_id, provider) DO NOTHING;
