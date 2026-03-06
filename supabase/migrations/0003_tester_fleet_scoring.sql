-- WU 1.7 tester fleet scoring migration (idempotent)
-- Adds probe_metadata_json to an_scores, creates tests table, adds performance indices

-- Extend an_scores with probe metadata column for tester fleet telemetry
ALTER TABLE an_scores
  ADD COLUMN IF NOT EXISTS probe_metadata_json JSONB DEFAULT NULL;

COMMENT ON COLUMN an_scores.probe_metadata_json IS
  'Tester fleet probe metadata: latency distribution, schema version, failure modes, auth flags';

-- Tests table: records each scoring run from the tester fleet
CREATE TABLE IF NOT EXISTS tests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  service_slug TEXT NOT NULL,
  probe_result_json JSONB NOT NULL,
  tested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  latency_p50 INT,
  latency_p95 INT,
  latency_p99 INT,
  status TEXT NOT NULL DEFAULT 'ok',
  auth_required BOOLEAN NOT NULL DEFAULT false,
  docs_unavailable BOOLEAN NOT NULL DEFAULT false,
  error_message TEXT,
  retry_count INT NOT NULL DEFAULT 0,
  runner_version TEXT NOT NULL DEFAULT 'score-dataset-v1',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tests_service_slug ON tests(service_slug);
CREATE INDEX IF NOT EXISTS idx_tests_tested_at ON tests(tested_at DESC);
CREATE INDEX IF NOT EXISTS idx_tests_service_tested ON tests(service_slug, tested_at DESC);

-- Additional performance indices for score queries
CREATE INDEX IF NOT EXISTS idx_an_scores_probe_metadata ON an_scores USING gin(probe_metadata_json);

-- Unique constraint to prevent duplicate scores per service per scoring run
-- (uses calculated_at rounded to minute for dedup)
CREATE UNIQUE INDEX IF NOT EXISTS idx_an_scores_service_unique_run
  ON an_scores(service_id, (date_trunc('minute', calculated_at)));
