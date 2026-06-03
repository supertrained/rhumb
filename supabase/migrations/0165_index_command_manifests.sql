-- Migration 0165: Durable Index command manifest storage
--
-- PP-1/PP-2 durable hosted storage for command-level route manifests and
-- evidence packets. This table intentionally stores full manifest/evidence JSON
-- alongside indexed route taxonomy columns so Resolve can query route truth
-- without depending on private fixture registries.

BEGIN;

CREATE TABLE IF NOT EXISTS index_command_manifests (
    route_id                TEXT PRIMARY KEY,
    manifest_id             TEXT NOT NULL,
    manifest_version        TEXT NOT NULL,
    manifest_digest         TEXT NOT NULL,
    service_id              TEXT NOT NULL,
    provider_id             TEXT NOT NULL,
    capability_id           TEXT NOT NULL,
    substrate               TEXT NOT NULL,
    provenance_origin       TEXT NOT NULL,
    source_risk             TEXT NOT NULL,
    side_effect_class       TEXT NOT NULL,
    promotion_state         TEXT,
    review_status           TEXT,
    evidence_packet_id      TEXT,
    evidence_packet_digest  TEXT,
    evidence_expires_at     TIMESTAMPTZ,
    public_claim_boundary   TEXT NOT NULL,
    manifest_json           JSONB NOT NULL,
    evidence_packet_json    JSONB,
    owner                   TEXT,
    reviewer                TEXT,
    expires_at              TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_index_command_manifests_capability
    ON index_command_manifests (capability_id, route_id);

CREATE INDEX IF NOT EXISTS idx_index_command_manifests_provider
    ON index_command_manifests (capability_id, provider_id);

CREATE INDEX IF NOT EXISTS idx_index_command_manifests_taxonomy
    ON index_command_manifests (substrate, provenance_origin, source_risk);

CREATE INDEX IF NOT EXISTS idx_index_command_manifests_manifest_digest
    ON index_command_manifests (manifest_digest);

CREATE INDEX IF NOT EXISTS idx_index_command_manifests_evidence_digest
    ON index_command_manifests (evidence_packet_digest)
    WHERE evidence_packet_digest IS NOT NULL;

ALTER TABLE index_command_manifests ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS index_command_manifests_read ON index_command_manifests;
CREATE POLICY index_command_manifests_read ON index_command_manifests
    FOR SELECT
    USING (true);

COMMIT;
