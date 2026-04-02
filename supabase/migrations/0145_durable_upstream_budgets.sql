-- AUD-R4-01: Durable managed upstream budgets
-- Persists managed provider budget counters across restarts and workers

CREATE TABLE IF NOT EXISTS upstream_budget_windows (
    provider_slug TEXT NOT NULL,
    window_key TEXT NOT NULL,
    usage_count BIGINT NOT NULL DEFAULT 0,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NULL,
    last_request_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (provider_slug, window_key)
);

CREATE INDEX IF NOT EXISTS idx_upstream_budget_windows_last_request
    ON upstream_budget_windows (last_request_at);

ALTER TABLE upstream_budget_windows ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION upstream_budget_check_and_increment(
    p_provider_slug TEXT,
    p_window_key TEXT,
    p_limit INTEGER,
    p_window_start TIMESTAMPTZ,
    p_window_end TIMESTAMPTZ DEFAULT NULL,
    p_enforce_limit BOOLEAN DEFAULT TRUE
) RETURNS TABLE (
    allowed BOOLEAN,
    remaining INTEGER,
    usage_count BIGINT,
    window_start TIMESTAMPTZ,
    window_end TIMESTAMPTZ
) LANGUAGE plpgsql AS $$
DECLARE
    v_usage_count BIGINT;
BEGIN
    LOOP
        UPDATE upstream_budget_windows
        SET
            usage_count = upstream_budget_windows.usage_count + 1,
            last_request_at = NOW(),
            window_start = p_window_start,
            window_end = p_window_end
        WHERE upstream_budget_windows.provider_slug = p_provider_slug
          AND upstream_budget_windows.window_key = p_window_key
          AND (
              NOT p_enforce_limit
              OR p_limit <= 0
              OR upstream_budget_windows.usage_count < p_limit
          )
        RETURNING
            upstream_budget_windows.usage_count,
            upstream_budget_windows.window_start,
            upstream_budget_windows.window_end
        INTO
            v_usage_count,
            upstream_budget_check_and_increment.window_start,
            upstream_budget_check_and_increment.window_end;

        IF FOUND THEN
            allowed := TRUE;
            usage_count := v_usage_count;
            remaining := CASE
                WHEN p_limit > 0 THEN GREATEST(p_limit - v_usage_count, 0)
                ELSE 0
            END;
            RETURN NEXT;
            RETURN;
        END IF;

        SELECT
            ubw.usage_count,
            ubw.window_start,
            ubw.window_end
        INTO
            v_usage_count,
            upstream_budget_check_and_increment.window_start,
            upstream_budget_check_and_increment.window_end
        FROM upstream_budget_windows ubw
        WHERE ubw.provider_slug = p_provider_slug
          AND ubw.window_key = p_window_key;

        IF FOUND THEN
            allowed := FALSE;
            usage_count := v_usage_count;
            remaining := 0;
            RETURN NEXT;
            RETURN;
        END IF;

        BEGIN
            INSERT INTO upstream_budget_windows (
                provider_slug,
                window_key,
                usage_count,
                window_start,
                window_end,
                last_request_at
            ) VALUES (
                p_provider_slug,
                p_window_key,
                1,
                p_window_start,
                p_window_end,
                NOW()
            );

            allowed := TRUE;
            usage_count := 1;
            remaining := CASE
                WHEN p_limit > 0 THEN GREATEST(p_limit - 1, 0)
                ELSE 0
            END;
            window_start := p_window_start;
            window_end := p_window_end;
            RETURN NEXT;
            RETURN;
        EXCEPTION
            WHEN unique_violation THEN
                -- Concurrent insert on same provider/window. Retry through the loop.
        END;
    END LOOP;
END;
$$;
