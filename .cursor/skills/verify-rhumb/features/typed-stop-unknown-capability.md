# Typed stop for an unknown capability

An invented capability id must 404. Rhumb must not invent an executable route for `time.travel`. Typo recovery may suggest nearby real ids.

## Sub-features

- `stop-404` returns HTTP 404 for `GET /v1/capabilities/time.travel/resolve`.
- `stop-error` sets `error` to `capability_not_found`.
- `stop-search-url` points at `GET /v1/capabilities?search=time.travel`.
- `stop-suggest` may include `suggested_capabilities` for nearby real ids. Suggestions are recovery, not a claim that time travel exists.

## How to get to it (user POV)

- Call `GET https://api.rhumb.dev/v1/capabilities/time.travel/resolve`.
- Call `GET https://api.rhumb.dev/v1/capabilities/time.travel`.
- Ask an MCP client to `resolve_capability` with `capability_id=time.travel`.

## Driving it with curl

Preconditions:

- Doctor passed against `$VERIFY_RHUMB_BASE`.
- Capability id is exactly `time.travel`.

- **Resolve stop.** Ask Resolve for time travel. Run `.cursor/skills/verify-rhumb/bin/drive typed-stop-unknown-capability` or `curl -sS -H 'User-Agent: rhumb-verify/1.0' -H 'Accept: application/json' "$VERIFY_RHUMB_BASE/v1/capabilities/time.travel/resolve"`. HTTP 404. Top-level `error` is `capability_not_found`. `message` contains `time.travel`. There is no `data.providers` list to execute.
- **Lookup stop.** Fetch the capability record. Run `curl -sS -H 'User-Agent: rhumb-verify/1.0' "$VERIFY_RHUMB_BASE/v1/capabilities/time.travel"`. HTTP 404 with the same `error` value.
- **Recovery pointer.** Read `search_url`. It is `/v1/capabilities?search=time.travel`. `resolution` tells the caller to use `GET /v1/capabilities` or that search URL.
- **Optional suggestions.** If `suggested_capabilities` is present, each item has an `id` that is not `time.travel`. Live production has suggested `travel.search_flights` and similar travel ids. That is typo recovery, not a time-travel capability.
- **Proof.** Keep the 404 body. The helper writes `evidence/$VERIFY_RHUMB_RUN_ID/drive-typed-stop-unknown-capability.json` and `evidence/$VERIFY_RHUMB_RUN_ID/http/resolve-time-travel.json`.

## Gotchas

- Tests in `packages/api/tests/test_capabilities.py` use `nonexistent` as the unknown id. This map uses `time.travel` as the live invented id. Do not swap them in the recorded proof.
- A 200 with an empty provider list is the wrong failure. That envelope is for a known capability with no execute-ready providers.
- Suggestions must not be treated as proof that the invented id works.
- MCP resolve maps the same 404 fields. An MCP empty-object fallback is not this proof.
