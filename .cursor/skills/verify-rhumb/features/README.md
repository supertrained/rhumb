# Rhumb verification map

This directory is the maintained source for verifying user-facing Rhumb Index and Resolve-read behavior. Read this index before driving the app, then use the matching feature file as the recipe.

## Baseline preconditions

- Target `https://api.rhumb.dev` unless `VERIFY_RHUMB_BASE` points at a doctor-verified local API.
- Run `.cursor/skills/verify-rhumb/bin/launch` then `.cursor/skills/verify-rhumb/bin/doctor`.
- Require `GET /v1/healthz` → `{"status":"ok"}` and `GET /v1/status` overall `operational` or `degraded`.
- Do not send `X-Rhumb-Key`.
- Do not call execute or estimate.
- Never drive an instance that doctor rejected.

## Driving conventions

- Start every recipe from the baseline unless its preconditions say otherwise.
- Treat every curl as literal. Keep query strings and capability IDs unchanged.
- Run HTTP actions through `.cursor/skills/verify-rhumb/bin/drive <feature-id>`.
- CLI and website paths are secondary. Record them as extra entry points, not as a substitute for the API proof.
- Restore nothing. These reads do not mutate Index or Resolve state.
- Do not remove proof artifacts during cleanup.

## Proof and skip reporting

- Capture the request URL, status code, and response body.
- Index search proof includes `data.query` and scored `data.results`.
- Resolve proof includes `data.capability`, at least one provider, and `execute_hint.preferred_provider`.
- Typed-stop proof includes HTTP 404 and `error=capability_not_found`.
- Record the feature ID with every artifact.
- Report an unreachable path with the attempted command and the unmet precondition.
- Do not report a skipped entry point as verified through a different path.

## Feature entry contract

Each feature file starts with an H1 title and one paragraph describing the user-visible behavior. It then uses exactly four H2 sections in this order.

1. `Sub-features` lists short IDs with one line for each behavior.
2. `How to get to it (user POV)` lists every user entry point.
3. `Driving it with curl` starts with `Preconditions:` and uses labeled bullets that pair each user action with an exact command and observable result.
4. `Gotchas` lists traps that can waste or invalidate a verification run.

Keep implementation details out of the map. Name only user paths, stable handles, required state, commands, and observable proof.

## Features

- [Index search](./index-search.md) covers `GET /v1/search`, `rhumb find`, MCP `find_services`, and the website search page.
- [Resolve search.query](./resolve-search-query.md) covers public resolve of the live `search.query` capability.
- [Typed stop for an unknown capability](./typed-stop-unknown-capability.md) covers `time.travel` 404 and typo recovery.
- [Index score](./index-score.md) covers `GET /v1/services/{slug}/score` for a known slug.
- [Capability discover](./capability-discover.md) covers `GET /v1/capabilities?search=`.
