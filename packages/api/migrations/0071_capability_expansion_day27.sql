-- Migration 0071: Capability Expansion Day 27
-- Domains: event_bus, social_analytics, contact, booking_resource
-- New capabilities: 10
-- New mappings: ~37
-- Cumulative target: ~321 capabilities / ~1110 mappings

-- ============================================================
-- DOMAIN: event_bus (Event Streaming & Pub/Sub)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('event_bus.publish', 'event_bus.publish', 'event_bus', 'Publish an event or message to a topic or exchange', '{"type":"object","required":["topic","payload"],"properties":{"topic":{"type":"string"},"payload":{"type":"object"},"key":{"type":"string","description":"Partition key for ordered delivery"},"headers":{"type":"object"},"deduplication_id":{"type":"string"}}}', '{"type":"object","properties":{"message_id":{"type":"string"},"sequence_number":{"type":"string"},"published_at":{"type":"string"}}}'),
  ('event_bus.subscribe', 'event_bus.subscribe', 'event_bus', 'Create a subscription to receive events from a topic', '{"type":"object","required":["topic","endpoint"],"properties":{"topic":{"type":"string"},"endpoint":{"type":"string","description":"Webhook URL or queue ARN to deliver events"},"filter":{"type":"object","description":"Attribute filter policy"},"batch_size":{"type":"integer","default":10}}}', '{"type":"object","properties":{"subscription_id":{"type":"string"},"status":{"type":"string"},"topic":{"type":"string"}}}'),
  ('event_bus.get_messages', 'event_bus.get_messages', 'event_bus', 'Pull pending messages from a queue or subscription', '{"type":"object","required":["queue_id"],"properties":{"queue_id":{"type":"string"},"max_messages":{"type":"integer","default":10},"visibility_timeout_sec":{"type":"integer","default":30},"wait_time_sec":{"type":"integer","default":0}}}', '{"type":"object","properties":{"messages":{"type":"array"},"count":{"type":"integer"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- event_bus.publish
  ('event_bus.publish', 'aws-eventbridge', 'byo', 0.002, 8.3, true),
  ('event_bus.publish', 'aws-sns', 'byo', 0.001, 8.1, false),
  ('event_bus.publish', 'google-pubsub', 'byo', 0.002, 8.0, false),
  ('event_bus.publish', 'confluent', 'byo', 0.005, 8.2, false),
  ('event_bus.publish', 'ably', 'byo', 0.003, 7.8, false),
  -- event_bus.subscribe
  ('event_bus.subscribe', 'aws-eventbridge', 'byo', 0.003, 8.3, true),
  ('event_bus.subscribe', 'aws-sns', 'byo', 0.001, 8.1, false),
  ('event_bus.subscribe', 'google-pubsub', 'byo', 0.002, 8.0, false),
  ('event_bus.subscribe', 'ably', 'byo', 0.003, 7.8, false),
  -- event_bus.get_messages
  ('event_bus.get_messages', 'aws-sqs', 'byo', 0.001, 8.2, true),
  ('event_bus.get_messages', 'google-pubsub', 'byo', 0.002, 8.0, false),
  ('event_bus.get_messages', 'confluent', 'byo', 0.004, 8.2, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: social_analytics (Social Media Scheduling & Analytics)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('social_analytics.schedule_post', 'social_analytics.schedule_post', 'social_analytics', 'Schedule a social media post across one or more platforms', '{"type":"object","required":["content","platforms"],"properties":{"content":{"type":"string"},"platforms":{"type":"array","items":{"type":"string","enum":["twitter","linkedin","instagram","facebook","tiktok"]}},"media_urls":{"type":"array"},"scheduled_at":{"type":"string","description":"ISO8601; omit for immediate publish"}}}', '{"type":"object","properties":{"post_id":{"type":"string"},"status":{"type":"string"},"scheduled_at":{"type":"string"},"platforms":{"type":"array"}}}'),
  ('social_analytics.get_analytics', 'social_analytics.get_analytics', 'social_analytics', 'Retrieve engagement analytics for social media posts or profiles', '{"type":"object","properties":{"profile_id":{"type":"string"},"post_id":{"type":"string"},"platform":{"type":"string"},"date_from":{"type":"string"},"date_to":{"type":"string"}}}', '{"type":"object","properties":{"impressions":{"type":"integer"},"engagements":{"type":"integer"},"reach":{"type":"integer"},"clicks":{"type":"integer"},"engagement_rate":{"type":"number"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- social_analytics.schedule_post
  ('social_analytics.schedule_post', 'buffer', 'byo', 0.003, 7.8, true),
  ('social_analytics.schedule_post', 'hootsuite', 'byo', 0.004, 7.7, false),
  ('social_analytics.schedule_post', 'sprout-social', 'byo', 0.006, 7.9, false),
  ('social_analytics.schedule_post', 'later', 'byo', 0.003, 7.5, false),
  -- social_analytics.get_analytics
  ('social_analytics.get_analytics', 'sprout-social', 'byo', 0.006, 7.9, true),
  ('social_analytics.get_analytics', 'hootsuite', 'byo', 0.005, 7.7, false),
  ('social_analytics.get_analytics', 'buffer', 'byo', 0.004, 7.8, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: contact (Contact Enrichment & Management)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('contact.enrich', 'contact.enrich', 'contact', 'Enrich a contact record with company, social, and demographic data', '{"type":"object","properties":{"email":{"type":"string"},"domain":{"type":"string"},"linkedin_url":{"type":"string"},"name":{"type":"string"}}}', '{"type":"object","properties":{"email":{"type":"string"},"name":{"type":"string"},"title":{"type":"string"},"company":{"type":"string"},"linkedin":{"type":"string"},"twitter":{"type":"string"},"location":{"type":"string"},"seniority":{"type":"string"}}}'),
  ('contact.search', 'contact.search', 'contact', 'Search for contacts matching filters like title, company, or location', '{"type":"object","properties":{"title":{"type":"string"},"company":{"type":"string"},"location":{"type":"string"},"seniority":{"type":"string"},"limit":{"type":"integer","default":25}}}', '{"type":"object","properties":{"contacts":{"type":"array"},"total":{"type":"integer"}}}'),
  ('contact.update', 'contact.update', 'contact', 'Update contact record fields in a CRM or contact database', '{"type":"object","required":["contact_id"],"properties":{"contact_id":{"type":"string"},"fields":{"type":"object","description":"Key-value pairs of fields to update"}}}', '{"type":"object","properties":{"contact_id":{"type":"string"},"updated_at":{"type":"string"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- contact.enrich
  ('contact.enrich', 'apollo', 'byo', 0.005, 8.0, true),
  ('contact.enrich', 'clearbit', 'byo', 0.008, 8.1, false),
  ('contact.enrich', 'pdl', 'byo', 0.006, 7.9, false),
  ('contact.enrich', 'hunter', 'byo', 0.004, 7.6, false),
  -- contact.search
  ('contact.search', 'apollo', 'byo', 0.008, 8.0, true),
  ('contact.search', 'pdl', 'byo', 0.010, 7.9, false),
  ('contact.search', 'clearbit', 'byo', 0.010, 8.1, false),
  -- contact.update
  ('contact.update', 'hubspot', 'byo', 0.003, 8.1, true),
  ('contact.update', 'salesforce', 'byo', 0.004, 8.2, false),
  ('contact.update', 'pipedrive', 'byo', 0.003, 7.8, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: booking_resource (Resource & Room Booking)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('booking_resource.search_availability', 'booking_resource.search_availability', 'booking_resource', 'Search available resources (rooms, equipment, desks) for a time window', '{"type":"object","required":["resource_type","date_from","date_to"],"properties":{"resource_type":{"type":"string","enum":["room","desk","equipment","vehicle"]},"date_from":{"type":"string"},"date_to":{"type":"string"},"capacity":{"type":"integer"},"location":{"type":"string"}}}', '{"type":"object","properties":{"resources":{"type":"array"},"count":{"type":"integer"}}}'),
  ('booking_resource.reserve', 'booking_resource.reserve', 'booking_resource', 'Reserve a resource for a specified time window', '{"type":"object","required":["resource_id","start","end","booker_id"],"properties":{"resource_id":{"type":"string"},"start":{"type":"string"},"end":{"type":"string"},"booker_id":{"type":"string"},"title":{"type":"string"},"attendees":{"type":"array"}}}', '{"type":"object","properties":{"booking_id":{"type":"string"},"status":{"type":"string"},"confirmation_code":{"type":"string"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- booking_resource.search_availability
  ('booking_resource.search_availability', 'robin', 'byo', 0.003, 7.7, true),
  ('booking_resource.search_availability', 'skedda', 'byo', 0.003, 7.5, false),
  ('booking_resource.search_availability', 'microsoft-bookings', 'byo', 0.002, 7.4, false),
  ('booking_resource.search_availability', 'condeco', 'byo', 0.004, 7.3, false),
  -- booking_resource.reserve
  ('booking_resource.reserve', 'robin', 'byo', 0.004, 7.7, true),
  ('booking_resource.reserve', 'skedda', 'byo', 0.004, 7.5, false),
  ('booking_resource.reserve', 'microsoft-bookings', 'byo', 0.003, 7.4, false)
ON CONFLICT (capability_id, provider) DO NOTHING;
