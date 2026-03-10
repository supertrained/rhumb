-- Migration 0009: Add AN Score v0.3 autonomy dimensions to scores table
-- Target: Supabase (PostgreSQL 15+)

ALTER TABLE scores
  ADD COLUMN IF NOT EXISTS payment_autonomy NUMERIC(4,2),
  ADD COLUMN IF NOT EXISTS payment_autonomy_rationale TEXT,
  ADD COLUMN IF NOT EXISTS payment_autonomy_confidence NUMERIC(5,4),
  ADD COLUMN IF NOT EXISTS governance_readiness NUMERIC(4,2),
  ADD COLUMN IF NOT EXISTS governance_readiness_rationale TEXT,
  ADD COLUMN IF NOT EXISTS governance_readiness_confidence NUMERIC(5,4),
  ADD COLUMN IF NOT EXISTS web_accessibility NUMERIC(4,2),
  ADD COLUMN IF NOT EXISTS web_accessibility_rationale TEXT,
  ADD COLUMN IF NOT EXISTS web_accessibility_confidence NUMERIC(5,4),
  ADD COLUMN IF NOT EXISTS autonomy_score NUMERIC(4,2);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'chk_scores_payment_autonomy_range'
  ) THEN
    ALTER TABLE scores
      ADD CONSTRAINT chk_scores_payment_autonomy_range
      CHECK (payment_autonomy IS NULL OR (payment_autonomy >= 0 AND payment_autonomy <= 10));
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'chk_scores_governance_readiness_range'
  ) THEN
    ALTER TABLE scores
      ADD CONSTRAINT chk_scores_governance_readiness_range
      CHECK (governance_readiness IS NULL OR (governance_readiness >= 0 AND governance_readiness <= 10));
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'chk_scores_web_accessibility_range'
  ) THEN
    ALTER TABLE scores
      ADD CONSTRAINT chk_scores_web_accessibility_range
      CHECK (web_accessibility IS NULL OR (web_accessibility >= 0 AND web_accessibility <= 10));
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'chk_scores_autonomy_score_range'
  ) THEN
    ALTER TABLE scores
      ADD CONSTRAINT chk_scores_autonomy_score_range
      CHECK (autonomy_score IS NULL OR (autonomy_score >= 0 AND autonomy_score <= 10));
  END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_scores_autonomy_score ON scores(autonomy_score DESC);
