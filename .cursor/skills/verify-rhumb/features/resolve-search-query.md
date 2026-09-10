# Resolve search.query

Resolve `search.query` shows ranked providers and the default execute hint for web-search-style capability routing. The read is public. Execution is not part of this feature.

## Sub-features

- `resolve-public` returns ranked providers with no auth header.
- `resolve-hint` includes `execute_hint.preferred_provider` and `selection_reason`.
- `resolve-mode-filter` accepts `credential_mode` as a query parameter without requiring a key.
- `resolve-no-execute` stops before estimate and execute.

## How to get to it (user POV)

- Call `GET https://api.rhumb.dev/v1/capabilities/search.query/resolve`.
- Call `GET https://api.rhumb.dev/v1/capabilities?search=web+research` first when you do not already have the slug.
- Ask an MCP client to `resolve_capability` with `capability_id=search.query`.
- Read the Resolve docs page at `https://rhumb.dev/resolve`.

## Driving it with curl

Preconditions:

- Doctor passed against `$VERIFY_RHUMB_BASE`.
- Capability id is exactly `search.query`.
- You will not call `/execute` or `/execute/estimate`.

- **Public resolve.** Resolve the live search capability. Run `.cursor/skills/verify-rhumb/bin/drive resolve-search-query` or `curl -sS -H 'User-Agent: rhumb-verify/1.0' -H 'Accept: application/json' "$VERIFY_RHUMB_BASE/v1/capabilities/search.query/resolve"`. HTTP 200. `error` is `null`. `data.capability` is `search.query`. `data.providers` has at least one object with `service_slug`.
- **Execute hint.** Read the preferred rail. The same response includes `data.execute_hint.preferred_provider` as a non-empty string and `data.execute_hint.selection_reason`. Record both. Do not POST to that provider.
- **Optional mode filter.** Repeat with `?credential_mode=rhumb_managed`. HTTP 200. The envelope stays `{data, error}`. An empty provider list must still keep `recovery_hint` instead of inventing a provider.
- **Proof.** Keep the public resolve body. The helper writes `evidence/$VERIFY_RHUMB_RUN_ID/drive-resolve-search-query.json` and `evidence/$VERIFY_RHUMB_RUN_ID/http/resolve-search-query.json`. Both name `search.query` and a preferred provider.

## Gotchas

- Resolve is the ranked recommendation. For `search.query`, default estimate should use the same provider as `execute_hint.preferred_provider` when that provider has a managed row. This skill does not call estimate.
- `scripts/dc90_search_query_pilot_smoke.py` resolves, estimates, then executes with a funded dogfood key. Do not run it.
- `examples/resolve-and-execute.py` stops after resolve when `RHUMB_API_KEY` is unset. Prefer `bin/drive` so estimate cannot start by accident.
- Provider objects use `service_slug` and `service_name`, not `name`.
- Do not treat `execute_hint` as permission to execute. The hint is documentation of the next paid step.
