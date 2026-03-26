# Discovery expansion — authorization (2026-03-25)

## Why this category

Authorization is a high-demand agent category because real autonomous systems need a reliable answer to:
- can this actor do this action?
- what relationships or roles grant access?
- how should access checks be externalized instead of hand-coded?

Yet the catalog only had 4 services in `authorization`:
- Permit.io
- Cerbos
- OpenFGA
- Warrant

That is too thin for a category this central to safe multi-tenant agent systems.

## Services added

1. **AuthZed** (`authzed`)
   - relationship-based authorization / SpiceDB
   - docs: <https://authzed.com/docs/>
2. **Aserto** (`aserto`)
   - policy + directory-aware authorization
   - docs: <https://www.aserto.com/docs>
3. **Oso Cloud** (`oso-cloud`)
   - hosted authorization checks and policy modeling
   - docs: <https://www.osohq.com/docs>
4. **WorkOS FGA** (`workos-fga`)
   - fine-grained authorization from WorkOS
   - docs: <https://workos.com/docs/fga>

## Initial scoring rationale

All four were scored as **L3 / Ready** rather than speculative:
- public developer docs are accessible
- the API surfaces clearly map to real authorization checks
- the category overlap with `authz.check_permission` is direct
- confidence stays moderate because these are discovery-stage scores, not runtime-backed reviews

## Phase 0 assessment for Resolve

### Strong immediate candidates

**AuthZed**
- Clean fit for `authz.check_permission`
- Expected action surface: permission/relationship check against a resource
- Good next-step candidate for BYO mapping once endpoint templates are verified

**WorkOS FGA**
- Direct fit for `authz.check_permission`
- Enterprise-friendly positioning makes it strategically useful even before deep runtime coverage
- Worth Phase 0 endpoint mapping once auth/header patterns are confirmed

### Also promising

**Aserto**
- Good permission-check fit
- Likely maps to `authz.check_permission` plus potential future policy-decision surfaces

**Oso Cloud**
- Also a direct `authz.check_permission` candidate
- Strong developer story for app-embedded authorization, worth Phase 0 after endpoint/method confirmation

## Net

This run widens authorization from **4 → 8 providers**, which is a healthier baseline for an agent-infrastructure category that directly affects trust and safe execution.
