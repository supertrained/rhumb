-- AUD-3 follow-on: preserve the exact canonical signed payload for score-audit rows
-- so future verification does not depend solely on reconstructing payloads from sparse columns.

ALTER TABLE score_audit_chain
ADD COLUMN IF NOT EXISTS payload_canonical_json TEXT;

COMMENT ON COLUMN score_audit_chain.payload_canonical_json IS
'Canonical JSON payload used for score_audit_chain HMAC signing at write time.';
