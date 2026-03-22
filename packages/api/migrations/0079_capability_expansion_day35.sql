-- Migration 0079: Capability Expansion Day 35
-- Domains: accessibility, load_test, sports, backup
-- New capabilities: 10
-- New mappings: ~36
-- Cumulative target: ~401 capabilities / ~1404 mappings
-- Milestone: 400-capability target reached

-- ============================================================
-- DOMAIN: accessibility (Web & App Accessibility Auditing)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('accessibility.scan', 'accessibility.scan', 'accessibility', 'Run an automated accessibility audit against a URL or HTML snippet', '{"type":"object","required":["target"],"properties":{"target":{"type":"string","description":"URL or raw HTML to audit"},"standard":{"type":"string","enum":["wcag2a","wcag2aa","wcag2aaa","wcag21aa","section508"],"default":"wcag2aa"},"include_warnings":{"type":"boolean","default":true}}}', '{"type":"object","properties":{"violations":{"type":"array"},"warnings":{"type":"array"},"passes":{"type":"integer"},"violation_count":{"type":"integer"},"score":{"type":"number","description":"0–100; higher is more accessible"}}}'),
  ('accessibility.report', 'accessibility.report', 'accessibility', 'Generate a formatted accessibility audit report for a URL', '{"type":"object","required":["url"],"properties":{"url":{"type":"string"},"standard":{"type":"string","enum":["wcag2aa","wcag21aa"],"default":"wcag2aa"},"format":{"type":"string","enum":["json","html","pdf"],"default":"json"}}}', '{"type":"object","properties":{"report_id":{"type":"string"},"url":{"type":"string"},"violation_count":{"type":"integer"},"report_url":{"type":"string"},"generated_at":{"type":"string"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- accessibility.scan
  ('accessibility.scan', 'deque-axe', 'byo', 0.005, 8.2, true),
  ('accessibility.scan', 'wave', 'byo', 0.004, 7.9, false),
  ('accessibility.scan', 'pa11y', 'byo', 0.003, 7.7, false),
  ('accessibility.scan', 'siteimprove', 'byo', 0.008, 8.0, false),
  -- accessibility.report
  ('accessibility.report', 'deque-axe', 'byo', 0.010, 8.2, true),
  ('accessibility.report', 'siteimprove', 'byo', 0.015, 8.0, false),
  ('accessibility.report', 'wave', 'byo', 0.008, 7.9, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: load_test (Load & Performance Testing)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('load_test.run', 'load_test.run', 'load_test', 'Start a load test against a target URL with specified concurrency and duration', '{"type":"object","required":["target_url","virtual_users","duration_sec"],"properties":{"target_url":{"type":"string"},"virtual_users":{"type":"integer"},"duration_sec":{"type":"integer"},"ramp_up_sec":{"type":"integer","default":30},"http_method":{"type":"string","enum":["GET","POST","PUT","DELETE"],"default":"GET"},"headers":{"type":"object"},"body":{"type":"string"},"thresholds":{"type":"object","description":"Pass/fail criteria, e.g. p95 < 500ms"}}}', '{"type":"object","properties":{"test_id":{"type":"string"},"status":{"type":"string","enum":["running","queued"]},"estimated_completion":{"type":"string"}}}'),
  ('load_test.get_results', 'load_test.get_results', 'load_test', 'Retrieve the results and performance metrics for a completed load test', '{"type":"object","required":["test_id"],"properties":{"test_id":{"type":"string"}}}', '{"type":"object","properties":{"test_id":{"type":"string"},"status":{"type":"string"},"p50_ms":{"type":"number"},"p95_ms":{"type":"number"},"p99_ms":{"type":"number"},"rps":{"type":"number"},"error_rate":{"type":"number"},"passed":{"type":"boolean"},"duration_sec":{"type":"integer"}}}'),
  ('load_test.get_metrics', 'load_test.get_metrics', 'load_test', 'Stream time-series performance metrics for a running or completed load test', '{"type":"object","required":["test_id"],"properties":{"test_id":{"type":"string"},"from":{"type":"string"},"to":{"type":"string"},"resolution":{"type":"string","enum":["1s","5s","30s","1m"],"default":"5s"}}}', '{"type":"object","properties":{"test_id":{"type":"string"},"series":{"type":"array","description":"Time-series data points with rps, p95, error_rate"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- load_test.run
  ('load_test.run', 'k6-cloud', 'byo', 0.020, 8.2, true),
  ('load_test.run', 'artillery-cloud', 'byo', 0.015, 7.9, false),
  ('load_test.run', 'gatling-cloud', 'byo', 0.018, 7.8, false),
  -- load_test.get_results
  ('load_test.get_results', 'k6-cloud', 'byo', 0.005, 8.2, true),
  ('load_test.get_results', 'artillery-cloud', 'byo', 0.004, 7.9, false),
  ('load_test.get_results', 'gatling-cloud', 'byo', 0.004, 7.8, false),
  -- load_test.get_metrics
  ('load_test.get_metrics', 'k6-cloud', 'byo', 0.008, 8.2, true),
  ('load_test.get_metrics', 'gatling-cloud', 'byo', 0.006, 7.8, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: sports (Sports Scores, Schedules & Standings)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('sports.get_scores', 'sports.get_scores', 'sports', 'Get live or final scores for games in a sport and league', '{"type":"object","required":["sport","league"],"properties":{"sport":{"type":"string"},"league":{"type":"string"},"date":{"type":"string","description":"YYYY-MM-DD; defaults to today"},"game_id":{"type":"string"}}}', '{"type":"object","properties":{"games":{"type":"array","items":{"type":"object","properties":{"game_id":{"type":"string"},"home_team":{"type":"string"},"away_team":{"type":"string"},"home_score":{"type":"integer"},"away_score":{"type":"integer"},"status":{"type":"string"},"period":{"type":"string"}}}}}}'),
  ('sports.get_schedule', 'sports.get_schedule', 'sports', 'Retrieve the upcoming game schedule for a team or league', '{"type":"object","required":["sport","league"],"properties":{"sport":{"type":"string"},"league":{"type":"string"},"team":{"type":"string"},"date_from":{"type":"string"},"date_to":{"type":"string"},"limit":{"type":"integer","default":10}}}', '{"type":"object","properties":{"games":{"type":"array"},"total":{"type":"integer"}}}'),
  ('sports.get_standings', 'sports.get_standings', 'sports', 'Get current league standings or division rankings', '{"type":"object","required":["sport","league"],"properties":{"sport":{"type":"string"},"league":{"type":"string"},"season":{"type":"string"},"division":{"type":"string"}}}', '{"type":"object","properties":{"standings":{"type":"array","items":{"type":"object","properties":{"rank":{"type":"integer"},"team":{"type":"string"},"wins":{"type":"integer"},"losses":{"type":"integer"},"points":{"type":"number"}}}}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- sports.get_scores
  ('sports.get_scores', 'sportradar', 'byo', 0.010, 8.3, true),
  ('sports.get_scores', 'thesportsdb', 'byo', 0.003, 7.5, false),
  ('sports.get_scores', 'api-sports', 'byo', 0.005, 7.8, false),
  -- sports.get_schedule
  ('sports.get_schedule', 'sportradar', 'byo', 0.008, 8.3, true),
  ('sports.get_schedule', 'thesportsdb', 'byo', 0.002, 7.5, false),
  ('sports.get_schedule', 'api-sports', 'byo', 0.004, 7.8, false),
  -- sports.get_standings
  ('sports.get_standings', 'sportradar', 'byo', 0.008, 8.3, true),
  ('sports.get_standings', 'thesportsdb', 'byo', 0.002, 7.5, false),
  ('sports.get_standings', 'api-sports', 'byo', 0.004, 7.8, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: backup (Data Backup & Recovery)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('backup.create', 'backup.create', 'backup', 'Trigger a backup job for a resource (database, volume, or storage bucket)', '{"type":"object","required":["resource_id","resource_type"],"properties":{"resource_id":{"type":"string"},"resource_type":{"type":"string","enum":["database","volume","bucket","vm"]},"retention_days":{"type":"integer","default":30},"tags":{"type":"object"}}}', '{"type":"object","properties":{"backup_id":{"type":"string"},"status":{"type":"string","enum":["started","queued"]},"estimated_completion":{"type":"string"}}}'),
  ('backup.get_status', 'backup.get_status', 'backup', 'Check the status and metadata of a backup job', '{"type":"object","required":["backup_id"],"properties":{"backup_id":{"type":"string"}}}', '{"type":"object","properties":{"backup_id":{"type":"string"},"status":{"type":"string","enum":["running","completed","failed"]},"size_gb":{"type":"number"},"completed_at":{"type":"string"},"expires_at":{"type":"string"},"restore_url":{"type":"string"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- backup.create
  ('backup.create', 'aws-backup', 'byo', 0.005, 8.3, true),
  ('backup.create', 'azure-backup', 'byo', 0.005, 8.2, false),
  ('backup.create', 'backblaze-b2', 'byo', 0.003, 7.8, false),
  ('backup.create', 'veeam', 'byo', 0.008, 7.9, false),
  -- backup.get_status
  ('backup.get_status', 'aws-backup', 'byo', 0.002, 8.3, true),
  ('backup.get_status', 'azure-backup', 'byo', 0.002, 8.2, false),
  ('backup.get_status', 'veeam', 'byo', 0.003, 7.9, false)
ON CONFLICT (capability_id, provider) DO NOTHING;
