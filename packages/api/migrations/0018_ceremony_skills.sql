-- Migration 0018: Ceremony skills table
-- Structured auth guides that teach agents how to obtain their own credentials
-- Mode 3 (Agent Vault) in the three-credential-mode architecture

CREATE TABLE IF NOT EXISTS ceremony_skills (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    service_slug TEXT NOT NULL,
    -- Structured ceremony steps
    display_name TEXT NOT NULL,
    description TEXT,
    auth_type TEXT NOT NULL DEFAULT 'api_key',  -- api_key, oauth2, basic_auth
    -- Step-by-step guide for agents
    steps JSONB NOT NULL DEFAULT '[]',
    -- Token format validation
    token_pattern TEXT,          -- regex pattern for format validation (e.g. 'sk-[a-zA-Z0-9]{48}')
    token_prefix TEXT,           -- expected prefix (e.g. 'sk-', 're_')
    -- Live verification endpoint (optional)
    verify_endpoint TEXT,        -- e.g. '/v1/models' for OpenAI
    verify_method TEXT DEFAULT 'GET',
    verify_expected_status INT DEFAULT 200,
    -- Metadata
    difficulty TEXT NOT NULL DEFAULT 'easy',  -- easy, medium, hard
    estimated_minutes INT DEFAULT 5,
    requires_human BOOLEAN NOT NULL DEFAULT false,  -- true if human approval needed
    documentation_url TEXT,
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(service_slug)
);

-- Index for lookups
CREATE INDEX IF NOT EXISTS idx_ceremony_skills_enabled
    ON ceremony_skills(enabled) WHERE enabled = true;

-- RLS
ALTER TABLE ceremony_skills ENABLE ROW LEVEL SECURITY;

CREATE POLICY "ceremony_skills_read" ON ceremony_skills
    FOR SELECT USING (true);

CREATE POLICY "ceremony_skills_admin" ON ceremony_skills
    FOR ALL USING (auth.role() = 'service_role');

COMMENT ON TABLE ceremony_skills IS
    'Structured auth guides for agents to obtain their own API credentials. '
    'Mode 3 (Agent Vault): agent completes ceremony, gets token, passes per-request.';


-- Seed 10 ceremony skills
INSERT INTO ceremony_skills (service_slug, display_name, description, auth_type, steps, token_pattern, token_prefix, verify_endpoint, verify_method, verify_expected_status, difficulty, estimated_minutes, requires_human, documentation_url) VALUES

('openai', 'OpenAI', 'Get an OpenAI API key for GPT, DALL-E, Whisper, and embeddings', 'api_key',
 '[{"step": 1, "action": "Navigate to https://platform.openai.com/api-keys", "type": "navigate"},
   {"step": 2, "action": "Click Create new secret key", "type": "click"},
   {"step": 3, "action": "Name the key and set permissions", "type": "configure"},
   {"step": 4, "action": "Copy the key (starts with sk-)", "type": "copy"}]'::jsonb,
 'sk-[a-zA-Z0-9_-]{40,}', 'sk-', '/v1/models', 'GET', 200,
 'easy', 3, false, 'https://platform.openai.com/docs/quickstart'),

('anthropic', 'Anthropic', 'Get an Anthropic API key for Claude models', 'api_key',
 '[{"step": 1, "action": "Navigate to https://console.anthropic.com/settings/keys", "type": "navigate"},
   {"step": 2, "action": "Click Create Key", "type": "click"},
   {"step": 3, "action": "Name the key and copy it", "type": "copy"}]'::jsonb,
 'sk-ant-[a-zA-Z0-9_-]{40,}', 'sk-ant-', '/v1/messages', 'POST', 200,
 'easy', 3, false, 'https://docs.anthropic.com/en/docs/getting-started'),

('resend', 'Resend', 'Get a Resend API key for transactional email', 'api_key',
 '[{"step": 1, "action": "Navigate to https://resend.com/api-keys", "type": "navigate"},
   {"step": 2, "action": "Click Create API Key", "type": "click"},
   {"step": 3, "action": "Set permissions (sending access) and domain", "type": "configure"},
   {"step": 4, "action": "Copy the key (starts with re_)", "type": "copy"}]'::jsonb,
 're_[a-zA-Z0-9_]{20,}', 're_', '/emails', 'POST', 200,
 'easy', 3, false, 'https://resend.com/docs/introduction'),

('sendgrid', 'SendGrid', 'Get a SendGrid API key for email delivery', 'api_key',
 '[{"step": 1, "action": "Navigate to https://app.sendgrid.com/settings/api_keys", "type": "navigate"},
   {"step": 2, "action": "Click Create API Key", "type": "click"},
   {"step": 3, "action": "Choose Full Access or Restricted Access", "type": "configure"},
   {"step": 4, "action": "Copy the key (starts with SG.)", "type": "copy"}]'::jsonb,
 'SG\\.[a-zA-Z0-9_-]{20,}', 'SG.', '/v3/mail/send', 'POST', 202,
 'easy', 5, false, 'https://docs.sendgrid.com/for-developers'),

('github', 'GitHub', 'Get a GitHub personal access token', 'api_key',
 '[{"step": 1, "action": "Navigate to https://github.com/settings/tokens?type=beta", "type": "navigate"},
   {"step": 2, "action": "Click Generate new token (fine-grained)", "type": "click"},
   {"step": 3, "action": "Set token name, expiration, and repository access", "type": "configure"},
   {"step": 4, "action": "Select required permissions", "type": "configure"},
   {"step": 5, "action": "Generate and copy the token (starts with github_pat_)", "type": "copy"}]'::jsonb,
 'github_pat_[a-zA-Z0-9_]{20,}|ghp_[a-zA-Z0-9]{36}', 'github_pat_', '/user', 'GET', 200,
 'easy', 5, false, 'https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens'),

('notion', 'Notion', 'Create a Notion integration and get an API key', 'api_key',
 '[{"step": 1, "action": "Navigate to https://www.notion.so/my-integrations", "type": "navigate"},
   {"step": 2, "action": "Click New integration", "type": "click"},
   {"step": 3, "action": "Name it, select workspace, set capabilities", "type": "configure"},
   {"step": 4, "action": "Copy the Internal Integration Secret (starts with ntn_)", "type": "copy"},
   {"step": 5, "action": "Share target pages/databases with the integration", "type": "configure"}]'::jsonb,
 'ntn_[a-zA-Z0-9]{40,}|secret_[a-zA-Z0-9]{40,}', 'ntn_', '/v1/users/me', 'GET', 200,
 'medium', 10, true, 'https://developers.notion.com/docs/create-a-notion-integration'),

('stripe', 'Stripe', 'Get a Stripe API key for payments', 'api_key',
 '[{"step": 1, "action": "Navigate to https://dashboard.stripe.com/apikeys", "type": "navigate"},
   {"step": 2, "action": "Copy the Secret key (starts with sk_test_ or sk_live_)", "type": "copy"},
   {"step": 3, "action": "For production: use Restricted keys with minimum permissions", "type": "configure"}]'::jsonb,
 'sk_(test|live)_[a-zA-Z0-9]{24,}|rk_(test|live)_[a-zA-Z0-9]{24,}', 'sk_', '/v1/balance', 'GET', 200,
 'easy', 3, false, 'https://docs.stripe.com/keys'),

('twilio', 'Twilio', 'Get Twilio credentials for SMS, voice, and messaging', 'basic_auth',
 '[{"step": 1, "action": "Navigate to https://console.twilio.com", "type": "navigate"},
   {"step": 2, "action": "Copy Account SID and Auth Token from the dashboard", "type": "copy"},
   {"step": 3, "action": "Format as AccountSID:AuthToken for Basic auth", "type": "configure"}]'::jsonb,
 'AC[a-f0-9]{32}:[a-f0-9]{32}', 'AC', '/2010-04-01/Accounts.json', 'GET', 200,
 'easy', 3, false, 'https://www.twilio.com/docs/usage/api'),

('slack', 'Slack', 'Create a Slack app and get a bot token', 'api_key',
 '[{"step": 1, "action": "Navigate to https://api.slack.com/apps and click Create New App", "type": "navigate"},
   {"step": 2, "action": "Choose From scratch, name it, select workspace", "type": "configure"},
   {"step": 3, "action": "Go to OAuth & Permissions, add required scopes", "type": "configure"},
   {"step": 4, "action": "Install to Workspace", "type": "click"},
   {"step": 5, "action": "Copy the Bot User OAuth Token (starts with xoxb-)", "type": "copy"}]'::jsonb,
 'xoxb-[0-9]+-[0-9]+-[a-zA-Z0-9]+', 'xoxb-', '/api/auth.test', 'POST', 200,
 'medium', 10, true, 'https://api.slack.com/tutorials/tracks/getting-a-token'),

('google-workspace', 'Google Workspace', 'Set up Google API credentials for Gmail, Calendar, Drive', 'oauth2',
 '[{"step": 1, "action": "Navigate to https://console.cloud.google.com/apis/credentials", "type": "navigate"},
   {"step": 2, "action": "Create project if needed, then click Create Credentials > OAuth client ID", "type": "click"},
   {"step": 3, "action": "Configure OAuth consent screen if prompted", "type": "configure"},
   {"step": 4, "action": "Select application type, set redirect URIs", "type": "configure"},
   {"step": 5, "action": "Download client_secret.json or copy Client ID and Client Secret", "type": "copy"},
   {"step": 6, "action": "Complete OAuth flow to get access_token + refresh_token", "type": "configure"}]'::jsonb,
 NULL, NULL, '/oauth2/v3/tokeninfo', 'GET', 200,
 'hard', 20, true, 'https://developers.google.com/identity/protocols/oauth2')

ON CONFLICT (service_slug) DO NOTHING;
