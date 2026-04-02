BEGIN;

-- Migration 0149: Authorization discovery expansion II (2026-04-02)
-- Rationale: live production still shows authorization as a thin, high-demand
-- category even though real agent workflows increasingly need fine-grained
-- permission checks, resource visibility evaluation, relationship graph lookups,
-- and policy-backed access decisions. The current catalog covers only five
-- providers, leaving a meaningful gap in one of the most structurally important
-- read-first control planes agents will need to query honestly.
-- Add five more API-backed authorization surfaces and document the clearest
-- Phase 0 Resolve wedge.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'authzed',
    'AuthZed',
    'authorization',
    'Hosted fine-grained authorization platform built on Zanzibar-style relationship graphs with APIs for permission checks, resource visibility, relationship writes, schema management, and access decision workflows.',
    'https://authzed.com/docs/authzed',
    NULL
  ),
  (
    'spicedb',
    'SpiceDB',
    'authorization',
    'Open-source Zanzibar-inspired authorization database with APIs for permission checks, relationship graph queries, schema operations, and access decision workflows across applications and internal tools.',
    'https://authzed.com/docs/spicedb',
    NULL
  ),
  (
    'oso-cloud',
    'Oso Cloud',
    'authorization',
    'Managed authorization platform with APIs for policy-backed access checks, relationship data, list filtering, and application-level authorization decisions.',
    'https://www.osohq.com/docs',
    NULL
  ),
  (
    'aserto',
    'Aserto',
    'authorization',
    'Authorization control plane with policy decision APIs, directory-backed identity context, relation-style checks, and application permission evaluation workflows.',
    'https://docs.aserto.com/',
    NULL
  ),
  (
    'styra-das',
    'Styra DAS',
    'authorization',
    'Policy control plane for Open Policy Agent with APIs for policy bundles, decision workflows, system management, and authorization-oriented governance across distributed systems.',
    'https://docs.styra.com/das',
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
    'authzed',
    8.55,
    8.70,
    8.25,
    0.69,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-02","category_rationale":"authorization expansion ii","notes":"Strongest immediate Resolve candidate in the batch. Hosted Zanzibar-style permission checks and object visibility APIs map cleanly onto a normalized authz.check / authz.list_resources lane."}'::jsonb,
    now()
  ),
  (
    'spicedb',
    8.40,
    8.55,
    7.95,
    0.66,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-02","category_rationale":"authorization expansion ii","notes":"Important open-source counterpart to AuthZed with clear value for self-hosted and infra-heavy teams. Strong long-term Resolve fit once the hosted lane is normalized."}'::jsonb,
    now()
  ),
  (
    'oso-cloud',
    8.30,
    8.45,
    8.05,
    0.64,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-02","category_rationale":"authorization expansion ii","notes":"Policy-backed app authorization surface with clear read-first access-check semantics and practical product relevance for modern SaaS teams."}'::jsonb,
    now()
  ),
  (
    'aserto',
    8.20,
    8.35,
    7.95,
    0.62,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-02","category_rationale":"authorization expansion ii","notes":"Credible authorization decision platform with policy evaluation and identity-context APIs. Slightly broader control-plane shape than the cleanest first wedge, but still highly relevant catalog depth."}'::jsonb,
    now()
  ),
  (
    'styra-das',
    8.10,
    8.25,
    7.80,
    0.60,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-02","category_rationale":"authorization expansion ii","notes":"Strategically important policy-control-plane coverage because many enterprises already standardize on OPA-style decisions. Better as a second-wave Resolve target after a narrower authz.check provider is live."}'::jsonb,
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
