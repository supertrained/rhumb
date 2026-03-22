-- Migration 0075: Capability Expansion Day 31
-- Domains: realtime, travel, payment_link, resume
-- New capabilities: 10
-- New mappings: ~37
-- Cumulative target: ~361 capabilities / ~1256 mappings

-- ============================================================
-- DOMAIN: realtime (WebSocket & Realtime Pub/Sub)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('realtime.publish', 'realtime.publish', 'realtime', 'Publish a message to a realtime channel for connected subscribers', '{"type":"object","required":["channel","event","data"],"properties":{"channel":{"type":"string"},"event":{"type":"string"},"data":{"type":"object"},"socket_id":{"type":"string","description":"Exclude a specific socket from receiving the message"}}}', '{"type":"object","properties":{"message_id":{"type":"string"},"subscribers_notified":{"type":"integer"}}}'),
  ('realtime.subscribe', 'realtime.subscribe', 'realtime', 'Create a server-side subscription to a realtime channel and register a webhook', '{"type":"object","required":["channel","webhook_url"],"properties":{"channel":{"type":"string"},"webhook_url":{"type":"string"},"events":{"type":"array","description":"Event names to subscribe to; omit for all"},"auth_required":{"type":"boolean","default":false}}}', '{"type":"object","properties":{"subscription_id":{"type":"string"},"channel":{"type":"string"},"status":{"type":"string"}}}'),
  ('realtime.presence', 'realtime.presence', 'realtime', 'Get the list of currently connected members on a presence channel', '{"type":"object","required":["channel"],"properties":{"channel":{"type":"string"}}}', '{"type":"object","properties":{"channel":{"type":"string"},"member_count":{"type":"integer"},"members":{"type":"array","items":{"type":"object","properties":{"user_id":{"type":"string"},"info":{"type":"object"}}}}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- realtime.publish
  ('realtime.publish', 'pusher', 'byo', 0.002, 8.1, true),
  ('realtime.publish', 'ably', 'byo', 0.002, 8.2, false),
  ('realtime.publish', 'supabase-realtime', 'byo', 0.001, 7.8, false),
  ('realtime.publish', 'partykit', 'byo', 0.002, 7.6, false),
  -- realtime.subscribe
  ('realtime.subscribe', 'pusher', 'byo', 0.003, 8.1, true),
  ('realtime.subscribe', 'ably', 'byo', 0.003, 8.2, false),
  ('realtime.subscribe', 'supabase-realtime', 'byo', 0.002, 7.8, false),
  -- realtime.presence
  ('realtime.presence', 'pusher', 'byo', 0.002, 8.1, true),
  ('realtime.presence', 'ably', 'byo', 0.002, 8.2, false),
  ('realtime.presence', 'partykit', 'byo', 0.002, 7.6, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: travel (Flight & Hotel Search)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('travel.search_flights', 'travel.search_flights', 'travel', 'Search available flights between two airports for given dates', '{"type":"object","required":["origin","destination","departure_date"],"properties":{"origin":{"type":"string","description":"IATA airport code"},"destination":{"type":"string","description":"IATA airport code"},"departure_date":{"type":"string","description":"YYYY-MM-DD"},"return_date":{"type":"string","description":"YYYY-MM-DD for round-trip"},"adults":{"type":"integer","default":1},"cabin_class":{"type":"string","enum":["economy","premium_economy","business","first"]},"currency":{"type":"string","default":"USD"}}}', '{"type":"object","properties":{"flights":{"type":"array"},"total":{"type":"integer"},"currency":{"type":"string"}}}'),
  ('travel.search_hotels', 'travel.search_hotels', 'travel', 'Search available hotels at a destination for given dates', '{"type":"object","required":["destination","check_in","check_out"],"properties":{"destination":{"type":"string"},"check_in":{"type":"string","description":"YYYY-MM-DD"},"check_out":{"type":"string","description":"YYYY-MM-DD"},"guests":{"type":"integer","default":1},"rooms":{"type":"integer","default":1},"min_stars":{"type":"integer"},"currency":{"type":"string","default":"USD"}}}', '{"type":"object","properties":{"hotels":{"type":"array"},"total":{"type":"integer"},"currency":{"type":"string"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- travel.search_flights
  ('travel.search_flights', 'amadeus', 'byo', 0.010, 8.2, true),
  ('travel.search_flights', 'skyscanner', 'byo', 0.008, 7.9, false),
  ('travel.search_flights', 'kiwi', 'byo', 0.007, 7.7, false),
  ('travel.search_flights', 'duffel', 'byo', 0.010, 8.0, false),
  -- travel.search_hotels
  ('travel.search_hotels', 'amadeus', 'byo', 0.010, 8.2, true),
  ('travel.search_hotels', 'booking-com', 'byo', 0.008, 8.0, false),
  ('travel.search_hotels', 'expedia', 'byo', 0.009, 7.9, false),
  ('travel.search_hotels', 'hotels-com', 'byo', 0.008, 7.7, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: payment_link (Payment Link Generation)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('payment_link.create', 'payment_link.create', 'payment_link', 'Generate a shareable payment link for a specific amount or product', '{"type":"object","required":["amount","currency"],"properties":{"amount":{"type":"integer","description":"Amount in smallest currency unit"},"currency":{"type":"string","default":"USD"},"description":{"type":"string"},"customer_email":{"type":"string"},"expires_at":{"type":"string"},"redirect_url":{"type":"string"},"metadata":{"type":"object"}}}', '{"type":"object","properties":{"link_id":{"type":"string"},"url":{"type":"string"},"expires_at":{"type":"string"},"status":{"type":"string"}}}'),
  ('payment_link.get', 'payment_link.get', 'payment_link', 'Retrieve the status and payment details of a payment link', '{"type":"object","required":["link_id"],"properties":{"link_id":{"type":"string"}}}', '{"type":"object","properties":{"link_id":{"type":"string"},"url":{"type":"string"},"status":{"type":"string","enum":["active","paid","expired","cancelled"]},"amount_received":{"type":"integer"},"paid_at":{"type":"string"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- payment_link.create
  ('payment_link.create', 'stripe', 'byo', 0.004, 8.5, true),
  ('payment_link.create', 'square', 'byo', 0.003, 8.0, false),
  ('payment_link.create', 'paypal', 'byo', 0.004, 7.8, false),
  ('payment_link.create', 'paddle', 'byo', 0.004, 7.7, false),
  -- payment_link.get
  ('payment_link.get', 'stripe', 'byo', 0.002, 8.5, true),
  ('payment_link.get', 'square', 'byo', 0.002, 8.0, false),
  ('payment_link.get', 'paypal', 'byo', 0.002, 7.8, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: resume (Resume Parsing & Candidate Matching)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('resume.parse', 'resume.parse', 'resume', 'Parse a resume document and extract structured candidate information', '{"type":"object","required":["document_url"],"properties":{"document_url":{"type":"string"},"document_type":{"type":"string","enum":["pdf","docx","txt","html"],"default":"pdf"}}}', '{"type":"object","properties":{"candidate":{"type":"object","properties":{"name":{"type":"string"},"email":{"type":"string"},"phone":{"type":"string"},"skills":{"type":"array"},"experience":{"type":"array"},"education":{"type":"array"},"languages":{"type":"array"}}}}}'),
  ('resume.match', 'resume.match', 'resume', 'Score a resume against a job description for candidate fit', '{"type":"object","required":["resume_id","job_description"],"properties":{"resume_id":{"type":"string"},"job_description":{"type":"string"},"required_skills":{"type":"array"}}}', '{"type":"object","properties":{"match_score":{"type":"number","description":"0–100 fit score"},"matched_skills":{"type":"array"},"missing_skills":{"type":"array"},"recommendation":{"type":"string","enum":["strong_fit","good_fit","partial_fit","poor_fit"]}}}'),
  ('resume.score', 'resume.score', 'resume', 'Score a resume for overall quality, completeness, and ATS compatibility', '{"type":"object","required":["document_url"],"properties":{"document_url":{"type":"string"},"target_role":{"type":"string"}}}', '{"type":"object","properties":{"overall_score":{"type":"number"},"ats_score":{"type":"number"},"completeness":{"type":"number"},"suggestions":{"type":"array"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- resume.parse
  ('resume.parse', 'affinda', 'byo', 0.010, 8.0, true),
  ('resume.parse', 'sovren', 'byo', 0.015, 7.9, false),
  ('resume.parse', 'hireability', 'byo', 0.012, 7.7, false),
  -- resume.match
  ('resume.match', 'affinda', 'byo', 0.015, 8.0, true),
  ('resume.match', 'sovren', 'byo', 0.020, 7.9, false),
  ('resume.match', 'skillate', 'byo', 0.018, 7.6, false),
  -- resume.score
  ('resume.score', 'affinda', 'byo', 0.012, 8.0, true),
  ('resume.score', 'jobscan', 'byo', 0.010, 7.8, false),
  ('resume.score', 'skillate', 'byo', 0.015, 7.6, false)
ON CONFLICT (capability_id, provider) DO NOTHING;
