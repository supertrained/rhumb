CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Email OTP user support + explicit credit policy fields
-- Mirrored from packages/api/migrations/0103_email_otp_user_bootstrap.sql so
-- the deploy-facing Supabase migration track includes the OTP auth schema.

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS signup_method TEXT NOT NULL DEFAULT 'oauth',
  ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS signup_ip TEXT DEFAULT '',
  ADD COLUMN IF NOT EXISTS signup_subnet TEXT DEFAULT '',
  ADD COLUMN IF NOT EXISTS credit_policy TEXT NOT NULL DEFAULT 'oauth_trial',
  ADD COLUMN IF NOT EXISTS risk_flags JSONB NOT NULL DEFAULT '{}'::jsonb;

UPDATE users
SET
  signup_method = COALESCE(NULLIF(signup_method, ''), 'oauth'),
  email_verified_at = COALESCE(email_verified_at, created_at),
  credit_policy = COALESCE(NULLIF(credit_policy, ''), 'oauth_trial'),
  signup_ip = COALESCE(signup_ip, ''),
  signup_subnet = COALESCE(signup_subnet, ''),
  risk_flags = COALESCE(risk_flags, '{}'::jsonb)
WHERE provider <> 'email';

CREATE INDEX IF NOT EXISTS idx_users_signup_method ON users (signup_method);

CREATE TABLE IF NOT EXISTS email_verification_codes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT NOT NULL,
  user_id UUID REFERENCES users(user_id) ON DELETE SET NULL,
  code_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 5,
  sent_ip TEXT DEFAULT '',
  sent_subnet TEXT DEFAULT '',
  used_at TIMESTAMPTZ,
  invalidated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_email_verification_codes_email_created
  ON email_verification_codes (email, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_email_verification_codes_active
  ON email_verification_codes (email, expires_at DESC)
  WHERE used_at IS NULL AND invalidated_at IS NULL;

ALTER TABLE email_verification_codes ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'email_verification_codes'
      AND policyname = 'email_verification_codes_service_role'
  ) THEN
    CREATE POLICY "email_verification_codes_service_role"
      ON email_verification_codes
      FOR ALL
      USING (current_role = 'service_role');
  END IF;
END
$$;
