-- Migration 0013: materialize review-level trust provenance
-- Goal: make quality-floor tracking measurable at the review row level.

ALTER TABLE service_reviews
  ADD COLUMN IF NOT EXISTS highest_trust_source TEXT;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'chk_service_reviews_highest_trust_source_valid'
  ) THEN
    ALTER TABLE service_reviews
      ADD CONSTRAINT chk_service_reviews_highest_trust_source_valid
      CHECK (
        highest_trust_source IS NULL
        OR highest_trust_source IN (
          'docs_derived',
          'runtime_verified',
          'tester_generated',
          'probe_generated',
          'manual_operator'
        )
      );
  END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_service_reviews_highest_trust_source
  ON service_reviews(highest_trust_source, reviewed_at DESC)
  WHERE highest_trust_source IS NOT NULL;

-- Backfill from linked evidence when provenance exists.
WITH ranked_sources AS (
  SELECT
    rel.review_id,
    er.source_type,
    row_number() OVER (
      PARTITION BY rel.review_id
      ORDER BY CASE er.source_type
        WHEN 'runtime_verified' THEN 5
        WHEN 'tester_generated' THEN 4
        WHEN 'probe_generated' THEN 3
        WHEN 'manual_operator' THEN 2
        WHEN 'docs_derived' THEN 1
        ELSE 0
      END DESC,
      er.observed_at DESC,
      er.created_at DESC,
      er.id DESC
    ) AS rn
  FROM review_evidence_links rel
  JOIN evidence_records er ON er.id = rel.evidence_record_id
)
UPDATE service_reviews sr
SET highest_trust_source = ranked_sources.source_type,
    updated_at = now()
FROM ranked_sources
WHERE sr.id = ranked_sources.review_id
  AND ranked_sources.rn = 1
  AND (sr.highest_trust_source IS DISTINCT FROM ranked_sources.source_type);

-- Fallback backfill when a review has no linked evidence yet.
UPDATE service_reviews
SET highest_trust_source = CASE review_type
    WHEN 'docs' THEN 'docs_derived'
    WHEN 'tester' THEN 'tester_generated'
    WHEN 'crawler' THEN 'probe_generated'
    WHEN 'manual' THEN 'manual_operator'
    WHEN 'provider' THEN 'manual_operator'
    WHEN 'synthesized' THEN 'docs_derived'
    ELSE highest_trust_source
  END,
  updated_at = now()
WHERE highest_trust_source IS NULL;
