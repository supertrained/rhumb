-- Migration 0068: Capability Expansion Day 24
-- Domains: ticket, subscription, job, feedback
-- New capabilities: 10
-- New mappings: ~37
-- Cumulative target: ~291 capabilities / ~1000 mappings

-- ============================================================
-- DOMAIN: ticket (Helpdesk & Support Ticketing)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('ticket.create', 'ticket.create', 'ticket', 'Create a support ticket on behalf of a user or agent', '{"type":"object","required":["subject","requester_email"],"properties":{"subject":{"type":"string"},"body":{"type":"string"},"requester_email":{"type":"string"},"requester_name":{"type":"string"},"priority":{"type":"string","enum":["low","normal","high","urgent"]},"tags":{"type":"array"},"channel":{"type":"string","enum":["email","chat","api","web"]}}}', '{"type":"object","properties":{"ticket_id":{"type":"string"},"url":{"type":"string"},"status":{"type":"string"}}}'),
  ('ticket.update', 'ticket.update', 'ticket', 'Update a support ticket status, priority, or assignee', '{"type":"object","required":["ticket_id"],"properties":{"ticket_id":{"type":"string"},"status":{"type":"string","enum":["open","pending","solved","closed"]},"assignee_id":{"type":"string"},"priority":{"type":"string"},"comment":{"type":"string"},"public":{"type":"boolean","default":false}}}', '{"type":"object","properties":{"ticket_id":{"type":"string"},"status":{"type":"string"},"updated_at":{"type":"string"}}}'),
  ('ticket.search', 'ticket.search', 'ticket', 'Search support tickets by query, status, or assignee', '{"type":"object","properties":{"query":{"type":"string"},"status":{"type":"string"},"assignee_id":{"type":"string"},"created_after":{"type":"string"},"limit":{"type":"integer","default":25}}}', '{"type":"object","properties":{"tickets":{"type":"array"},"total":{"type":"integer"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- ticket.create
  ('ticket.create', 'zendesk', 'byo', 0.003, 8.2, true),
  ('ticket.create', 'freshdesk', 'byo', 0.002, 7.8, false),
  ('ticket.create', 'intercom', 'byo', 0.004, 7.9, false),
  ('ticket.create', 'help-scout', 'byo', 0.002, 7.6, false),
  -- ticket.update
  ('ticket.update', 'zendesk', 'byo', 0.003, 8.2, true),
  ('ticket.update', 'freshdesk', 'byo', 0.002, 7.8, false),
  ('ticket.update', 'intercom', 'byo', 0.003, 7.9, false),
  ('ticket.update', 'help-scout', 'byo', 0.002, 7.6, false),
  -- ticket.search
  ('ticket.search', 'zendesk', 'byo', 0.003, 8.2, true),
  ('ticket.search', 'freshdesk', 'byo', 0.002, 7.8, false),
  ('ticket.search', 'intercom', 'byo', 0.003, 7.9, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: subscription (Subscription Lifecycle Management)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('subscription.create', 'subscription.create', 'subscription', 'Create a new subscription for a customer on a plan', '{"type":"object","required":["customer_id","plan_id"],"properties":{"customer_id":{"type":"string"},"plan_id":{"type":"string"},"trial_days":{"type":"integer"},"coupon":{"type":"string"},"metadata":{"type":"object"}}}', '{"type":"object","properties":{"subscription_id":{"type":"string"},"status":{"type":"string"},"current_period_end":{"type":"string"},"trial_end":{"type":"string"}}}'),
  ('subscription.cancel', 'subscription.cancel', 'subscription', 'Cancel a subscription immediately or at period end', '{"type":"object","required":["subscription_id"],"properties":{"subscription_id":{"type":"string"},"at_period_end":{"type":"boolean","default":true},"reason":{"type":"string"}}}', '{"type":"object","properties":{"subscription_id":{"type":"string"},"status":{"type":"string"},"cancel_at":{"type":"string"}}}'),
  ('subscription.get_status', 'subscription.get_status', 'subscription', 'Retrieve the current status and billing details of a subscription', '{"type":"object","required":["subscription_id"],"properties":{"subscription_id":{"type":"string"}}}', '{"type":"object","properties":{"subscription_id":{"type":"string"},"status":{"type":"string","enum":["active","trialing","past_due","canceled","unpaid"]},"plan":{"type":"object"},"current_period_end":{"type":"string"},"mrr":{"type":"number"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- subscription.create
  ('subscription.create', 'stripe', 'byo', 0.005, 8.5, true),
  ('subscription.create', 'chargebee', 'byo', 0.006, 8.0, false),
  ('subscription.create', 'recurly', 'byo', 0.006, 7.8, false),
  ('subscription.create', 'paddle', 'byo', 0.005, 7.6, false),
  -- subscription.cancel
  ('subscription.cancel', 'stripe', 'byo', 0.004, 8.5, true),
  ('subscription.cancel', 'chargebee', 'byo', 0.005, 8.0, false),
  ('subscription.cancel', 'recurly', 'byo', 0.005, 7.8, false),
  ('subscription.cancel', 'paddle', 'byo', 0.004, 7.6, false),
  -- subscription.get_status
  ('subscription.get_status', 'stripe', 'byo', 0.002, 8.5, true),
  ('subscription.get_status', 'chargebee', 'byo', 0.003, 8.0, false),
  ('subscription.get_status', 'recurly', 'byo', 0.003, 7.8, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: job (Recruiting & Job Posting)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('job.post_listing', 'job.post_listing', 'job', 'Post a job listing to a recruiting platform or job board', '{"type":"object","required":["title","department","location"],"properties":{"title":{"type":"string"},"department":{"type":"string"},"location":{"type":"string"},"description":{"type":"string"},"employment_type":{"type":"string","enum":["full_time","part_time","contract","internship"]},"remote":{"type":"boolean"},"salary_min":{"type":"number"},"salary_max":{"type":"number"}}}', '{"type":"object","properties":{"job_id":{"type":"string"},"url":{"type":"string"},"status":{"type":"string"}}}'),
  ('job.get_candidates', 'job.get_candidates', 'job', 'Retrieve candidates who applied for a job listing', '{"type":"object","required":["job_id"],"properties":{"job_id":{"type":"string"},"stage":{"type":"string"},"limit":{"type":"integer","default":50},"since":{"type":"string"}}}', '{"type":"object","properties":{"candidates":{"type":"array"},"total":{"type":"integer"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- job.post_listing
  ('job.post_listing', 'greenhouse', 'byo', 0.005, 8.1, true),
  ('job.post_listing', 'lever', 'byo', 0.005, 8.0, false),
  ('job.post_listing', 'workable', 'byo', 0.004, 7.7, false),
  ('job.post_listing', 'breezyhr', 'byo', 0.003, 7.3, false),
  -- job.get_candidates
  ('job.get_candidates', 'greenhouse', 'byo', 0.004, 8.1, true),
  ('job.get_candidates', 'lever', 'byo', 0.004, 8.0, false),
  ('job.get_candidates', 'workable', 'byo', 0.003, 7.7, false),
  ('job.get_candidates', 'breezyhr', 'byo', 0.003, 7.3, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: feedback (NPS & User Feedback)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('feedback.collect_nps', 'feedback.collect_nps', 'feedback', 'Send an NPS or CSAT survey to a user or cohort', '{"type":"object","required":["recipient_email"],"properties":{"recipient_email":{"type":"string"},"recipient_name":{"type":"string"},"survey_type":{"type":"string","enum":["nps","csat","ces"],"default":"nps"},"delay_seconds":{"type":"integer","default":0},"properties":{"type":"object","description":"Custom properties for survey personalization"}}}', '{"type":"object","properties":{"survey_id":{"type":"string"},"sent":{"type":"boolean"},"scheduled_at":{"type":"string"}}}'),
  ('feedback.get_responses', 'feedback.get_responses', 'feedback', 'Retrieve NPS or feedback survey responses for analysis', '{"type":"object","properties":{"survey_type":{"type":"string","enum":["nps","csat","ces"]},"since":{"type":"string"},"segment":{"type":"string"},"limit":{"type":"integer","default":100}}}', '{"type":"object","properties":{"responses":{"type":"array"},"nps_score":{"type":"number"},"promoters":{"type":"integer"},"passives":{"type":"integer"},"detractors":{"type":"integer"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- feedback.collect_nps
  ('feedback.collect_nps', 'delighted', 'byo', 0.004, 8.0, true),
  ('feedback.collect_nps', 'hotjar', 'byo', 0.003, 7.7, false),
  ('feedback.collect_nps', 'medallia', 'byo', 0.008, 7.9, false),
  ('feedback.collect_nps', 'satismeter', 'byo', 0.004, 7.5, false),
  -- feedback.get_responses
  ('feedback.get_responses', 'delighted', 'byo', 0.003, 8.0, true),
  ('feedback.get_responses', 'hotjar', 'byo', 0.003, 7.7, false),
  ('feedback.get_responses', 'medallia', 'byo', 0.006, 7.9, false)
ON CONFLICT (capability_id, provider) DO NOTHING;
