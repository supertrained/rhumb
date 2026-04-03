# Discovery expansion — secrets III

Date: 2026-04-03
Owner: Pedro / Keel runtime review loop

## Why this category

Live production category counts still show **`secrets`** at only **5** providers:
- `aws-secrets-manager`
- `bitwarden-secrets`
- `doppler`
- `hashicorp-vault`
- `infisical`

That is too thin for a category agents increasingly need for:
- governed runtime secret retrieval before executing external tools
- machine-to-machine credential delivery in CI/CD and automation flows
- version-aware secret inspection and rollback debugging
- secure operator workflows across cloud and self-hosted infrastructure
- future Resolve lanes where agents need a normalized read-first secret surface without inventing bespoke auth glue per vault

The honest Mission 2 move was to deepen **secrets** with more API-backed vault systems rather than leave a core agent-infrastructure category shallow.

## Added services

### 1. Akeyless
- Slug: `akeyless`
- Score: **8.55**
- Execution: **8.65**
- Access readiness: **8.25**
- Why it made the cut:
  - explicit secret retrieval and metadata APIs
  - strongest immediate Phase 0 candidate in the batch
  - cloud-agnostic posture makes normalization cleaner than cloud-specific IAM-first vaults
  - strong fit for agent runtime secret access and machine identity workflows

### 2. 1Password Secrets Automation
- Slug: `onepassword-secrets`
- Score: **8.45**
- Execution: **8.50**
- Access readiness: **8.20**
- Why it made the cut:
  - strategically important operator-grade vault with real machine-accessible secret retrieval
  - strong fit for teams already storing operational credentials in 1Password
  - Connect / Secrets Automation makes it a real API-backed target instead of only a human UI
  - slightly heavier setup than Akeyless, but high practical relevance

### 3. Google Secret Manager
- Slug: `google-secret-manager`
- Score: **8.40**
- Execution: **8.55**
- Access readiness: **8.05**
- Why it made the cut:
  - clear versioned REST API for secret access and metadata reads
  - important first-party GCP system-of-record depth
  - excellent fit for read-first secret retrieval in cloud-native workloads
  - IAM setup is heavier than Akeyless but the execution surface is strong

### 4. Azure Key Vault
- Slug: `azure-key-vault`
- Score: **8.30**
- Execution: **8.45**
- Access readiness: **8.00**
- Why it made the cut:
  - major enterprise cloud vault with real REST APIs for secrets and versions
  - adds Microsoft ecosystem depth that is currently missing from the catalog
  - useful for agent workflows running inside Azure / Entra-heavy environments
  - auth complexity makes it a second-wave provider rather than the first wedge

### 5. CyberArk Conjur
- Slug: `cyberark-conjur`
- Score: **8.10**
- Execution: **8.25**
- Access readiness: **7.85**
- Why it made the cut:
  - meaningful enterprise machine-identity and secrets-governance depth
  - exposes real policy-governed secret retrieval APIs
  - strong later-wave provider for regulated or large-enterprise environments
  - less attractive than Akeyless as the first normalized execution wedge, but worth indexing now

## Phase 0 capability assessment

### Services with accessible APIs
All five added services expose accessible machine-facing APIs or SDK-backed retrieval surfaces suitable for a Phase 0 assessment.

Strongest early Resolve targets:
1. **Akeyless**
2. **Google Secret Manager**
3. **1Password Secrets Automation**

### Candidate capability shapes
- `secret.get`
- `secret.list`
- `secret.version.get`
- `secret.version.list`
- `vault.item.get`

### Best initial Phase 0 wedge
The cleanest first move is read-first secrets retrieval:
- `secret.get`
- `secret.version.get`
- `secret.list`

**Best first provider:** **Akeyless**

Why:
- explicit API for secret retrieval and metadata inspection
- cloud-agnostic, so the first normalization does not depend on one hyperscaler’s auth model
- strong machine-identity fit for agent runtime execution
- supports a practical first wedge without starting on write/rotation semantics

Secondary wedge:
- **Google Secret Manager** for `secret.version.get`

Why:
- extremely clean versioned read surface
- strong production relevance for cloud-native workloads
- good second implementation once the generic `secret.get` contract is stable

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0155_secrets_expansion_iii.sql`

## Verdict

Secrets is still underrepresented relative to real agent demand. This batch adds five real API-backed vault systems and sharpens the next honest Resolve wedge around **read-first secret retrieval**, with **Akeyless** now the clearest Phase 0 target and **Google Secret Manager** / **1Password Secrets Automation** close behind for second-wave provider coverage.
