-- Seed: Capability Registry
-- 90+ capabilities mapped to 212 services
-- Date: 2026-03-16

-- ============================================================
-- CAPABILITIES (domain.action taxonomy)
-- ============================================================

INSERT INTO capabilities (id, domain, action, description, input_hint, outcome) VALUES
-- Email
('email.send', 'email', 'send', 'Send transactional or marketing email', 'recipient, subject, body, optional: from, template_id, attachments', 'Email delivered to recipient inbox'),
('email.verify', 'email', 'verify', 'Verify an email address is valid and deliverable', 'email_address', 'Verification result: valid, invalid, risky, or unknown'),
('email.template', 'email', 'template', 'Create or render an email template', 'template_id or template_content, merge_variables', 'Rendered HTML/text email content'),
('email.list_manage', 'email', 'list_manage', 'Manage email subscriber lists and segments', 'list_id, subscriber_email, action (add/remove/update)', 'Subscriber list updated'),
('email.track', 'email', 'track', 'Track email opens, clicks, and delivery events', 'message_id or webhook configuration', 'Event stream of email engagement data'),

-- Payments
('payment.charge', 'payment', 'charge', 'Process a one-time payment', 'amount, currency, payment_method, description', 'Payment captured or authorized'),
('payment.refund', 'payment', 'refund', 'Refund a previous payment', 'payment_id or charge_id, amount (optional for partial)', 'Refund processed'),
('payment.subscribe', 'payment', 'subscribe', 'Create a recurring subscription', 'customer_id, plan_id or price, billing_interval', 'Active subscription created'),
('payment.invoice', 'payment', 'invoice', 'Create and send an invoice', 'customer, line_items, due_date', 'Invoice created and optionally sent'),
('payment.payout', 'payment', 'payout', 'Send funds to a bank account or recipient', 'recipient, amount, currency', 'Payout initiated'),

-- AI / ML
('ai.generate_text', 'ai', 'generate_text', 'Generate text using a language model', 'prompt or messages, model (optional), max_tokens', 'Generated text completion'),
('ai.generate_image', 'ai', 'generate_image', 'Generate an image from a text prompt', 'prompt, size (optional), style (optional)', 'Generated image URL or binary'),
('ai.embed', 'ai', 'embed', 'Generate vector embeddings from text', 'text or texts array, model (optional)', 'Float array(s) of embedding vectors'),
('ai.transcribe', 'ai', 'transcribe', 'Transcribe audio to text', 'audio_url or audio_file, language (optional)', 'Transcribed text with optional timestamps'),
('ai.classify', 'ai', 'classify', 'Classify text into categories', 'text, categories or model', 'Classification label with confidence score'),
('ai.generate_speech', 'ai', 'generate_speech', 'Convert text to spoken audio', 'text, voice (optional), format (optional)', 'Audio file of spoken text'),

-- Data Enrichment
('data.enrich_person', 'data', 'enrich_person', 'Enrich a person profile with professional data', 'email or linkedin_url or name+company', 'Enriched profile: title, company, phone, social links'),
('data.enrich_company', 'data', 'enrich_company', 'Enrich a company profile with firmographic data', 'domain or company_name', 'Company data: size, industry, revenue, tech stack'),
('data.search_contacts', 'data', 'search_contacts', 'Search for contact information', 'domain, role, or name', 'List of matching contacts with available data'),
('data.validate', 'data', 'validate', 'Validate contact data (email, phone)', 'email or phone_number', 'Validation result with deliverability status'),

-- Authentication
('auth.authenticate', 'auth', 'authenticate', 'Authenticate a user or verify credentials', 'credentials (email+password, token, etc.)', 'Authentication result with session/token'),
('auth.verify_identity', 'auth', 'verify_identity', 'Verify user identity (MFA, email, phone)', 'user_id, verification_method', 'Verification status'),
('auth.manage_users', 'auth', 'manage_users', 'Create, update, or delete user accounts', 'user_data (email, name, role, etc.)', 'User account created/updated'),
('auth.sso', 'auth', 'sso', 'Configure or initiate single sign-on', 'provider, redirect_url, scopes', 'SSO redirect URL or token exchange'),

-- Storage
('storage.upload', 'storage', 'upload', 'Upload a file to cloud storage', 'file_content or file_url, path/key, content_type', 'Stored file URL/key'),
('storage.download', 'storage', 'download', 'Download a file from cloud storage', 'file_key or file_url', 'File content or download URL'),
('storage.list', 'storage', 'list', 'List files in a storage bucket/container', 'prefix or path, limit', 'List of file objects with metadata'),
('storage.presign', 'storage', 'presign', 'Generate a pre-signed URL for direct upload/download', 'file_key, expiration, method (GET/PUT)', 'Pre-signed URL valid for specified duration'),

-- Search
('search.index', 'search', 'index', 'Index a document or record for search', 'index_name, document_id, document_body', 'Document indexed'),
('search.query', 'search', 'query', 'Search indexed documents', 'query_string, index (optional), filters', 'Ranked search results with scores'),
('search.autocomplete', 'search', 'autocomplete', 'Get search suggestions for partial input', 'partial_query, index', 'List of completion suggestions'),

-- Communication
('communication.send_sms', 'communication', 'send_sms', 'Send an SMS message', 'to_phone, body, from_phone (optional)', 'SMS delivered'),
('communication.send_push', 'communication', 'send_push', 'Send a push notification', 'device_token or user_id, title, body', 'Push notification delivered'),
('communication.call', 'communication', 'call', 'Initiate a phone call', 'to_phone, from_phone, twiml or callback_url', 'Call initiated'),
('communication.send_message', 'communication', 'send_message', 'Send a message via chat platform', 'channel_id or user_id, message_text', 'Message sent'),

-- CRM
('crm.create_contact', 'crm', 'create_contact', 'Create a new contact/lead in CRM', 'name, email, company, phone (optional)', 'Contact record created with ID'),
('crm.update_deal', 'crm', 'update_deal', 'Update a deal/opportunity in CRM', 'deal_id, stage, value, notes', 'Deal record updated'),
('crm.log_activity', 'crm', 'log_activity', 'Log an activity (call, email, meeting) on a record', 'record_id, activity_type, description, timestamp', 'Activity logged'),
('crm.query', 'crm', 'query', 'Query CRM records with filters', 'object_type, filters, fields', 'List of matching CRM records'),

-- Database
('database.query', 'database', 'query', 'Execute a database query', 'query_string or structured query, parameters', 'Query results as rows/documents'),
('database.insert', 'database', 'insert', 'Insert records into a database', 'table/collection, records', 'Inserted record IDs'),
('database.vector_search', 'database', 'vector_search', 'Search by vector similarity', 'query_vector, collection, top_k, filters', 'Similar records ranked by distance'),

-- DevOps
('devops.deploy', 'devops', 'deploy', 'Deploy an application or service', 'project_id, environment, source (branch/image)', 'Deployment initiated with status URL'),
('devops.build', 'devops', 'build', 'Trigger a build/CI pipeline', 'repo, branch, config (optional)', 'Build started with run ID'),
('devops.monitor', 'devops', 'monitor', 'Check deployment/service health', 'service_id or url', 'Health status with metrics'),
('devops.rollback', 'devops', 'rollback', 'Rollback to a previous deployment', 'project_id, deployment_id or version', 'Rollback completed'),

-- Notifications
('notification.send', 'notification', 'send', 'Send a notification to users', 'user_ids, channel (push/in-app/email), title, body', 'Notification delivered'),
('notification.manage_prefs', 'notification', 'manage_prefs', 'Manage user notification preferences', 'user_id, channel, enabled/disabled', 'Preferences updated'),

-- Calendar
('calendar.create_event', 'calendar', 'create_event', 'Create a calendar event', 'title, start_time, end_time, attendees, description', 'Event created with ID'),
('calendar.list_events', 'calendar', 'list_events', 'List calendar events in a time range', 'start_date, end_date, calendar_id', 'List of events with details'),
('calendar.check_availability', 'calendar', 'check_availability', 'Check availability for scheduling', 'attendees, time_range, duration', 'Available time slots'),

-- Media
('media.transcribe', 'media', 'transcribe', 'Transcribe audio/video to text', 'media_url or file, language (optional)', 'Transcript with timestamps'),
('media.process_image', 'media', 'process_image', 'Transform or optimize an image', 'image_url, transformations (resize, crop, format)', 'Processed image URL'),
('media.generate_speech', 'media', 'generate_speech', 'Convert text to speech audio', 'text, voice_id, output_format', 'Audio file URL'),

-- Monitoring
('monitoring.alert', 'monitoring', 'alert', 'Create or manage monitoring alerts', 'metric, threshold, notification_channels', 'Alert rule created/updated'),
('monitoring.push_metric', 'monitoring', 'push_metric', 'Push a custom metric data point', 'metric_name, value, tags, timestamp', 'Metric recorded'),
('monitoring.query_logs', 'monitoring', 'query_logs', 'Query application logs', 'query, time_range, source', 'Matching log entries'),

-- Analytics
('analytics.track_event', 'analytics', 'track_event', 'Track a user event', 'event_name, user_id, properties', 'Event recorded'),
('analytics.identify_user', 'analytics', 'identify_user', 'Identify/update a user profile', 'user_id, traits (name, email, plan, etc.)', 'User profile updated'),
('analytics.query_metrics', 'analytics', 'query_metrics', 'Query analytics metrics', 'metric, time_range, filters, group_by', 'Metric data points'),

-- E-commerce
('ecommerce.create_product', 'ecommerce', 'create_product', 'Create a product listing', 'name, price, description, images, variants', 'Product created with ID'),
('ecommerce.process_order', 'ecommerce', 'process_order', 'Process or update an order', 'order_id, action (fulfill, cancel, refund)', 'Order updated'),
('ecommerce.manage_inventory', 'ecommerce', 'manage_inventory', 'Update inventory levels', 'product_id, variant_id, quantity, location', 'Inventory updated'),

-- Social
('social.post', 'social', 'post', 'Publish a post to a social platform', 'content, media (optional), platform-specific fields', 'Post published with ID/URL'),
('social.dm', 'social', 'dm', 'Send a direct message', 'recipient_id, message_text', 'Message sent'),
('social.read_feed', 'social', 'read_feed', 'Read posts from a feed or timeline', 'user_id or feed_id, limit', 'List of posts with metadata'),

-- Document
('document.sign', 'document', 'sign', 'Send a document for electronic signature', 'document_url, signers, fields', 'Signature request sent'),
('document.generate', 'document', 'generate', 'Generate a document from template', 'template_id, merge_data, output_format', 'Generated document URL'),

-- Translation
('translation.translate', 'translation', 'translate', 'Translate text between languages', 'text, source_lang, target_lang', 'Translated text'),
('translation.detect', 'translation', 'detect', 'Detect the language of text', 'text', 'Detected language with confidence'),

-- Workflow
('workflow.trigger', 'workflow', 'trigger', 'Trigger a workflow or automation', 'workflow_id, input_data', 'Workflow execution started'),
('workflow.webhook', 'workflow', 'webhook', 'Receive or configure a webhook', 'url, events, secret', 'Webhook configured'),
('workflow.schedule', 'workflow', 'schedule', 'Schedule a task for future execution', 'task, schedule (cron or timestamp), payload', 'Task scheduled'),

-- Content (headless CMS)
('content.create', 'content', 'create', 'Create content in a CMS', 'content_type, fields, status (draft/published)', 'Content entry created with ID'),
('content.update', 'content', 'update', 'Update existing content', 'entry_id, fields', 'Content entry updated'),
('content.publish', 'content', 'publish', 'Publish a content entry', 'entry_id, environment (optional)', 'Content published'),
('content.query', 'content', 'query', 'Query content entries', 'content_type, filters, limit, order', 'List of content entries'),

-- Browser Automation
('browser.scrape', 'browser', 'scrape', 'Extract data from a web page', 'url, selectors or extraction_rules', 'Extracted structured data'),
('browser.screenshot', 'browser', 'screenshot', 'Capture a screenshot of a web page', 'url, viewport (optional), full_page', 'Screenshot image'),
('browser.crawl', 'browser', 'crawl', 'Crawl a website and extract content', 'start_url, depth, rules', 'Crawled pages with content'),

-- Maps / Location
('maps.geocode', 'maps', 'geocode', 'Convert address to coordinates or vice versa', 'address or lat/lng', 'Coordinates and/or formatted address'),
('maps.places_search', 'maps', 'places_search', 'Search for places/businesses near a location', 'query, location, radius', 'List of matching places with details'),
('maps.directions', 'maps', 'directions', 'Get directions between locations', 'origin, destination, mode (driving/walking/transit)', 'Route with steps, distance, duration'),

-- Vector Database (separate from general database)
('vector.upsert', 'vector', 'upsert', 'Insert or update vectors in a collection', 'collection, vectors with ids and metadata', 'Vectors upserted'),
('vector.search', 'vector', 'search', 'Search vectors by similarity', 'collection, query_vector, top_k, filters', 'Similar vectors with scores'),

-- Feature Flags
('feature.evaluate', 'feature', 'evaluate', 'Evaluate a feature flag for a user/context', 'flag_key, user_context', 'Flag value (boolean, string, or JSON)'),
('feature.manage', 'feature', 'manage', 'Create or update feature flags', 'flag_key, targeting_rules, default_value', 'Flag created/updated'),

-- Secrets
('secrets.get', 'secrets', 'get', 'Retrieve a secret value', 'secret_name, environment', 'Secret value'),
('secrets.set', 'secrets', 'set', 'Store a secret value', 'secret_name, secret_value, environment', 'Secret stored')

ON CONFLICT (id) DO UPDATE SET
    description = EXCLUDED.description,
    input_hint = EXCLUDED.input_hint,
    outcome = EXCLUDED.outcome,
    updated_at = now();


-- ============================================================
-- CAPABILITY-SERVICE MAPPINGS
-- Maps each service to the capabilities it provides
-- ============================================================

-- Email services
INSERT INTO capability_services (capability_id, service_slug, auth_method, endpoint_pattern, cost_per_call, free_tier_calls) VALUES
('email.send', 'sendgrid', 'api_key', 'POST /v3/mail/send', 0.001, 100),
('email.send', 'resend', 'api_key', 'POST /emails', NULL, 100),
('email.send', 'postmark', 'api_key', 'POST /email', 0.001, 100),
('email.send', 'amazon-ses', 'api_key', 'POST /v2/email/outbound-emails', 0.0001, 62000),
('email.send', 'mailgun', 'api_key', 'POST /v3/{domain}/messages', 0.0008, 100),
('email.send', 'brevo', 'api_key', 'POST /v3/smtp/email', NULL, 300),
('email.send', 'customer-io', 'api_key', 'POST /v1/send/email', 0.001, NULL),
('email.send', 'convertkit', 'api_key', 'POST /v4/broadcasts', NULL, 1000),
('email.template', 'sendgrid', 'api_key', 'GET /v3/templates', NULL, NULL),
('email.template', 'resend', 'api_key', 'POST /emails (with html/react)', NULL, NULL),
('email.template', 'postmark', 'api_key', 'POST /email/withTemplate', NULL, NULL),
('email.list_manage', 'sendgrid', 'api_key', 'POST /v3/marketing/contacts', NULL, NULL),
('email.list_manage', 'convertkit', 'api_key', 'POST /v4/subscribers', NULL, NULL),
('email.list_manage', 'brevo', 'api_key', 'POST /v3/contacts', NULL, NULL),
('email.track', 'sendgrid', 'api_key', 'Webhooks + GET /v3/stats', NULL, NULL),
('email.track', 'postmark', 'api_key', 'GET /stats/outbound', NULL, NULL),

-- Payment services
('payment.charge', 'stripe', 'api_key', 'POST /v1/payment_intents', 0.029, NULL),
('payment.charge', 'square', 'oauth2', 'POST /v2/payments', 0.029, NULL),
('payment.charge', 'adyen', 'api_key', 'POST /payments', NULL, NULL),
('payment.charge', 'braintree', 'api_key', 'POST /transactions', 0.029, NULL),
('payment.charge', 'paypal', 'oauth2', 'POST /v2/checkout/orders', 0.029, NULL),
('payment.subscribe', 'stripe', 'api_key', 'POST /v1/subscriptions', NULL, NULL),
('payment.subscribe', 'paddle', 'api_key', 'POST /subscriptions', NULL, NULL),
('payment.subscribe', 'lemon-squeezy', 'api_key', 'POST /v1/subscriptions', NULL, NULL),
('payment.refund', 'stripe', 'api_key', 'POST /v1/refunds', NULL, NULL),
('payment.refund', 'square', 'oauth2', 'POST /v2/refunds', NULL, NULL),
('payment.refund', 'paypal', 'oauth2', 'POST /v2/payments/captures/{id}/refund', NULL, NULL),
('payment.invoice', 'stripe', 'api_key', 'POST /v1/invoices', NULL, NULL),
('payment.payout', 'stripe', 'api_key', 'POST /v1/payouts', NULL, NULL),

-- AI services
('ai.generate_text', 'anthropic', 'api_key', 'POST /v1/messages', 0.003, NULL),
('ai.generate_text', 'openai', 'api_key', 'POST /v1/chat/completions', 0.002, NULL),
('ai.generate_text', 'groq', 'api_key', 'POST /v1/chat/completions', 0.0002, NULL),
('ai.generate_text', 'cohere', 'api_key', 'POST /v2/chat', 0.001, NULL),
('ai.generate_text', 'deepseek', 'api_key', 'POST /chat/completions', 0.0003, NULL),
('ai.generate_text', 'google-ai', 'api_key', 'POST /v1beta/models/{model}:generateContent', 0.001, NULL),
('ai.generate_text', 'mistral', 'api_key', 'POST /v1/chat/completions', 0.001, NULL),
('ai.generate_text', 'together-ai', 'api_key', 'POST /v1/chat/completions', 0.0005, NULL),
('ai.generate_text', 'fireworks-ai', 'api_key', 'POST /inference/v1/chat/completions', 0.0005, NULL),
('ai.generate_text', 'perplexity', 'api_key', 'POST /chat/completions', 0.001, NULL),
('ai.generate_text', 'replicate', 'api_key', 'POST /v1/predictions', NULL, NULL),
('ai.embed', 'openai', 'api_key', 'POST /v1/embeddings', 0.0001, NULL),
('ai.embed', 'cohere', 'api_key', 'POST /v2/embed', 0.0001, NULL),
('ai.embed', 'google-ai', 'api_key', 'POST /v1beta/models/embedding-001:embedContent', NULL, NULL),
('ai.embed', 'together-ai', 'api_key', 'POST /v1/embeddings', NULL, NULL),
('ai.generate_image', 'openai', 'api_key', 'POST /v1/images/generations', 0.04, NULL),
('ai.generate_image', 'replicate', 'api_key', 'POST /v1/predictions', 0.01, NULL),
('ai.generate_image', 'stability-ai', 'api_key', 'POST /v1/generation/{id}/text-to-image', 0.01, NULL),
('ai.transcribe', 'openai', 'api_key', 'POST /v1/audio/transcriptions', 0.006, NULL),
('ai.transcribe', 'assemblyai', 'api_key', 'POST /v2/transcript', 0.006, NULL),
('ai.transcribe', 'deepgram', 'api_key', 'POST /v1/listen', 0.004, NULL),
('ai.generate_speech', 'elevenlabs', 'api_key', 'POST /v1/text-to-speech/{voice_id}', 0.03, 10000),
('ai.generate_speech', 'openai', 'api_key', 'POST /v1/audio/speech', 0.015, NULL),

-- Data Enrichment
('data.enrich_person', 'apollo', 'api_key', 'POST /v1/people/match', 0.03, 50),
('data.enrich_person', 'people-data-labs', 'api_key', 'GET /v5/person/enrich', 0.10, 100),
('data.enrich_person', 'clearbit', 'api_key', 'GET /v2/people/find', 0.10, NULL),
('data.enrich_person', 'hunter', 'api_key', 'GET /v2/email-finder', 0.03, 25),
('data.enrich_company', 'apollo', 'api_key', 'POST /v1/organizations/enrich', 0.03, 50),
('data.enrich_company', 'clearbit', 'api_key', 'GET /v2/companies/find', 0.10, NULL),
('data.enrich_company', 'people-data-labs', 'api_key', 'GET /v5/company/enrich', 0.10, 100),
('data.search_contacts', 'apollo', 'api_key', 'POST /v1/mixed_people/search', 0.03, NULL),
('data.search_contacts', 'hunter', 'api_key', 'GET /v2/domain-search', 0.03, NULL),

-- Auth services
('auth.manage_users', 'clerk', 'api_key', 'POST /v1/users', NULL, 10000),
('auth.manage_users', 'auth0', 'oauth2', 'POST /api/v2/users', NULL, 7500),
('auth.manage_users', 'cognito', 'api_key', 'AdminCreateUser', NULL, 50000),
('auth.manage_users', 'supabase', 'api_key', 'POST /auth/v1/admin/users', NULL, 50000),
('auth.manage_users', 'firebase-auth', 'api_key', 'POST identitytoolkit/v3/relyingparty/signupNewUser', NULL, NULL),
('auth.authenticate', 'clerk', 'api_key', 'POST /v1/sessions/verify', NULL, NULL),
('auth.authenticate', 'auth0', 'oauth2', 'POST /oauth/token', NULL, NULL),
('auth.sso', 'auth0', 'oauth2', 'GET /authorize', NULL, NULL),
('auth.sso', 'descope', 'api_key', 'POST /v1/auth/sso/start', NULL, NULL),
('auth.sso', 'workos', 'api_key', 'POST /sso/authorize', NULL, NULL),

-- Storage
('storage.upload', 'aws-s3', 'api_key', 'PUT /{bucket}/{key}', 0.000005, NULL),
('storage.upload', 'cloudflare-r2', 'api_key', 'PUT /{bucket}/{key}', NULL, 10000000),
('storage.upload', 'supabase-storage', 'api_key', 'POST /storage/v1/object/{bucket}', NULL, 1000),
('storage.upload', 'backblaze-b2', 'api_key', 'POST /b2api/v3/b2_upload_file', 0.000005, NULL),
('storage.upload', 'cloudinary', 'api_key', 'POST /v1_1/{cloud}/image/upload', NULL, 25000),
('storage.upload', 'uploadthing', 'api_key', 'POST /api/uploadthing', NULL, 2000),
('storage.download', 'aws-s3', 'api_key', 'GET /{bucket}/{key}', NULL, NULL),
('storage.download', 'cloudflare-r2', 'api_key', 'GET /{bucket}/{key}', NULL, NULL),
('storage.presign', 'aws-s3', 'api_key', 'GetObject/PutObject presign', NULL, NULL),
('storage.presign', 'cloudflare-r2', 'api_key', 'Presign via S3 API', NULL, NULL),

-- Search
('search.query', 'algolia', 'api_key', 'POST /1/indexes/{index}/query', 0.001, 10000),
('search.query', 'elasticsearch', 'api_key', 'POST /{index}/_search', NULL, NULL),
('search.query', 'typesense', 'api_key', 'GET /collections/{col}/documents/search', NULL, NULL),
('search.query', 'meilisearch', 'api_key', 'POST /indexes/{uid}/search', NULL, NULL),
('search.query', 'brave-search', 'api_key', 'GET /res/v1/web/search', 0.003, 2000),
('search.query', 'exa', 'api_key', 'POST /search', 0.001, 1000),
('search.query', 'tavily', 'api_key', 'POST /search', 0.001, 1000),
('search.index', 'algolia', 'api_key', 'POST /1/indexes/{index}', 0.001, NULL),
('search.index', 'elasticsearch', 'api_key', 'POST /{index}/_doc', NULL, NULL),
('search.index', 'typesense', 'api_key', 'POST /collections/{col}/documents', NULL, NULL),
('search.autocomplete', 'algolia', 'api_key', 'POST /1/indexes/{index}/query (prefix)', NULL, NULL),

-- Communication
('communication.send_sms', 'twilio', 'api_key', 'POST /2010-04-01/Accounts/{sid}/Messages.json', 0.0079, NULL),
('communication.send_sms', 'messagebird', 'api_key', 'POST /messages', 0.007, NULL),
('communication.send_sms', 'plivo', 'api_key', 'POST /v1/Account/{id}/Message/', 0.005, NULL),
('communication.send_sms', 'vonage', 'api_key', 'POST /v1/messages', 0.007, NULL),
('communication.call', 'twilio', 'api_key', 'POST /2010-04-01/Accounts/{sid}/Calls.json', 0.014, NULL),
('communication.send_message', 'slack', 'oauth2', 'POST /api/chat.postMessage', NULL, NULL),
('communication.send_message', 'discord', 'api_key', 'POST /api/v10/channels/{id}/messages', NULL, NULL),
('communication.send_message', 'microsoft-teams', 'oauth2', 'POST /v1.0/chats/{id}/messages', NULL, NULL),

-- CRM
('crm.create_contact', 'hubspot', 'oauth2', 'POST /crm/v3/objects/contacts', NULL, NULL),
('crm.create_contact', 'salesforce', 'oauth2', 'POST /services/data/vXX.0/sobjects/Contact', NULL, NULL),
('crm.create_contact', 'attio', 'api_key', 'POST /v2/objects/people/records', NULL, NULL),
('crm.create_contact', 'close-crm', 'api_key', 'POST /v1/lead/', NULL, NULL),
('crm.create_contact', 'pipedrive', 'api_key', 'POST /v1/persons', NULL, NULL),
('crm.create_contact', 'freshsales', 'api_key', 'POST /api/contacts', NULL, NULL),
('crm.update_deal', 'hubspot', 'oauth2', 'PATCH /crm/v3/objects/deals/{id}', NULL, NULL),
('crm.update_deal', 'salesforce', 'oauth2', 'PATCH /services/data/vXX.0/sobjects/Opportunity/{id}', NULL, NULL),
('crm.update_deal', 'pipedrive', 'api_key', 'PUT /v1/deals/{id}', NULL, NULL),
('crm.query', 'hubspot', 'oauth2', 'POST /crm/v3/objects/{type}/search', NULL, NULL),
('crm.query', 'salesforce', 'oauth2', 'GET /services/data/vXX.0/query?q=SOQL', NULL, NULL),

-- Database
('database.query', 'supabase', 'api_key', 'GET /rest/v1/{table}?select=*', NULL, 500000000),
('database.query', 'mongodb-atlas', 'api_key', 'POST /action/find', NULL, NULL),
('database.query', 'neon', 'api_key', 'SQL over HTTP', NULL, NULL),
('database.query', 'planetscale', 'api_key', 'SQL over HTTP', NULL, NULL),
('database.query', 'turso', 'api_key', 'POST /v2/pipeline', NULL, 9000000000),
('database.insert', 'supabase', 'api_key', 'POST /rest/v1/{table}', NULL, NULL),
('database.insert', 'mongodb-atlas', 'api_key', 'POST /action/insertOne', NULL, NULL),
('database.vector_search', 'pinecone', 'api_key', 'POST /query', 0.0001, NULL),
('database.vector_search', 'qdrant', 'api_key', 'POST /collections/{name}/points/search', NULL, NULL),
('database.vector_search', 'weaviate', 'api_key', 'POST /v1/graphql', NULL, NULL),
('database.vector_search', 'chroma', 'api_key', 'POST /api/v1/collections/{id}/query', NULL, NULL),
('database.vector_search', 'milvus', 'api_key', 'POST /v2/vectordb/entities/search', NULL, NULL),

-- DevOps
('devops.deploy', 'vercel', 'api_key', 'POST /v13/deployments', NULL, NULL),
('devops.deploy', 'railway', 'api_key', 'GraphQL mutation deploymentCreate', NULL, NULL),
('devops.deploy', 'netlify', 'api_key', 'POST /api/v1/sites/{id}/deploys', NULL, NULL),
('devops.deploy', 'fly-io', 'api_key', 'POST /v1/apps/{app}/machines', NULL, NULL),
('devops.deploy', 'render', 'api_key', 'POST /v1/services/{id}/deploys', NULL, NULL),
('devops.deploy', 'digital-ocean', 'api_key', 'POST /v2/apps/{id}/deployments', NULL, NULL),
('devops.build', 'github', 'api_key', 'POST /repos/{owner}/{repo}/actions/workflows/{id}/dispatches', NULL, NULL),
('devops.build', 'circleci', 'api_key', 'POST /v2/project/{slug}/pipeline', NULL, NULL),
('devops.build', 'bitbucket', 'api_key', 'POST /2.0/repositories/{workspace}/{repo}/pipelines/', NULL, NULL),
('devops.monitor', 'betterstack', 'api_key', 'GET /v2/monitors', NULL, NULL),
('devops.monitor', 'datadog', 'api_key', 'GET /api/v1/monitor', NULL, NULL),
('devops.monitor', 'grafana-cloud', 'api_key', 'GET /api/datasources/proxy/{id}/api/v1/query', NULL, NULL),

-- Calendar
('calendar.create_event', 'cal-com', 'api_key', 'POST /v2/bookings', NULL, NULL),
('calendar.create_event', 'google-calendar', 'oauth2', 'POST /calendar/v3/calendars/{id}/events', NULL, NULL),
('calendar.create_event', 'calendly', 'api_key', 'POST /scheduling_links', NULL, NULL),
('calendar.list_events', 'google-calendar', 'oauth2', 'GET /calendar/v3/calendars/{id}/events', NULL, NULL),
('calendar.list_events', 'microsoft-outlook', 'oauth2', 'GET /v1.0/me/events', NULL, NULL),
('calendar.check_availability', 'cal-com', 'api_key', 'GET /v2/slots/available', NULL, NULL),
('calendar.check_availability', 'calendly', 'api_key', 'GET /user_availability_schedules', NULL, NULL),

-- Media
('media.transcribe', 'assemblyai', 'api_key', 'POST /v2/transcript', 0.006, NULL),
('media.transcribe', 'deepgram', 'api_key', 'POST /v1/listen', 0.004, NULL),
('media.process_image', 'cloudinary', 'api_key', 'GET /image/upload/transformations', NULL, 25000),
('media.process_image', 'imgix', 'api_key', 'GET /{path}?params', NULL, 1000),
('media.generate_speech', 'elevenlabs', 'api_key', 'POST /v1/text-to-speech/{voice_id}', 0.03, 10000),

-- Monitoring
('monitoring.alert', 'betterstack', 'api_key', 'POST /v2/monitors', NULL, NULL),
('monitoring.alert', 'datadog', 'api_key', 'POST /api/v1/monitor', NULL, NULL),
('monitoring.alert', 'pagerduty', 'api_key', 'POST /incidents', NULL, NULL),
('monitoring.push_metric', 'datadog', 'api_key', 'POST /api/v2/series', NULL, NULL),
('monitoring.push_metric', 'grafana-cloud', 'api_key', 'POST /api/v1/push', NULL, 10000),
('monitoring.query_logs', 'datadog', 'api_key', 'POST /api/v2/logs/events/search', NULL, NULL),
('monitoring.query_logs', 'axiom', 'api_key', 'POST /v1/datasets/{dataset}/query', NULL, NULL),
('monitoring.query_logs', 'papertrail', 'api_key', 'GET /api/v1/events/search.json', NULL, NULL),

-- Analytics
('analytics.track_event', 'amplitude', 'api_key', 'POST /2/httpapi', NULL, NULL),
('analytics.track_event', 'mixpanel', 'api_key', 'POST /track', NULL, NULL),
('analytics.track_event', 'posthog', 'api_key', 'POST /capture/', NULL, 1000000),
('analytics.track_event', 'segment', 'api_key', 'POST /v1/track', NULL, NULL),
('analytics.identify_user', 'amplitude', 'api_key', 'POST /identify', NULL, NULL),
('analytics.identify_user', 'mixpanel', 'api_key', 'POST /engage', NULL, NULL),
('analytics.identify_user', 'segment', 'api_key', 'POST /v1/identify', NULL, NULL),

-- E-commerce
('ecommerce.create_product', 'shopify', 'api_key', 'POST /admin/api/2024-01/products.json', NULL, NULL),
('ecommerce.create_product', 'bigcommerce', 'api_key', 'POST /v3/catalog/products', NULL, NULL),
('ecommerce.process_order', 'shopify', 'api_key', 'POST /admin/api/2024-01/orders/{id}/fulfillments.json', NULL, NULL),
('ecommerce.manage_inventory', 'shopify', 'api_key', 'POST /admin/api/2024-01/inventory_levels/set.json', NULL, NULL),

-- Social
('social.post', 'twitter-api', 'oauth2', 'POST /2/tweets', NULL, NULL),
('social.post', 'linkedin-api', 'oauth2', 'POST /v2/ugcPosts', NULL, NULL),
('social.post', 'bluesky-api', 'api_key', 'POST /xrpc/com.atproto.repo.createRecord', NULL, NULL),
('social.dm', 'slack', 'oauth2', 'POST /api/chat.postMessage (DM channel)', NULL, NULL),
('social.dm', 'discord', 'api_key', 'POST /api/v10/users/@me/channels → /messages', NULL, NULL),
('social.read_feed', 'twitter-api', 'oauth2', 'GET /2/users/{id}/tweets', NULL, NULL),

-- Document
('document.sign', 'docusign', 'oauth2', 'POST /v2.1/accounts/{id}/envelopes', NULL, NULL),
('document.sign', 'pandadoc', 'api_key', 'POST /public/v1/documents', NULL, NULL),

-- Translation
('translation.translate', 'deepl', 'api_key', 'POST /v2/translate', 0.00002, 500000),
('translation.translate', 'google-translate', 'api_key', 'POST /language/translate/v2', 0.00002, NULL),
('translation.detect', 'deepl', 'api_key', 'POST /v2/translate (detect)', NULL, NULL),
('translation.detect', 'google-translate', 'api_key', 'POST /language/translate/v2/detect', NULL, NULL),

-- Workflow
('workflow.trigger', 'zapier', 'api_key', 'POST webhooks.zapier.com/hooks/{id}', NULL, 100),
('workflow.trigger', 'make', 'api_key', 'POST hook.make.com/hooks/{id}', NULL, 1000),
('workflow.trigger', 'inngest', 'api_key', 'POST /v1/events', NULL, 25000),
('workflow.trigger', 'trigger-dev', 'api_key', 'POST /api/v1/events', NULL, NULL),
('workflow.schedule', 'inngest', 'api_key', 'POST /v1/events (with delay)', NULL, NULL),
('workflow.schedule', 'temporal', 'api_key', 'StartWorkflowExecution', NULL, NULL),
('workflow.webhook', 'hookdeck', 'api_key', 'POST /api/2024-03-01/connections', NULL, 100000),
('workflow.webhook', 'svix', 'api_key', 'POST /api/v1/app/{appId}/endpoint/', NULL, NULL),
('workflow.webhook', 'ngrok', 'api_key', 'POST /api/endpoints', NULL, NULL),

-- Content (Headless CMS)
('content.create', 'contentful', 'api_key', 'PUT /spaces/{id}/environments/{env}/entries/{entryId}', NULL, NULL),
('content.create', 'sanity', 'api_key', 'POST /v2021-06-07/data/mutate/{dataset}', NULL, NULL),
('content.create', 'strapi', 'api_key', 'POST /api/{collection}', NULL, NULL),
('content.create', 'directus', 'api_key', 'POST /items/{collection}', NULL, NULL),
('content.query', 'contentful', 'api_key', 'GET /spaces/{id}/environments/{env}/entries', NULL, NULL),
('content.query', 'sanity', 'api_key', 'GET /v2021-06-07/data/query/{dataset}?query=GROQ', NULL, NULL),
('content.query', 'strapi', 'api_key', 'GET /api/{collection}', NULL, NULL),
('content.publish', 'contentful', 'api_key', 'PUT /entries/{id}/published', NULL, NULL),

-- Browser Automation
('browser.scrape', 'firecrawl', 'api_key', 'POST /v1/scrape', 0.001, 500),
('browser.scrape', 'apify', 'api_key', 'POST /v2/acts/{id}/runs', 0.001, NULL),
('browser.scrape', 'scrapingbee', 'api_key', 'GET /api/v1/?url={url}', 0.005, 1000),
('browser.screenshot', 'browserless', 'api_key', 'POST /screenshot', 0.001, NULL),
('browser.crawl', 'firecrawl', 'api_key', 'POST /v1/crawl', 0.005, NULL),
('browser.crawl', 'apify', 'api_key', 'POST /v2/acts/apify~web-scraper/runs', NULL, NULL),

-- Maps
('maps.geocode', 'google-maps', 'api_key', 'GET /maps/api/geocode/json', 0.005, NULL),
('maps.geocode', 'mapbox', 'api_key', 'GET /geocoding/v5/mapbox.places/{query}.json', 0.0005, 100000),
('maps.places_search', 'google-places', 'api_key', 'GET /maps/api/place/textsearch/json', 0.032, NULL),
('maps.directions', 'google-maps', 'api_key', 'GET /maps/api/directions/json', 0.005, NULL),
('maps.directions', 'mapbox', 'api_key', 'GET /directions/v5/mapbox/driving/{coords}', 0.0005, 100000),

-- Feature Flags
('feature.evaluate', 'launchdarkly', 'api_key', 'GET /sdk/evalx/{envId}/users/{userId}', NULL, NULL),
('feature.evaluate', 'statsig', 'api_key', 'POST /v1/check_gate', NULL, NULL),
('feature.evaluate', 'unleash', 'api_key', 'GET /api/client/features', NULL, NULL),

-- Secrets
('secrets.get', 'doppler', 'api_key', 'GET /v3/configs/config/secrets', NULL, NULL),
('secrets.get', 'infisical', 'api_key', 'GET /api/v3/secrets/raw', NULL, NULL),
('secrets.get', 'hashicorp-vault', 'api_key', 'GET /v1/secret/data/{path}', NULL, NULL),
('secrets.set', 'doppler', 'api_key', 'POST /v3/configs/config/secrets', NULL, NULL),
('secrets.set', 'infisical', 'api_key', 'POST /api/v3/secrets/raw', NULL, NULL),

-- Notifications
('notification.send', 'knock', 'api_key', 'POST /v1/workflows/{key}/trigger', NULL, 10000),
('notification.send', 'novu', 'api_key', 'POST /v1/events/trigger', NULL, 30000),
('notification.send', 'onesignal', 'api_key', 'POST /notifications', NULL, NULL),
('notification.send', 'pusher', 'api_key', 'POST /apps/{id}/events', NULL, 200000)

ON CONFLICT (capability_id, service_slug) DO UPDATE SET
    auth_method = EXCLUDED.auth_method,
    endpoint_pattern = EXCLUDED.endpoint_pattern,
    cost_per_call = EXCLUDED.cost_per_call,
    free_tier_calls = EXCLUDED.free_tier_calls,
    updated_at = now();


-- ============================================================
-- CAPABILITY BUNDLES (Tom's "combinations" concept)
-- ============================================================

INSERT INTO capability_bundles (id, name, description, example, value_proposition) VALUES
('prospect.enrich_and_verify', 'Prospect Enrichment + Verification',
 'Find prospect data and verify contact information before outreach',
 'Given a LinkedIn URL, get verified email + phone + company data',
 'Rhumb chains Apollo (enrichment) + email verifier + phone lookup — one call instead of three'),

('email.compose_and_deliver', 'Email Compose + Deliver + Track',
 'Generate email content, send it, and track engagement',
 'Write a follow-up email based on meeting notes, send via SendGrid, track opens',
 'AI generation + delivery + engagement tracking in a single workflow'),

('content.create_and_publish', 'Content Creation + CMS + Distribution',
 'Generate content, push to CMS, and distribute to social channels',
 'Create a blog post with AI, publish to Contentful, share on Twitter and LinkedIn',
 'Combines AI writing + CMS publishing + social distribution'),

('deploy.build_test_ship', 'Build + Test + Deploy',
 'Build code, run tests, and deploy to production',
 'Push to GitHub, trigger CI, deploy to Railway on success',
 'CI/CD pipeline as a single capability chain'),

('customer.support_and_resolve', 'Support Ticket + CRM Update + Notification',
 'Process a support request, update CRM, and notify relevant parties',
 'Receive support email, create ticket in Freshdesk, log in HubSpot, alert team on Slack',
 'Connects customer support, CRM, and team communication')
ON CONFLICT (id) DO UPDATE SET
    description = EXCLUDED.description,
    value_proposition = EXCLUDED.value_proposition,
    updated_at = now();

-- Bundle-capability mappings
INSERT INTO bundle_capabilities (bundle_id, capability_id, sequence_order) VALUES
('prospect.enrich_and_verify', 'data.enrich_person', 1),
('prospect.enrich_and_verify', 'email.verify', 2),
('prospect.enrich_and_verify', 'data.validate', 3),

('email.compose_and_deliver', 'ai.generate_text', 1),
('email.compose_and_deliver', 'email.send', 2),
('email.compose_and_deliver', 'email.track', 3),

('content.create_and_publish', 'ai.generate_text', 1),
('content.create', 'content.create', 2),
('content.create_and_publish', 'social.post', 3),

('deploy.build_test_ship', 'devops.build', 1),
('deploy.build_test_ship', 'devops.deploy', 2),
('deploy.build_test_ship', 'devops.monitor', 3),

('customer.support_and_resolve', 'crm.create_contact', 1),
('customer.support_and_resolve', 'crm.log_activity', 2),
('customer.support_and_resolve', 'communication.send_message', 3)
ON CONFLICT (bundle_id, capability_id) DO NOTHING;
