-- Migration 0012: Create failure_modes table and seed top 10 services
-- Uses service_slug (text) instead of service_id (UUID FK) for simplicity with REST API

CREATE TABLE IF NOT EXISTS failure_modes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  service_slug TEXT NOT NULL,
  category TEXT NOT NULL,         -- e.g. "auth", "rate-limiting", "schema", "error-handling"
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  severity TEXT NOT NULL,         -- "critical", "high", "medium", "low"
  frequency TEXT NOT NULL,        -- "common", "occasional", "rare"
  agent_impact TEXT,              -- How this specifically affects agents
  workaround TEXT,                -- Known mitigation
  first_detected TIMESTAMPTZ DEFAULT now(),
  last_verified TIMESTAMPTZ DEFAULT now(),
  resolved_at TIMESTAMPTZ,       -- NULL = still active
  evidence_count INT DEFAULT 1,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_failure_modes_slug ON failure_modes(service_slug, resolved_at);
CREATE INDEX IF NOT EXISTS idx_failure_modes_severity ON failure_modes(severity);

-- Enable RLS
ALTER TABLE failure_modes ENABLE ROW LEVEL SECURITY;

-- Read access for anon and authenticated
CREATE POLICY "failure_modes_read" ON failure_modes FOR SELECT USING (true);

-- ============================================================
-- SEED DATA: Top 10 services by AN Score
-- ============================================================

-- Stripe (8.09)
INSERT INTO failure_modes (service_slug, category, title, description, severity, frequency, agent_impact, workaround) VALUES
('stripe', 'rate-limiting', 'Aggressive rate limits on test mode', 'Test mode rate limits are lower than live mode. Agents running integration tests hit 429s faster than expected, especially on list endpoints.', 'medium', 'common', 'Agent test suites fail intermittently. Retry logic may mask the root cause, leading to flaky CI.', 'Implement exponential backoff with jitter. Use Stripe test clocks for time-dependent tests instead of rapid-fire API calls.'),
('stripe', 'auth', 'Restricted key scope confusion', 'Restricted API keys silently return empty results instead of 403 when accessing resources outside their scope. Agents may interpret empty responses as "no data" rather than "no permission."', 'high', 'occasional', 'Agent believes no customers exist when it simply lacks read permission. Can lead to incorrect business logic execution.', 'Always test restricted keys explicitly. Check response headers for scope indicators. Prefer full secret keys in trusted environments.'),
('stripe', 'schema', 'Webhook payload version drift', 'Stripe webhooks send payloads matching the API version set on the account, not the version the agent expects. Schema drift causes silent parsing failures.', 'high', 'occasional', 'Agent webhook handler processes events with unexpected field structures. May silently drop data or crash on missing fields.', 'Pin webhook endpoint to a specific API version. Always validate incoming payload structure before processing.');

-- Resend (7.79)
INSERT INTO failure_modes (service_slug, category, title, description, severity, frequency, agent_impact, workaround) VALUES
('resend', 'rate-limiting', 'Burst rate limit on free tier', 'Free tier allows 100 emails/day with a 1 email/second burst limit. Agents sending batch notifications hit limits quickly with no queuing.', 'medium', 'common', 'Batch email operations fail partway through. Agent may not know which emails succeeded vs failed without checking each response.', 'Implement client-side rate limiting (1 req/sec). Use batch endpoint when available. Upgrade to paid tier for production workloads.'),
('resend', 'error-handling', 'Non-standard error response format', 'Some error responses return a flat string message instead of the documented JSON error object. Parsing logic expecting structured errors may crash.', 'medium', 'rare', 'Agent error handling fails on malformed error responses, potentially causing unhandled exceptions in retry logic.', 'Wrap all error parsing in try/catch. Fall back to raw response body as error message when JSON parsing fails.');

-- GitHub (7.8)
INSERT INTO failure_modes (service_slug, category, title, description, severity, frequency, agent_impact, workaround) VALUES
('github', 'rate-limiting', 'Secondary rate limits on content creation', 'Beyond the primary 5000 req/hour limit, GitHub enforces undocumented secondary rate limits on write operations (issues, comments, PRs). Agents creating multiple items in quick succession get 403s.', 'high', 'common', 'Agent workflows that create multiple issues or PR comments in sequence fail unpredictably. The 403 looks different from a permissions error.', 'Add 1-second delays between write operations. Check for "secondary rate limit" in error message body. Implement progressive backoff.'),
('github', 'auth', 'Fine-grained PAT scope inheritance confusion', 'Fine-grained personal access tokens have complex permission inheritance across org/repo/endpoint. Agents may have partial access that produces confusing 404s (not 403s) on resources they cannot see.', 'medium', 'occasional', 'Agent receives 404 for repos that exist but are invisible to its token scope. May incorrectly conclude the resource does not exist.', 'Use classic PATs for broad access. For fine-grained tokens, explicitly test each required endpoint at startup and fail fast.'),
('github', 'schema', 'GraphQL schema deprecation without warning', 'GitHub''s GraphQL API deprecates fields with minimal notice. Agents relying on deprecated fields get null values instead of errors.', 'medium', 'occasional', 'Agent data pipeline silently receives null for previously-populated fields. Score calculations or reports become inaccurate without obvious errors.', 'Pin to REST API for critical data paths. Monitor GitHub changelog for GraphQL deprecations. Add null-checks with alerting on critical fields.');

-- Supabase (7.5)
INSERT INTO failure_modes (service_slug, category, title, description, severity, frequency, agent_impact, workaround) VALUES
('supabase', 'connection', 'Connection pooler timeout on cold start', 'Supabase connection pooler (pgBouncer) can timeout on first connection after idle period. Default timeout is aggressive for serverless environments.', 'medium', 'common', 'Agent''s first database query after idle period fails. If no retry logic, the entire operation aborts.', 'Implement connection retry with 2-second initial delay. Use session pooler mode (port 5432) for persistent connections. Add health check pings.'),
('supabase', 'auth', 'RLS policy silent data filtering', 'Row Level Security policies silently filter results rather than returning permission errors. Agents querying with wrong auth context get empty results, not errors.', 'high', 'common', 'Agent believes table is empty when RLS is filtering all rows. Extremely hard to debug — no error message, just missing data.', 'Always verify RLS context by testing with known-existing data. Use service_role key for administrative operations. Add explicit RLS policy tests.');

-- Meilisearch (7.49)
INSERT INTO failure_modes (service_slug, category, title, description, severity, frequency, agent_impact, workaround) VALUES
('meilisearch', 'async-ops', 'Task queue backlog on large imports', 'Document indexing is async. Large batch imports create a task queue backlog where search results are stale for minutes. No push notification when indexing completes.', 'medium', 'occasional', 'Agent indexes documents then immediately searches — gets stale or empty results. May incorrectly conclude import failed.', 'Poll task status endpoint after import. Wait for task completion before querying. Set realistic timeout for large batches (1000+ docs = minutes, not seconds).'),
('meilisearch', 'schema', 'Implicit schema inference on first document', 'Meilisearch infers field types from the first document indexed. Later documents with different types for the same field cause silent data loss or indexing errors.', 'high', 'rare', 'Agent sends heterogeneous documents and gets partial indexing. No clear error — some documents just missing from search results.', 'Define explicit schema (filterable/sortable attributes) before first import. Validate document structure client-side before sending.');

-- Clerk (7.43)
INSERT INTO failure_modes (service_slug, category, title, description, severity, frequency, agent_impact, workaround) VALUES
('clerk', 'auth', 'JWT verification clock skew', 'Clerk JWTs have tight expiry windows (60s default). Server clock skew >5s causes valid tokens to fail verification. Common in containerized environments.', 'medium', 'occasional', 'Agent auth middleware rejects valid requests intermittently. Users appear randomly logged out. Hard to reproduce locally.', 'Add 10-second clock tolerance to JWT verification. Sync container clocks via NTP. Use Clerk''s backend SDK which handles this automatically.'),
('clerk', 'webhook', 'Webhook signature verification timing', 'Clerk webhook signatures use a timestamp that must be within 5 minutes. Slow webhook processing or queue delays cause legitimate webhooks to fail verification.', 'medium', 'occasional', 'Agent loses webhook events when processing queue has any latency. No retry from Clerk side — event is permanently lost.', 'Process webhook verification immediately on receipt, queue the payload for async processing after verification. Increase tolerance window if possible.');

-- Slack (7.2)
INSERT INTO failure_modes (service_slug, category, title, description, severity, frequency, agent_impact, workaround) VALUES
('slack', 'rate-limiting', 'Per-method rate limits with no global header', 'Slack rate limits are per-method, not global. There''s no single header showing remaining quota across all methods. Agents must track limits per-endpoint.', 'medium', 'common', 'Agent hits rate limit on chat.postMessage while other methods are fine. Global rate limiting strategies don''t work — must be per-method.', 'Implement per-method rate tracking. Use Slack''s Retry-After header. Prioritize critical messages (alerts) over bulk operations (channel history).'),
('slack', 'auth', 'Bot token vs user token confusion', 'Some Slack API methods require user tokens (xoxp-), others accept bot tokens (xoxb-). Documentation doesn''t always clearly distinguish. Agents using wrong token type get cryptic "not_authed" errors.', 'high', 'common', 'Agent fails on specific operations (e.g., searching messages) because it uses bot token where user token is required. Error message doesn''t indicate token type mismatch.', 'Maintain both token types. Check method documentation for required token type. Map operations to token types at initialization.');

-- Algolia (7.18)
INSERT INTO failure_modes (service_slug, category, title, description, severity, frequency, agent_impact, workaround) VALUES
('algolia', 'rate-limiting', 'Search operations count toward record quota', 'Algolia''s pricing model counts both records AND operations. High-volume agent queries can silently exceed the operations quota even with few records.', 'high', 'common', 'Agent search-heavy workflows hit billing limits unexpectedly. Service degrades (slower, then blocked) without clear error until quota is fully exhausted.', 'Monitor operations dashboard proactively. Cache frequent queries client-side. Implement query deduplication — agents often search the same thing repeatedly in a loop.'),
('algolia', 'schema', 'Facet value limits silently truncate results', 'Algolia limits facet values to 100 by default. Agents filtering by facets with >100 unique values get incomplete results with no warning.', 'medium', 'occasional', 'Agent category filtering misses items because facet enumeration is silently capped. Data analysis based on facets is incorrect.', 'Increase maxFacetHits in query parameters. Use browse endpoint for exhaustive enumeration. Never assume facet counts are complete.');

-- Typesense (7.11)
INSERT INTO failure_modes (service_slug, category, title, description, severity, frequency, agent_impact, workaround) VALUES
('typesense', 'schema', 'Strict schema enforcement rejects partial documents', 'Typesense requires all defined fields in every document (unless field is optional). Missing a single field causes the entire document to be rejected.', 'medium', 'common', 'Agent import batches fail when any document has a missing field. Single bad document can cause entire batch rejection depending on import mode.', 'Use dirty_values: "coerce_or_drop" in import params. Define non-critical fields as optional in schema. Validate documents before import.'),
('typesense', 'connection', 'Node failover requires client-side configuration', 'Multi-node Typesense clusters require the client to know all node addresses. No automatic discovery. If primary node fails, agent must have fallback configured.', 'medium', 'rare', 'Agent loses search capability when primary node goes down, even if cluster is healthy. No automatic reconnection to healthy nodes.', 'Configure all cluster nodes in client initialization. Use nearest-node option for latency optimization. Implement health check pings to detect node failures.');
