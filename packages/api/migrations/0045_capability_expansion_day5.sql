-- Migration: 0045_capability_expansion_day5
-- Description: Day 5 capability expansion — 11 new capabilities (logging, payment, security, geo,
--              finance, billing, queue messaging, content moderation, authorization) + provider depth.
-- Date: 2026-03-21
-- Author: Helm (rhumb-access)
-- Result: 125 capabilities, 393 mappings.

-- ============================================================
-- NEW CAPABILITIES (11)
-- ============================================================

INSERT INTO capabilities (id, domain, action, description, input_hint, outcome) VALUES
('logging.ingest', 'logging', 'ingest', 'Send log events or structured logs to a centralized logging service', 'log_lines, level?, source?, tags?', 'Logs ingested with confirmation and ingestion ID'),
('logging.search', 'logging', 'search', 'Query and search logs from a centralized logging platform', 'query, time_from?, time_to?, limit?', 'Matching log entries with timestamps and metadata'),
('payment.create_link', 'payment', 'create_link', 'Generate a shareable payment link or hosted checkout page', 'amount, currency, description?, customer_email?, metadata?', 'Payment link URL and link ID'),
('payment.manage_subscription', 'payment', 'manage_subscription', 'Update, pause, cancel, or resume a recurring subscription', 'subscription_id, action (pause|cancel|resume|update), new_plan?', 'Updated subscription object with status and next billing date'),
('security.scan_code', 'security', 'scan_code', 'Scan source code or dependencies for vulnerabilities and security issues', 'repo_url or package_manifest, scan_type?', 'Vulnerability list with severity, CVE IDs, and remediation hints'),
('geo.lookup', 'geo', 'lookup', 'Resolve an IP address or postal code to geographic location data', 'ip_address or postal_code, fields?', 'Country, region, city, coordinates, and timezone'),
('finance.get_account', 'finance', 'get_account', 'Retrieve a bank account balance or transaction history via Open Banking or fintech API', 'account_id, date_from?, date_to?, limit?', 'Account balance, currency, and recent transactions'),
('billing.manage_subscription', 'billing', 'manage_subscription', 'Create, update, pause, or cancel a subscription billing plan for a customer', 'customer_id, action (create|update|pause|cancel), plan_id?, metadata?', 'Updated subscription object with status and next billing date'),
('queue.publish_message', 'queue', 'publish_message', 'Publish a message to a message queue or event streaming topic', 'topic, message, partition_key?, headers?', 'Published message ID and offset or sequence number'),
('content.moderate', 'content', 'moderate', 'Classify and score content for harmful or policy-violating material', 'text or image_url, categories?', 'Moderation verdict with category scores and recommended action'),
('authz.check_permission', 'authz', 'check_permission', 'Evaluate whether a user or principal has permission to perform an action on a resource', 'user_id, action, resource, context?', 'Boolean allow/deny with matching policy rule')
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- SERVICE MAPPINGS — NEW CAPABILITIES (39 new mappings)
-- ============================================================

-- logging.ingest → datadog (7.8), logtail (7.2), betterstack (6.6), sentry (7.6)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('logging.ingest', 'datadog', '{byo}', 'api_key', 'POST /api/v2/logs', 'Structured log ingestion'),
('logging.ingest', 'logtail', '{byo}', 'bearer', 'POST /', 'BetterStack Logs — structured log ingestion'),
('logging.ingest', 'betterstack', '{byo}', 'bearer', 'POST /', 'BetterStack logging platform'),
('logging.ingest', 'sentry', '{byo}', 'bearer', 'POST /api/{project}/store/', 'Error + event ingestion')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- logging.search → datadog, logtail, opensearch, sentry
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('logging.search', 'datadog', '{byo}', 'api_key', 'POST /api/v2/logs/events/search', 'DDQL log query with time filters'),
('logging.search', 'logtail', '{byo}', 'bearer', 'GET /query', 'SQL-like log search'),
('logging.search', 'opensearch', '{byo}', 'bearer', 'GET /{index}/_search', 'Elasticsearch-compatible log search'),
('logging.search', 'sentry', '{byo}', 'bearer', 'GET /api/0/projects/{org}/{project}/events/', 'Error event search and aggregation')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- payment.create_link → stripe (8.1), paddle (7.0), lemonsqueezy (6.8)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('payment.create_link', 'stripe', '{byo}', 'bearer', 'POST /v1/payment_links', 'Stripe Payment Links — no-code checkout'),
('payment.create_link', 'paddle', '{byo}', 'bearer', 'POST /checkout/url', 'Paddle Checkout — MoR, handles VAT automatically'),
('payment.create_link', 'lemonsqueezy', '{byo}', 'bearer', 'POST /v1/checkouts', 'Lemon Squeezy — SaaS-native checkout')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- payment.manage_subscription → stripe, paddle, lemonsqueezy
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('payment.manage_subscription', 'stripe', '{byo}', 'bearer', 'POST /v1/subscriptions/{id}', 'Full subscription lifecycle management'),
('payment.manage_subscription', 'paddle', '{byo}', 'bearer', 'PATCH /subscriptions/{id}', 'Paddle subscription management with MoR'),
('payment.manage_subscription', 'lemonsqueezy', '{byo}', 'bearer', 'PATCH /v1/subscriptions/{id}', 'SaaS subscription CRUD')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- security.scan_code → snyk (7.5), sonarqube (7.2), semgrep (7.3)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('security.scan_code', 'snyk', '{byo}', 'bearer', 'POST /api/v1/test', 'Dependency + code vulnerability scanning'),
('security.scan_code', 'sonarqube', '{byo}', 'bearer', 'GET /api/issues/search', 'Code quality + security issue detection'),
('security.scan_code', 'semgrep', '{byo}', 'bearer', 'POST /api/v1/scan', 'SAST scanning, 2000+ open rules')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- geo.lookup → ipinfo (7.2), maxmind (7.0), radar (7.4)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, free_tier_calls, notes) VALUES
('geo.lookup', 'ipinfo', '{byo,agent_vault}', 'bearer', 'GET /{ip}', 50000, 'IP geolocation + ASN, 50k/month free'),
('geo.lookup', 'maxmind', '{byo}', 'api_key', 'GET /geoip/v2.1/city/{ip}', NULL, 'MaxMind GeoIP2 — city + country accuracy'),
('geo.lookup', 'radar', '{byo}', 'api_key', 'GET /v1/geocode/ip/{ip}', NULL, 'IP + address geolocation')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- finance.get_account → plaid (7.5), brex (7.2), mercury (7.1)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('finance.get_account', 'plaid', '{byo}', 'bearer', 'POST /accounts/get', 'Open banking — balance + transactions via Plaid Link'),
('finance.get_account', 'brex', '{byo}', 'bearer', 'GET /v2/accounts/cash', 'Brex corporate card + balance API'),
('finance.get_account', 'mercury', '{byo}', 'bearer', 'GET /api/v1/accounts', 'Mercury startup banking API')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- billing.manage_subscription → chargebee (7.4), recurly (7.2), zuora (7.0)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('billing.manage_subscription', 'chargebee', '{byo}', 'api_key', 'POST /api/v2/subscriptions/{id}/update_for_items', 'Full subscription billing lifecycle'),
('billing.manage_subscription', 'recurly', '{byo}', 'bearer', 'PUT /subscriptions/{uuid}', 'Subscription management with dunning'),
('billing.manage_subscription', 'zuora', '{byo}', 'bearer', 'PUT /v1/subscriptions/{subscription_key}', 'Enterprise subscription billing')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- queue.publish_message → confluent-kafka (7.5), upstash-kafka (7.1), amazon-sqs (7.5)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('queue.publish_message', 'confluent-kafka', '{byo}', 'api_key', 'POST /kafka/v3/clusters/{cluster_id}/topics/{topic_name}/records', 'Confluent Cloud managed Kafka'),
('queue.publish_message', 'upstash-kafka', '{byo}', 'bearer', 'POST /produce/{topic}', 'Serverless Kafka, per-request pricing'),
('queue.publish_message', 'amazon-sqs', '{byo}', 'aws_sigv4', 'POST /?Action=SendMessage', 'AWS SQS — standard + FIFO queues')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- content.moderate → hive-moderation, sightengine
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('content.moderate', 'hive-moderation', '{byo}', 'bearer', 'POST /api/v2/task/sync', 'Image + text moderation, multi-category'),
('content.moderate', 'sightengine', '{byo}', 'api_key', 'GET /1.0/check.json', 'Real-time image + video content moderation')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- authz.check_permission → permit-io (7.5), cerbos (7.4), openfga (7.3)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('authz.check_permission', 'permit-io', '{byo}', 'bearer', 'POST /v2/allowed', 'ReBAC/ABAC permission check engine'),
('authz.check_permission', 'cerbos', '{byo}', 'bearer', 'POST /api/check/resources', 'Policy-as-code authorization engine'),
('authz.check_permission', 'openfga', '{byo}', 'bearer', 'POST /stores/{store_id}/check', 'Google Zanzibar-inspired fine-grained authz')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- ============================================================
-- DEPTH: Add providers to thin capabilities
-- ============================================================

-- monitoring.push_metric +new-relic, +honeycomb
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('monitoring.push_metric', 'new-relic', '{byo}', 'api_key', 'POST /metric/v1', 'New Relic dimensional metrics API'),
('monitoring.push_metric', 'honeycomb', '{byo}', 'api_key', 'POST /1/events/{dataset}', 'Honeycomb structured event ingestion')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- ai.generate_image +fal-ai
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('ai.generate_image', 'fal-ai', '{byo}', 'bearer', 'POST /fal-ai/fast-sdxl', 'Fast SDXL + Flux image generation')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- payment.invoice +paddle, +lemonsqueezy
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('payment.invoice', 'paddle', '{byo}', 'bearer', 'POST /transactions', 'Paddle invoice/transaction creation'),
('payment.invoice', 'lemonsqueezy', '{byo}', 'bearer', 'GET /v1/orders/{id}', 'Lemon Squeezy order/invoice retrieval')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- payment.payout +square
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, notes) VALUES
('payment.payout', 'square', '{byo}', 'bearer', 'POST /v2/payouts', 'Square payouts API')
ON CONFLICT (capability_id, service_slug) DO NOTHING;
