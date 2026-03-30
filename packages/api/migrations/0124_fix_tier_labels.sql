BEGIN;

-- Migration 0124: Fix tier and tier_label on all scores
-- 
-- Root cause: v-suffixed service entries were bulk-imported with hardcoded
-- tier='L2', tier_label='Trusted'. Both values are wrong:
--   1. Tiers should be computed from aggregate_recommendation_score
--      (<4→L1, <6→L2, <8→L3, ≥8→L4)
--   2. 'Trusted' is not a published tier label
--      (correct labels: Emerging, Developing, Ready, Native)
--
-- This migration recomputes tier and tier_label for EVERY score row
-- using the canonical thresholds from scoring.py:assign_tier().

UPDATE scores
SET
  tier = CASE
    WHEN aggregate_recommendation_score < 4.0 THEN 'L1'
    WHEN aggregate_recommendation_score < 6.0 THEN 'L2'
    WHEN aggregate_recommendation_score < 8.0 THEN 'L3'
    ELSE 'L4'
  END,
  tier_label = CASE
    WHEN aggregate_recommendation_score < 4.0 THEN 'Emerging'
    WHEN aggregate_recommendation_score < 6.0 THEN 'Developing'
    WHEN aggregate_recommendation_score < 8.0 THEN 'Ready'
    ELSE 'Native'
  END
WHERE aggregate_recommendation_score IS NOT NULL;

COMMIT;
