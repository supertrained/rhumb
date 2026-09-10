---
name: verify-rhumb
description: Drive Rhumb Index and Resolve the way a user does. Use the public HTTP API at https://api.rhumb.dev (optional local uvicorn) to prove search, resolve, and typed 404s with captured evidence. Use when verifying Rhumb discovery or resolve-read behavior.
---

# Verify Rhumb

Read this file, then `features/README.md`, then the one feature file you will drive. Do not invent capabilities. Do not execute.

Primary surface is the public HTTP API. MCP, CLI, and the website wrap the same Index and Resolve reads. This skill drives those reads with curl. It does not call `POST /v1/capabilities/{id}/execute` or any paid rail.

## Launch

Default target is live production. Do not start a local process.

```bash
export VERIFY_RHUMB_BASE="${VERIFY_RHUMB_BASE:-https://api.rhumb.dev}"
export VERIFY_RHUMB_SITE="${VERIFY_RHUMB_SITE:-https://rhumb.dev}"
export VERIFY_RHUMB_RUN_ID="${VERIFY_RHUMB_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
.cursor/skills/verify-rhumb/bin/launch
```

Ready means `GET $VERIFY_RHUMB_BASE/v1/healthz` returns HTTP 200 and `{"status":"ok"}`.

Teardown is `bin/cleanup`. Live launch creates no process. Cleanup must still run so scratch state under `/tmp/verify-rhumb-state-$VERIFY_RHUMB_RUN_ID` is removed.

### Optional local API

This checkout documents local start in the Makefile and `packages/api/README.md`.

```bash
make dev
cd packages/api && python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn main:app --reload --port 8000
```

`packages/api/main.py` re-exports `app` from `app.py`. The root README `uvicorn app:app` line also works. Prefer `uvicorn main:app --port 8000`.

Local search and resolve read Supabase through `packages/api/routes/_supabase.py`. `.env.example` sets `SUPABASE_URL=http://localhost:54321` and placeholder keys. Without a real Supabase catalog, `/v1/search` returns empty results or `"Search unavailable."` That is not a production proof.

`make dev` needs Docker for Postgres `54322` and Redis `6379`. If `docker` is missing, stay on `https://api.rhumb.dev`.

Astro web, if you need it: `cd packages/astro-web && npm ci && npm run dev` on port `4321`. MCP discovery: `npx -y --package rhumb-mcp@latest rhumb-mcp` with no key.

## Doctor

Run this first whenever the instance looks off.

```bash
.cursor/skills/verify-rhumb/bin/doctor
```

Pass only when all of these hold:

1. `GET $VERIFY_RHUMB_BASE/v1/healthz` is HTTP 200 and `status` is `ok`.
2. `GET $VERIFY_RHUMB_BASE/v1/status` is HTTP 200. Overall `status` is `operational` or `degraded`. Refuse `partial_outage`.
3. `meta.environment` on live is `production` when `$VERIFY_RHUMB_BASE` is `https://api.rhumb.dev`.
4. You are not about to call execute or estimate.

`degraded` is still driveable for Index and Resolve reads. `partial_outage` is not.

## Drive

Harness is curl plus `bin/drive`. Stable handles are URL paths and JSON fields, not CSS.

```bash
.cursor/skills/verify-rhumb/bin/drive index-search
```

Allowed feature ids live in `features/`. Beachhead ids are `index-search`, `resolve-search-query`, `typed-stop-unknown-capability`, `index-score`, and `capability-discover`.

Rules:

- Send `User-Agent: rhumb-verify/1.0` and `Accept: application/json`.
- Read `data.results` on `/v1/search`. Do not read `data.items` there. `examples/discover-and-evaluate.py` still looks at `data.items` and is the wrong harness.
- Read `data.items` on `GET /v1/capabilities`.
- Score lookup is a top-level object. There is no `data` wrapper on `GET /v1/services/{slug}/score`.
- Unknown capability resolve is a top-level 404 object. There is no `data` wrapper.
- Do not POST execute. Do not GET estimate. Do not run `scripts/dc90_search_query_pilot_smoke.py`. That script executes funded `search.query`.
- Do not send `X-Rhumb-Key` on these read paths.
- Live rate limit observed on `api.rhumb.dev` is `x-ratelimit-limit: 120` per window. Do not loop.

Canonical live curls:

```bash
curl -sS -H 'User-Agent: rhumb-verify/1.0' -H 'Accept: application/json' \
  -G "$VERIFY_RHUMB_BASE/v1/search" --data-urlencode 'q=email' --data-urlencode 'limit=5'

curl -sS -H 'User-Agent: rhumb-verify/1.0' -H 'Accept: application/json' \
  "$VERIFY_RHUMB_BASE/v1/capabilities/search.query/resolve"

curl -sS -H 'User-Agent: rhumb-verify/1.0' -H 'Accept: application/json' \
  "$VERIFY_RHUMB_BASE/v1/capabilities/time.travel/resolve"
```

CLI secondary path. Override the CLI default host, which is `https://rhumb-api-production-f173.up.railway.app/v1` in `packages/cli/config.py`.

```bash
RHUMB_API_BASE_URL=https://api.rhumb.dev/v1 rhumb find email --limit 5 --json
```

Website secondary path for Index search is `https://rhumb.dev/search?q=email`. That page filters `GET /v1/services` in `packages/astro-web/src/pages/search.astro`. It is not `GET /v1/search`. Prove Index search on the API first.

## Evidence

Write proof under `.cursor/skills/verify-rhumb/evidence/$VERIFY_RHUMB_RUN_ID/`.

Required files for a run:

- `launch.json`
- `doctor.json`
- `drive-<feature-id>.json`
- `http/` request and response bodies the helper saved

Proof standard:

- Exercise the live user path (`api.rhumb.dev` or a doctor-verified local API).
- Capture the request URL, HTTP status, and response body, not only a pass boolean.
- For Index search, keep the query and the scored `results` list.
- For Resolve, keep `data.capability`, `data.providers`, and `data.execute_hint.preferred_provider`. Stop there.
- For typed stop, keep HTTP 404 and `error=capability_not_found`.
- Do not treat a website screenshot as enough when the feature is an API read.

You may also copy a run to `/tmp/verify-rhumb-$VERIFY_RHUMB_RUN_ID` by setting `VERIFY_RHUMB_EVIDENCE_DIR`. Cleanup must not delete either location.

## Cleanup

```bash
.cursor/skills/verify-rhumb/bin/cleanup
```

Cleanup removes `/tmp/verify-rhumb-state-$VERIFY_RHUMB_RUN_ID` and, if launch recorded a local PID, kills that PID only. It never kills by process name. It never deletes `evidence/`. It never touches Railway, Vercel, or production data.

## Helpers

All helpers are executable. Run them from the repo root. They locate the skill directory from their own path.

```bash
.cursor/skills/verify-rhumb/bin/launch
.cursor/skills/verify-rhumb/bin/doctor
.cursor/skills/verify-rhumb/bin/drive index-search
.cursor/skills/verify-rhumb/bin/cleanup
```

One-shot proof of the generated skill:

```bash
.cursor/skills/verify-rhumb/bin/prove index-search
```

`bin/common.sh` is sourced by the others. Do not execute it.

## Isolate

Live `api.rhumb.dev` is a shared production host. Two read-only doctor or drive runs may overlap. They share the 120-request rate-limit window. Do not drive execute against that host from this skill.

Two local APIs can share a machine if they use different ports (`--port 8000` and `--port 8001`) and different `VERIFY_RHUMB_RUN_ID` values. Do not point two writers at one local Postgres volume from `docker-compose.yml`.

## Maintenance

After the app changes, run `/maintain-verification-skill` against this skill and refresh the feature map from live reads.
