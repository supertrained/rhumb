BEGIN;

-- Migration 0146: Secrets discovery expansion II (2026-04-01)
-- Rationale: secrets infrastructure is still thin relative to real agent demand.
-- Add 5 widely-used secret managers / secret-distribution surfaces spanning
-- cloud-native vaults, zero-trust platforms, and developer-first automation.
-- Phase 0 assessment: the cleanest follow-on wedge is extending the existing
-- secrets.get / secrets.list / secrets.set family to Google Cloud Secret Manager,
-- Azure Key Vault, 1Password Secrets Automation, Akeyless, and SSM Parameter Store.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    '1password-secrets-automation',
    '1Password Secrets Automation',
    'secrets',
    'Developer-first secret management and service-account automation for securely reading, writing, and rotating secrets across CI, agents, and operational workflows.',
    'https://developer.1password.com/docs/service-accounts/',
    'api.1password.com'
  ),
  (
    'google-cloud-secret-manager',
    'Google Cloud Secret Manager',
    'secrets',
    'Managed Google Cloud secret store for versioned secret access, IAM-scoped reads, writes, replication controls, and operational secret distribution.',
    'https://cloud.google.com/secret-manager/docs/reference/rest',
    'secretmanager.googleapis.com'
  ),
  (
    'azure-key-vault',
    'Azure Key Vault',
    'secrets',
    'Azure-managed vault for secrets, keys, and certificates with REST APIs for secret retrieval, versioning, rotation workflows, and tenant-scoped access control.',
    'https://learn.microsoft.com/en-us/rest/api/keyvault/secrets',
    'vault.azure.net'
  ),
  (
    'akeyless',
    'Akeyless',
    'secrets',
    'Centralized secrets and machine-identity platform with APIs for secret retrieval, dynamic credentials, rotation, access federation, and zero-trust delivery.',
    'https://docs.akeyless.io/reference',
    'api.akeyless.io'
  ),
  (
    'aws-ssm-parameter-store',
    'AWS Systems Manager Parameter Store',
    'secrets',
    'AWS parameter and secret storage surface for hierarchical key/value config, SecureString secrets, versioning, and agent-friendly retrieval through the SSM API.',
    'https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html',
    'ssm.amazonaws.com'
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
    '1password-secrets-automation',
    8.55,
    8.60,
    8.45,
    0.66,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-01","category_rationale":"secrets expansion ii","phase0_assessment":"Strongest immediate Resolve candidate in the batch because the service-account/API posture maps cleanly onto the existing secrets.get/list/set family.","notes":"High agent relevance, strong developer trust, explicit automation-first docs, and a clear read-first wedge for scoped secret retrieval."}'::jsonb,
    now()
  ),
  (
    'google-cloud-secret-manager',
    8.40,
    8.35,
    8.45,
    0.64,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-01","category_rationale":"secrets expansion ii","phase0_assessment":"Immediate Phase 0 candidate for secrets.get/list because the REST surface is explicit and already fits normalized versioned-secret retrieval patterns.","notes":"Very strong enterprise demand and durable cloud-native secret storage posture; auth/config is heavier than 1Password but the API surface is straightforward."}'::jsonb,
    now()
  ),
  (
    'azure-key-vault',
    8.25,
    8.25,
    8.20,
    0.62,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-01","category_rationale":"secrets expansion ii","phase0_assessment":"Good follow-on Phase 0 target once cloud-secret auth handling is widened beyond the current secrets batch.","notes":"Strong enterprise footprint and clear REST primitives for read/write/version flows, but Azure tenant auth complexity is a little heavier than the top two additions."}'::jsonb,
    now()
  ),
  (
    'akeyless',
    8.15,
    8.20,
    8.05,
    0.60,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-01","category_rationale":"secrets expansion ii","phase0_assessment":"Attractive later Phase 0 candidate for scoped secrets.get and dynamic-credential retrieval once the core cloud-vault additions are live.","notes":"Excellent agent infrastructure fit thanks to machine-identity and dynamic-secret posture; slightly lower familiarity than the hyperscaler options but strategically relevant."}'::jsonb,
    now()
  ),
  (
    'aws-ssm-parameter-store',
    8.00,
    7.95,
    8.05,
    0.60,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-01","category_rationale":"secrets expansion ii","phase0_assessment":"Credible follow-on Resolve target for secrets.get/list where teams prefer Parameter Store over Secrets Manager for hierarchical config + SecureString retrieval.","notes":"Huge installed base and simple retrieval semantics, though the split between plain parameters and SecureString secret handling makes it slightly less elegant than dedicated secret-manager surfaces."}'::jsonb,
    now()
  );

COMMIT;
