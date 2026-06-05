-- PP-6: route-fact and compact-verification fields on execution receipts

ALTER TABLE execution_receipts
    ADD COLUMN IF NOT EXISTS route_id TEXT,
    ADD COLUMN IF NOT EXISTS service_id TEXT,
    ADD COLUMN IF NOT EXISTS substrate TEXT,
    ADD COLUMN IF NOT EXISTS provenance_origin TEXT,
    ADD COLUMN IF NOT EXISTS source_risk TEXT,
    ADD COLUMN IF NOT EXISTS manifest_digest TEXT,
    ADD COLUMN IF NOT EXISTS evidence_packet_digest TEXT,
    ADD COLUMN IF NOT EXISTS route_plan_id_hash TEXT,
    ADD COLUMN IF NOT EXISTS route_explanation_id TEXT,
    ADD COLUMN IF NOT EXISTS stop_condition TEXT,
    ADD COLUMN IF NOT EXISTS retryable BOOLEAN,
    ADD COLUMN IF NOT EXISTS next_recommended_action TEXT;

CREATE INDEX IF NOT EXISTS idx_receipts_route_id_created
    ON execution_receipts (route_id, created_at DESC)
    WHERE route_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_receipts_manifest_digest
    ON execution_receipts (manifest_digest)
    WHERE manifest_digest IS NOT NULL;
