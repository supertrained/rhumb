-- WU 1.2 probe runner scaffold migration (idempotent)

CREATE TABLE IF NOT EXISTS probe_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  service_id UUID REFERENCES services(id),
  probe_type TEXT NOT NULL,
  status TEXT NOT NULL,
  trigger_source TEXT NOT NULL DEFAULT 'internal',
  runner_version TEXT NOT NULL DEFAULT 'scaffold-v1',
  error_message TEXT,
  metadata JSONB,
  started_at TIMESTAMPTZ DEFAULT now(),
  finished_at TIMESTAMPTZ
);

ALTER TABLE probe_results
  ADD COLUMN IF NOT EXISTS run_id UUID REFERENCES probe_runs(id);

CREATE INDEX IF NOT EXISTS idx_probe_runs_service
  ON probe_runs(service_id, finished_at DESC);

CREATE INDEX IF NOT EXISTS idx_probe_results_run
  ON probe_results(run_id, probed_at DESC);
