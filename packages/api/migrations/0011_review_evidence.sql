-- Migration 0011: Review + evidence provenance spine for 500-review scale
-- Target: Supabase (PostgreSQL 15+)
-- Canonical score contract: `scores` (public read surface)

-- ============================================================
-- evidence_records
-- ============================================================
CREATE TABLE IF NOT EXISTS evidence_records (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  service_slug TEXT NOT NULL REFERENCES services(slug) ON DELETE CASCADE,
  source_type TEXT NOT NULL,
  source_ref TEXT,
  evidence_kind TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT,
  raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  normalized_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  fresh_until TIMESTAMPTZ,
  confidence NUMERIC(5,4),
  agent_id TEXT REFERENCES agents(agent_id) ON DELETE SET NULL,
  run_id TEXT,
  created_by TEXT NOT NULL DEFAULT 'system',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT chk_evidence_records_source_type_nonempty CHECK (char_length(trim(source_type)) > 0),
  CONSTRAINT chk_evidence_records_kind_nonempty CHECK (char_length(trim(evidence_kind)) > 0),
  CONSTRAINT chk_evidence_records_title_nonempty CHECK (char_length(trim(title)) > 0),
  CONSTRAINT chk_evidence_records_confidence_range CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);

CREATE INDEX IF NOT EXISTS idx_evidence_records_service_slug
  ON evidence_records(service_slug, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_evidence_records_source_type
  ON evidence_records(source_type, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_evidence_records_kind
  ON evidence_records(evidence_kind, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_evidence_records_agent_id
  ON evidence_records(agent_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_evidence_records_run_id
  ON evidence_records(run_id)
  WHERE run_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_evidence_records_fresh_until
  ON evidence_records(fresh_until)
  WHERE fresh_until IS NOT NULL;

ALTER TABLE evidence_records ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public read evidence_records" ON evidence_records FOR SELECT USING (true);
CREATE POLICY "Service role write evidence_records" ON evidence_records FOR ALL USING (true) WITH CHECK (true);

-- ============================================================
-- service_reviews
-- ============================================================
CREATE TABLE IF NOT EXISTS service_reviews (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  service_slug TEXT NOT NULL REFERENCES services(slug) ON DELETE CASCADE,
  reviewed_score_id UUID REFERENCES scores(id) ON DELETE SET NULL,
  review_type TEXT NOT NULL,
  review_status TEXT NOT NULL DEFAULT 'draft',
  headline TEXT NOT NULL,
  summary TEXT,
  execution_score NUMERIC(4,2),
  access_score NUMERIC(4,2),
  autonomy_score NUMERIC(4,2),
  confidence NUMERIC(5,4),
  reviewed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  reviewer_agent_id TEXT REFERENCES agents(agent_id) ON DELETE SET NULL,
  reviewer_label TEXT NOT NULL,
  source_batch_id TEXT,
  fresh_until TIMESTAMPTZ,
  evidence_count INTEGER NOT NULL DEFAULT 0,
  evidence_refs_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  tags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT chk_service_reviews_type_valid CHECK (review_type IN ('manual', 'tester', 'crawler', 'docs', 'provider', 'synthesized')),
  CONSTRAINT chk_service_reviews_status_valid CHECK (review_status IN ('draft', 'published', 'superseded', 'retracted')),
  CONSTRAINT chk_service_reviews_headline_nonempty CHECK (char_length(trim(headline)) > 0),
  CONSTRAINT chk_service_reviews_reviewer_label_nonempty CHECK (char_length(trim(reviewer_label)) > 0),
  CONSTRAINT chk_service_reviews_execution_score_range CHECK (execution_score IS NULL OR (execution_score >= 0 AND execution_score <= 10)),
  CONSTRAINT chk_service_reviews_access_score_range CHECK (access_score IS NULL OR (access_score >= 0 AND access_score <= 10)),
  CONSTRAINT chk_service_reviews_autonomy_score_range CHECK (autonomy_score IS NULL OR (autonomy_score >= 0 AND autonomy_score <= 10)),
  CONSTRAINT chk_service_reviews_confidence_range CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
  CONSTRAINT chk_service_reviews_evidence_count_nonnegative CHECK (evidence_count >= 0)
);

CREATE INDEX IF NOT EXISTS idx_service_reviews_service_slug
  ON service_reviews(service_slug, reviewed_at DESC);
CREATE INDEX IF NOT EXISTS idx_service_reviews_status
  ON service_reviews(review_status, reviewed_at DESC);
CREATE INDEX IF NOT EXISTS idx_service_reviews_type
  ON service_reviews(review_type, reviewed_at DESC);
CREATE INDEX IF NOT EXISTS idx_service_reviews_score_id
  ON service_reviews(reviewed_score_id)
  WHERE reviewed_score_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_service_reviews_reviewer_agent_id
  ON service_reviews(reviewer_agent_id, reviewed_at DESC)
  WHERE reviewer_agent_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_service_reviews_source_batch_id
  ON service_reviews(source_batch_id)
  WHERE source_batch_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_service_reviews_published
  ON service_reviews(service_slug, reviewed_at DESC)
  WHERE review_status = 'published';

ALTER TABLE service_reviews ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public read service_reviews" ON service_reviews FOR SELECT USING (true);
CREATE POLICY "Service role write service_reviews" ON service_reviews FOR ALL USING (true) WITH CHECK (true);

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM pg_proc
    WHERE proname = 'update_updated_at'
  ) AND NOT EXISTS (
    SELECT 1
    FROM pg_trigger
    WHERE tgname = 'service_reviews_updated_at'
  ) THEN
    CREATE TRIGGER service_reviews_updated_at
      BEFORE UPDATE ON service_reviews
      FOR EACH ROW EXECUTE FUNCTION update_updated_at();
  END IF;
END
$$;

-- ============================================================
-- review_evidence_links
-- ============================================================
CREATE TABLE IF NOT EXISTS review_evidence_links (
  review_id UUID NOT NULL REFERENCES service_reviews(id) ON DELETE CASCADE,
  evidence_record_id UUID NOT NULL REFERENCES evidence_records(id) ON DELETE CASCADE,
  role TEXT NOT NULL DEFAULT 'supporting',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (review_id, evidence_record_id),
  CONSTRAINT chk_review_evidence_links_role_valid CHECK (role IN ('primary', 'supporting', 'counterexample', 'freshness'))
);

CREATE INDEX IF NOT EXISTS idx_review_evidence_links_evidence_record_id
  ON review_evidence_links(evidence_record_id);
CREATE INDEX IF NOT EXISTS idx_review_evidence_links_role
  ON review_evidence_links(role);

ALTER TABLE review_evidence_links ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public read review_evidence_links" ON review_evidence_links FOR SELECT USING (true);
CREATE POLICY "Service role write review_evidence_links" ON review_evidence_links FOR ALL USING (true) WITH CHECK (true);
