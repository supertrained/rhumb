-- Migration 0062: Capability expansion Day 18
-- 10 new capabilities across 4 domains: chat, code, seo, export
-- Running total: ~247 capabilities / ~790 mappings

BEGIN;

-- ============================================================
-- NEW CAPABILITIES
-- ============================================================
INSERT INTO capabilities (id, domain, description, status) VALUES
  -- Chat / LLM inference (3)
  ('chat.complete',        'chat',   'Single-turn or multi-turn chat completion',              'active'),
  ('chat.stream',          'chat',   'Streaming chat completion (SSE or chunked response)',    'active'),
  ('chat.function_call',   'chat',   'Chat completion with structured function/tool calling', 'active'),
  -- Code tooling (3)
  ('code.format',          'code',   'Auto-format source code according to a style guide',    'active'),
  ('code.lint',            'code',   'Static analysis and lint check on source code',         'active'),
  ('code.analyze',         'code',   'Extract structure, symbols, or metrics from code',      'active'),
  -- SEO / search intelligence (2)
  ('seo.check',            'seo',    'Audit a URL for on-page SEO signals and issues',        'active'),
  ('seo.keywords',         'seo',    'Fetch keyword volume, difficulty, and ranking data',    'active'),
  -- Data export (2)
  ('export.csv',           'export', 'Convert structured data to a CSV file or stream',      'active'),
  ('export.xlsx',          'export', 'Convert structured data to an Excel (xlsx) workbook',  'active')
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- PROVIDER MAPPINGS
-- ============================================================

-- chat.complete
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('chat.complete', 'openai',     '{byo}', 'api_key', 'POST /v1/chat/completions',    'GPT-4o and o-series. Pay-per-token.'),
  ('chat.complete', 'anthropic',  '{byo}', 'api_key', 'POST /v1/messages',            'Claude 3.x/4.x family. Pay-per-token.'),
  ('chat.complete', 'groq',       '{byo}', 'api_key', 'POST /openai/v1/chat/completions', 'Ultra-low-latency inference. Free tier available.'),
  ('chat.complete', 'mistral',    '{byo}', 'api_key', 'POST /v1/chat/completions',    'Mistral and Mixtral models. Free tier available.'),
  ('chat.complete', 'together-ai','{byo}', 'api_key', 'POST /v1/chat/completions',    '100+ open-source models. $5 free credits.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- chat.stream
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('chat.stream', 'openai',    '{byo}', 'api_key', 'POST /v1/chat/completions (stream=true)',    'SSE token streaming.'),
  ('chat.stream', 'anthropic', '{byo}', 'api_key', 'POST /v1/messages (stream=true)',            'SSE delta streaming.'),
  ('chat.stream', 'groq',      '{byo}', 'api_key', 'POST /openai/v1/chat/completions (stream=true)', 'Lowest-latency streaming available.'),
  ('chat.stream', 'mistral',   '{byo}', 'api_key', 'POST /v1/chat/completions (stream=true)',    'SSE streaming.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- chat.function_call
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('chat.function_call', 'openai',    '{byo}', 'api_key', 'POST /v1/chat/completions (tools=[...])', 'Parallel tool calling, JSON mode.'),
  ('chat.function_call', 'anthropic', '{byo}', 'api_key', 'POST /v1/messages (tools=[...])',          'Native tool use with input_schema.'),
  ('chat.function_call', 'groq',      '{byo}', 'api_key', 'POST /openai/v1/chat/completions (tools=[...])', 'OpenAI-compatible tool calling.'),
  ('chat.function_call', 'mistral',   '{byo}', 'api_key', 'POST /v1/chat/completions (tools=[...])', 'Native function calling support.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- code.format
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('code.format', 'e2b',          '{byo,rhumb_managed}', 'api_key', 'Sandbox exec: prettier/black/gofmt', 'PROXY-CALLABLE — run any formatter in an E2B sandbox.'),
  ('code.format', 'sourcegraph',  '{byo}', 'api_key', 'POST /api/code-intelligence/format', 'Sourcegraph code formatting.'),
  ('code.format', 'github-api',   '{byo}', 'api_key', 'GitHub Actions runner',               'CI-based formatting via GitHub API.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- code.lint
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('code.lint', 'e2b',         '{byo,rhumb_managed}', 'api_key', 'Sandbox exec: eslint/pylint/clippy', 'PROXY-CALLABLE — run any linter in an E2B sandbox.'),
  ('code.lint', 'sonarcloud',  '{byo}', 'api_key', 'POST /api/issues/search',             'SonarCloud SAST. Free for public repos.'),
  ('code.lint', 'deepsource',  '{byo}', 'api_key', 'GraphQL API',                         'Automated code review.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- code.analyze
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('code.analyze', 'github-api',   '{byo}', 'api_key', 'GET /repos/{owner}/{repo}/contents', 'Tree + blob traversal for static analysis.'),
  ('code.analyze', 'sourcegraph',  '{byo}', 'api_key', 'POST /api/graphql',                  'Symbol extraction, references, SCIP.'),
  ('code.analyze', 'sonarcloud',   '{byo}', 'api_key', 'GET /api/measures/component',        'Complexity, coverage, duplication metrics.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- seo.check
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('seo.check', 'dataforseo',  '{byo}', 'basic_auth', 'POST /v3/on_page/task_post',   'On-page SEO audit. Pay-per-task.'),
  ('seo.check', 'semrush',     '{byo}', 'api_key',    'GET /reports/analytics/backlinks/', 'Site audit API. 10 req/day free.'),
  ('seo.check', 'moz',         '{byo}', 'api_key',    'POST /v2/url_metrics',          'DA, PA, spam score. 5 req/day free.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- seo.keywords
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('seo.keywords', 'dataforseo', '{byo}', 'basic_auth', 'POST /v3/keywords_data/google_ads/search_volume/task_post', 'Volume + CPC + competition.'),
  ('seo.keywords', 'semrush',    '{byo}', 'api_key',    'GET /reports/analytics/phrase_all/',   'Keyword overview, SERP features.'),
  ('seo.keywords', 'moz',        '{byo}', 'api_key',    'POST /v2/keyword_difficulty',          'KD score + SERP difficulty.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- export.csv
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('export.csv', 'flatfile',    '{byo}', 'api_key', 'POST /v1/workbooks',           'Managed CSV import/export pipelines.'),
  ('export.csv', 'dataexporter','{byo}', 'api_key', 'POST /api/v1/exports',         'Scheduled data exports to CSV.'),
  ('export.csv', 'airbyte',     '{byo}', 'api_key', 'POST /v1/connections/sync',    'Airbyte CSV destination connector.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- export.xlsx
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('export.xlsx', 'flatfile',    '{byo}', 'api_key', 'POST /v1/workbooks',           'XLSX workbook generation.'),
  ('export.xlsx', 'pdfmonkey',   '{byo}', 'api_key', 'POST /api/v1/documents',       'Template-driven Excel export.'),
  ('export.xlsx', 'dbtcloud',    '{byo}', 'api_key', 'GET /api/v2/accounts/{id}/runs', 'Export dbt run results as tabular data.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- ============================================================
-- Summary
-- 10 new capabilities: chat.complete, chat.stream, chat.function_call,
--   code.format, code.lint, code.analyze, seo.check, seo.keywords,
--   export.csv, export.xlsx
-- ~33 new mappings
-- Running total: ~247 capabilities / ~789 mappings
-- ============================================================

COMMIT;
