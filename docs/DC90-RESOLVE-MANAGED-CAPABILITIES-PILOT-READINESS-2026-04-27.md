# DC90 Resolve Managed-Capabilities Pilot Readiness

Date: 2026-04-27
Owner: Pedro
Scope: trusted-user pilot for Resolve **Rhumb-managed capabilities**, not public launch and not broad unmanaged system-of-record rails.

## Verdict

**Small-group ready, narrowly scoped.**

Rhumb is ready for a controlled trusted-user pilot where the first task is a Rhumb-managed `search.query` call through the governed `X-Rhumb-Key` rail. This should be a **2-5 trusted-user / friend-agent pilot**, not a public launch and not a claim that all managed capabilities are equally pilot-ready.

The pilot should start with:

1. open preflight: `resolve`;
2. open preflight: `estimate`;
3. governed execution with a capped key;
4. receipt / error inspection;
5. short feedback capture on where the agent got stuck.

## Why this is ready

Live no-spend checks on 2026-04-27 show the public hosted surface still supports the managed-capability story:

- `GET /v1/capabilities/search.query/resolve` returns HTTP 200.
- `search.query` currently exposes 7 provider paths.
- Managed-capable providers surfaced for `search.query`: `exa`, `tavily`, and `brave-search-api`.
- `GET /v1/capabilities/search.query/credential-modes` returns configured `rhumb_managed` modes for `exa`, `tavily`, and `brave-search-api`.
- `GET /v1/capabilities/search.query/execute/estimate` returns HTTP 200 with concrete managed execution rail:
  - provider: `brave-search-api`
  - `credential_mode`: `rhumb_managed`
  - circuit: `closed`
  - estimated cost: `$0.003`
- `POST /v1/capabilities/search.query/execute` without auth returns HTTP 402 with machine-readable payment/auth handoff, not anonymous execution.
- `GET /v1/capabilities/rhumb-managed` returns HTTP 200 and currently lists 68 managed capability configs.

Existing Helm validation from 2026-04-25 already proved the governed-key execute path for the same pilot snippet: `search.query` executed via `brave-search-api` in `rhumb_managed` mode with upstream 200. Treat that as still useful but not a substitute for a fresh smoke immediately before sending keys.

## Pilot boundary

This is **not** ready as an unrestricted “try any managed capability” launch.

Use this exact promise:

> Resolve can give your agent a governed, capped key for supported Rhumb-managed capabilities. Start with web search: resolve the capability, estimate the active execution rail before spend, then execute with a capped governed key.

Do not promise:

- anonymous execution;
- universal managed execution across all indexed services;
- that every one of the 68 managed configs is equally polished;
- that Resolve always chooses the highest AN Score provider;
- public MEO / retrieval / citation improvement;
- `rhumb-mcp@2.0.0` availability on npm.

## Pilot cohort shape

Recommended first cohort:

- 2-5 trusted users or friend agents.
- Each gets a capped governed key, not provider credentials.
- Suggested initial cap: `$5-$10/month`, `60 qpm`.
- Start with `search.query` only.
- Expand only after at least one complete run includes: resolve artifact, estimate artifact, execution result, receipt/error, and user friction notes.

## Operator flow

Use `docs/ONBOARD-A-FRIEND-AGENT.md` for key issuance.

For each trusted user:

1. Mint a governed key with `scripts/issue_friend_key.py`.
2. Set a low monthly budget and sane rate limit.
3. Send only:
   - `RHUMB_API_KEY=...`
   - quickstart snippet
   - the pilot boundary above
4. Ask them to paste back:
   - the resolve response if confusing;
   - the estimate response;
   - the execution status;
   - any receipt/error id;
   - the exact point their agent got stuck.

## Fresh smoke required before sending keys

Before issuing real pilot keys, run one final governed-key smoke:

```bash
API="https://api.rhumb.dev/v1"

curl "${API}/capabilities/search.query/resolve"
curl "${API}/capabilities/search.query/execute/estimate"
curl -X POST "${API}/capabilities/search.query/execute" \
  -H "X-Rhumb-Key: $RHUMB_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"body":{"query":"best tools for agent web search","max_results":3}}'
```

The execute call is a paid/authorized managed execution. Run it with a dogfood governed key immediately before issuing pilot keys; store the result as the fresh readiness artifact.

## Current go / no-go

- **Go:** controlled trusted-user pilot for `search.query` managed execution through governed keys.
- **No-go:** public launch, broad unmanaged system-of-record pilot, or “all managed capabilities are ready” claim.
- **One remaining action before invites:** fresh governed execute smoke plus capped key issuance for named trusted users.
