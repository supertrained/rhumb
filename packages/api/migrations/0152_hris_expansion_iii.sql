BEGIN;

-- Migration 0152: HRIS discovery expansion III (2026-04-03)
-- Rationale: live production still shows HRIS at only four providers even though
-- agent workflows repeatedly need employee directory lookups, manager resolution,
-- org sync, onboarding/offboarding checks, and leave-aware operational context.
-- Add five more API-backed HRIS platforms with strong read-first Resolve shape.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'personio',
    'Personio',
    'hris',
    'European-focused HR and people operations platform with APIs for employees, attendance, time off, recruiting, org structure, and workflow data used in directory sync and people-ops automation.',
    'https://developer.personio.de/',
    'api.personio.de'
  ),
  (
    'hibob',
    'HiBob',
    'hris',
    'Modern HRIS platform with APIs for people records, lifecycle events, org structure, time off, payroll-adjacent workflows, and workforce data across midmarket teams.',
    'https://apidocs.hibob.com/',
    'api.hibob.com'
  ),
  (
    'humaans',
    'Humaans',
    'hris',
    'People operations platform with API access to employees, teams, reporting lines, compensation context, and workflow data for lightweight but operationally useful HR automation.',
    'https://docs.humaans.io/',
    'api.humaans.io'
  ),
  (
    'factorial-hr',
    'Factorial HR',
    'hris',
    'HR and business operations platform with APIs for employees, time off, documents, attendance, contracts, and operational records used in internal tooling and people workflows.',
    'https://apidoc.factorialhr.com/',
    'api.factorialhr.com'
  ),
  (
    'employment-hero',
    'Employment Hero',
    'hris',
    'Employment platform covering HRIS, payroll-adjacent workflows, employee records, time off, and workforce operations with programmable APIs for people-system automation.',
    'https://developer.employmenthero.com/',
    'api.employmenthero.com'
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
    'personio',
    8.45,
    8.55,
    8.20,
    0.68,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"hris expansion iii","phase0_assessment":"Best immediate Resolve candidate in the batch because Personio exposes clear employee, absence, and org-oriented primitives with strong read-first value for directory lookup and people-ops automation.","notes":"Strong practical demand across internal ops, onboarding/offboarding checks, manager lookup, and time-off-aware coordination, especially for modern European SMB and midmarket teams."}'::jsonb,
    now()
  ),
  (
    'hibob',
    8.30,
    8.40,
    8.05,
    0.66,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"hris expansion iii","phase0_assessment":"Strong follow-on Resolve candidate for employee.get/list, manager lookup, and timeoff.list because HiBob exposes rich people and lifecycle data on a modern API surface.","notes":"Strategically useful because HiBob is common in scaling midmarket companies where agents need reliable people-system context without enterprise-heavy integration friction."}'::jsonb,
    now()
  ),
  (
    'humaans',
    8.15,
    8.20,
    8.05,
    0.63,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"hris expansion iii","phase0_assessment":"Clean later Resolve target for lightweight employee directory, reporting-line lookup, and org sync workflows where developer ergonomics matter as much as raw breadth.","notes":"Good fit for modern software teams that want simple people-system automation without the heaviest enterprise HR stack."}'::jsonb,
    now()
  ),
  (
    'factorial-hr',
    8.05,
    8.10,
    7.95,
    0.61,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"hris expansion iii","phase0_assessment":"Credible Resolve target for employee.get/list and timeoff.list because Factorial exposes practical employee, attendance, and document workflows with strong operational relevance.","notes":"Adds useful SMB/midmarket HR depth beyond the U.S.-centric providers already in the catalog."}'::jsonb,
    now()
  ),
  (
    'employment-hero',
    7.95,
    8.00,
    7.85,
    0.60,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"hris expansion iii","phase0_assessment":"Worth indexing now because it exposes meaningful people and employment workflows, though the cleanest first Resolve wedge is still Personio or HiBob.","notes":"Important regional category depth for APAC-heavy teams running agent workflows against employee lifecycle and payroll-adjacent operations."}'::jsonb,
    now()
  )
ON CONFLICT (service_slug) DO UPDATE SET
  aggregate_recommendation_score = EXCLUDED.aggregate_recommendation_score,
  execution_score = EXCLUDED.execution_score,
  access_readiness_score = EXCLUDED.access_readiness_score,
  confidence = EXCLUDED.confidence,
  tier = EXCLUDED.tier,
  tier_label = EXCLUDED.tier_label,
  probe_metadata = EXCLUDED.probe_metadata,
  calculated_at = EXCLUDED.calculated_at;

COMMIT;
