-- Migration 0081: Capability Expansion Day 37
-- Domains: conversation_intelligence, geofence, package, forecast
-- New capabilities: 10
-- New mappings: ~37
-- Cumulative target: ~421 capabilities / ~1478 mappings

-- ============================================================
-- DOMAIN: conversation_intelligence (Sales Call Analysis)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('conversation_intelligence.analyze_call', 'conversation_intelligence.analyze_call', 'conversation_intelligence', 'Submit a call recording for AI-powered conversation analysis', '{"type":"object","required":["recording_url"],"properties":{"recording_url":{"type":"string"},"participants":{"type":"array","items":{"type":"object","properties":{"name":{"type":"string"},"role":{"type":"string","enum":["rep","prospect","customer"]}}}},"crm_deal_id":{"type":"string"},"language":{"type":"string","default":"en"}}}', '{"type":"object","properties":{"analysis_id":{"type":"string"},"status":{"type":"string","enum":["processing","completed","failed"]},"estimated_seconds":{"type":"integer"}}}'),
  ('conversation_intelligence.get_transcript', 'conversation_intelligence.get_transcript', 'conversation_intelligence', 'Retrieve the full transcript and speaker diarization for an analyzed call', '{"type":"object","required":["analysis_id"],"properties":{"analysis_id":{"type":"string"}}}', '{"type":"object","properties":{"analysis_id":{"type":"string"},"transcript":{"type":"array","items":{"type":"object","properties":{"speaker":{"type":"string"},"text":{"type":"string"},"start_sec":{"type":"number"},"end_sec":{"type":"number"}}}},"duration_sec":{"type":"integer"}}}'),
  ('conversation_intelligence.get_insights', 'conversation_intelligence.get_insights', 'conversation_intelligence', 'Get AI-extracted insights from an analyzed call: topics, sentiment, next steps', '{"type":"object","required":["analysis_id"],"properties":{"analysis_id":{"type":"string"}}}', '{"type":"object","properties":{"topics":{"type":"array"},"sentiment":{"type":"string","enum":["positive","neutral","negative"]},"talk_ratio":{"type":"object","description":"Speaker name → percentage"},"next_steps":{"type":"array"},"questions_asked":{"type":"integer"},"filler_words":{"type":"integer"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- conversation_intelligence.analyze_call
  ('conversation_intelligence.analyze_call', 'gong', 'byo', 0.020, 8.4, true),
  ('conversation_intelligence.analyze_call', 'chorus', 'byo', 0.018, 8.1, false),
  ('conversation_intelligence.analyze_call', 'fireflies', 'byo', 0.010, 7.9, false),
  ('conversation_intelligence.analyze_call', 'clari', 'byo', 0.022, 8.2, false),
  -- conversation_intelligence.get_transcript
  ('conversation_intelligence.get_transcript', 'gong', 'byo', 0.008, 8.4, true),
  ('conversation_intelligence.get_transcript', 'chorus', 'byo', 0.007, 8.1, false),
  ('conversation_intelligence.get_transcript', 'fireflies', 'byo', 0.005, 7.9, false),
  -- conversation_intelligence.get_insights
  ('conversation_intelligence.get_insights', 'gong', 'byo', 0.010, 8.4, true),
  ('conversation_intelligence.get_insights', 'chorus', 'byo', 0.009, 8.1, false),
  ('conversation_intelligence.get_insights', 'clari', 'byo', 0.012, 8.2, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: geofence (Geofencing & Location Events)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('geofence.create', 'geofence.create', 'geofence', 'Create a geographic boundary that triggers events when entered or exited', '{"type":"object","required":["name","geometry"],"properties":{"name":{"type":"string"},"geometry":{"type":"object","description":"GeoJSON Polygon or Circle with center + radius_meters"},"metadata":{"type":"object"},"notify_url":{"type":"string","description":"Webhook URL for enter/exit events"}}}', '{"type":"object","properties":{"geofence_id":{"type":"string"},"name":{"type":"string"},"status":{"type":"string","enum":["active","inactive"]}}}'),
  ('geofence.check', 'geofence.check', 'geofence', 'Check whether a coordinate is inside one or more active geofences', '{"type":"object","required":["latitude","longitude"],"properties":{"latitude":{"type":"number"},"longitude":{"type":"number"},"geofence_ids":{"type":"array","description":"Specific fences to check; omit for all active"}}}', '{"type":"object","properties":{"inside":{"type":"array","items":{"type":"string","description":"Geofence IDs the point is within"}},"outside":{"type":"array"}}}'),
  ('geofence.list_events', 'geofence.list_events', 'geofence', 'List enter/exit events for a geofence within a time range', '{"type":"object","required":["geofence_id"],"properties":{"geofence_id":{"type":"string"},"event_type":{"type":"string","enum":["enter","exit","dwell"]},"from":{"type":"string"},"to":{"type":"string"},"limit":{"type":"integer","default":25}}}', '{"type":"object","properties":{"events":{"type":"array"},"total":{"type":"integer"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- geofence.create
  ('geofence.create', 'radar', 'byo', 0.004, 8.1, true),
  ('geofence.create', 'here', 'byo', 0.005, 8.0, false),
  ('geofence.create', 'google-maps', 'byo', 0.005, 8.2, false),
  -- geofence.check
  ('geofence.check', 'radar', 'byo', 0.002, 8.1, true),
  ('geofence.check', 'here', 'byo', 0.003, 8.0, false),
  ('geofence.check', 'google-maps', 'byo', 0.003, 8.2, false),
  -- geofence.list_events
  ('geofence.list_events', 'radar', 'byo', 0.003, 8.1, true),
  ('geofence.list_events', 'here', 'byo', 0.004, 8.0, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: package (Software Package Registry)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('package.search', 'package.search', 'package', 'Search a software package registry by name or keyword', '{"type":"object","required":["query"],"properties":{"query":{"type":"string"},"registry":{"type":"string","enum":["npm","pypi","crates","rubygems","packagist","maven"],"default":"npm"},"limit":{"type":"integer","default":10}}}', '{"type":"object","properties":{"packages":{"type":"array","items":{"type":"object","properties":{"name":{"type":"string"},"description":{"type":"string"},"version":{"type":"string"},"downloads":{"type":"integer"},"registry":{"type":"string"}}}},"total":{"type":"integer"}}}'),
  ('package.get_info', 'package.get_info', 'package', 'Retrieve metadata, version history, and dependencies for a package', '{"type":"object","required":["name","registry"],"properties":{"name":{"type":"string"},"registry":{"type":"string","enum":["npm","pypi","crates","rubygems","packagist","maven"]},"version":{"type":"string","description":"Specific version; omit for latest"}}}', '{"type":"object","properties":{"name":{"type":"string"},"version":{"type":"string"},"description":{"type":"string"},"license":{"type":"string"},"homepage":{"type":"string"},"dependencies":{"type":"object"},"weekly_downloads":{"type":"integer"},"published_at":{"type":"string"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- package.search
  ('package.search', 'npm-registry', 'byo', 0.001, 8.0, true),
  ('package.search', 'pypi', 'byo', 0.001, 7.9, false),
  ('package.search', 'crates-io', 'byo', 0.001, 7.8, false),
  ('package.search', 'libraries-io', 'byo', 0.003, 7.7, false),
  -- package.get_info
  ('package.get_info', 'npm-registry', 'byo', 0.001, 8.0, true),
  ('package.get_info', 'pypi', 'byo', 0.001, 7.9, false),
  ('package.get_info', 'libraries-io', 'byo', 0.002, 7.7, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: forecast (Demand & Time-Series Forecasting)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('forecast.run', 'forecast.run', 'forecast', 'Submit a time-series dataset and run a demand or metric forecast', '{"type":"object","required":["series"],"properties":{"series":{"type":"array","items":{"type":"object","required":["timestamp","value"],"properties":{"timestamp":{"type":"string"},"value":{"type":"number"},"item_id":{"type":"string"}}}},"horizon":{"type":"integer","description":"Number of future periods to forecast","default":30},"frequency":{"type":"string","enum":["D","W","M","H"],"description":"Daily, Weekly, Monthly, Hourly","default":"D"},"algorithm":{"type":"string","enum":["auto","arima","prophet","deepar"],"default":"auto"}}}', '{"type":"object","properties":{"job_id":{"type":"string"},"status":{"type":"string","enum":["queued","running"]},"estimated_seconds":{"type":"integer"}}}'),
  ('forecast.get_results', 'forecast.get_results', 'forecast', 'Retrieve the completed forecast values and confidence intervals', '{"type":"object","required":["job_id"],"properties":{"job_id":{"type":"string"}}}', '{"type":"object","properties":{"job_id":{"type":"string"},"status":{"type":"string"},"predictions":{"type":"array","items":{"type":"object","properties":{"timestamp":{"type":"string"},"value":{"type":"number"},"lower":{"type":"number"},"upper":{"type":"number"}}}},"algorithm_used":{"type":"string"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- forecast.run
  ('forecast.run', 'aws-forecast', 'byo', 0.020, 8.1, true),
  ('forecast.run', 'nixtla', 'byo', 0.010, 8.0, false),
  ('forecast.run', 'google-vertex-forecast', 'byo', 0.018, 7.9, false),
  -- forecast.get_results
  ('forecast.get_results', 'aws-forecast', 'byo', 0.005, 8.1, true),
  ('forecast.get_results', 'nixtla', 'byo', 0.004, 8.0, false),
  ('forecast.get_results', 'google-vertex-forecast', 'byo', 0.005, 7.9, false)
ON CONFLICT (capability_id, provider) DO NOTHING;
