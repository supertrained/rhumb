BEGIN;

-- Migration 0148: Identity discovery expansion (2026-04-02)
-- Rationale: live public category counts still show identity as badly
-- underrepresented relative to real developer and operator demand. Agents often
-- need to inspect users, organizations, memberships, sessions, and auth state
-- before taking action, but the current catalog only surfaces four identity
-- providers. This batch adds five major API-backed identity platforms.
-- Phase 0 assessment: Clerk is the cleanest first Resolve wedge because its
-- Backend API exposes direct read-first user / org / membership primitives on a
-- stable developer-facing control plane. Auth0 is strategically essential but
-- tenant-domain and token setup are a little heavier for a first normalized lane.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'auth0',
    'Auth0',
    'identity',
    'Customer identity platform with APIs for users, organizations, roles, sessions, logins, MFA, enterprise federation, and lifecycle management across consumer and B2B applications.',
    'https://auth0.com/docs/api/management/v2',
    NULL
  ),
  (
    'clerk',
    'Clerk',
    'identity',
    'Developer-first authentication and user management platform with backend APIs for users, organizations, memberships, sessions, invitations, and access-control-aware identity workflows.',
    'https://clerk.com/docs/reference/backend-api',
    'api.clerk.com'
  ),
  (
    'stytch',
    'Stytch',
    'identity',
    'Authentication platform with APIs for user lifecycle, sessions, organizations, B2B memberships, passwordless auth, MFA, and fraud-aware identity controls.',
    'https://stytch.com/docs/api',
    'api.stytch.com'
  ),
  (
    'descope',
    'Descope',
    'identity',
    'Identity and customer-auth platform with management APIs for users, tenants, roles, flows, SSO, MFA, and authorization-adjacent lifecycle operations.',
    'https://docs.descope.com/api/',
    'api.descope.com'
  ),
  (
    'kinde',
    'Kinde',
    'identity',
    'Authentication and user-management platform with APIs for users, organizations, permissions, feature flags, and B2B identity administration.',
    'https://kinde.com/docs/api/',
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
    'auth0',
    8.85,
    8.95,
    8.70,
    0.72,
    'L4',
    'Native',
    '{"source":"pedro-keel-discovery-2026-04-02","category_rationale":"identity expansion","phase0_assessment":"Strategically essential identity provider with rich Management API coverage for users, organizations, roles, and sessions. Strong Resolve target once tenant-scoped auth setup is normalized.","notes":"Huge market demand, deep enterprise footprint, excellent lifecycle/admin coverage, and durable identity relevance for agent-facing software."}'::jsonb,
    now()
  ),
  (
    'clerk',
    8.75,
    8.85,
    8.60,
    0.69,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-02","category_rationale":"identity expansion","phase0_assessment":"Best immediate Resolve candidate in this batch. Clerk Backend API exposes explicit read-first user, organization, membership, invitation, and session primitives on a stable developer-first control plane.","notes":"Strong developer adoption, clean backend API ergonomics, and a clear path to normalized identity.user.get/list plus organization.members.list capability shapes."}'::jsonb,
    now()
  ),
  (
    'stytch',
    8.60,
    8.75,
    8.40,
    0.67,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-02","category_rationale":"identity expansion","phase0_assessment":"Excellent follow-on Resolve target for user/session/org reads, especially for B2B identity workflows and passwordless-heavy stacks.","notes":"Strong API surface, modern auth posture, and meaningful B2B membership/session semantics that map well to agent-safe read-first operations."}'::jsonb,
    now()
  ),
  (
    'descope',
    8.45,
    8.55,
    8.30,
    0.64,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-02","category_rationale":"identity expansion","phase0_assessment":"Good Resolve candidate after Clerk/Stytch for tenant, user, and role inspection workflows once the core identity read lane is established.","notes":"Strong enterprise and CIAM relevance, broad auth surface, and useful tenant/role APIs, though the flow-oriented product shape is a bit broader than the cleanest first wedge."}'::jsonb,
    now()
  ),
  (
    'kinde',
    8.20,
    8.25,
    8.15,
    0.60,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-02","category_rationale":"identity expansion","phase0_assessment":"Credible later Resolve candidate for user/org/permission reads and adjacent feature-flag-aware identity workflows.","notes":"Developer-friendly product with useful organizations/permissions surfaces; strategically relevant even if less mature and less enterprise-proven than Auth0, Clerk, or Stytch."}'::jsonb,
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
