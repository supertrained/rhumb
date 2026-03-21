-- Migration 0009: Service alternatives junction table
-- Supports "Alternatives" sections on service pages and agent discovery.
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS service_alternatives (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  service_id UUID NOT NULL REFERENCES services(id) ON DELETE CASCADE,
  alternative_id UUID NOT NULL REFERENCES services(id) ON DELETE CASCADE,
  relationship TEXT NOT NULL DEFAULT 'alternative'
    CHECK (relationship IN ('alternative', 'complement', 'subset')),
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(service_id, alternative_id),
  CHECK (service_id != alternative_id)
);

CREATE INDEX IF NOT EXISTS idx_service_alternatives_service
  ON service_alternatives(service_id);

CREATE INDEX IF NOT EXISTS idx_service_alternatives_alt
  ON service_alternatives(alternative_id);

-- Enable RLS (match pattern from other tables)
ALTER TABLE service_alternatives ENABLE ROW LEVEL SECURITY;

-- Public read access (alternatives are public data)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'service_alternatives' AND policyname = 'public_read_alternatives'
  ) THEN
    CREATE POLICY public_read_alternatives ON service_alternatives
      FOR SELECT USING (true);
  END IF;
END $$;

-- Service role full access
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'service_alternatives' AND policyname = 'service_role_all_alternatives'
  ) THEN
    CREATE POLICY service_role_all_alternatives ON service_alternatives
      FOR ALL USING (true) WITH CHECK (true);
  END IF;
END $$;

COMMENT ON TABLE service_alternatives IS 'Junction table linking services to their alternatives, complements, or subsets. Bidirectional: if A→B exists, the reverse relationship is implied.';
COMMENT ON COLUMN service_alternatives.relationship IS 'alternative = direct competitor, complement = works well together, subset = narrower version of the other service';
