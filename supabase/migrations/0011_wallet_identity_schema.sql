CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Wallet identity + auth schema
-- Mirrored from packages/api/migrations/0106_wallet_identity_schema.sql so
-- the deploy-facing Supabase migration track includes the wallet auth schema.

-- ── Wallet Identities ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS wallet_identities (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  chain TEXT NOT NULL DEFAULT 'base',
  address TEXT NOT NULL,
  address_normalized TEXT NOT NULL,
  org_id TEXT NOT NULL REFERENCES orgs(id),
  default_agent_id TEXT NOT NULL REFERENCES agents(agent_id),
  linked_user_id UUID NULL,
  status TEXT NOT NULL DEFAULT 'active',
  auth_method TEXT NOT NULL DEFAULT 'personal_sign',
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_verified_at TIMESTAMPTZ NULL,
  last_verified_ip TEXT NOT NULL DEFAULT '',
  last_verified_subnet TEXT NOT NULL DEFAULT '',
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_wallet_identities_chain_addr
  ON wallet_identities(chain, address_normalized);
CREATE INDEX IF NOT EXISTS idx_wallet_identities_org
  ON wallet_identities(org_id);
CREATE INDEX IF NOT EXISTS idx_wallet_identities_linked_user
  ON wallet_identities(linked_user_id)
  WHERE linked_user_id IS NOT NULL;

ALTER TABLE wallet_identities ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'wallet_identities'
      AND policyname = 'wallet_identities_service_role'
  ) THEN
    CREATE POLICY "wallet_identities_service_role"
      ON wallet_identities
      FOR ALL
      USING (current_role = 'service_role');
  END IF;
END
$$;

-- ── Wallet Auth Challenges ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS wallet_auth_challenges (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  chain TEXT NOT NULL DEFAULT 'base',
  address TEXT NOT NULL,
  address_normalized TEXT NOT NULL,
  purpose TEXT NOT NULL DEFAULT 'access',
  nonce TEXT NOT NULL,
  message TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ NULL,
  request_ip TEXT NOT NULL DEFAULT '',
  request_subnet TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_wallet_challenges_addr_created
  ON wallet_auth_challenges(address_normalized, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_wallet_challenges_active
  ON wallet_auth_challenges(address_normalized, expires_at)
  WHERE used_at IS NULL;

ALTER TABLE wallet_auth_challenges ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'wallet_auth_challenges'
      AND policyname = 'wallet_auth_challenges_service_role'
  ) THEN
    CREATE POLICY "wallet_auth_challenges_service_role"
      ON wallet_auth_challenges
      FOR ALL
      USING (current_role = 'service_role');
  END IF;
END
$$;

-- ── Wallet Balance Top-ups ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS wallet_balance_topups (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  wallet_identity_id UUID NOT NULL REFERENCES wallet_identities(id),
  org_id TEXT NOT NULL REFERENCES orgs(id),
  payment_request_id UUID NULL REFERENCES payment_requests(id),
  receipt_id UUID NULL REFERENCES usdc_receipts(id),
  amount_usd_cents INTEGER NOT NULL,
  amount_usdc_atomic TEXT NOT NULL DEFAULT '0',
  status TEXT NOT NULL DEFAULT 'pending',
  credited_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_wallet_topups_wallet
  ON wallet_balance_topups(wallet_identity_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_wallet_topups_org
  ON wallet_balance_topups(org_id, created_at DESC);

ALTER TABLE wallet_balance_topups ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'wallet_balance_topups'
      AND policyname = 'wallet_balance_topups_service_role'
  ) THEN
    CREATE POLICY "wallet_balance_topups_service_role"
      ON wallet_balance_topups
      FOR ALL
      USING (current_role = 'service_role');
  END IF;
END
$$;

-- ── Schema adjustments for wallet-linked orgs ──────────────────────

ALTER TABLE orgs ALTER COLUMN email DROP NOT NULL;

ALTER TABLE payment_requests
  ADD COLUMN IF NOT EXISTS purpose TEXT NOT NULL DEFAULT 'execution';

ALTER TABLE payment_requests
  ALTER COLUMN capability_id DROP NOT NULL;
