CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Services indexed by Rhumb
CREATE TABLE IF NOT EXISTS services (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  description TEXT,
  base_url TEXT,
  docs_url TEXT,
  openapi_url TEXT,
  mcp_server_url TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Individual dimension scores
CREATE TABLE IF NOT EXISTS dimension_scores (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  service_id UUID REFERENCES services(id),
  dimension TEXT NOT NULL,
  score NUMERIC(3,1) NOT NULL,
  evidence_count INT DEFAULT 0,
  last_evidence_at TIMESTAMPTZ,
  explanation TEXT,
  calculated_at TIMESTAMPTZ DEFAULT now()
);

-- Composite AN Score (materialized)
CREATE TABLE IF NOT EXISTS an_scores (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  service_id UUID REFERENCES services(id),
  score NUMERIC(3,1) NOT NULL,
  confidence NUMERIC(3,2) NOT NULL,
  tier TEXT NOT NULL,
  explanation TEXT NOT NULL,
  dimension_snapshot JSONB NOT NULL,
  calculated_at TIMESTAMPTZ DEFAULT now()
);

-- Raw probe results
CREATE TABLE IF NOT EXISTS probe_results (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  service_id UUID REFERENCES services(id),
  probe_type TEXT NOT NULL,
  status TEXT NOT NULL,
  latency_ms INT,
  response_code INT,
  response_schema_hash TEXT,
  raw_response JSONB,
  metadata JSONB,
  probed_at TIMESTAMPTZ DEFAULT now()
);

-- Schema snapshots for change detection
CREATE TABLE IF NOT EXISTS schema_snapshots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  service_id UUID REFERENCES services(id),
  endpoint TEXT NOT NULL,
  schema_hash TEXT NOT NULL,
  schema_body JSONB NOT NULL,
  previous_hash TEXT,
  is_breaking BOOLEAN DEFAULT false,
  diff_summary TEXT,
  captured_at TIMESTAMPTZ DEFAULT now()
);

-- Failure modes
CREATE TABLE IF NOT EXISTS failure_modes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  service_id UUID REFERENCES services(id),
  category TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  severity TEXT NOT NULL,
  frequency TEXT NOT NULL,
  agent_impact TEXT,
  workaround TEXT,
  first_detected TIMESTAMPTZ,
  last_verified TIMESTAMPTZ,
  resolved_at TIMESTAMPTZ,
  evidence_count INT DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_probe_results_service ON probe_results(service_id, probed_at DESC);
CREATE INDEX IF NOT EXISTS idx_an_scores_service ON an_scores(service_id, calculated_at DESC);
CREATE INDEX IF NOT EXISTS idx_schema_snapshots_service ON schema_snapshots(service_id, captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_failure_modes_service ON failure_modes(service_id, resolved_at);
CREATE INDEX IF NOT EXISTS idx_services_category ON services(category);
