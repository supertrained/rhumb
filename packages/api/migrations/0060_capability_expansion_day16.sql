-- Migration 0060: Capability expansion Day 16
-- 9 new capabilities across 3 domains: embed, ratelimit, audit
-- Running total: ~228 capabilities, ~726 mappings

BEGIN;

-- ============================================================
-- NEW CAPABILITIES
-- ============================================================
INSERT INTO capabilities (id, domain, description, status) VALUES
  -- Embeddings (3)
  ('embed.text',        'embed',     'Generate a vector embedding for a text string',        'active'),
  ('embed.batch',       'embed',     'Generate embeddings for multiple inputs in one call',  'active'),
  ('embed.similarity',  'embed',     'Compute similarity score between two embeddings',      'active'),
  -- Rate limiting / counters (3)
  ('ratelimit.check',   'ratelimit', 'Check whether a key is within its rate limit',         'active'),
  ('ratelimit.increment','ratelimit','Increment a counter and return remaining quota',        'active'),
  ('ratelimit.reset',   'ratelimit', 'Reset a rate-limit counter for a given key',           'active'),
  -- Audit logging (3)
  ('audit.log',         'audit',     'Write a structured audit event to a durable log',      'active'),
  ('audit.query',       'audit',     'Query audit logs with filters (user, action, time)',   'active'),
  ('audit.export',      'audit',     'Export audit log entries as CSV or JSON',              'active')
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- PROVIDER MAPPINGS
-- ============================================================

-- embed.text
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('embed.text', 'openai',       '{byo}', 'api_key', 'POST /v1/embeddings',              'text-embedding-3-small, 1536 dims. ~$0.00002/1K tokens.'),
  ('embed.text', 'cohere',       '{byo}', 'api_key', 'POST /v1/embed',                   'embed-english-v3. Free tier available.'),
  ('embed.text', 'huggingface',  '{byo}', 'api_key', 'POST /models/{model}',             'Open-source models via Inference API.'),
  ('embed.text', 'google-ai',    '{byo}', 'api_key', 'POST /v1beta/models/{m}:embedContent', 'text-embedding-004. Free tier.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- embed.batch
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('embed.batch', 'openai',      '{byo}', 'api_key', 'POST /v1/embeddings',              'Pass array of input strings.'),
  ('embed.batch', 'cohere',      '{byo}', 'api_key', 'POST /v1/embed',                   'texts[] array supported.'),
  ('embed.batch', 'huggingface', '{byo}', 'api_key', 'POST /models/{model}',             'inputs[] array.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- embed.similarity
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('embed.similarity', 'cohere',  '{byo}', 'api_key', 'POST /v1/rerank',                 'Rerank / similarity via rerank endpoint.'),
  ('embed.similarity', 'openai',  '{byo}', 'api_key', 'POST /v1/embeddings',             'Compute cosine similarity client-side after embed calls.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- ratelimit.check
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('ratelimit.check', 'upstash',       '{byo,rhumb_managed}', 'api_key', 'POST /rl/limit',           'PROXY-CALLABLE — live Upstash credential. Serverless rate limiting.'),
  ('ratelimit.check', 'redis-cloud',   '{byo}',               'api_key', 'Redis INCR / TTL pattern', 'Self-managed counter via Redis.'),
  ('ratelimit.check', 'momento',       '{byo}',               'api_key', 'POST /cache/{name}/{key}', 'Momento serverless cache.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- ratelimit.increment
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('ratelimit.increment', 'upstash',    '{byo,rhumb_managed}', 'api_key', 'POST /rl/limit',           'PROXY-CALLABLE — live Upstash credential.'),
  ('ratelimit.increment', 'redis-cloud','{byo}',               'api_key', 'Redis INCR + EXPIRE',      'Atomic increment.'),
  ('ratelimit.increment', 'momento',    '{byo}',               'api_key', 'POST /cache/{name}/{key}', 'Set/increment via HTTP API.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- ratelimit.reset
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('ratelimit.reset', 'upstash',      '{byo,rhumb_managed}', 'api_key', 'POST /rl/reset',            'PROXY-CALLABLE — live Upstash credential.'),
  ('ratelimit.reset', 'redis-cloud',  '{byo}',               'api_key', 'Redis DEL {key}',           'Delete counter key.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- audit.log
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('audit.log', 'axiom',     '{byo}', 'api_key', 'POST /v1/datasets/{dataset}/ingest', 'Ingest structured events. Free: 500GB/mo ingestion.'),
  ('audit.log', 'datadog',   '{byo}', 'api_key', 'POST /api/v2/logs',                 'Log ingest API.'),
  ('audit.log', 'papertrail','{byo}', 'api_key', 'UDP syslog / HTTP',                 'Simple audit trail. Free: 48hr search.'),
  ('audit.log', 'workos',    '{byo}', 'api_key', 'POST /events',                      'Dedicated audit trail SaaS. Free tier.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- audit.query
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('audit.query', 'axiom',   '{byo}', 'api_key', 'POST /v1/datasets/{dataset}/query', 'APL query language, fast search.'),
  ('audit.query', 'datadog', '{byo}', 'api_key', 'GET /api/v2/logs/events',           'Log search API.'),
  ('audit.query', 'workos',  '{byo}', 'api_key', 'GET /events',                       'Filter by actor/target/action/time.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- audit.export
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('audit.export', 'axiom',  '{byo}', 'api_key', 'POST /v1/datasets/{dataset}/query', 'Format=tabular, export JSON/CSV.'),
  ('audit.export', 'workos', '{byo}', 'api_key', 'GET /events?limit=100&...',         'Paginate all events for export.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- ============================================================
-- Note: upstash ratelimit.* is rhumb_managed — Upstash credential
-- already in 1Password (Tester - Upstash), needs Railway env var:
-- RHUMB_CREDENTIAL_UPSTASH_API_KEY
-- ============================================================

-- Totals: 9 new capabilities, ~29 new mappings
-- Running total: ~228 capabilities, ~726 mappings

COMMIT;
