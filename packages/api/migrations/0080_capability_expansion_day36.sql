-- Migration 0080: Capability Expansion Day 36
-- Domains: image_moderation, domain_registration, address_verification, fleet
-- New capabilities: 10
-- New mappings: ~37
-- Cumulative target: ~411 capabilities / ~1441 mappings

-- ============================================================
-- DOMAIN: image_moderation (Content Safety & Moderation)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('image_moderation.check_image', 'image_moderation.check_image', 'image_moderation', 'Scan an image for unsafe, explicit, or policy-violating content', '{"type":"object","required":["image_url"],"properties":{"image_url":{"type":"string"},"categories":{"type":"array","items":{"type":"string","enum":["nudity","violence","hate","drugs","self-harm","spam"]},"description":"Omit to check all categories"},"min_confidence":{"type":"number","default":0.7}}}', '{"type":"object","properties":{"safe":{"type":"boolean"},"categories":{"type":"object","description":"Category → confidence score map"},"action":{"type":"string","enum":["allow","review","block"]}}}'),
  ('image_moderation.check_text', 'image_moderation.check_text', 'image_moderation', 'Scan a text string for toxic, hateful, or policy-violating content', '{"type":"object","required":["text"],"properties":{"text":{"type":"string"},"categories":{"type":"array","items":{"type":"string","enum":["hate","harassment","self-harm","sexual","violence","spam"]}},"language":{"type":"string","default":"en"}}}', '{"type":"object","properties":{"safe":{"type":"boolean"},"categories":{"type":"object"},"action":{"type":"string","enum":["allow","review","block"]}}}'),
  ('image_moderation.get_report', 'image_moderation.get_report', 'image_moderation', 'Retrieve a moderation report or audit log for a previous check', '{"type":"object","required":["check_id"],"properties":{"check_id":{"type":"string"}}}', '{"type":"object","properties":{"check_id":{"type":"string"},"type":{"type":"string","enum":["image","text"]},"result":{"type":"object"},"checked_at":{"type":"string"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- image_moderation.check_image
  ('image_moderation.check_image', 'aws-rekognition', 'byo', 0.005, 8.3, true),
  ('image_moderation.check_image', 'azure-content-moderator', 'byo', 0.005, 8.1, false),
  ('image_moderation.check_image', 'hive', 'byo', 0.006, 8.2, false),
  ('image_moderation.check_image', 'sightengine', 'byo', 0.004, 7.8, false),
  -- image_moderation.check_text
  ('image_moderation.check_text', 'openai-moderation', 'byo', 0.001, 8.0, true),
  ('image_moderation.check_text', 'azure-content-moderator', 'byo', 0.003, 8.1, false),
  ('image_moderation.check_text', 'hive', 'byo', 0.004, 8.2, false),
  ('image_moderation.check_text', 'perspective', 'byo', 0.002, 7.9, false),
  -- image_moderation.get_report
  ('image_moderation.get_report', 'aws-rekognition', 'byo', 0.002, 8.3, true),
  ('image_moderation.get_report', 'hive', 'byo', 0.002, 8.2, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: domain_registration (Domain Search & Registration)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('domain_registration.search_availability', 'domain_registration.search_availability', 'domain_registration', 'Check whether one or more domain names are available for registration', '{"type":"object","required":["domains"],"properties":{"domains":{"type":"array","items":{"type":"string"},"description":"List of fully-qualified domain names to check"}}}', '{"type":"object","properties":{"results":{"type":"array","items":{"type":"object","properties":{"domain":{"type":"string"},"available":{"type":"boolean"},"price_usd":{"type":"number"},"premium":{"type":"boolean"}}}}}}'),
  ('domain_registration.register', 'domain_registration.register', 'domain_registration', 'Register a domain name with contact and DNS details', '{"type":"object","required":["domain","registrant"],"properties":{"domain":{"type":"string"},"years":{"type":"integer","default":1},"registrant":{"type":"object","required":["name","email","address"],"properties":{"name":{"type":"string"},"email":{"type":"string"},"phone":{"type":"string"},"address":{"type":"object"}}},"nameservers":{"type":"array","items":{"type":"string"}},"privacy":{"type":"boolean","default":true}}}', '{"type":"object","properties":{"domain":{"type":"string"},"order_id":{"type":"string"},"status":{"type":"string"},"expires_at":{"type":"string"}}}'),
  ('domain_registration.get_info', 'domain_registration.get_info', 'domain_registration', 'Get WHOIS and registration details for a domain', '{"type":"object","required":["domain"],"properties":{"domain":{"type":"string"}}}', '{"type":"object","properties":{"domain":{"type":"string"},"registered":{"type":"boolean"},"registrar":{"type":"string"},"created_at":{"type":"string"},"expires_at":{"type":"string"},"nameservers":{"type":"array"},"status":{"type":"array"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- domain_registration.search_availability
  ('domain_registration.search_availability', 'namecheap', 'byo', 0.003, 8.0, true),
  ('domain_registration.search_availability', 'godaddy', 'byo', 0.003, 7.9, false),
  ('domain_registration.search_availability', 'cloudflare-registrar', 'byo', 0.002, 8.1, false),
  ('domain_registration.search_availability', 'porkbun', 'byo', 0.002, 7.8, false),
  -- domain_registration.register
  ('domain_registration.register', 'namecheap', 'byo', 0.010, 8.0, true),
  ('domain_registration.register', 'godaddy', 'byo', 0.012, 7.9, false),
  ('domain_registration.register', 'cloudflare-registrar', 'byo', 0.008, 8.1, false),
  -- domain_registration.get_info
  ('domain_registration.get_info', 'namecheap', 'byo', 0.002, 8.0, true),
  ('domain_registration.get_info', 'godaddy', 'byo', 0.002, 7.9, false),
  ('domain_registration.get_info', 'whoisjson', 'byo', 0.001, 7.5, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: address_verification (Address Standardization & Autocomplete)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('address_verification.verify', 'address_verification.verify', 'address_verification', 'Validate and standardize a postal address', '{"type":"object","required":["address"],"properties":{"address":{"type":"object","required":["address1","city","country"],"properties":{"address1":{"type":"string"},"address2":{"type":"string"},"city":{"type":"string"},"state":{"type":"string"},"zip":{"type":"string"},"country":{"type":"string","description":"ISO-3166 2-letter code"}}}}}', '{"type":"object","properties":{"valid":{"type":"boolean"},"standardized":{"type":"object"},"deliverability":{"type":"string","enum":["deliverable","undeliverable","unknown"]},"components":{"type":"object"}}}'),
  ('address_verification.autocomplete', 'address_verification.autocomplete', 'address_verification', 'Suggest address completions as a user types', '{"type":"object","required":["query"],"properties":{"query":{"type":"string"},"country":{"type":"string","description":"ISO-3166 2-letter code; omit for global"},"limit":{"type":"integer","default":5}}}', '{"type":"object","properties":{"suggestions":{"type":"array","items":{"type":"object","properties":{"address":{"type":"string"},"place_id":{"type":"string"}}}}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- address_verification.verify
  ('address_verification.verify', 'smarty', 'byo', 0.005, 8.3, true),
  ('address_verification.verify', 'lob', 'byo', 0.006, 8.2, false),
  ('address_verification.verify', 'google-address', 'byo', 0.004, 8.1, false),
  ('address_verification.verify', 'melissa', 'byo', 0.005, 8.0, false),
  -- address_verification.autocomplete
  ('address_verification.autocomplete', 'google-places', 'byo', 0.003, 8.4, true),
  ('address_verification.autocomplete', 'smarty', 'byo', 0.004, 8.3, false),
  ('address_verification.autocomplete', 'here', 'byo', 0.003, 8.0, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: fleet (Vehicle Tracking & Fleet Management)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('fleet.track_vehicle', 'fleet.track_vehicle', 'fleet', 'Get real-time location and telemetry for a fleet vehicle', '{"type":"object","required":["vehicle_id"],"properties":{"vehicle_id":{"type":"string"}}}', '{"type":"object","properties":{"vehicle_id":{"type":"string"},"latitude":{"type":"number"},"longitude":{"type":"number"},"speed_mph":{"type":"number"},"heading":{"type":"number"},"status":{"type":"string","enum":["moving","idle","stopped","offline"]},"updated_at":{"type":"string"}}}'),
  ('fleet.get_location_history', 'fleet.get_location_history', 'fleet', 'Retrieve the location history and trip data for a fleet vehicle', '{"type":"object","required":["vehicle_id"],"properties":{"vehicle_id":{"type":"string"},"from":{"type":"string"},"to":{"type":"string"},"limit":{"type":"integer","default":100}}}', '{"type":"object","properties":{"vehicle_id":{"type":"string"},"points":{"type":"array"},"distance_miles":{"type":"number"},"duration_sec":{"type":"integer"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- fleet.track_vehicle
  ('fleet.track_vehicle', 'samsara', 'byo', 0.005, 8.2, true),
  ('fleet.track_vehicle', 'geotab', 'byo', 0.005, 8.0, false),
  ('fleet.track_vehicle', 'verizon-connect', 'byo', 0.006, 7.8, false),
  -- fleet.get_location_history
  ('fleet.get_location_history', 'samsara', 'byo', 0.006, 8.2, true),
  ('fleet.get_location_history', 'geotab', 'byo', 0.006, 8.0, false),
  ('fleet.get_location_history', 'verizon-connect', 'byo', 0.007, 7.8, false)
ON CONFLICT (capability_id, provider) DO NOTHING;
