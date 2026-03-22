-- Migration 0064: Capability Expansion Day 20
-- Domains: hr, survey, localization, iam
-- New capabilities: 10
-- New mappings: ~34
-- Cumulative target: ~251 capabilities / ~855 mappings

-- ============================================================
-- DOMAIN: hr (Human Resources / Workforce Management)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('hr.list_employees', 'hr.list_employees', 'hr', 'List employees in an organization with optional filters', '{"type":"object","properties":{"department":{"type":"string"},"status":{"type":"string","enum":["active","inactive","all"]},"limit":{"type":"integer"}}}', '{"type":"object","properties":{"employees":{"type":"array"},"total":{"type":"integer"}}}'),
  ('hr.onboard_employee', 'hr.onboard_employee', 'hr', 'Initiate onboarding workflow for a new employee', '{"type":"object","required":["employee"],"properties":{"employee":{"type":"object","required":["name","email","start_date"],"properties":{"name":{"type":"string"},"email":{"type":"string"},"start_date":{"type":"string"},"role":{"type":"string"},"department":{"type":"string"}}}}}', '{"type":"object","properties":{"onboarding_id":{"type":"string"},"status":{"type":"string"},"tasks":{"type":"array"}}}'),
  ('hr.sync_roster', 'hr.sync_roster', 'hr', 'Sync employee roster from HRIS to downstream systems', '{"type":"object","properties":{"since":{"type":"string","description":"ISO8601 timestamp for delta sync"},"include_terminated":{"type":"boolean"}}}', '{"type":"object","properties":{"synced":{"type":"integer"},"updated":{"type":"integer"},"errors":{"type":"array"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- hr.list_employees
  ('hr.list_employees', 'bamboohr', 'byo', 0.001, 7.8, true),
  ('hr.list_employees', 'rippling', 'byo', 0.001, 7.6, false),
  ('hr.list_employees', 'gusto', 'byo', 0.001, 7.4, false),
  ('hr.list_employees', 'workday', 'byo', 0.002, 7.9, false),
  -- hr.onboard_employee
  ('hr.onboard_employee', 'bamboohr', 'byo', 0.005, 7.8, true),
  ('hr.onboard_employee', 'rippling', 'byo', 0.005, 7.7, false),
  ('hr.onboard_employee', 'gusto', 'byo', 0.005, 7.3, false),
  -- hr.sync_roster
  ('hr.sync_roster', 'bamboohr', 'byo', 0.002, 7.8, true),
  ('hr.sync_roster', 'workday', 'byo', 0.003, 7.9, false),
  ('hr.sync_roster', 'namely', 'byo', 0.002, 6.8, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: survey (Survey & Feedback Collection)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('survey.create', 'survey.create', 'survey', 'Create a new survey with questions and settings', '{"type":"object","required":["title","questions"],"properties":{"title":{"type":"string"},"questions":{"type":"array"},"settings":{"type":"object"}}}', '{"type":"object","properties":{"survey_id":{"type":"string"},"url":{"type":"string"},"embed_code":{"type":"string"}}}'),
  ('survey.get_responses', 'survey.get_responses', 'survey', 'Retrieve responses for a survey', '{"type":"object","required":["survey_id"],"properties":{"survey_id":{"type":"string"},"since":{"type":"string"},"limit":{"type":"integer"}}}', '{"type":"object","properties":{"responses":{"type":"array"},"total":{"type":"integer"},"completion_rate":{"type":"number"}}}'),
  ('survey.get_results', 'survey.get_results', 'survey', 'Get aggregated results and analytics for a survey', '{"type":"object","required":["survey_id"],"properties":{"survey_id":{"type":"string"}}}', '{"type":"object","properties":{"summary":{"type":"object"},"per_question":{"type":"array"},"nps_score":{"type":"number"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- survey.create
  ('survey.create', 'typeform', 'byo', 0.003, 8.1, true),
  ('survey.create', 'surveymonkey', 'byo', 0.003, 7.8, false),
  ('survey.create', 'tally', 'byo', 0.002, 7.2, false),
  ('survey.create', 'google-forms', 'byo', 0.001, 6.9, false),
  -- survey.get_responses
  ('survey.get_responses', 'typeform', 'byo', 0.002, 8.1, true),
  ('survey.get_responses', 'surveymonkey', 'byo', 0.002, 7.8, false),
  ('survey.get_responses', 'tally', 'byo', 0.001, 7.0, false),
  -- survey.get_results
  ('survey.get_results', 'typeform', 'byo', 0.003, 8.1, true),
  ('survey.get_results', 'surveymonkey', 'byo', 0.003, 7.8, false),
  ('survey.get_results', 'delighted', 'byo', 0.003, 7.5, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: localization (i18n / Localization Management)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('localization.translate_keys', 'localization.translate_keys', 'localization', 'Translate i18n key-value pairs into target locales', '{"type":"object","required":["keys","target_locales"],"properties":{"keys":{"type":"object","description":"Key-value pairs to translate"},"target_locales":{"type":"array","items":{"type":"string"}},"source_locale":{"type":"string","default":"en"}}}', '{"type":"object","properties":{"translations":{"type":"object","description":"Locale→key→value map"},"missing":{"type":"array"}}}'),
  ('localization.sync', 'localization.sync', 'localization', 'Sync translation files with a localization platform', '{"type":"object","required":["project_id"],"properties":{"project_id":{"type":"string"},"branch":{"type":"string"},"format":{"type":"string","enum":["json","yaml","po","xliff"]}}}', '{"type":"object","properties":{"synced_keys":{"type":"integer"},"languages":{"type":"array"},"pull_url":{"type":"string"}}}'),
  ('localization.export', 'localization.export', 'localization', 'Export translation files for a project in a specified format', '{"type":"object","required":["project_id","format"],"properties":{"project_id":{"type":"string"},"format":{"type":"string","enum":["json","yaml","po","xliff","csv"]},"locales":{"type":"array"}}}', '{"type":"object","properties":{"files":{"type":"array","items":{"type":"object","properties":{"locale":{"type":"string"},"url":{"type":"string"}}}}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- localization.translate_keys (uses translation providers where available)
  ('localization.translate_keys', 'lokalise', 'byo', 0.005, 7.9, true),
  ('localization.translate_keys', 'phrase', 'byo', 0.005, 7.8, false),
  ('localization.translate_keys', 'crowdin', 'byo', 0.004, 7.6, false),
  -- localization.sync
  ('localization.sync', 'lokalise', 'byo', 0.003, 7.9, true),
  ('localization.sync', 'phrase', 'byo', 0.003, 7.8, false),
  ('localization.sync', 'crowdin', 'byo', 0.003, 7.6, false),
  ('localization.sync', 'transifex', 'byo', 0.003, 7.2, false),
  -- localization.export
  ('localization.export', 'lokalise', 'byo', 0.002, 7.9, true),
  ('localization.export', 'phrase', 'byo', 0.002, 7.8, false),
  ('localization.export', 'crowdin', 'byo', 0.002, 7.6, false),
  ('localization.export', 'transifex', 'byo', 0.002, 7.2, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: iam (Identity & Access Management / User Provisioning)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('iam.provision_user', 'iam.provision_user', 'iam', 'Provision a user account in a service via SCIM or native API', '{"type":"object","required":["user"],"properties":{"user":{"type":"object","required":["email"],"properties":{"email":{"type":"string"},"name":{"type":"string"},"groups":{"type":"array"},"role":{"type":"string"}}},"service":{"type":"string"}}}', '{"type":"object","properties":{"user_id":{"type":"string"},"status":{"type":"string"},"provisioned_at":{"type":"string"}}}'),
  ('iam.deprovision_user', 'iam.deprovision_user', 'iam', 'Deprovision or suspend a user account', '{"type":"object","required":["user_id"],"properties":{"user_id":{"type":"string"},"suspend_only":{"type":"boolean","default":false}}}', '{"type":"object","properties":{"status":{"type":"string"},"deprovisioned_at":{"type":"string"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- iam.provision_user
  ('iam.provision_user', 'okta', 'byo', 0.005, 8.2, true),
  ('iam.provision_user', 'auth0', 'byo', 0.004, 7.9, false),
  ('iam.provision_user', 'workos', 'byo', 0.004, 7.8, false),
  ('iam.provision_user', 'jumpcloud', 'byo', 0.003, 7.3, false),
  -- iam.deprovision_user
  ('iam.deprovision_user', 'okta', 'byo', 0.005, 8.2, true),
  ('iam.deprovision_user', 'auth0', 'byo', 0.004, 7.9, false),
  ('iam.deprovision_user', 'workos', 'byo', 0.004, 7.8, false),
  ('iam.deprovision_user', 'jumpcloud', 'byo', 0.003, 7.3, false)
ON CONFLICT (capability_id, provider) DO NOTHING;
