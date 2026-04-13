# Repo Boundary

Rhumb uses a **hard public/private boundary**.

## Public repo: `supertrained/rhumb`
This repo should contain only material that helps users, developers, and agents:
- product code
- public website
- public docs
- SDK / CLI / MCP surfaces
- curated public datasets
- examples and integration guidance

## Private ops repo: `tomdmeredith/rhumb-workspace`
This is where operator and company work belongs:
- planning and internal strategy
- memory and agent operating context
- GTM and internal business work
- raw proof artifacts
- screenshots and bootstrap traces
- credential discovery notes
- internal runbooks and panels
- anything with vault references, internal emails, temp paths, or operator-only context

## Default rule
- **If it helps users or agents use, trust, or integrate Rhumb, keep it public.**
- **If it helps us operate, debug, plan, sell, recover, or access Rhumb, keep it private.**

## What is intentionally not tracked here by default
- `.compound-beads/`
- `anchors/*.json`
- raw generated files under `artifacts/` (except curated public datasets)
- internal runbooks under `docs/runbooks/`
- internal research / panel docs under `docs/panels/`

## Public artifacts rule
`artifacts/` is a local working directory for generated outputs.
Only deliberately curated, user-safe datasets should be committed here.

Current committed exceptions:
- `artifacts/autonomy-scores.json`
- `artifacts/dataset-scores.json`

## Publication standard
Before committing a new file to the public repo, ask:
1. Would a user, developer, or agent genuinely benefit from this being public?
2. Does it avoid exposing operator-only context?
3. Is it stable enough to be part of the public surface, not just a local work byproduct?

If the answer is not clearly yes, it belongs in the private ops workspace instead.
