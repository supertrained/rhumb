-- Migration: 0043_capability_expansion_day3
-- Description: Day 3 capability expansion — 4 new capabilities (messaging, webhook, document.search, search.semantic)
--              Feature flags (feature.evaluate) already existed; mapped 4 new providers.
-- Date: 2026-03-21
-- Author: Helm (rhumb-access)

-- ============================================================
-- NEW CAPABILITIES (4)
-- ============================================================

INSERT INTO capabilities (id, domain, action, description, input_hint, outcome) VALUES
('messaging.publish', 'messaging', 'publish', 'Publish a message or event to a real-time channel or topic', 'channel, message, event_type?', 'Message published with message ID and delivery status'),
('webhook.deliver', 'webhook', 'deliver', 'Deliver a webhook event to a target URL with guaranteed delivery and retry', 'destination_url, event_type, payload, headers?', 'Delivery attempt ID with status, retry count, and response code'),
('document.search', 'document', 'search', 'Full-text search across a document index or collection', 'query, index?, limit?, filters?', 'Ranked list of matching documents with relevance scores'),
('search.semantic', 'search', 'semantic', 'Semantic similarity search over vector-indexed content', 'query_text, collection, top_k?, score_threshold?', 'Nearest neighbors with similarity scores and metadata')
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- SERVICE MAPPINGS (22 new)
-- ============================================================

-- messaging.publish → ably (7.5), pusher (6.9), getstream (7.2), sendbird (7.4)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('messaging.publish', 'ably', '{byo,agent_vault}', 'api_key', 'POST /messages', 'Real-time pub/sub, WebSocket fallback'),
('messaging.publish', 'pusher', '{byo}', 'api_key', 'POST /apps/{app_id}/events', 'Pusher Channels — server-sent events'),
('messaging.publish', 'getstream', '{byo}', 'api_key', 'POST /api/v2/channels/{type}/{id}/message', 'Activity feeds + chat messaging'),
('messaging.publish', 'sendbird', '{byo}', 'api_key', 'POST /v3/group_channels/{channel_url}/messages', 'In-app messaging SDK')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- feature.evaluate → flagsmith (7.0), growthbook (7.1)
-- (launchdarkly and statsig already mapped in prior migration)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('feature.evaluate', 'flagsmith', '{byo}', 'api_key', 'GET /api/v1/flags/', 'Open-source option, self-hostable'),
('feature.evaluate', 'growthbook', '{byo}', 'api_key', 'GET /api/v1/features/{key}', 'A/B testing + feature flags with stats')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- webhook.deliver → hookdeck (7.0), svix (7.3), ngrok (6.9)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('webhook.deliver', 'hookdeck', '{byo}', 'bearer', 'POST /events', 'Webhook gateway with retry + dead letter queue'),
('webhook.deliver', 'svix', '{byo}', 'bearer', 'POST /api/v1/app/{app_id}/msg/', 'Enterprise webhook delivery, signing + versioning'),
('webhook.deliver', 'ngrok', '{byo}', 'bearer', 'POST /api/v1/tunnel_sessions', 'Tunnel-based webhook delivery for local/edge')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- document.search → algolia (7.2), meilisearch (7.5), typesense (7.1)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('document.search', 'algolia', '{byo,agent_vault}', 'api_key', 'POST /1/indexes/{indexName}/query', 'Enterprise search, hosted, rich faceting'),
('document.search', 'meilisearch', '{byo}', 'bearer', 'POST /indexes/{uid}/search', 'Open-source, fast, typo-tolerant'),
('document.search', 'typesense', '{byo}', 'api_key', 'GET /collections/{name}/documents/search', 'Open-source alternative to Algolia, low-latency')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- search.semantic → qdrant (7.4), weaviate (7.1), milvus (6.8), pinecone (7.5)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('search.semantic', 'qdrant', '{byo}', 'bearer', 'POST /collections/{collection_name}/points/search', 'High-performance vector DB, payload filtering'),
('search.semantic', 'weaviate', '{byo}', 'bearer', 'POST /v1/graphql (nearVector/nearText)', 'GraphQL interface, hybrid dense+sparse search'),
('search.semantic', 'milvus', '{byo}', 'bearer', 'POST /v1/vector/search', 'Cloud Milvus (Zilliz), massive-scale vector search'),
('search.semantic', 'pinecone', '{byo,agent_vault}', 'api_key', 'POST /query', 'Managed vector DB, serverless tier, top AN score')
ON CONFLICT (capability_id, service_slug) DO NOTHING;
