-- AUD-3 follow-on: durable chain row key-version parity
--
-- The in-memory/event payloads already carry key_version for billing and audit
-- chains, but the durable Postgres rows still lacked explicit key_version
-- columns. Add them so stored rows can be verified against the correct signing
-- key after rotation.

ALTER TABLE billing_events
    ADD COLUMN IF NOT EXISTS key_version INTEGER;

ALTER TABLE audit_events
    ADD COLUMN IF NOT EXISTS key_version INTEGER;

COMMENT ON COLUMN billing_events.key_version IS
    'Signing key version used to compute chain_hash; NULL for legacy rows.';

COMMENT ON COLUMN audit_events.key_version IS
    'Signing key version used to compute chain_hash; NULL for legacy rows.';
