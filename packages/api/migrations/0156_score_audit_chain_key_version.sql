-- AUD-3 follow-on: score_audit_chain key-version parity
--
-- Billing, audit, and kill-switch chains already persist key_version for
-- rotation-safe verification. score_audit_chain still lacked this field,
-- which meant score-chain entries could not prove which signing key version
-- produced a given hash.
--
-- Existing rows remain valid without key_version because verification falls
-- back across configured keys for legacy entries. New rows must persist the
-- active key version.

ALTER TABLE score_audit_chain
    ADD COLUMN IF NOT EXISTS key_version INTEGER;

COMMENT ON COLUMN score_audit_chain.key_version IS
    'Signing key version used to compute chain_hash; NULL for legacy pre-rotation rows.';
