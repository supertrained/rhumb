BEGIN;

-- Migration 0120: HRIS discovery expansion II (2026-03-29)
-- Rationale: HRIS is still a thin but high-demand operational category for
-- agents handling employee directories, onboarding/offboarding checks,
-- manager lookups, org sync, payroll-adjacent workflows, and leave-aware
-- automation. Live production depth is only five providers, so add five more
-- API-backed vendors with clear read-first Resolve potential.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'adp',
    'ADP',
    'hris',
    'Enterprise payroll and workforce platform with documented APIs for workers, organizations, events, payroll-adjacent records, and employee lifecycle integrations across large employer environments.',
    'https://developers.adp.com/',
    'api.adp.com'
  ),
  (
    'dayforce',
    'Dayforce',
    'hris',
    'HR, workforce, time, and payroll platform with developer APIs spanning employee records, org structure, schedules, workforce management, and enterprise people operations workflows.',
    'https://developers.dayforce.com/',
    'api.dayforce.com'
  ),
  (
    'paylocity',
    'Paylocity',
    'hris',
    'HR and payroll platform with APIs for employees, companies, earnings, deductions, time, and workforce data useful for directory sync, payroll support, and operational automation.',
    'https://developer.paylocity.com/integrations/docs/',
    'api.paylocity.com'
  ),
  (
    'ukg',
    'UKG',
    'hris',
    'Workforce and HR suite with developer APIs for employee, job, labor, schedule, and organizational data used in enterprise staffing, payroll, and workforce operations.',
    'https://developer.ukg.com/',
    'api.ukg.com'
  ),
  (
    'zenefits',
    'Zenefits',
    'hris',
    'SMB-focused HR platform with APIs for people records, benefits, payroll-adjacent data, time off, and org workflows that fit read-heavy assistant and internal-tool integrations.',
    'https://developers.zenefits.com/docs/getting-started',
    'api.zenefits.com'
  )
ON CONFLICT (slug) DO NOTHING;

INSERT INTO scores (
  service_slug,
  aggregate_recommendation_score,
  execution_score,
  access_readiness_score,
  confidence,
  tier,
  tier_label,
  probe_metadata,
  calculated_at
)
VALUES
  (
    'paylocity',
    8.20,
    8.35,
    8.00,
    0.64,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-29","category_rationale":"hris expansion ii","notes":"Best immediate Phase 0 target in the batch. Public docs expose concrete employee and company primitives that map cleanly to read-first employee.list/get workflows without the heaviest enterprise setup burden."}'::jsonb,
    now()
  ),
  (
    'adp',
    8.15,
    8.30,
    7.90,
    0.63,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-29","category_rationale":"hris expansion ii","notes":"Very high strategic demand and broad workforce coverage. Strong long-term Resolve target for employee and org sync primitives, but enterprise auth and provisioning complexity make it a slightly less direct first Phase 0 lane than Paylocity."}'::jsonb,
    now()
  ),
  (
    'dayforce',
    8.05,
    8.20,
    7.85,
    0.61,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-29","category_rationale":"hris expansion ii","notes":"Strong enterprise HR/workforce platform with credible employee, labor, and scheduling primitives. Valuable category depth with a good future path into employee.get/list plus schedule-aware workflows."}'::jsonb,
    now()
  ),
  (
    'ukg',
    7.95,
    8.10,
    7.75,
    0.59,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-29","category_rationale":"hris expansion ii","notes":"Important workforce operations vendor with meaningful schedule and labor context. More enterprise-shaped than the leaders, but still a strong addition for HRIS breadth and future workforce-management capability expansion."}'::jsonb,
    now()
  ),
  (
    'zenefits',
    7.85,
    7.95,
    7.75,
    0.57,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-29","category_rationale":"hris expansion ii","notes":"Useful SMB HR depth with practical people, benefits, and org data surfaces for read-heavy assistant workflows. Slightly less strategically differentiated than the leaders but still meaningful for category coverage."}'::jsonb,
    now()
  );

COMMIT;
