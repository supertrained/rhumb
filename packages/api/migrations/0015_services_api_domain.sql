-- Migration 0015: Add api_domain column to services table
-- Required for capability execute to proxy requests to dynamic (non-hardcoded) services

ALTER TABLE services ADD COLUMN IF NOT EXISTS api_domain text;
COMMENT ON COLUMN services.api_domain IS 'Base API domain for this service (e.g. api.resend.com)';

-- Seed domains for top services used in capability execute
UPDATE services SET api_domain = 'api.resend.com' WHERE slug = 'resend' AND api_domain IS NULL;
UPDATE services SET api_domain = 'api.sendgrid.com' WHERE slug = 'sendgrid' AND api_domain IS NULL;
UPDATE services SET api_domain = 'api.stripe.com' WHERE slug = 'stripe' AND api_domain IS NULL;
UPDATE services SET api_domain = 'api.github.com' WHERE slug = 'github' AND api_domain IS NULL;
UPDATE services SET api_domain = 'slack.com' WHERE slug = 'slack' AND api_domain IS NULL;
UPDATE services SET api_domain = 'api.twilio.com' WHERE slug = 'twilio' AND api_domain IS NULL;
UPDATE services SET api_domain = 'api.openai.com' WHERE slug = 'openai' AND api_domain IS NULL;
UPDATE services SET api_domain = 'api.anthropic.com' WHERE slug = 'anthropic' AND api_domain IS NULL;
UPDATE services SET api_domain = 'api.postmarkapp.com' WHERE slug = 'postmark' AND api_domain IS NULL;
UPDATE services SET api_domain = 'rest.hubapi.com' WHERE slug = 'hubspot' AND api_domain IS NULL;
