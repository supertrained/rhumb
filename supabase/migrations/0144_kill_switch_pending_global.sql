-- AUD-5 follow-up: durable pending global kill approvals
-- Persist pending two-person approval requests across restarts/workers

ALTER TABLE kill_switch_state
    ADD COLUMN IF NOT EXISTS second_approver TEXT,
    ADD COLUMN IF NOT EXISTS chain_hash TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS kill_switch_pending_global (
    request_id TEXT PRIMARY KEY,
    reason TEXT NOT NULL DEFAULT '',
    requester_type TEXT NOT NULL,
    requester_unique_id TEXT NOT NULL,
    requester_display_name TEXT NOT NULL,
    requester_verified_at TIMESTAMPTZ NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE kill_switch_pending_global ENABLE ROW LEVEL SECURITY;
