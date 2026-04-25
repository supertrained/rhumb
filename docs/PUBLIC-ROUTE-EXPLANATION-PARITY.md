# Public route-explanation parity

Purpose: keep `/resolve/routing`, `llms.txt`, schema/agent-context copy, and comparison CTAs aligned with the runtime route-explanation contract before distribution.

## 2026-04-25 DC90-10 pass

### What was verified

- Runtime builder contract: `packages/api/services/route_explanation.py::RouteExplanation.to_dict()` emits:
  - `capability_id`
  - `winner.provider_id`
  - `winner.selection_reason`
  - `candidates[].factors`
  - `candidates[].policy_checks`
  - `candidates[].ineligible_reason` when present
  - `policy_active`
  - `strategy`
- Runtime factor keys are exactly:
  - `an_score`
  - `availability`
  - `estimated_cost`
  - `latency`
  - `credential_mode`
- Runtime policy-check keys are exactly:
  - `pinned`
  - `denied`
  - `cost_ceiling_ok`
  - `quality_floor_ok`
  - `circuit_healthy`
  - `allow_list_ok`
- Live read-path check: `GET https://rhumb-api-production-f173.up.railway.app/v2/capabilities/search.query/resolve` returned provider candidates with `cost_per_call`, `credential_modes`, `circuit_state`, `available_for_execute`, and `configured` fields, matching the public claim that route candidates expose cost, credential, availability/readiness inputs before execution.

### Public copy decision

Public wording now distinguishes:

- **candidate filter:** supported capability path / providers mapped to the requested capability;
- **runtime factors:** AN Score, availability / circuit state, estimated cost, latency proxy, credential mode;
- **policy constraints:** pin, allow list, deny list, and max-cost ceiling.

This replaces looser language like `capability fit` as if it were a serialized route-explanation factor, and avoids generic `provider health` wording where the runtime-backed field is currently circuit state / availability.

### Boundary

No paid/live execution was run in this pass. The public route-explanation page is now aligned to the runtime builder and live resolve read path. A future live receipt sample should be added once a no-spend or pre-approved dogfood execution path is available.
