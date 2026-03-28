BEGIN;

-- Migration 0107: HRIS discovery expansion (2026-03-27)
-- Rationale: HRIS remains a high-demand operational category for agencies, internal tooling,
-- and AI assistants doing people, leave, directory, and employee-lifecycle work, but live
-- production coverage is still thin (5 services before this batch: BambooHR, Deel, Gusto,
-- Rippling, Workday). Add four recognizable vendors with documented APIs and plausible
-- Phase 0 Resolve potential.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'hibob',
    'HiBob',
    'hris',
    'Modern HRIS platform with a public REST API covering people data, time off, attendance, hiring, workforce planning, payroll-adjacent records, and webhooks for employee lifecycle changes.',
    'https://apidocs.hibob.com/',
    'api.hibob.com'
  ),
  (
    'personio',
    'Personio',
    'hris',
    'European SMB HR platform with developer docs for people records, attendance, absences, projects, recruiting feeds, and webhook-driven integration workflows.',
    'https://developer.personio.de/',
    'api.personio.de'
  ),
  (
    'factorial',
    'Factorial',
    'hris',
    'HR and operations platform with public developer docs, GraphQL API coverage, and integration surfaces spanning employees, time off, attendance, contracts, shifts, and org workflows.',
    'https://apidoc.factorialhr.com/docs/getting-started',
    'api.factorialhr.com'
  ),
  (
    'employment-hero',
    'Employment Hero',
    'hris',
    'Employment operating system with developer and partner documentation for HR, payroll, ATS, and recruiting integrations used across SMB and mid-market teams.',
    'https://developer.employmenthero.com/',
    NULL
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
    'hibob',
    8.10,
    8.25,
    7.90,
    0.63,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-27","category_rationale":"hris expansion","notes":"Strong category anchor with broad people/time-off/attendance coverage and explicit webhook surfaces. Good later Resolve candidate for employee.list/get plus timeoff.list/read workflows, though enterprise tenant setup and permission scoping raise Phase 0 complexity."}'::jsonb,
    now()
  ),
  (
    'personio',
    8.20,
    8.35,
    8.00,
    0.65,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-27","category_rationale":"hris expansion","notes":"Best near-term read-heavy HRIS candidate in the batch. Public docs clearly expose persons, attendance, absence, project, and webhook primitives that map cleanly to future Resolve employee and leave capabilities."}'::jsonb,
    now()
  ),
  (
    'factorial',
    8.25,
    8.45,
    8.05,
    0.67,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-27","category_rationale":"hris expansion","notes":"Strongest Phase 0 candidate in this batch. Factorial publishes approachable getting-started docs and a public GraphQL API surface for employee, leave, attendance, and schedule-adjacent workflows that should translate well into agent-facing primitives."}'::jsonb,
    now()
  ),
  (
    'employment-hero',
    7.95,
    8.05,
    7.75,
    0.60,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-27","category_rationale":"hris expansion","notes":"Important regional HRIS/payroll platform with meaningful partner demand, but the public API reference is less immediately concrete than Factorial or Personio. Good catalog inclusion now; Phase 0 should wait until we pin the most stable employee and ATS endpoints."}'::jsonb,
    now()
  );

COMMIT;
