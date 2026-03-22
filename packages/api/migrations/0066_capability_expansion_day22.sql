-- Migration 0066: Capability Expansion Day 22
-- Domains: project, appointment, telephony, experiment
-- New capabilities: 10
-- New mappings: ~36
-- Cumulative target: ~271 capabilities / ~927 mappings

-- ============================================================
-- DOMAIN: project (Project & Task Management)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('project.create_task', 'project.create_task', 'project', 'Create a task or issue in a project management system', '{"type":"object","required":["title"],"properties":{"title":{"type":"string"},"description":{"type":"string"},"assignee_id":{"type":"string"},"project_id":{"type":"string"},"priority":{"type":"string","enum":["urgent","high","medium","low"]},"due_date":{"type":"string"},"labels":{"type":"array"}}}', '{"type":"object","properties":{"task_id":{"type":"string"},"url":{"type":"string"},"status":{"type":"string"}}}'),
  ('project.update_status', 'project.update_status', 'project', 'Update the status or state of a task or issue', '{"type":"object","required":["task_id","status"],"properties":{"task_id":{"type":"string"},"status":{"type":"string"},"comment":{"type":"string"}}}', '{"type":"object","properties":{"task_id":{"type":"string"},"status":{"type":"string"},"updated_at":{"type":"string"}}}'),
  ('project.get_board', 'project.get_board', 'project', 'Retrieve the current state of a project board with tasks grouped by status', '{"type":"object","required":["project_id"],"properties":{"project_id":{"type":"string"},"assignee_id":{"type":"string"},"include_done":{"type":"boolean","default":false}}}', '{"type":"object","properties":{"columns":{"type":"array"},"total_tasks":{"type":"integer"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- project.create_task
  ('project.create_task', 'linear', 'byo', 0.002, 8.2, true),
  ('project.create_task', 'jira', 'byo', 0.003, 7.8, false),
  ('project.create_task', 'asana', 'byo', 0.002, 7.6, false),
  ('project.create_task', 'github', 'byo', 0.001, 7.5, false),
  -- project.update_status
  ('project.update_status', 'linear', 'byo', 0.002, 8.2, true),
  ('project.update_status', 'jira', 'byo', 0.003, 7.8, false),
  ('project.update_status', 'asana', 'byo', 0.002, 7.6, false),
  ('project.update_status', 'trello', 'byo', 0.001, 7.0, false),
  -- project.get_board
  ('project.get_board', 'linear', 'byo', 0.002, 8.2, true),
  ('project.get_board', 'jira', 'byo', 0.003, 7.8, false),
  ('project.get_board', 'asana', 'byo', 0.002, 7.6, false),
  ('project.get_board', 'trello', 'byo', 0.001, 7.0, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: appointment (Scheduling & Appointment Booking)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('appointment.get_availability', 'appointment.get_availability', 'appointment', 'Retrieve available time slots for a user or resource', '{"type":"object","required":["owner_id"],"properties":{"owner_id":{"type":"string"},"date_from":{"type":"string"},"date_to":{"type":"string"},"duration_min":{"type":"integer","default":30},"timezone":{"type":"string"}}}', '{"type":"object","properties":{"slots":{"type":"array","items":{"type":"object","properties":{"start":{"type":"string"},"end":{"type":"string"}}}}}}'),
  ('appointment.book', 'appointment.book', 'appointment', 'Book an appointment slot for an attendee', '{"type":"object","required":["owner_id","start","attendee_email"],"properties":{"owner_id":{"type":"string"},"start":{"type":"string"},"duration_min":{"type":"integer","default":30},"attendee_email":{"type":"string"},"attendee_name":{"type":"string"},"notes":{"type":"string"},"timezone":{"type":"string"}}}', '{"type":"object","properties":{"booking_id":{"type":"string"},"confirmation_url":{"type":"string"},"calendar_invite_sent":{"type":"boolean"}}}'),
  ('appointment.cancel', 'appointment.cancel', 'appointment', 'Cancel an existing appointment booking', '{"type":"object","required":["booking_id"],"properties":{"booking_id":{"type":"string"},"reason":{"type":"string"},"notify_attendee":{"type":"boolean","default":true}}}', '{"type":"object","properties":{"status":{"type":"string"},"cancelled_at":{"type":"string"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- appointment.get_availability
  ('appointment.get_availability', 'calendly', 'byo', 0.002, 8.0, true),
  ('appointment.get_availability', 'cal-com', 'byo', 0.001, 7.7, false),
  ('appointment.get_availability', 'acuity', 'byo', 0.002, 7.4, false),
  ('appointment.get_availability', 'savvycal', 'byo', 0.002, 7.2, false),
  -- appointment.book
  ('appointment.book', 'calendly', 'byo', 0.003, 8.0, true),
  ('appointment.book', 'cal-com', 'byo', 0.002, 7.7, false),
  ('appointment.book', 'acuity', 'byo', 0.003, 7.4, false),
  -- appointment.cancel
  ('appointment.cancel', 'calendly', 'byo', 0.002, 8.0, true),
  ('appointment.cancel', 'cal-com', 'byo', 0.001, 7.7, false),
  ('appointment.cancel', 'acuity', 'byo', 0.002, 7.4, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: telephony (Voice Calls & Recordings)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('telephony.make_call', 'telephony.make_call', 'telephony', 'Initiate an outbound voice call to a phone number', '{"type":"object","required":["to","from"],"properties":{"to":{"type":"string"},"from":{"type":"string"},"url":{"type":"string","description":"TwiML or webhook URL for call instructions"},"record":{"type":"boolean","default":false},"timeout":{"type":"integer","default":30}}}', '{"type":"object","properties":{"call_id":{"type":"string"},"status":{"type":"string"},"direction":{"type":"string"}}}'),
  ('telephony.get_recording', 'telephony.get_recording', 'telephony', 'Retrieve a call recording URL and metadata', '{"type":"object","required":["call_id"],"properties":{"call_id":{"type":"string"}}}', '{"type":"object","properties":{"recording_id":{"type":"string"},"url":{"type":"string"},"duration_sec":{"type":"integer"},"created_at":{"type":"string"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- telephony.make_call
  ('telephony.make_call', 'twilio', 'byo', 0.02, 8.3, true),
  ('telephony.make_call', 'vonage', 'byo', 0.018, 7.8, false),
  ('telephony.make_call', 'plivo', 'byo', 0.015, 7.5, false),
  ('telephony.make_call', 'signalwire', 'byo', 0.016, 7.3, false),
  -- telephony.get_recording
  ('telephony.get_recording', 'twilio', 'byo', 0.003, 8.3, true),
  ('telephony.get_recording', 'vonage', 'byo', 0.003, 7.8, false),
  ('telephony.get_recording', 'plivo', 'byo', 0.002, 7.5, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: experiment (A/B Testing & Feature Experiments)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('experiment.create', 'experiment.create', 'experiment', 'Create a new A/B test or feature experiment', '{"type":"object","required":["name","variants"],"properties":{"name":{"type":"string"},"variants":{"type":"array","items":{"type":"object","properties":{"key":{"type":"string"},"weight":{"type":"number"}}}},"targeting":{"type":"object"},"hypothesis":{"type":"string"}}}', '{"type":"object","properties":{"experiment_id":{"type":"string"},"status":{"type":"string"},"url":{"type":"string"}}}'),
  ('experiment.get_results', 'experiment.get_results', 'experiment', 'Retrieve statistical results for a running or completed experiment', '{"type":"object","required":["experiment_id"],"properties":{"experiment_id":{"type":"string"}}}', '{"type":"object","properties":{"experiment_id":{"type":"string"},"status":{"type":"string"},"winner":{"type":"string"},"variants":{"type":"array"},"confidence":{"type":"number"},"sample_size":{"type":"integer"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- experiment.create
  ('experiment.create', 'statsig', 'byo', 0.003, 8.0, true),
  ('experiment.create', 'optimizely', 'byo', 0.005, 7.9, false),
  ('experiment.create', 'launchdarkly', 'byo', 0.004, 7.8, false),
  ('experiment.create', 'growthbook', 'byo', 0.002, 7.5, false),
  -- experiment.get_results
  ('experiment.get_results', 'statsig', 'byo', 0.003, 8.0, true),
  ('experiment.get_results', 'optimizely', 'byo', 0.004, 7.9, false),
  ('experiment.get_results', 'launchdarkly', 'byo', 0.003, 7.8, false),
  ('experiment.get_results', 'growthbook', 'byo', 0.002, 7.5, false)
ON CONFLICT (capability_id, provider) DO NOTHING;
