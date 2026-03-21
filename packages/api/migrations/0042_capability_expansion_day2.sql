-- Migration: 0042_capability_expansion_day2
-- Description: Day 2 capability expansion — 3 new capabilities (video × 2, forms × 1), 2 previously-unmapped capabilities mapped
-- Date: 2026-03-21
-- Author: Helm (rhumb-access)
-- Context: Daily expansion cadence — target 200+ capabilities.
--          Prioritized: video domain (new), forms domain (new), vector domain (fill 0-provider gaps).

-- ============================================================
-- NEW CAPABILITIES (3)
-- ============================================================

-- Video — dedicated domain (video upload + adaptive streaming)
INSERT INTO capabilities (id, domain, action, description, input_hint, outcome) VALUES
('video.upload', 'video', 'upload', 'Upload and ingest a video file for hosting and streaming', 'file_url or file_bytes, title?, metadata?', 'Video asset created with playback URL and processing status'),
('video.stream', 'video', 'stream', 'Retrieve adaptive streaming playback URL for a video asset', 'asset_id, format? (hls|dash|mp4)', 'Playback URL with format options and stream metadata')
ON CONFLICT (id) DO NOTHING;

-- Forms — dedicated domain (response collection)
INSERT INTO capabilities (id, domain, action, description, input_hint, outcome) VALUES
('forms.collect', 'forms', 'collect', 'Retrieve submitted responses from a form', 'form_id, since?, limit?, filter?', 'Array of form responses with field values and submission timestamps')
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- SERVICE MAPPINGS FOR NEW CAPABILITIES (9)
-- ============================================================

-- video.upload → mux (7.4), cloudflare-stream (7.4), api-video (6.9)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('video.upload', 'mux', '{byo}', 'basic', 'POST /video/v1/assets', 'Developer-first video platform, strong analytics'),
('video.upload', 'cloudflare-stream', '{byo}', 'bearer', 'POST /client/v4/accounts/{account_id}/stream', 'Cloudflare-native, global edge delivery'),
('video.upload', 'api-video', '{byo}', 'bearer', 'POST /videos', 'Straightforward video API, good free tier')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- video.stream → mux (7.4), cloudflare-stream (7.4), bunny-stream (7.2)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('video.stream', 'mux', '{byo}', 'basic', 'GET /video/v1/assets/{id}/playback-ids', 'HLS/DASH adaptive streaming with signed URLs'),
('video.stream', 'cloudflare-stream', '{byo}', 'bearer', 'GET /client/v4/accounts/{account_id}/stream/{id}', 'HLS playback via Cloudflare edge'),
('video.stream', 'bunny-stream', '{byo}', 'api_key', 'GET /library/{libraryId}/videos/{videoId}', 'Cost-effective CDN, simple API')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- forms.collect → typeform (6.8), jotform (6.9), fillout (6.8)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, free_tier_calls, notes) VALUES
('forms.collect', 'typeform', '{byo}', 'bearer', 'GET /forms/{form_id}/responses', 100, 'Conversational forms, strong developer API'),
('forms.collect', 'jotform', '{byo}', 'api_key', 'GET /form/{formID}/submissions', 100, 'Broad integration support, generous free tier'),
('forms.collect', 'fillout', '{byo}', 'bearer', 'GET /v1/api/forms/{formId}/submissions', 100, 'Modern AI-powered forms')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- ============================================================
-- MAP EXISTING 0-PROVIDER CAPABILITIES: vector.search + vector.upsert (10 mappings)
-- ============================================================

-- vector.search → pinecone (7.5), qdrant (7.4), weaviate (7.1), milvus (6.8), chroma (6.5)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('vector.search', 'pinecone', '{byo}', 'api_key', 'POST /query', 'Managed vector DB, strong SaaS offering'),
('vector.search', 'qdrant', '{byo}', 'api_key', 'POST /collections/{collection_name}/points/search', 'Open-source, cloud hosted or self-hosted'),
('vector.search', 'weaviate', '{byo}', 'api_key', 'POST /v1/graphql', 'GraphQL interface, strong multimodal support'),
('vector.search', 'milvus', '{byo}', 'bearer', 'POST /v1/vector/search', 'High-performance, Zilliz cloud managed option'),
('vector.search', 'chroma', '{byo}', 'bearer', 'POST /api/v1/collections/{collection_id}/query', 'Open-source first, easy local dev')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- vector.upsert → pinecone (7.5), qdrant (7.4), weaviate (7.1), milvus (6.8), chroma (6.5)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('vector.upsert', 'pinecone', '{byo}', 'api_key', 'POST /vectors/upsert', 'Managed vector DB, strong SaaS offering'),
('vector.upsert', 'qdrant', '{byo}', 'api_key', 'PUT /collections/{collection_name}/points', 'Open-source, cloud hosted or self-hosted'),
('vector.upsert', 'weaviate', '{byo}', 'api_key', 'POST /v1/objects', 'GraphQL interface, strong multimodal support'),
('vector.upsert', 'milvus', '{byo}', 'bearer', 'POST /v1/vector/insert', 'High-performance, Zilliz cloud managed option'),
('vector.upsert', 'chroma', '{byo}', 'bearer', 'POST /api/v1/collections/{collection_id}/upsert', 'Open-source first, easy local dev')
ON CONFLICT (capability_id, service_slug) DO NOTHING;
