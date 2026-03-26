BEGIN;

-- Migration 0091: Authorization discovery expansion (2026-03-25)
-- Rationale: authorization/fine-grained access control is a high-demand agent category
-- but the catalog only had 4 providers. Add 4 more API-first authorization systems
-- with initial AN scoring.

INSERT INTO services (slug, name, category, description, official_docs)
VALUES
  (
    'authzed',
    'AuthZed',
    'authorization',
    'Fine-grained authorization platform built around relationship-based access control and the SpiceDB API.',
    'https://authzed.com/docs/'
  ),
  (
    'aserto',
    'Aserto',
    'authorization',
    'Policy-based and relationship-aware authorization platform for API, app, and microservice access checks.',
    'https://www.aserto.com/docs'
  ),
  (
    'oso-cloud',
    'Oso Cloud',
    'authorization',
    'Managed authorization service for permission checks, policy modeling, and application-level access control.',
    'https://www.osohq.com/docs'
  ),
  (
    'workos-fga',
    'WorkOS FGA',
    'authorization',
    'Fine-grained authorization service from WorkOS for relationship checks, resource permissions, and enterprise access control.',
    'https://workos.com/docs/fga'
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
    7.55,
    7.80,
    7.30,
    0.56,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-25","category_rationale":"authorization expansion","notes":"Strong Zanzibar/relationship-based API surface with mature docs and direct overlap with authz.check_permission use cases."}'::jsonb,
    now()
  ),
  (
    'aserto',
    7.25,
    7.50,
    7.00,
    0.53,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-25","category_rationale":"authorization expansion","notes":"Good policy and directory-aware authz surface with accessible docs and practical API coverage for permission checks."}'::jsonb,
    now()
  ),
  (
    'oso-cloud',
    7.35,
    7.60,
    7.10,
    0.54,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-25","category_rationale":"authorization expansion","notes":"Clear developer story for hosted authorization checks and policy modeling; practical fit for app-embedded agent decisions."}'::jsonb,
    now()
  ),
  (
    'workos-fga',
    7.30,
    7.55,
    7.05,
    0.53,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-25","category_rationale":"authorization expansion","notes":"Enterprise-friendly FGA surface from a widely adopted identity platform; good Phase 0 candidate for permission-check capabilities."}'::jsonb,
    now()
  );

COMMIT;
