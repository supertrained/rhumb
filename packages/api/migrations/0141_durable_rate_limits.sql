-- AUD-21: Durable rate limiting state
-- Persists rate limit counters across restarts and workers

CREATE TABLE IF NOT EXISTS rate_limit_windows (
    key TEXT PRIMARY KEY,
    request_count INTEGER NOT NULL DEFAULT 0,
    window_start TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    window_end TIMESTAMPTZ NOT NULL,
    last_request_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rate_limit_windows_end
    ON rate_limit_windows (window_end);

ALTER TABLE rate_limit_windows ENABLE ROW LEVEL SECURITY;

-- Atomic check-and-increment RPC
-- Returns whether the request is allowed and how many remain
CREATE OR REPLACE FUNCTION rate_limit_check(
    p_key TEXT,
    p_limit INTEGER,
    p_window_seconds INTEGER,
    p_now TIMESTAMPTZ DEFAULT NOW()
) RETURNS TABLE (
    allowed BOOLEAN,
    remaining INTEGER,
    request_count INTEGER,
    window_start TIMESTAMPTZ,
    window_end TIMESTAMPTZ
) LANGUAGE plpgsql AS $$
DECLARE
    v_window_end TIMESTAMPTZ;
    v_count INTEGER;
BEGIN
    v_window_end := p_now + (p_window_seconds || ' seconds')::INTERVAL;

    -- Try to get existing window
    SELECT rw.request_count, rw.window_end INTO v_count, rate_limit_check.window_end
    FROM rate_limit_windows rw WHERE rw.key = p_key;

    IF NOT FOUND THEN
        -- No existing window: create one and allow
        INSERT INTO rate_limit_windows (key, request_count, window_start, window_end, last_request_at)
        VALUES (p_key, 1, p_now, v_window_end, p_now)
        ON CONFLICT (key) DO UPDATE SET
            request_count = rate_limit_windows.request_count + 1,
            last_request_at = p_now;

        allowed := TRUE;
        remaining := p_limit - 1;
        request_count := 1;
        window_start := p_now;
        window_end := v_window_end;
        RETURN NEXT;
        RETURN;
    END IF;

    -- Window exists: check if expired
    IF rate_limit_check.window_end < p_now THEN
        -- Expired: reset window
        UPDATE rate_limit_windows SET
            request_count = 1,
            window_start = p_now,
            window_end = v_window_end,
            last_request_at = p_now
        WHERE rate_limit_windows.key = p_key;

        allowed := TRUE;
        remaining := p_limit - 1;
        request_count := 1;
        window_start := p_now;
        window_end := v_window_end;
        RETURN NEXT;
        RETURN;
    END IF;

    -- Window active: check limit
    IF v_count >= p_limit THEN
        -- Rate limited
        allowed := FALSE;
        remaining := 0;
        request_count := v_count;
        window_start := p_now;  -- approximate
        RETURN NEXT;
        RETURN;
    END IF;

    -- Under limit: increment
    UPDATE rate_limit_windows SET
        request_count = rate_limit_windows.request_count + 1,
        last_request_at = p_now
    WHERE rate_limit_windows.key = p_key;

    allowed := TRUE;
    remaining := p_limit - v_count - 1;
    request_count := v_count + 1;
    window_start := p_now;  -- approximate
    RETURN NEXT;
END;
$$;
