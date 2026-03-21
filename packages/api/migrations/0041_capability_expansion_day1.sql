-- Migration: 0041_capability_expansion_day1
-- Description: Day 1 capability expansion — 3 new capabilities, 11 previously-unmapped capabilities mapped
-- Date: 2026-03-21
-- Author: Helm (rhumb-access)
-- Context: Standing order from Pedro — daily expansion cadence to reach 200+ capabilities.
--          Prioritized: (1) new domain coverage in build-plan gap categories,
--          (2) mapping 0-provider capabilities to scored services for routing/comparison value.

-- ============================================================
-- NEW CAPABILITIES (3)
-- ============================================================

-- Background Jobs / Queues — build plan priority category #8
INSERT INTO capabilities (id, domain, action, description, input_hint, outcome) VALUES
('queue.enqueue', 'queue', 'enqueue', 'Add a job or task to a background queue', 'queue_name, payload, delay_seconds?, priority?', 'Job enqueued with job ID and estimated run time'),
('queue.process', 'queue', 'process', 'Trigger or consume jobs from a background queue', 'queue_name, batch_size?, filter?', 'Processed jobs with results and status')
ON CONFLICT (id) DO NOTHING;

-- Customer Support — high provider count, high agent demand
INSERT INTO capabilities (id, domain, action, description, input_hint, outcome) VALUES
('support.create_ticket', 'support', 'create_ticket', 'Create a customer support ticket or conversation', 'subject, description, requester_email, priority?, tags?', 'Ticket created with tracking ID and status URL')
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- NEW CAPABILITY-SERVICE MAPPINGS FOR NEW CAPABILITIES (9)
-- ============================================================

-- queue.enqueue → inngest (7.2), temporal (7.5), trigger-dev (6.8)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('queue.enqueue', 'inngest', '{byo,agent_vault}', 'bearer', 'POST /api/inngest (event trigger)', 'Event-driven, serverless-first'),
('queue.enqueue', 'temporal', '{byo,agent_vault}', 'bearer', 'POST /api/v1/namespaces/{ns}/workflows', 'Durable workflow execution'),
('queue.enqueue', 'trigger-dev', '{byo,agent_vault}', 'bearer', 'POST /api/v1/events', 'Developer-first background jobs')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- queue.process → inngest (7.2), temporal (7.5), trigger-dev (6.8)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern) VALUES
('queue.process', 'inngest', '{byo,agent_vault}', 'bearer', 'POST /api/inngest (function invoke)'),
('queue.process', 'temporal', '{byo,agent_vault}', 'bearer', 'POST /api/v1/namespaces/{ns}/workflows/{id}/signal'),
('queue.process', 'trigger-dev', '{byo,agent_vault}', 'bearer', 'POST /api/v1/runs')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- support.create_ticket → zendesk (7.0), intercom (7.1), freshdesk (6.5)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('support.create_ticket', 'zendesk', '{byo,agent_vault}', 'bearer', 'POST /api/v2/tickets', 'Industry standard, REST API'),
('support.create_ticket', 'intercom', '{byo,agent_vault}', 'bearer', 'POST /conversations', 'Conversation-based model'),
('support.create_ticket', 'freshdesk', '{byo,agent_vault}', 'bearer', 'POST /api/v2/tickets', 'Simple REST, good free tier')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- ============================================================
-- MAP EXISTING 0-PROVIDER CAPABILITIES TO SCORED SERVICES (27 mappings)
-- ============================================================

-- compute.execute_code → e2b (7.8), modal (7.6), replit (6.9)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('compute.execute_code', 'e2b', '{byo,agent_vault}', 'bearer', 'POST /api/v1/sandboxes/{id}/code', 'Cloud sandboxes for AI agents, Python/JS/TS'),
('compute.execute_code', 'modal', '{byo}', 'bearer', 'modal.Function.remote()', 'Serverless GPU/CPU compute, Python-first'),
('compute.execute_code', 'replit', '{byo}', 'bearer', 'POST /v1/repls/{id}/exec', 'Browser-based IDE with API')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- compute.create_sandbox → e2b (7.8), modal (7.6)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('compute.create_sandbox', 'e2b', '{byo,agent_vault}', 'bearer', 'POST /api/v1/sandboxes', 'Purpose-built for AI agent sandboxes'),
('compute.create_sandbox', 'modal', '{byo}', 'bearer', 'modal.Sandbox.create()', 'Persistent sandboxes via Modal SDK')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- compute.run_function → modal (7.6), e2b (7.8)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('compute.run_function', 'modal', '{byo}', 'bearer', 'modal.Function.remote()', 'Serverless function execution'),
('compute.run_function', 'e2b', '{byo,agent_vault}', 'bearer', 'POST /api/v1/sandboxes/{id}/code', 'Execute function in isolated sandbox')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- search.web_search → tavily (7.2), exa (7.3), brave-search (7.1)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, cost_per_call, free_tier_calls, notes) VALUES
('search.web_search', 'tavily', '{byo,agent_vault}', 'api_key', 'POST /search', 0.01, 1000, 'Purpose-built for AI agent search'),
('search.web_search', 'exa', '{byo,agent_vault}', 'api_key', 'POST /search', 0.003, 1000, 'Neural search engine, returns full content'),
('search.web_search', 'brave-search', '{byo}', 'api_key', 'GET /res/v1/web/search', NULL, 2000, 'Privacy-focused, generous free tier')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- document.extract → google-document-ai (7.4), reducto (7.4), unstructured (7.0)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, cost_per_call, free_tier_calls, notes) VALUES
('document.extract', 'google-document-ai', '{byo}', 'oauth2', 'POST /v1/projects/{project}/locations/{location}/processors/{processor}:process', 0.01, 1000, 'Enterprise-grade OCR and form parsing'),
('document.extract', 'reducto', '{byo}', 'api_key', 'POST /parse', NULL, NULL, 'AI-native document parsing, tables and forms'),
('document.extract', 'unstructured', '{byo}', 'api_key', 'POST /general/v0/general', NULL, NULL, 'Open-source compatible, multi-format extraction')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- storage.list → aws-s3 (8.1), cloudflare-r2 (7.4), google-cloud-storage (7.8), backblaze-b2 (6.6)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('storage.list', 'aws-s3', '{byo}', 'aws_sigv4', 'GET /{bucket}?list-type=2', 'Industry standard, S3 API compatible'),
('storage.list', 'cloudflare-r2', '{byo}', 'aws_sigv4', 'GET /{bucket}?list-type=2', 'S3-compatible, zero egress fees'),
('storage.list', 'google-cloud-storage', '{byo}', 'oauth2', 'GET /storage/v1/b/{bucket}/o', 'Google Cloud native, also supports S3 interop'),
('storage.list', 'backblaze-b2', '{byo}', 'api_key', 'GET /b2api/v3/b2_list_file_names', 'S3-compatible, lowest-cost storage')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- auth.verify_identity → persona (7.5), onfido (7.4), stripe-identity (7.4), jumio (7.3)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, cost_per_call, notes) VALUES
('auth.verify_identity', 'persona', '{byo}', 'bearer', 'POST /api/v1/inquiries', 0.50, 'KYC/KYB identity verification'),
('auth.verify_identity', 'onfido', '{byo}', 'bearer', 'POST /v3.6/checks', 1.00, 'Document + biometric verification'),
('auth.verify_identity', 'stripe-identity', '{byo}', 'bearer', 'POST /v1/identity/verification_sessions', 1.50, 'Stripe-native identity verification'),
('auth.verify_identity', 'jumio', '{byo}', 'bearer', 'POST /api/v1/accounts', 2.00, 'Enterprise KYC, AI-powered')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- data.validate → kickbox (7.1), zerobounce (7.2), neverbounce (7.0)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, cost_per_call, free_tier_calls, notes) VALUES
('data.validate', 'kickbox', '{byo}', 'api_key', 'GET /v2/verify?email={email}', 0.01, 100, 'Email verification and deliverability'),
('data.validate', 'zerobounce', '{byo}', 'api_key', 'GET /v2/validate?email={email}', 0.008, 100, 'Email validation with abuse/spam detection'),
('data.validate', 'neverbounce', '{byo}', 'api_key', 'GET /v4/single/check?email={email}', 0.008, 0, 'Real-time email verification')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- communication.send_push → onesignal (6.8), courier (7.4), knock (7.1)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, free_tier_calls, notes) VALUES
('communication.send_push', 'onesignal', '{byo}', 'api_key', 'POST /api/v1/notifications', 10000, 'Multi-platform push, generous free tier'),
('communication.send_push', 'courier', '{byo}', 'bearer', 'POST /send', 10000, 'Multi-channel notification orchestration'),
('communication.send_push', 'knock', '{byo}', 'bearer', 'POST /v1/workflows/{key}/trigger', 10000, 'Notification infrastructure, workflow-driven')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- email.verify → kickbox (7.1), zerobounce (7.2), neverbounce (7.0)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, cost_per_call, free_tier_calls, notes) VALUES
('email.verify', 'kickbox', '{byo}', 'api_key', 'GET /v2/verify?email={email}', 0.01, 100, 'Inbox verification + deliverability scoring'),
('email.verify', 'zerobounce', '{byo}', 'api_key', 'GET /v2/validate?email={email}', 0.008, 100, 'Abuse detection + bounce analysis'),
('email.verify', 'neverbounce', '{byo}', 'api_key', 'GET /v4/single/check?email={email}', 0.008, 0, 'Bulk + single email verification')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- ai.classify → openai, google-ai, anthropic
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('ai.classify', 'openai', '{byo}', 'bearer', 'POST /v1/chat/completions', 'Classification via structured output or function calling'),
('ai.classify', 'google-ai', '{byo}', 'api_key', 'POST /v1/models/{model}:generateContent', 'Gemini-based classification with structured output'),
('ai.classify', 'anthropic', '{byo}', 'api_key', 'POST /v1/messages', 'Classification via tool_use or structured prompting')
ON CONFLICT (capability_id, service_slug) DO NOTHING;
