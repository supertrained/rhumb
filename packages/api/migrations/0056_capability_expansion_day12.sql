-- Migration 0056: Capability expansion Day 12
-- 10 new capabilities across 4 domains: esign, workflow, monitoring, secrets
-- Running total: ~195 capabilities, ~608 mappings

BEGIN;

-- ============================================================
-- NEW CAPABILITIES
-- ============================================================
INSERT INTO capabilities (id, domain, description, status) VALUES
  -- E-Signature (2)
  ('esign.create_request',  'esign',      'Create a document signing request',                   'active'),
  ('esign.get_status',      'esign',      'Check the status of a signing request',               'active'),
  -- Workflow automation (2)
  ('workflow.trigger',      'workflow',   'Trigger an existing workflow or automation',          'active'),
  ('workflow.create',       'workflow',   'Create a new workflow or zap from a template',        'active'),
  -- Uptime / status monitoring (3)
  ('monitoring.create_alert',   'monitoring', 'Create an uptime or threshold alert',             'active'),
  ('monitoring.check_uptime',   'monitoring', 'Query the uptime status of a monitored endpoint', 'active'),
  ('monitoring.get_status_page','monitoring', 'Retrieve the current status page summary',        'active'),
  -- Secrets management (3)
  ('secrets.get',           'secrets',    'Retrieve a secret value by key',                      'active'),
  ('secrets.set',           'secrets',    'Store or update a secret value',                      'active'),
  ('secrets.list',          'secrets',    'List available secret keys in a namespace',           'active')
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- PROVIDER MAPPINGS
-- ============================================================

-- esign.create_request
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('esign.create_request', 'docusign',   '{byo}', 'oauth2',   'POST /v2.1/accounts/{id}/envelopes',     'DocuSign. 1 user free forever (25 sends/mo).'),
  ('esign.create_request', 'hellosign',  '{byo}', 'api_key',  'POST /v3/signature_request/send',        'Dropbox Sign. 3 documents/mo free.'),
  ('esign.create_request', 'pandadoc',   '{byo}', 'api_key',  'POST /public/v1/documents',              'PandaDoc. 5 docs/mo free.'),
  ('esign.create_request', 'signnow',    '{byo}', 'oauth2',   'POST /document',                         'SignNow. 3 docs/mo free.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- esign.get_status
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('esign.get_status', 'docusign',  '{byo}', 'oauth2',  'GET /v2.1/accounts/{id}/envelopes/{envelopeId}', 'Envelope status + recipient tracking.'),
  ('esign.get_status', 'hellosign', '{byo}', 'api_key', 'GET /v3/signature_request/{id}',                 'Request status.'),
  ('esign.get_status', 'pandadoc',  '{byo}', 'api_key', 'GET /public/v1/documents/{id}',                  'Document status.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- workflow.trigger
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('workflow.trigger', 'zapier',  '{byo}', 'api_key', 'POST /hooks/catch/{hook_id}/',         'Trigger a Zap via webhook.'),
  ('workflow.trigger', 'make',    '{byo}', 'api_key', 'POST /api/v2/scenarios/{id}/run',      'Trigger a Make (Integromat) scenario.'),
  ('workflow.trigger', 'n8n',     '{byo}', 'api_key', 'POST /webhook/{path}',                 'Trigger an n8n workflow via webhook.'),
  ('workflow.trigger', 'pipedream','{byo}','api_key', 'POST /workflows/{id}/events',          'Pipedream workflow trigger.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- workflow.create
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('workflow.create', 'zapier',   '{byo}', 'api_key', 'POST /v1/zaps',                         'Create a Zap via API.'),
  ('workflow.create', 'make',     '{byo}', 'api_key', 'POST /api/v2/scenarios',                'Create a Make scenario.'),
  ('workflow.create', 'pipedream','{byo}', 'api_key', 'POST /v1/workflows',                    'Create a Pipedream workflow.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- monitoring.create_alert
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('monitoring.create_alert', 'pagerduty',     '{byo}', 'api_key', 'POST /services',                  'PagerDuty service + escalation policy.'),
  ('monitoring.create_alert', 'uptimerobot',   '{byo}', 'api_key', 'POST /v2/newMonitor',             'UptimeRobot. 50 monitors free.'),
  ('monitoring.create_alert', 'betterstack',   '{byo,rhumb_managed}', 'api_key', 'POST /api/v2/monitors', 'Better Stack. 10 monitors free. PROXY-CALLABLE — live credential.'),
  ('monitoring.create_alert', 'freshstatus',   '{byo}', 'api_key', 'POST /v2/monitors',               'FreshStatus / Freshping.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- monitoring.check_uptime
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('monitoring.check_uptime', 'uptimerobot',  '{byo}', 'api_key', 'POST /v2/getMonitors',           '50 monitors, 5-min checks free.'),
  ('monitoring.check_uptime', 'betterstack',  '{byo,rhumb_managed}', 'api_key', 'GET /api/v2/monitors', 'PROXY-CALLABLE — live credential.'),
  ('monitoring.check_uptime', 'freshstatus',  '{byo}', 'api_key', 'GET /v2/monitors/{id}',           'Check uptime stats.'),
  ('monitoring.check_uptime', 'statuscake',   '{byo}', 'api_key', 'GET /v1/uptime',                  'StatusCake. 10 checks free.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- monitoring.get_status_page
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('monitoring.get_status_page', 'statuspage-io', '{byo}', 'api_key', 'GET /api/v2/summary.json', 'Atlassian Statuspage public summary.'),
  ('monitoring.get_status_page', 'betterstack',   '{byo,rhumb_managed}', 'api_key', 'GET /api/v2/status-pages', 'PROXY-CALLABLE — live credential.'),
  ('monitoring.get_status_page', 'freshstatus',   '{byo}', 'api_key', 'GET /v2/services',          'FreshStatus service summary.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- secrets.get
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('secrets.get', 'doppler',            '{byo}', 'api_key', 'GET /v3/configs/config/secret',          'Doppler. Free tier: 5 projects.'),
  ('secrets.get', 'hashicorp-vault',    '{byo}', 'api_key', 'GET /v1/{mount}/data/{path}',             'Vault. Open-source, self-hosted.'),
  ('secrets.get', 'aws-secrets-manager','{byo}', 'api_key', 'GetSecretValue (AWS SDK)',                'AWS. $0.40/secret/month after 30-day trial.'),
  ('secrets.get', 'infisical',          '{byo}', 'api_key', 'GET /api/v3/secrets/raw/{secretName}',   'Infisical. Open-source, free cloud tier.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- secrets.set
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('secrets.set', 'doppler',            '{byo}', 'api_key', 'POST /v3/configs/config/secrets',         'Upsert a secret value.'),
  ('secrets.set', 'hashicorp-vault',    '{byo}', 'api_key', 'POST /v1/{mount}/data/{path}',             'KV v2 write.'),
  ('secrets.set', 'aws-secrets-manager','{byo}', 'api_key', 'PutSecretValue / CreateSecret (AWS SDK)',  'Create or rotate a secret.'),
  ('secrets.set', 'infisical',          '{byo}', 'api_key', 'POST /api/v3/secrets/raw/{secretName}',   'Create or update secret.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- secrets.list
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('secrets.list', 'doppler',            '{byo}', 'api_key', 'GET /v3/configs/config/secrets',         'List all secrets in a config.'),
  ('secrets.list', 'hashicorp-vault',    '{byo}', 'api_key', 'LIST /v1/{mount}/metadata/{path}',        'KV v2 list keys.'),
  ('secrets.list', 'infisical',          '{byo}', 'api_key', 'GET /api/v3/secrets/raw',                 'List all secrets in a project.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- ============================================================
-- Totals: 10 new capabilities, ~37 new mappings
-- Running total: ~195 capabilities, ~608 mappings
-- ============================================================

COMMIT;
