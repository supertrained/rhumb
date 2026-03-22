-- Migration 0065: Capability Expansion Day 21
-- Domains: knowledge, recommendation, cms, reporting
-- New capabilities: 10
-- New mappings: ~36
-- Cumulative target: ~261 capabilities / ~891 mappings

-- ============================================================
-- DOMAIN: knowledge (Knowledge Base Management)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('knowledge.search', 'knowledge.search', 'knowledge', 'Search a knowledge base for articles or documents matching a query', '{"type":"object","required":["query"],"properties":{"query":{"type":"string"},"limit":{"type":"integer","default":10},"locale":{"type":"string"},"section_id":{"type":"string"}}}', '{"type":"object","properties":{"articles":{"type":"array"},"total":{"type":"integer"}}}'),
  ('knowledge.create_article', 'knowledge.create_article', 'knowledge', 'Create or draft a new knowledge base article', '{"type":"object","required":["title","body"],"properties":{"title":{"type":"string"},"body":{"type":"string"},"section_id":{"type":"string"},"labels":{"type":"array"},"draft":{"type":"boolean","default":true}}}', '{"type":"object","properties":{"article_id":{"type":"string"},"url":{"type":"string"},"status":{"type":"string"}}}'),
  ('knowledge.get_article', 'knowledge.get_article', 'knowledge', 'Retrieve a specific knowledge base article by ID or slug', '{"type":"object","required":["article_id"],"properties":{"article_id":{"type":"string"},"locale":{"type":"string"}}}', '{"type":"object","properties":{"id":{"type":"string"},"title":{"type":"string"},"body":{"type":"string"},"section":{"type":"string"},"updated_at":{"type":"string"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- knowledge.search
  ('knowledge.search', 'confluence', 'byo', 0.002, 7.9, true),
  ('knowledge.search', 'notion', 'byo', 0.002, 7.8, false),
  ('knowledge.search', 'zendesk-guide', 'byo', 0.002, 7.5, false),
  ('knowledge.search', 'document360', 'byo', 0.002, 7.2, false),
  -- knowledge.create_article
  ('knowledge.create_article', 'confluence', 'byo', 0.004, 7.9, true),
  ('knowledge.create_article', 'notion', 'byo', 0.003, 7.8, false),
  ('knowledge.create_article', 'zendesk-guide', 'byo', 0.003, 7.5, false),
  ('knowledge.create_article', 'guru', 'byo', 0.003, 7.3, false),
  -- knowledge.get_article
  ('knowledge.get_article', 'confluence', 'byo', 0.001, 7.9, true),
  ('knowledge.get_article', 'notion', 'byo', 0.001, 7.8, false),
  ('knowledge.get_article', 'zendesk-guide', 'byo', 0.001, 7.5, false),
  ('knowledge.get_article', 'document360', 'byo', 0.001, 7.2, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: recommendation (Personalization & Recommendations)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('recommendation.get_items', 'recommendation.get_items', 'recommendation', 'Get personalized item recommendations for a user', '{"type":"object","required":["user_id"],"properties":{"user_id":{"type":"string"},"scenario":{"type":"string","description":"Recommendation scenario, e.g. homepage, similar_items"},"item_id":{"type":"string"},"limit":{"type":"integer","default":10},"filter":{"type":"string"}}}', '{"type":"object","properties":{"items":{"type":"array"},"scenario":{"type":"string"},"model_version":{"type":"string"}}}'),
  ('recommendation.track_event', 'recommendation.track_event', 'recommendation', 'Track a user interaction event to improve recommendations', '{"type":"object","required":["user_id","event_type","item_id"],"properties":{"user_id":{"type":"string"},"event_type":{"type":"string","enum":["view","purchase","add_to_cart","rating","bookmark"]},"item_id":{"type":"string"},"value":{"type":"number"}}}', '{"type":"object","properties":{"accepted":{"type":"boolean"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- recommendation.get_items
  ('recommendation.get_items', 'recombee', 'byo', 0.003, 7.8, true),
  ('recommendation.get_items', 'aws-personalize', 'byo', 0.004, 7.9, false),
  ('recommendation.get_items', 'dynamic-yield', 'byo', 0.005, 7.6, false),
  ('recommendation.get_items', 'barilliance', 'byo', 0.004, 7.0, false),
  -- recommendation.track_event
  ('recommendation.track_event', 'recombee', 'byo', 0.001, 7.8, true),
  ('recommendation.track_event', 'aws-personalize', 'byo', 0.001, 7.9, false),
  ('recommendation.track_event', 'segment', 'byo', 0.001, 8.0, false),
  ('recommendation.track_event', 'dynamic-yield', 'byo', 0.001, 7.6, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: cms (Content Management)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('cms.get_page', 'cms.get_page', 'cms', 'Retrieve a CMS page or entry by ID or slug', '{"type":"object","required":["entry_id"],"properties":{"entry_id":{"type":"string"},"content_type":{"type":"string"},"locale":{"type":"string","default":"en"},"preview":{"type":"boolean","default":false}}}', '{"type":"object","properties":{"id":{"type":"string"},"title":{"type":"string"},"slug":{"type":"string"},"content":{"type":"object"},"published_at":{"type":"string"}}}'),
  ('cms.create_page', 'cms.create_page', 'cms', 'Create a new page or content entry in a CMS', '{"type":"object","required":["content_type","fields"],"properties":{"content_type":{"type":"string"},"fields":{"type":"object"},"locale":{"type":"string","default":"en"},"publish":{"type":"boolean","default":false}}}', '{"type":"object","properties":{"entry_id":{"type":"string"},"status":{"type":"string"},"url":{"type":"string"}}}'),
  ('cms.publish', 'cms.publish', 'cms', 'Publish or schedule a CMS entry for public visibility', '{"type":"object","required":["entry_id"],"properties":{"entry_id":{"type":"string"},"schedule_at":{"type":"string","description":"ISO8601 datetime for scheduled publish; omit for immediate"}}}', '{"type":"object","properties":{"entry_id":{"type":"string"},"status":{"type":"string"},"published_at":{"type":"string"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- cms.get_page
  ('cms.get_page', 'contentful', 'byo', 0.001, 8.1, true),
  ('cms.get_page', 'sanity', 'byo', 0.001, 7.9, false),
  ('cms.get_page', 'prismic', 'byo', 0.001, 7.5, false),
  ('cms.get_page', 'strapi', 'byo', 0.001, 7.2, false),
  -- cms.create_page
  ('cms.create_page', 'contentful', 'byo', 0.003, 8.1, true),
  ('cms.create_page', 'sanity', 'byo', 0.003, 7.9, false),
  ('cms.create_page', 'prismic', 'byo', 0.003, 7.5, false),
  ('cms.create_page', 'ghost', 'byo', 0.002, 7.3, false),
  -- cms.publish
  ('cms.publish', 'contentful', 'byo', 0.002, 8.1, true),
  ('cms.publish', 'sanity', 'byo', 0.002, 7.9, false),
  ('cms.publish', 'ghost', 'byo', 0.002, 7.3, false),
  ('cms.publish', 'prismic', 'byo', 0.002, 7.5, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: reporting (Report Generation & Scheduling)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('reporting.generate', 'reporting.generate', 'reporting', 'Generate a report from a dataset or query with optional formatting', '{"type":"object","required":["report_id"],"properties":{"report_id":{"type":"string"},"parameters":{"type":"object"},"format":{"type":"string","enum":["pdf","csv","xlsx","json"],"default":"pdf"}}}', '{"type":"object","properties":{"url":{"type":"string"},"expires_at":{"type":"string"},"format":{"type":"string"}}}'),
  ('reporting.schedule', 'reporting.schedule', 'reporting', 'Schedule a report for recurring automated delivery', '{"type":"object","required":["report_id","cron","recipients"],"properties":{"report_id":{"type":"string"},"cron":{"type":"string"},"recipients":{"type":"array","items":{"type":"string"}},"format":{"type":"string","enum":["pdf","csv","xlsx"],"default":"pdf"}}}', '{"type":"object","properties":{"schedule_id":{"type":"string"},"next_run":{"type":"string"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- reporting.generate
  ('reporting.generate', 'metabase', 'byo', 0.005, 7.8, true),
  ('reporting.generate', 'looker', 'byo', 0.008, 8.0, false),
  ('reporting.generate', 'redash', 'byo', 0.004, 7.2, false),
  ('reporting.generate', 'retool', 'byo', 0.006, 7.5, false),
  -- reporting.schedule
  ('reporting.schedule', 'metabase', 'byo', 0.003, 7.8, true),
  ('reporting.schedule', 'looker', 'byo', 0.005, 8.0, false),
  ('reporting.schedule', 'redash', 'byo', 0.003, 7.2, false)
ON CONFLICT (capability_id, provider) DO NOTHING;
