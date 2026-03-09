-- Migration 0008: Create core tables for Discover layer + seed 50-service dataset
-- Target: Supabase (PostgreSQL 15+)

-- Services table (source of truth for indexed services)
CREATE TABLE IF NOT EXISTS services (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  description TEXT,
  official_docs TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- AN Scores table (latest + historical scores per service)
CREATE TABLE IF NOT EXISTS scores (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  service_slug TEXT NOT NULL REFERENCES services(slug) ON DELETE CASCADE,
  aggregate_recommendation_score NUMERIC(4,2),
  execution_score NUMERIC(4,2),
  access_readiness_score NUMERIC(4,2),
  confidence NUMERIC(5,4),
  tier TEXT,
  tier_label TEXT,
  probe_metadata JSONB DEFAULT '{}',
  calculated_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Index for leaderboard queries (category + score)
CREATE INDEX IF NOT EXISTS idx_scores_service_slug ON scores(service_slug);
CREATE INDEX IF NOT EXISTS idx_services_category ON services(category);
CREATE INDEX IF NOT EXISTS idx_scores_calculated_at ON scores(calculated_at DESC);

-- Unique constraint: one "latest" score per service (we'll use DISTINCT ON queries)
-- For now, allow multiple scores per service (historical tracking)

-- Enable RLS
ALTER TABLE services ENABLE ROW LEVEL SECURITY;
ALTER TABLE scores ENABLE ROW LEVEL SECURITY;

-- Public read access (anon key can read, only service_role can write)
CREATE POLICY "Public read services" ON services FOR SELECT USING (true);
CREATE POLICY "Public read scores" ON scores FOR SELECT USING (true);
CREATE POLICY "Service role write services" ON services FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role write scores" ON scores FOR ALL USING (true) WITH CHECK (true);

-- Updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER services_updated_at
  BEFORE UPDATE ON services
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
