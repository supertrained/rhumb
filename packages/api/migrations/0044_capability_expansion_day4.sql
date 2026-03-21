-- Migration: 0044_capability_expansion_day4
-- Description: Day 4 capability expansion — 1 new capability (analytics.track), resolved all 8 remaining
--              zero-provider capabilities, stretch: added elasticsearch/opensearch to document.search,
--              zapier to webhook.deliver.
-- Date: 2026-03-21
-- Author: Helm (rhumb-access)
-- Result: 114 capabilities, 353 mappings, 0 zero-provider capabilities.

-- ============================================================
-- NEW CAPABILITY (1)
-- ============================================================

INSERT INTO capabilities (id, domain, action, description, input_hint, outcome) VALUES
('analytics.track', 'analytics', 'track', 'Track a user event or action for analytics and product insights', 'event_name, user_id, properties?, timestamp?', 'Event recorded with timestamp and confirmation')
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- SERVICE MAPPINGS — ZERO-PROVIDER RESOLUTION (8 caps → 28 mappings)
-- ============================================================

-- analytics.track → segment (6.4), posthog (6.9), mixpanel (6.2), amplitude (5.7)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('analytics.track', 'segment', '{byo,agent_vault}', 'api_key', 'POST /v1/track', 'Event tracking'),
('analytics.track', 'posthog', '{byo,agent_vault}', 'api_key', 'POST /v1/track', 'Event tracking'),
('analytics.track', 'mixpanel', '{byo}', 'api_key', 'POST /v1/track', 'Event tracking'),
('analytics.track', 'amplitude', '{byo}', 'api_key', 'POST /v1/track', 'Event tracking')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- analytics.query_metrics → segment, posthog, mixpanel, amplitude
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('analytics.query_metrics', 'segment', '{byo}', 'api_key', 'POST /v1/query', 'Product analytics query API'),
('analytics.query_metrics', 'posthog', '{byo}', 'api_key', 'POST /v1/query', 'Product analytics query API'),
('analytics.query_metrics', 'mixpanel', '{byo}', 'api_key', 'POST /v1/query', 'Product analytics query API'),
('analytics.query_metrics', 'amplitude', '{byo}', 'api_key', 'POST /v1/query', 'Product analytics query API')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- content.update → contentful (7.5), sanity (7.3), ghost (7.4), strapi (6.7)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('content.update', 'contentful', '{byo}', 'bearer', 'PUT /spaces/{spaceId}/entries/{entryId}', 'Headless CMS, structured content management'),
('content.update', 'sanity', '{byo}', 'bearer', 'POST /v2021-06-07/data/mutate/{dataset}', 'GROQ-based mutations, real-time content'),
('content.update', 'ghost', '{byo}', 'bearer', 'PUT /ghost/api/admin/posts/{id}/', 'Ghost CMS Admin API'),
('content.update', 'strapi', '{byo}', 'bearer', 'PUT /api/{contentType}/{id}', 'Open-source headless CMS')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- crm.log_activity → hubspot (4.6), pipedrive (5.6), salesforce (4.7)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('crm.log_activity', 'hubspot', '{byo}', 'bearer', 'POST /crm/v3/objects/notes', 'HubSpot CRM — activities via engagements API'),
('crm.log_activity', 'pipedrive', '{byo}', 'api_key', 'POST /v1/activities', 'Pipedrive activity logging'),
('crm.log_activity', 'salesforce', '{byo}', 'oauth2', 'POST /sobjects/Task', 'Salesforce Task/Activity object creation')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- devops.rollback → github-actions (8.0), argocd (7.6), render (6.5)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('devops.rollback', 'github-actions', '{byo}', 'bearer', 'POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches', 'Trigger rollback workflow dispatch'),
('devops.rollback', 'argocd', '{byo}', 'bearer', 'POST /api/v1/applications/{name}/rollback', 'ArgoCD native rollback to previous revision'),
('devops.rollback', 'render', '{byo}', 'bearer', 'POST /v1/services/{serviceId}/deploys/{deployId}/rollback', 'Render service rollback')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- document.convert → pdf-co (7.0), reducto (7.4), unstructured (7.0)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('document.convert', 'pdf-co', '{byo}', 'api_key', 'POST /pdf/convert/to/{format}', 'Document format conversion, HTML/Word/PDF'),
('document.convert', 'reducto', '{byo}', 'api_key', 'POST /parse', 'AI-native doc processing with format normalization'),
('document.convert', 'unstructured', '{byo}', 'api_key', 'POST /general/v0/general', 'Multi-format doc normalization to structured output')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- document.generate → pandadoc (6.4), docusign (6.7), openai
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('document.generate', 'pandadoc', '{byo}', 'bearer', 'POST /public/v1/documents', 'Template-based document generation + e-sign'),
('document.generate', 'docusign', '{byo}', 'bearer', 'POST /restapi/v2.1/accounts/{accountId}/envelopes', 'Contract + agreement generation with e-signature'),
('document.generate', 'openai', '{byo}', 'bearer', 'POST /v1/chat/completions', 'LLM-based document generation from prompt/template')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- feature.manage → launchdarkly (7.4), flagsmith (7.0), growthbook (7.1)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('feature.manage', 'launchdarkly', '{byo}', 'bearer', 'PATCH /api/v2/flags/{projectKey}/{featureFlagKey}', 'Flag CRUD + targeting rules management'),
('feature.manage', 'flagsmith', '{byo}', 'api_key', 'PUT /api/v1/features/{id}/', 'Feature flag management via REST'),
('feature.manage', 'growthbook', '{byo}', 'bearer', 'POST /api/v1/features', 'Feature and experiment lifecycle management')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- notification.manage_prefs → courier (7.4), knock (7.1), novu (6.6)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('notification.manage_prefs', 'courier', '{byo}', 'bearer', 'PUT /profiles/{user_id}', 'User notification preference management'),
('notification.manage_prefs', 'knock', '{byo}', 'bearer', 'PUT /v1/users/{user_id}/notification-preferences', 'Per-user notification preferences per channel'),
('notification.manage_prefs', 'novu', '{byo}', 'api_key', 'PUT /v1/subscribers/{subscriberId}/preferences', 'Subscriber notification preference update')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- ============================================================
-- STRETCH: Depth on high-value capabilities
-- ============================================================

-- document.search + elasticsearch (6.2), opensearch (7.3)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('document.search', 'elasticsearch', '{byo}', 'bearer', 'GET /{index}/_search', 'Battle-tested full-text search, BM25+kNN'),
('document.search', 'opensearch', '{byo}', 'bearer', 'GET /{index}/_search', 'Elasticsearch fork, AWS-managed, open-source')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- webhook.deliver + zapier (6.3)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('webhook.deliver', 'zapier', '{byo}', 'bearer', 'POST /hooks/catch/{zap_id}/', 'Zapier catch-hook for workflow automation triggers')
ON CONFLICT (capability_id, service_slug) DO NOTHING;
