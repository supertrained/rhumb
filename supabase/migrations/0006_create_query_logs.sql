-- Migration: Create query_logs table for usage analytics instrumentation
-- WU 3.5: Track query patterns from agents discovering and evaluating tools
-- Idempotent: uses IF NOT EXISTS throughout

CREATE TABLE IF NOT EXISTS query_logs (
  id BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,

  -- Source: 'mcp', 'cli', 'web', 'api'
  source VARCHAR(50) NOT NULL,

  -- Query classification
  query_type VARCHAR(100),          -- 'score_lookup', 'search', 'list_by_category', etc.
  query_text TEXT,                   -- Raw query or command

  -- Structured parameters (flexible JSON)
  query_params JSONB,

  -- Agent/User context (optional, extracted from headers)
  agent_id VARCHAR(255),
  user_agent TEXT,

  -- Results
  result_count INT,
  result_status VARCHAR(50),        -- 'success', 'not_found', 'rate_limit', 'error'

  -- Performance
  latency_ms INT
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_query_logs_source
  ON query_logs(source);

CREATE INDEX IF NOT EXISTS idx_query_logs_created_at
  ON query_logs(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_query_logs_agent_id
  ON query_logs(agent_id);

CREATE INDEX IF NOT EXISTS idx_query_logs_result_status
  ON query_logs(result_status);

-- RLS: enable row-level security
ALTER TABLE query_logs ENABLE ROW LEVEL SECURITY;

-- Policy: service role can insert (for backend logging)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'query_logs' AND policyname = 'service_role_insert_query_logs'
  ) THEN
    CREATE POLICY service_role_insert_query_logs ON query_logs
      FOR INSERT
      TO service_role
      WITH CHECK (true);
  END IF;
END $$;

-- Policy: anyone can select last 30 days (for analytics/dashboards)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'query_logs' AND policyname = 'public_select_recent_query_logs'
  ) THEN
    CREATE POLICY public_select_recent_query_logs ON query_logs
      FOR SELECT
      TO anon, authenticated, service_role
      USING (created_at >= NOW() - INTERVAL '30 days');
  END IF;
END $$;

-- Grant permissions
GRANT SELECT ON query_logs TO anon, authenticated;
GRANT INSERT ON query_logs TO service_role;
GRANT ALL ON query_logs TO service_role;
GRANT USAGE, SELECT ON SEQUENCE query_logs_id_seq TO service_role;
