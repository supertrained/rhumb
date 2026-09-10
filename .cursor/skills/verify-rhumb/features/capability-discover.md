# Capability discover

Capability discover lets a user search the capability registry by job text and receive capability ids such as `search.query` that Resolve can accept.

## Sub-features

- `discover-search` returns capability rows for `search=web research`.
- `discover-fields` includes `id`, `domain`, `action`, and `description` on each item.
- `discover-empty` returns `data.items=[]` when the search matches nothing.

## How to get to it (user POV)

- Call `GET https://api.rhumb.dev/v1/capabilities?search=<query>`.
- Browse `https://rhumb.dev/capabilities`.
- Ask an MCP client to `discover_capabilities`.

## Driving it with curl

Preconditions:

- Doctor passed against `$VERIFY_RHUMB_BASE`.
- You need a capability id, not a vendor slug.

- **Intent search.** Search for web research. Run `.cursor/skills/verify-rhumb/bin/drive capability-discover` or `curl -sS -H 'User-Agent: rhumb-verify/1.0' -H 'Accept: application/json' -G "$VERIFY_RHUMB_BASE/v1/capabilities" --data-urlencode 'search=web research' --data-urlencode 'limit=5'`. HTTP 200. `data.items` is a non-empty list. Each item has an `id`.
- **Hand-off.** Pick an `id` from that list only if it already exists in the response. Pass that id to Resolve. Do not invent `time.travel`.
- **Proof.** Keep the list response. The helper writes `evidence/$VERIFY_RHUMB_RUN_ID/drive-capability-discover.json` and `evidence/$VERIFY_RHUMB_RUN_ID/http/capabilities-web-research.json`.

## Gotchas

- Capability list uses `data.items`. Index search uses `data.results`.
- `docs/API.md` cold-start flow is search services, search capabilities, then resolve. Do not skip to execute.
- Domain filter values are validated. An unknown `domain` query fails instead of returning a silent empty page.
- Degraded catalog reads can add `_DEGRADED_DISCOVERY_ERROR` in `error` while still showing synthetic direct capabilities. If `error` is set, say so in the proof. Do not treat that as a healthy catalog.
