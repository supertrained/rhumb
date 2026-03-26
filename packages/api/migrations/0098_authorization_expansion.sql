BEGIN;

-- Migration 0098: Authorization discovery expansion (2026-03-26)
-- Rationale: authorization is a high-demand category for agent-safe execution,
-- but the catalog remained thin. Add 5 authorization-first platforms spanning
-- hosted authorizers, Zanzibar-style graph authz, policy control planes, and
-- governed access orchestration.

INSERT INTO services (slug, name, category, description, official_docs)
VALUES
  (
    'aserto',
    'Aserto',
    'authorization',
    'Cloud-native authorization platform with authorizer, directory, decision logs, and control-plane APIs for application access control.',
    'https://docs.aserto.com/docs'
  ),
  (
    'authzed',
    'AuthZed',
    'authorization',
    'Managed Zanzibar-style authorization platform built around relationship-based access control, permission checks, schema management, and low-latency authz APIs.',
    'https://authzed.com/docs'
  ),
  (
    'oso-cloud',
    'Oso Cloud',
    'authorization',
    'Centralized authorization service for RBAC, ReBAC, ABAC, and fine-grained policy evaluation with Polar-based APIs and fact management.',
    'https://www.osohq.com/docs'
  ),
  (
    'opal-security',
    'Opal Security',
    'authorization',
    'Access orchestration and entitlement-management platform with APIs for service users, approvals, access governance, and permission administration.',
    'https://docs.opal.dev/reference'
  ),
  (
    'styra-das',
    'Styra DAS',
    'authorization',
    'Enterprise policy control plane built on Open Policy Agent for declarative authorization, policy lifecycle management, and API-driven policy governance.',
    'https://docs.styra.com/das'
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
    'aserto',
    7.95,
    8.20,
    7.70,
    0.58,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-26","category_rationale":"authorization expansion","notes":"Strong developer-facing authorization platform with explicit authorizer, directory, and decision-log APIs. Good fit for future authz.check and authz.directory read capabilities."}'::jsonb,
    now()
  ),
  (
    'authzed',
    8.20,
    8.55,
    7.90,
    0.60,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-26","category_rationale":"authorization expansion","notes":"Best immediate Phase 0 candidate in the batch. Zanzibar-style schema, relationship, and permission-check APIs map directly onto authz.check / authz.write_relationships / authz.expand capabilities."}'::jsonb,
    now()
  ),
  (
    'oso-cloud',
    8.00,
    8.25,
    7.75,
    0.58,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-26","category_rationale":"authorization expansion","notes":"Strong centralized authorization service with broad model expressiveness (RBAC/ReBAC/ABAC) and HTTP/SDK access patterns. Attractive candidate for authz.check and policy-backed list/filter workflows."}'::jsonb,
    now()
  ),
  (
    'opal-security',
    7.45,
    7.70,
    7.15,
    0.54,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-26","category_rationale":"authorization expansion","notes":"Operational entitlement and access-governance API surface looks strong for access-request and approval workflows, though it is less universal than pure decision-engine authz APIs."}'::jsonb,
    now()
  ),
  (
    'styra-das',
    7.20,
    7.55,
    6.75,
    0.53,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-26","category_rationale":"authorization expansion","notes":"Enterprise-grade OPA control plane with strong policy-governance value. Important category coverage, though near-term Resolve fit is better for later policy.evaluate than first-wave authz primitives."}'::jsonb,
    now()
  );

COMMIT;
