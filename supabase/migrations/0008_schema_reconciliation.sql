CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Migration 0008: Schema reconciliation migration
-- Resolves WU-28.1 schema conflicts across the Supabase migration track.
--
-- Notes:
-- - This migration is intentionally idempotent and backward compatible.
-- - No columns are dropped or renamed.
-- - Conflicts 006-009 are code-only or already fixed, so they are not handled here.
-- - Legacy tier scan (2026-03-20): no schema-level platinum/gold/silver tier values were
--   found in the repo. Remaining matches are prose-only usages such as "gold standard"
--   and an Elasticsearch docs reference to vendor "Platinum/Cloud" tiers.

-- ---------------------------------------------------------------------------
-- services enrichment
-- ---------------------------------------------------------------------------

ALTER TABLE services
  ADD COLUMN IF NOT EXISTS primary_domain TEXT,
  ADD COLUMN IF NOT EXISTS tier TEXT,
  ADD COLUMN IF NOT EXISTS tier_label TEXT,
  ADD COLUMN IF NOT EXISTS logo_url TEXT,
  ADD COLUMN IF NOT EXISTS pricing_model TEXT,
  ADD COLUMN IF NOT EXISTS has_free_tier BOOLEAN DEFAULT false,
  ADD COLUMN IF NOT EXISTS api_style TEXT,
  ADD COLUMN IF NOT EXISTS auth_methods TEXT[],
  ADD COLUMN IF NOT EXISTS sdks_available TEXT[];

CREATE INDEX IF NOT EXISTS idx_services_primary_domain
  ON services(primary_domain);

CREATE INDEX IF NOT EXISTS idx_services_tier
  ON services(tier);

CREATE INDEX IF NOT EXISTS idx_services_pricing_model
  ON services(pricing_model);

CREATE INDEX IF NOT EXISTS idx_services_api_style
  ON services(api_style);

CREATE INDEX IF NOT EXISTS idx_services_auth_methods
  ON services USING gin(auth_methods);

CREATE INDEX IF NOT EXISTS idx_services_sdks_available
  ON services USING gin(sdks_available);

-- ---------------------------------------------------------------------------
-- canonical L-tier constraints
-- ---------------------------------------------------------------------------

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'an_scores_tier_l_tier_check'
      AND conrelid = 'an_scores'::regclass
  ) THEN
    ALTER TABLE an_scores
      ADD CONSTRAINT an_scores_tier_l_tier_check
      CHECK (tier IN ('L1', 'L2', 'L3', 'L4')) NOT VALID;
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'services_tier_l_tier_check'
      AND conrelid = 'services'::regclass
  ) THEN
    ALTER TABLE services
      ADD CONSTRAINT services_tier_l_tier_check
      CHECK (tier IS NULL OR tier IN ('L1', 'L2', 'L3', 'L4')) NOT VALID;
  END IF;
END $$;

-- ---------------------------------------------------------------------------
-- capability_services
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS capability_services (
  capability_id TEXT NOT NULL,
  service_slug TEXT NOT NULL,
  priority INTEGER DEFAULT 0,
  cost_per_call NUMERIC(10,6),
  created_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (capability_id, service_slug)
);

ALTER TABLE capability_services
  ADD COLUMN IF NOT EXISTS priority INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS cost_per_call NUMERIC(10,6),
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();

-- Compatibility columns already expected by the API capability routing paths.
ALTER TABLE capability_services
  ADD COLUMN IF NOT EXISTS credential_modes TEXT[] NOT NULL DEFAULT ARRAY['byo'],
  ADD COLUMN IF NOT EXISTS auth_method TEXT,
  ADD COLUMN IF NOT EXISTS endpoint_pattern TEXT,
  ADD COLUMN IF NOT EXISTS cost_currency TEXT DEFAULT 'USD',
  ADD COLUMN IF NOT EXISTS free_tier_calls BIGINT,
  ADD COLUMN IF NOT EXISTS notes TEXT,
  ADD COLUMN IF NOT EXISTS is_primary BOOLEAN DEFAULT true,
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_capability_services_service_slug
  ON capability_services(service_slug);

CREATE INDEX IF NOT EXISTS idx_capability_services_priority
  ON capability_services(priority DESC, service_slug);

CREATE INDEX IF NOT EXISTS idx_capability_services_modes
  ON capability_services USING gin(credential_modes);

ALTER TABLE capability_services ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'capability_services'
      AND policyname = 'capability_services_service_role_all'
  ) THEN
    CREATE POLICY capability_services_service_role_all
      ON capability_services
      FOR ALL
      TO service_role
      USING (true)
      WITH CHECK (true);
  END IF;
END $$;

-- ---------------------------------------------------------------------------
-- capability_executions
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS capability_executions (
  -- Preserves the existing exec_<hex> identifier contract used by current API routes.
  id TEXT PRIMARY KEY DEFAULT ('exec_' || replace(gen_random_uuid()::text, '-', '')),
  agent_id TEXT NOT NULL,
  capability_id TEXT NOT NULL,
  service_slug TEXT NOT NULL,
  credential_mode TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  cost_usd_cents BIGINT NOT NULL DEFAULT 0,
  upstream_cost_cents BIGINT NOT NULL DEFAULT 0,
  margin_cents BIGINT NOT NULL DEFAULT 0,
  latency_ms INTEGER,
  error_code TEXT,
  error_message TEXT,
  request_metadata JSONB,
  response_metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT now(),
  completed_at TIMESTAMPTZ,

  -- Compatibility columns already used by the API and later repo migrations.
  provider_used TEXT,
  method TEXT,
  path TEXT,
  upstream_status INTEGER,
  success BOOLEAN,
  cost_estimate_usd NUMERIC,
  total_latency_ms NUMERIC,
  upstream_latency_ms NUMERIC,
  fallback_attempted BOOLEAN DEFAULT false,
  fallback_provider TEXT,
  idempotency_key TEXT,
  billing_status TEXT DEFAULT 'unbilled',
  interface TEXT DEFAULT 'rest'
);

ALTER TABLE capability_executions
  ADD COLUMN IF NOT EXISTS agent_id TEXT,
  ADD COLUMN IF NOT EXISTS capability_id TEXT,
  ADD COLUMN IF NOT EXISTS service_slug TEXT,
  ADD COLUMN IF NOT EXISTS credential_mode TEXT,
  ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending',
  ADD COLUMN IF NOT EXISTS cost_usd_cents BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS upstream_cost_cents BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS margin_cents BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS latency_ms INTEGER,
  ADD COLUMN IF NOT EXISTS error_code TEXT,
  ADD COLUMN IF NOT EXISTS error_message TEXT,
  ADD COLUMN IF NOT EXISTS request_metadata JSONB,
  ADD COLUMN IF NOT EXISTS response_metadata JSONB,
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now(),
  ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS provider_used TEXT,
  ADD COLUMN IF NOT EXISTS method TEXT,
  ADD COLUMN IF NOT EXISTS path TEXT,
  ADD COLUMN IF NOT EXISTS upstream_status INTEGER,
  ADD COLUMN IF NOT EXISTS success BOOLEAN,
  ADD COLUMN IF NOT EXISTS cost_estimate_usd NUMERIC,
  ADD COLUMN IF NOT EXISTS total_latency_ms NUMERIC,
  ADD COLUMN IF NOT EXISTS upstream_latency_ms NUMERIC,
  ADD COLUMN IF NOT EXISTS fallback_attempted BOOLEAN DEFAULT false,
  ADD COLUMN IF NOT EXISTS fallback_provider TEXT,
  ADD COLUMN IF NOT EXISTS idempotency_key TEXT,
  ADD COLUMN IF NOT EXISTS billing_status TEXT DEFAULT 'unbilled',
  ADD COLUMN IF NOT EXISTS interface TEXT DEFAULT 'rest';

UPDATE capability_executions
SET
  service_slug = COALESCE(service_slug, provider_used),
  provider_used = COALESCE(provider_used, service_slug),
  status = COALESCE(
    status,
    CASE
      WHEN success IS TRUE THEN 'success'
      WHEN success IS FALSE THEN 'error'
      ELSE 'pending'
    END
  ),
  latency_ms = COALESCE(
    latency_ms,
    CASE
      WHEN total_latency_ms IS NOT NULL THEN round(total_latency_ms)::INTEGER
      ELSE NULL
    END
  ),
  total_latency_ms = COALESCE(total_latency_ms, latency_ms),
  completed_at = COALESCE(
    completed_at,
    CASE
      WHEN COALESCE(
        status,
        CASE
          WHEN success IS TRUE THEN 'success'
          WHEN success IS FALSE THEN 'error'
          ELSE 'pending'
        END
      ) IN ('success', 'error')
      THEN COALESCE(created_at, now())
      ELSE NULL
    END
  )
WHERE
  service_slug IS NULL
  OR provider_used IS NULL
  OR status IS NULL
  OR latency_ms IS NULL
  OR total_latency_ms IS NULL
  OR completed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_cap_exec_agent
  ON capability_executions(agent_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_cap_exec_capability
  ON capability_executions(capability_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_cap_exec_status
  ON capability_executions(status);

CREATE INDEX IF NOT EXISTS idx_cap_exec_service_slug
  ON capability_executions(service_slug, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_cap_exec_provider_used
  ON capability_executions(provider_used, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_cap_exec_idempotency
  ON capability_executions(idempotency_key)
  WHERE idempotency_key IS NOT NULL;

CREATE OR REPLACE FUNCTION reconcile_capability_execution_compat()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.service_slug IS NULL AND NEW.provider_used IS NOT NULL THEN
    NEW.service_slug := NEW.provider_used;
  END IF;

  IF NEW.provider_used IS NULL AND NEW.service_slug IS NOT NULL THEN
    NEW.provider_used := NEW.service_slug;
  END IF;

  IF NEW.latency_ms IS NULL AND NEW.total_latency_ms IS NOT NULL THEN
    NEW.latency_ms := round(NEW.total_latency_ms)::INTEGER;
  END IF;

  IF NEW.total_latency_ms IS NULL AND NEW.latency_ms IS NOT NULL THEN
    NEW.total_latency_ms := NEW.latency_ms;
  END IF;

  IF NEW.status = 'pending' AND NEW.success IS NOT NULL THEN
    NEW.status := CASE WHEN NEW.success THEN 'success' ELSE 'error' END;
  END IF;

  IF NEW.completed_at IS NULL AND NEW.status IN ('success', 'error') THEN
    NEW.completed_at := COALESCE(NEW.completed_at, now());
  END IF;

  RETURN NEW;
END;
$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_trigger
    WHERE tgname = 'trg_capability_executions_reconcile_compat'
      AND tgrelid = 'capability_executions'::regclass
  ) THEN
    CREATE TRIGGER trg_capability_executions_reconcile_compat
      BEFORE INSERT OR UPDATE ON capability_executions
      FOR EACH ROW
      EXECUTE FUNCTION reconcile_capability_execution_compat();
  END IF;
END $$;

ALTER TABLE capability_executions ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'capability_executions'
      AND policyname = 'capability_executions_service_role_all'
  ) THEN
    CREATE POLICY capability_executions_service_role_all
      ON capability_executions
      FOR ALL
      TO service_role
      USING (true)
      WITH CHECK (true);
  END IF;
END $$;

-- ---------------------------------------------------------------------------
-- orgs and org_members
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS orgs (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT,
  tier TEXT NOT NULL DEFAULT 'free',
  stripe_customer_id TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE orgs
  ADD COLUMN IF NOT EXISTS name TEXT,
  ADD COLUMN IF NOT EXISTS email TEXT,
  ADD COLUMN IF NOT EXISTS tier TEXT DEFAULT 'free',
  ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT,
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now(),
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

CREATE TABLE IF NOT EXISTS org_members (
  org_id TEXT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  user_id UUID NOT NULL,
  role TEXT NOT NULL DEFAULT 'member',
  joined_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (org_id, user_id)
);

ALTER TABLE org_members
  ADD COLUMN IF NOT EXISTS joined_at TIMESTAMPTZ DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_orgs_tier
  ON orgs(tier);

CREATE UNIQUE INDEX IF NOT EXISTS idx_orgs_stripe_customer_id
  ON orgs(stripe_customer_id)
  WHERE stripe_customer_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_org_members_user_id
  ON org_members(user_id);

CREATE INDEX IF NOT EXISTS idx_org_members_role
  ON org_members(role);

ALTER TABLE orgs ENABLE ROW LEVEL SECURITY;
ALTER TABLE org_members ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'orgs'
      AND policyname = 'orgs_service_role_all'
  ) THEN
    CREATE POLICY orgs_service_role_all
      ON orgs
      FOR ALL
      TO service_role
      USING (true)
      WITH CHECK (true);
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'org_members'
      AND policyname = 'org_members_service_role_all'
  ) THEN
    CREATE POLICY org_members_service_role_all
      ON org_members
      FOR ALL
      TO service_role
      USING (true)
      WITH CHECK (true);
  END IF;
END $$;

GRANT ALL ON TABLE capability_services TO service_role;
GRANT ALL ON TABLE capability_executions TO service_role;
GRANT ALL ON TABLE orgs TO service_role;
GRANT ALL ON TABLE org_members TO service_role;
