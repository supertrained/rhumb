BEGIN;

-- Migration 0155: Secrets discovery expansion III (2026-04-03)
-- Rationale: live production still shows the `secrets` category at only five
-- providers (AWS Secrets Manager, Bitwarden Secrets Manager, Doppler,
-- HashiCorp Vault, Infisical) even though agents increasingly need safe,
-- read-first secret retrieval and metadata inspection across cloud, enterprise,
-- and operator-grade vault systems.
--
-- This batch deepens the category with API-backed secrets platforms that expose
-- real retrieval / metadata surfaces and sharpens the next honest Resolve wedge
-- around secret.get / secret.list / secret.version.get.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'onepassword-secrets',
    '1Password Secrets Automation',
    'secrets',
    '1Password Secrets Automation and Connect provide machine-accessible secret retrieval, vault item access, and service-account driven secret delivery for applications, CI/CD systems, and agent runtime workflows.',
    'https://developer.1password.com/docs/connect/',
    'connect.1password.com'
  ),
  (
    'akeyless',
    'Akeyless',
    'secrets',
    'Cloud-native secrets management platform with APIs for static and dynamic secrets, machine identities, secret rotation, certificate automation, and secure runtime retrieval across cloud and Kubernetes environments.',
    'https://docs.akeyless.io/reference/overview',
    'api.akeyless.io'
  ),
  (
    'google-secret-manager',
    'Google Secret Manager',
    'secrets',
    'Google Cloud managed secrets service with versioned secret storage, IAM-governed access, rotation hooks, and REST APIs for retrieving secrets and secret metadata in production systems.',
    'https://cloud.google.com/secret-manager/docs/reference/rest',
    'secretmanager.googleapis.com'
  ),
  (
    'azure-key-vault',
    'Azure Key Vault',
    'secrets',
    'Azure managed key and secrets service with REST APIs for secret retrieval, certificate and key lifecycle, versioned secret access, and identity-governed access across Azure workloads.',
    'https://learn.microsoft.com/en-us/rest/api/keyvault/secrets',
    'vault.azure.net'
  ),
  (
    'cyberark-conjur',
    'CyberArk Conjur',
    'secrets',
    'Enterprise secrets and machine identity platform with APIs for policy-governed secret retrieval, dynamic access control, and runtime credential delivery across applications, containers, and CI/CD systems.',
    'https://www.cyberark.com/resources/secrets-management/conjur-rest-api',
    'conjur-api'
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
    'onepassword-secrets',
    8.45,
    8.50,
    8.20,
    0.69,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"secrets expansion","phase0_assessment":"Strong read-first candidate for secret.get and vault.item.get because 1Password Connect and Secrets Automation expose machine-accessible secret retrieval with clear vault semantics and broad operator relevance.","notes":"Strategically important because many teams already store operational secrets in 1Password, but Connect/Secrets Automation setup is slightly heavier than the simplest API-key-first vaults."}'::jsonb,
    now()
  ),
  (
    'akeyless',
    8.55,
    8.65,
    8.25,
    0.71,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"secrets expansion","phase0_assessment":"Best immediate Resolve candidate in the batch because Akeyless exposes explicit secret retrieval and metadata APIs without requiring a cloud-specific control plane, making secret.get and secret.list cleaner to normalize first.","notes":"Very strong fit for agent runtime secret retrieval, machine identities, and operator-grade secret access workflows across hybrid infrastructure."}'::jsonb,
    now()
  ),
  (
    'google-secret-manager',
    8.40,
    8.55,
    8.05,
    0.68,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"secrets expansion","phase0_assessment":"Excellent provider for secret.version.get and secret.metadata.get because Google Secret Manager has a clean versioned REST API and strong read-first semantics, though IAM and service-account setup are heavier than Akeyless.","notes":"Important cloud-platform depth because many production agent systems already run on GCP and need first-party secret retrieval primitives."}'::jsonb,
    now()
  ),
  (
    'azure-key-vault',
    8.30,
    8.45,
    8.00,
    0.66,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"secrets expansion","phase0_assessment":"High-value enterprise cloud target for secret.get, secret.version.list, and certificate metadata reads once the simpler cross-cloud wedge is shaped.","notes":"Important Microsoft ecosystem coverage, but Entra/Azure auth complexity makes it a second-wave managed provider rather than the first secrets execution target."}'::jsonb,
    now()
  ),
  (
    'cyberark-conjur',
    8.10,
    8.25,
    7.85,
    0.63,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"secrets expansion","phase0_assessment":"Valuable later-wave enterprise provider for secret.get and policy-scoped machine access patterns, even if the first normalized wedge should start on cleaner cloud/API-key-first providers.","notes":"Adds meaningful enterprise machine-identity and secrets-governance depth for larger organizations that standardize on CyberArk."}'::jsonb,
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
