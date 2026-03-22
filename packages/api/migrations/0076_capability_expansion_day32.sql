-- Migration 0076: Capability Expansion Day 32
-- Domains: fraud, video_conference, review, legal
-- New capabilities: 10
-- New mappings: ~38
-- Cumulative target: ~371 capabilities / ~1294 mappings

-- ============================================================
-- DOMAIN: fraud (Fraud Detection & Risk Scoring)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('fraud.score_transaction', 'fraud.score_transaction', 'fraud', 'Score a payment transaction for fraud risk before authorization', '{"type":"object","required":["transaction_id","amount","currency"],"properties":{"transaction_id":{"type":"string"},"amount":{"type":"integer","description":"Amount in smallest currency unit"},"currency":{"type":"string"},"user_id":{"type":"string"},"ip":{"type":"string"},"user_agent":{"type":"string"},"card_bin":{"type":"string"},"billing_country":{"type":"string"},"shipping_country":{"type":"string"}}}', '{"type":"object","properties":{"risk_score":{"type":"number","description":"0–100; higher is riskier"},"risk_level":{"type":"string","enum":["low","medium","high","critical"]},"signals":{"type":"array"},"recommendation":{"type":"string","enum":["allow","review","block"]}}}'),
  ('fraud.flag_user', 'fraud.flag_user', 'fraud', 'Flag a user account for suspected fraud or abuse', '{"type":"object","required":["user_id","reason"],"properties":{"user_id":{"type":"string"},"reason":{"type":"string"},"evidence":{"type":"object"},"action":{"type":"string","enum":["flag","suspend","block"],"default":"flag"}}}', '{"type":"object","properties":{"case_id":{"type":"string"},"status":{"type":"string"},"actioned_at":{"type":"string"}}}'),
  ('fraud.review', 'fraud.review', 'fraud', 'Retrieve fraud review queue items or the decision on a specific case', '{"type":"object","properties":{"case_id":{"type":"string"},"status":{"type":"string","enum":["pending","approved","declined"]},"limit":{"type":"integer","default":25}}}', '{"type":"object","properties":{"cases":{"type":"array"},"total":{"type":"integer"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- fraud.score_transaction
  ('fraud.score_transaction', 'signifyd', 'byo', 0.010, 8.2, true),
  ('fraud.score_transaction', 'stripe-radar', 'byo', 0.005, 8.3, false),
  ('fraud.score_transaction', 'kount', 'byo', 0.012, 8.0, false),
  ('fraud.score_transaction', 'sift', 'byo', 0.008, 8.1, false),
  -- fraud.flag_user
  ('fraud.flag_user', 'sift', 'byo', 0.006, 8.1, true),
  ('fraud.flag_user', 'signifyd', 'byo', 0.008, 8.2, false),
  ('fraud.flag_user', 'kount', 'byo', 0.009, 8.0, false),
  -- fraud.review
  ('fraud.review', 'signifyd', 'byo', 0.005, 8.2, true),
  ('fraud.review', 'sift', 'byo', 0.004, 8.1, false),
  ('fraud.review', 'kount', 'byo', 0.006, 8.0, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: video_conference (Video Meetings & Recordings)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('video_conference.create_meeting', 'video_conference.create_meeting', 'video_conference', 'Create a scheduled video meeting and return a join URL', '{"type":"object","required":["topic"],"properties":{"topic":{"type":"string"},"start_time":{"type":"string","description":"ISO8601; omit for instant meeting"},"duration_min":{"type":"integer","default":60},"host_email":{"type":"string"},"password":{"type":"string"},"waiting_room":{"type":"boolean","default":true},"recording":{"type":"boolean","default":false}}}', '{"type":"object","properties":{"meeting_id":{"type":"string"},"join_url":{"type":"string"},"host_url":{"type":"string"},"password":{"type":"string"},"start_time":{"type":"string"}}}'),
  ('video_conference.get_recording', 'video_conference.get_recording', 'video_conference', 'Retrieve the recording URL and metadata for a completed meeting', '{"type":"object","required":["meeting_id"],"properties":{"meeting_id":{"type":"string"}}}', '{"type":"object","properties":{"recording_id":{"type":"string"},"url":{"type":"string"},"duration_sec":{"type":"integer"},"file_size_mb":{"type":"number"},"expires_at":{"type":"string"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- video_conference.create_meeting
  ('video_conference.create_meeting', 'zoom', 'byo', 0.005, 8.3, true),
  ('video_conference.create_meeting', 'daily', 'byo', 0.004, 8.0, false),
  ('video_conference.create_meeting', 'google-meet', 'byo', 0.003, 7.8, false),
  ('video_conference.create_meeting', 'whereby', 'byo', 0.004, 7.7, false),
  -- video_conference.get_recording
  ('video_conference.get_recording', 'zoom', 'byo', 0.003, 8.3, true),
  ('video_conference.get_recording', 'daily', 'byo', 0.003, 8.0, false),
  ('video_conference.get_recording', 'google-meet', 'byo', 0.002, 7.8, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: review (Product & Business Review Collection)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('review.request', 'review.request', 'review', 'Send a review request to a customer after a purchase or interaction', '{"type":"object","required":["customer_email","product_id"],"properties":{"customer_email":{"type":"string"},"customer_name":{"type":"string"},"product_id":{"type":"string"},"product_name":{"type":"string"},"order_id":{"type":"string"},"delay_hours":{"type":"integer","default":24}}}', '{"type":"object","properties":{"request_id":{"type":"string"},"status":{"type":"string"},"scheduled_at":{"type":"string"}}}'),
  ('review.get_summary', 'review.get_summary', 'review', 'Get aggregated review stats and recent reviews for a product or business', '{"type":"object","required":["entity_id"],"properties":{"entity_id":{"type":"string"},"entity_type":{"type":"string","enum":["product","business","app"],"default":"product"},"limit":{"type":"integer","default":20}}}', '{"type":"object","properties":{"average_rating":{"type":"number"},"review_count":{"type":"integer"},"rating_distribution":{"type":"object"},"reviews":{"type":"array"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- review.request
  ('review.request', 'yotpo', 'byo', 0.004, 7.9, true),
  ('review.request', 'trustpilot', 'byo', 0.005, 8.0, false),
  ('review.request', 'bazaarvoice', 'byo', 0.006, 7.8, false),
  ('review.request', 'okendo', 'byo', 0.004, 7.7, false),
  -- review.get_summary
  ('review.get_summary', 'yotpo', 'byo', 0.003, 7.9, true),
  ('review.get_summary', 'trustpilot', 'byo', 0.004, 8.0, false),
  ('review.get_summary', 'bazaarvoice', 'byo', 0.004, 7.8, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: legal (Corporate & Sanctions Lookup)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('legal.search_entity', 'legal.search_entity', 'legal', 'Search for a company or legal entity by name or registration number', '{"type":"object","required":["query"],"properties":{"query":{"type":"string"},"country":{"type":"string","description":"ISO-3166 country code"},"entity_type":{"type":"string","enum":["company","person","organisation"]},"limit":{"type":"integer","default":10}}}', '{"type":"object","properties":{"entities":{"type":"array","items":{"type":"object","properties":{"name":{"type":"string"},"registration_number":{"type":"string"},"country":{"type":"string"},"status":{"type":"string"},"source":{"type":"string"}}}},"total":{"type":"integer"}}}'),
  ('legal.check_sanctions', 'legal.check_sanctions', 'legal', 'Screen a person or entity against global sanctions and watchlists', '{"type":"object","required":["name"],"properties":{"name":{"type":"string"},"dob":{"type":"string"},"country":{"type":"string"},"id_number":{"type":"string"},"lists":{"type":"array","description":"Specific sanction lists to check; omit for all"}}}', '{"type":"object","properties":{"screened":{"type":"boolean"},"matched":{"type":"boolean"},"matches":{"type":"array"},"risk_level":{"type":"string","enum":["clear","review","hit"]}}}'),
  ('legal.get_filings', 'legal.get_filings', 'legal', 'Retrieve regulatory filings or corporate documents for a legal entity', '{"type":"object","required":["entity_id"],"properties":{"entity_id":{"type":"string"},"filing_type":{"type":"string"},"limit":{"type":"integer","default":10}}}', '{"type":"object","properties":{"filings":{"type":"array"},"entity_name":{"type":"string"},"total":{"type":"integer"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- legal.search_entity
  ('legal.search_entity', 'opencorporates', 'byo', 0.005, 8.0, true),
  ('legal.search_entity', 'dnb', 'byo', 0.010, 8.1, false),
  ('legal.search_entity', 'gleif', 'byo', 0.003, 7.7, false),
  -- legal.check_sanctions
  ('legal.check_sanctions', 'complyadvantage', 'byo', 0.015, 8.3, true),
  ('legal.check_sanctions', 'refinitiv', 'byo', 0.020, 8.2, false),
  ('legal.check_sanctions', 'dowjones-riskscreening', 'byo', 0.018, 8.1, false),
  -- legal.get_filings
  ('legal.get_filings', 'opencorporates', 'byo', 0.006, 8.0, true),
  ('legal.get_filings', 'sec-edgar', 'byo', 0.002, 7.8, false),
  ('legal.get_filings', 'dnb', 'byo', 0.008, 8.1, false)
ON CONFLICT (capability_id, provider) DO NOTHING;
