-- Migration: create click_events for launch dashboard outbound tracking
-- Captures provider/docs/dispute/contact clicks via first-party redirect flow.

CREATE TABLE IF NOT EXISTS click_events (
  id BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
  event_type VARCHAR(64) NOT NULL,
  service_slug TEXT,
  page_path TEXT,
  destination_url TEXT NOT NULL,
  destination_domain TEXT NOT NULL,
  source_surface VARCHAR(64) NOT NULL DEFAULT 'unknown',
  visitor_id TEXT,
  session_id TEXT,
  utm_source TEXT,
  utm_medium TEXT,
  utm_campaign TEXT,
  utm_content TEXT,
  referrer_url TEXT
);

CREATE INDEX IF NOT EXISTS idx_click_events_created_at
  ON click_events (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_click_events_event_type
  ON click_events (event_type);

CREATE INDEX IF NOT EXISTS idx_click_events_service_slug
  ON click_events (service_slug);

CREATE INDEX IF NOT EXISTS idx_click_events_destination_domain
  ON click_events (destination_domain);

ALTER TABLE click_events ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'click_events' AND policyname = 'service_role_insert_click_events'
  ) THEN
    CREATE POLICY service_role_insert_click_events ON click_events
      FOR INSERT
      TO service_role
      WITH CHECK (true);
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'click_events' AND policyname = 'service_role_select_click_events'
  ) THEN
    CREATE POLICY service_role_select_click_events ON click_events
      FOR SELECT
      TO service_role
      USING (true);
  END IF;
END $$;

GRANT SELECT, INSERT ON click_events TO service_role;
GRANT ALL ON click_events TO service_role;
GRANT USAGE, SELECT ON SEQUENCE click_events_id_seq TO service_role;
