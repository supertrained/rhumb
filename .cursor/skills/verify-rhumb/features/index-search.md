# Index search

Index search lets a user find scored services by free text, see an empty result list for a miss, and get a 400 when the query is missing.

## Sub-features

- `search-match` returns scored services for a real query such as `email`.
- `search-empty` returns HTTP 200 and `data.results=[]` for a query with no indexed match.
- `search-invalid` returns HTTP 400 `INVALID_PARAMETERS` when `q` is empty.
- `search-cli` returns the same `/v1/search` payload through `rhumb find --json`.
- `search-web` lists matching services on `https://rhumb.dev/search?q=email`.

## How to get to it (user POV)

- Call `GET https://api.rhumb.dev/v1/search?q=<query>&limit=<n>`.
- Run `rhumb find <query>` in a terminal.
- Ask an MCP client to `find_services` with the same query.
- Open `https://rhumb.dev/search` and submit the search box, or go to `https://rhumb.dev/search?q=<query>`.

## Driving it with curl

Preconditions:

- Doctor passed against `$VERIFY_RHUMB_BASE`.
- You will not call execute.

- **Match.** Search email services. Run `.cursor/skills/verify-rhumb/bin/drive index-search` or `curl -sS -H 'User-Agent: rhumb-verify/1.0' -H 'Accept: application/json' -G "$VERIFY_RHUMB_BASE/v1/search" --data-urlencode 'q=email' --data-urlencode 'limit=5'`. HTTP 200. `error` is `null`. `data.query` is `email`. `data.results` has at least one object with `service_slug` and numeric `an_score`.
- **Empty.** Search a nonsense string. Run `curl -sS -H 'User-Agent: rhumb-verify/1.0' -G "$VERIFY_RHUMB_BASE/v1/search" --data-urlencode 'q=zzzqpxnotaservice'`. HTTP 200. `data.results` is `[]`. `error` is `null`.
- **Invalid.** Omit a real query. Run `curl -sS -H 'User-Agent: rhumb-verify/1.0' -G "$VERIFY_RHUMB_BASE/v1/search" --data-urlencode 'q='`. HTTP 400. `error.code` is `INVALID_PARAMETERS`. `error.detail` is `Provide a non-empty search query.`
- **CLI entry.** Search from the terminal. Run `RHUMB_API_BASE_URL=https://api.rhumb.dev/v1 rhumb find email --limit 5 --json`. Exit code `0`. Stdout uses `data.results`.
- **Website entry.** Open the public search page. Run `curl -sS -o /dev/null -w '%{http_code}' 'https://rhumb.dev/search?q=email'`. HTTP 200. HTML title is `Search | Rhumb` and the page names at least one matching service.
- **Proof.** Keep the match response. The helper writes `evidence/$VERIFY_RHUMB_RUN_ID/drive-index-search.json` and `evidence/$VERIFY_RHUMB_RUN_ID/http/search-email.json`. Both identify the query `email` and at least one scored `service_slug`.

## Gotchas

- `/v1/search` puts hits in `data.results`. Capability list puts hits in `data.items`. Mixing those fields looks like an empty catalog.
- `limit` must be an integer from 1 to 50. Other values return `INVALID_PARAMETERS`.
- Query length is capped at 200 characters in `packages/api/routes/search.py`.
- Scoreless catalog rows are dropped. A hit without `an_score` does not appear.
- `rhumb find` human output reads `aggregate_recommendation_score` or `score`, not `an_score`. Use `--json` and assert `data.results`.
- CLI default base is `https://rhumb-api-production-f173.up.railway.app/v1`. Set `RHUMB_API_BASE_URL=https://api.rhumb.dev/v1` for the documented host.
- The website search page filters `GET /v1/services` in `search.astro`. It is not `GET /v1/search`. Do not treat a web HTML match as the Index search API proof.
- MCP `find_services` swallows fetch errors and returns `{ "services": [] }`. An empty MCP list is not proof the Index is empty. Recheck `/v1/search`.
