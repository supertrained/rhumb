# Authorization discovery expansion — 2026-03-26

Date: 2026-03-26
Operator: Pedro / Keel runtime loop

## Why this category

Authorization remains underrepresented in the catalog relative to how central it is for agent-safe tool use. Real agents need to answer questions like "can this actor do this action on this resource?", write or sync relationship facts, and reason about policy boundaries. The catalog previously had only four authorization-first vendors.

## Added services

- `aserto`
- `authzed`
- `oso-cloud`
- `opal-security`
- `styra-das`

## Category read

This batch covers the major design centers inside modern authorization infrastructure:

- **Decision APIs / hosted authorizers:** Aserto, Oso Cloud
- **Zanzibar-style relationship authorization:** AuthZed
- **Policy control plane / OPA enterprise:** Styra DAS
- **Access orchestration / governed access workflows:** Opal Security

That gives Rhumb better breadth across fine-grained authz, policy-as-code, and operational entitlement control.

## Phase 0 capability assessment

### Best immediate Resolve candidate: AuthZed

AuthZed is the cleanest Phase 0 target because its API surface maps directly onto agent-meaningful authorization primitives.

Recommended first capability set:
- `authz.check` → permission check for subject/resource/relation
- `authz.write_relationships` → create/update/delete tuple-style authorization facts
- `authz.expand` → expand reachable principals/resources for a permission
- `authz.read_schema` → inspect current authorization model

Why AuthZed first:
- the API is explicit and machine-native
- the request/response shapes are crisp enough for normalization
- it gives Rhumb a strong authorization primitive that can later generalize to OpenFGA, Permit, and Aserto decision surfaces

### Secondary candidates

- **Aserto:** strong follow-on for `authz.check` plus decision-log / directory reads
- **Oso Cloud:** good fit for `authz.check` and list/filter decisions against Polar-backed models
- **Styra DAS:** better later as `policy.evaluate` or `rego.query`, but less immediately universal than tuple/dependency graph authz checks
- **Opal Security:** more natural for access-request and entitlement-governance capabilities than pure authorization checks

## Operator takeaway

Authorization is no longer a thin category, and AuthZed now stands out as the best Phase 0 next step if we want a high-signal, agent-native authorization capability in Resolve.
