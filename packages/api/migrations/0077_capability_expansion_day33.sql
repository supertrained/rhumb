-- Migration 0077: Capability Expansion Day 33
-- Domains: lead, quote, waitlist, social_listening
-- New capabilities: 10
-- New mappings: ~37
-- Cumulative target: ~381 capabilities / ~1331 mappings

-- ============================================================
-- DOMAIN: lead (Lead Management & Scoring)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('lead.create', 'lead.create', 'lead', 'Create a new sales lead in a CRM or marketing automation platform', '{"type":"object","required":["email"],"properties":{"email":{"type":"string"},"first_name":{"type":"string"},"last_name":{"type":"string"},"company":{"type":"string"},"title":{"type":"string"},"phone":{"type":"string"},"source":{"type":"string"},"utm_campaign":{"type":"string"},"metadata":{"type":"object"}}}', '{"type":"object","properties":{"lead_id":{"type":"string"},"status":{"type":"string"},"created_at":{"type":"string"}}}'),
  ('lead.score', 'lead.score', 'lead', 'Score a lead based on firmographic and behavioral signals', '{"type":"object","required":["lead_id"],"properties":{"lead_id":{"type":"string"},"email":{"type":"string"},"company_domain":{"type":"string"},"page_views":{"type":"integer"},"events":{"type":"array"}}}', '{"type":"object","properties":{"lead_id":{"type":"string"},"score":{"type":"integer","description":"0–100"},"tier":{"type":"string","enum":["hot","warm","cold"]},"signals":{"type":"array"}}}'),
  ('lead.assign', 'lead.assign', 'lead', 'Assign a lead to a sales representative or round-robin queue', '{"type":"object","required":["lead_id"],"properties":{"lead_id":{"type":"string"},"assignee_id":{"type":"string"},"queue":{"type":"string","description":"Named round-robin queue; overrides assignee_id"},"notify":{"type":"boolean","default":true}}}', '{"type":"object","properties":{"lead_id":{"type":"string"},"assigned_to":{"type":"string"},"assigned_at":{"type":"string"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- lead.create
  ('lead.create', 'hubspot', 'byo', 0.003, 8.2, true),
  ('lead.create', 'salesforce', 'byo', 0.004, 8.3, false),
  ('lead.create', 'marketo', 'byo', 0.005, 7.9, false),
  ('lead.create', 'pardot', 'byo', 0.004, 7.8, false),
  -- lead.score
  ('lead.score', 'madkudu', 'byo', 0.010, 8.0, true),
  ('lead.score', 'hubspot', 'byo', 0.004, 8.2, false),
  ('lead.score', 'clearbit', 'byo', 0.008, 7.9, false),
  -- lead.assign
  ('lead.assign', 'hubspot', 'byo', 0.003, 8.2, true),
  ('lead.assign', 'salesforce', 'byo', 0.003, 8.3, false),
  ('lead.assign', 'pipedrive', 'byo', 0.003, 7.9, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: quote (CPQ & Sales Quote Generation)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('quote.create', 'quote.create', 'quote', 'Generate a sales quote or proposal document for a prospect', '{"type":"object","required":["recipient_email","line_items"],"properties":{"recipient_email":{"type":"string"},"recipient_name":{"type":"string"},"company":{"type":"string"},"line_items":{"type":"array","items":{"type":"object","required":["name","price"],"properties":{"name":{"type":"string"},"description":{"type":"string"},"quantity":{"type":"integer","default":1},"price":{"type":"number"},"discount":{"type":"number"}}}},"currency":{"type":"string","default":"USD"},"expires_at":{"type":"string"},"notes":{"type":"string"}}}', '{"type":"object","properties":{"quote_id":{"type":"string"},"total":{"type":"number"},"status":{"type":"string"},"edit_url":{"type":"string"}}}'),
  ('quote.send', 'quote.send', 'quote', 'Send a quote to the recipient for review and electronic acceptance', '{"type":"object","required":["quote_id"],"properties":{"quote_id":{"type":"string"},"message":{"type":"string"},"cc":{"type":"array"}}}', '{"type":"object","properties":{"quote_id":{"type":"string"},"sent_at":{"type":"string"},"view_url":{"type":"string"}}}'),
  ('quote.get_status', 'quote.get_status', 'quote', 'Get the current status of a quote (viewed, accepted, declined, expired)', '{"type":"object","required":["quote_id"],"properties":{"quote_id":{"type":"string"}}}', '{"type":"object","properties":{"quote_id":{"type":"string"},"status":{"type":"string","enum":["draft","sent","viewed","accepted","declined","expired"]},"viewed_at":{"type":"string"},"accepted_at":{"type":"string"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- quote.create
  ('quote.create', 'pandadoc', 'byo', 0.010, 8.1, true),
  ('quote.create', 'hubspot-quotes', 'byo', 0.006, 8.0, false),
  ('quote.create', 'proposify', 'byo', 0.009, 7.8, false),
  ('quote.create', 'better-proposals', 'byo', 0.007, 7.6, false),
  -- quote.send
  ('quote.send', 'pandadoc', 'byo', 0.005, 8.1, true),
  ('quote.send', 'hubspot-quotes', 'byo', 0.004, 8.0, false),
  ('quote.send', 'proposify', 'byo', 0.005, 7.8, false),
  -- quote.get_status
  ('quote.get_status', 'pandadoc', 'byo', 0.003, 8.1, true),
  ('quote.get_status', 'hubspot-quotes', 'byo', 0.002, 8.0, false),
  ('quote.get_status', 'proposify', 'byo', 0.003, 7.8, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: waitlist (Waitlist & Early Access Management)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('waitlist.join', 'waitlist.join', 'waitlist', 'Add a user to a waitlist and return their position', '{"type":"object","required":["email"],"properties":{"email":{"type":"string"},"name":{"type":"string"},"referral_code":{"type":"string"},"metadata":{"type":"object"}}}', '{"type":"object","properties":{"entry_id":{"type":"string"},"position":{"type":"integer"},"referral_link":{"type":"string"},"status":{"type":"string","enum":["pending","approved"]}}}'),
  ('waitlist.get_position', 'waitlist.get_position', 'waitlist', 'Get a waitlist member\'s current position and referral stats', '{"type":"object","required":["email"],"properties":{"email":{"type":"string"}}}', '{"type":"object","properties":{"entry_id":{"type":"string"},"position":{"type":"integer"},"referrals":{"type":"integer"},"status":{"type":"string"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- waitlist.join
  ('waitlist.join', 'waitlistapi', 'byo', 0.002, 7.6, true),
  ('waitlist.join', 'getwaitlist', 'byo', 0.002, 7.5, false),
  ('waitlist.join', 'prefinery', 'byo', 0.003, 7.4, false),
  -- waitlist.get_position
  ('waitlist.get_position', 'waitlistapi', 'byo', 0.001, 7.6, true),
  ('waitlist.get_position', 'getwaitlist', 'byo', 0.001, 7.5, false),
  ('waitlist.get_position', 'prefinery', 'byo', 0.002, 7.4, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: social_listening (Brand Monitoring & Mention Tracking)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('social_listening.search_mentions', 'social_listening.search_mentions', 'social_listening', 'Search for brand mentions, keywords, or hashtags across social and web sources', '{"type":"object","required":["query"],"properties":{"query":{"type":"string"},"sources":{"type":"array","items":{"type":"string","enum":["twitter","reddit","news","blogs","forums","all"]},"default":["all"]},"sentiment":{"type":"string","enum":["positive","negative","neutral"]},"date_from":{"type":"string"},"date_to":{"type":"string"},"limit":{"type":"integer","default":25}}}', '{"type":"object","properties":{"mentions":{"type":"array"},"total":{"type":"integer"},"sentiment_breakdown":{"type":"object"}}}'),
  ('social_listening.get_alerts', 'social_listening.get_alerts', 'social_listening', 'Retrieve active brand monitoring alert configurations and recent triggers', '{"type":"object","properties":{"alert_id":{"type":"string"},"limit":{"type":"integer","default":20}}}', '{"type":"object","properties":{"alerts":{"type":"array"},"total":{"type":"integer"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- social_listening.search_mentions
  ('social_listening.search_mentions', 'brandwatch', 'byo', 0.015, 8.2, true),
  ('social_listening.search_mentions', 'mention', 'byo', 0.008, 7.8, false),
  ('social_listening.search_mentions', 'sprinklr', 'byo', 0.020, 8.0, false),
  ('social_listening.search_mentions', 'talkwalker', 'byo', 0.018, 7.9, false),
  -- social_listening.get_alerts
  ('social_listening.get_alerts', 'brandwatch', 'byo', 0.005, 8.2, true),
  ('social_listening.get_alerts', 'mention', 'byo', 0.004, 7.8, false),
  ('social_listening.get_alerts', 'talkwalker', 'byo', 0.006, 7.9, false)
ON CONFLICT (capability_id, provider) DO NOTHING;
