-- WU 1.1 score engine migration (idempotent)

CREATE TABLE IF NOT EXISTS an_scores (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  service_id UUID REFERENCES services(id),
  score NUMERIC(3,1) NOT NULL,
  confidence NUMERIC(3,2) NOT NULL,
  tier TEXT NOT NULL,
  explanation TEXT NOT NULL,
  dimension_snapshot JSONB NOT NULL,
  calculated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_an_scores_service ON an_scores(service_id, calculated_at DESC);
CREATE INDEX IF NOT EXISTS idx_an_scores_score ON an_scores(score DESC, calculated_at DESC);
