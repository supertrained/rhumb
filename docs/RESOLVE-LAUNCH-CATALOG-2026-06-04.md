# Resolve Launch Catalog

This is the current P0 Rhumb-managed capability surface for agents using a Rhumb API key. The goal is a small public catalog that works before agents wire their own provider accounts.

## Agent Contract

Use this loop:

1. Discover the capability ID.
2. Resolve the managed route.
3. Estimate the route before spend.
4. Execute only bounded, allowed capabilities.
5. Store the execution receipt.

```bash
API="https://api.rhumb.dev/v1"

curl "$API/capabilities/search.query/resolve?credential_mode=rhumb_managed"

curl "$API/capabilities/search.query/execute/estimate?credential_mode=rhumb_managed" \
  -H "X-Rhumb-Key: $RHUMB_API_KEY"

curl -X POST "$API/capabilities/search.query/execute" \
  -H "X-Rhumb-Key: $RHUMB_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "credential_mode": "rhumb_managed",
    "provider": "exa",
    "body": {"query": "agent native API capability routing", "numResults": 3}
  }'
```

For MCP, use the same order:

```text
resolve_capability({"capability":"search.query","credential_mode":"rhumb_managed"})
estimate_capability({"capability_id":"search.query","credential_mode":"rhumb_managed"})
execute_capability({
  "capability_id":"search.query",
  "credential_mode":"rhumb_managed",
  "provider":"exa",
  "body":{"query":"agent native API capability routing","numResults":3}
})
```

## P0 Capabilities

| Capability | Preferred provider | Status | Execution policy |
| --- | --- | --- | --- |
| `search.query` | `exa` | Launch | Safe read execution |
| `scrape.extract` | `firecrawl` | Launch | Safe one-page public extract |
| `ai.generate_text` | `openai` | Launch | Bounded short text generation |
| `ai.generate_image` | `openai` | Launch | Bounded one-image generation, compact evidence only |
| `data.enrich_person` | `people-data-labs` | Launch with proof substitute | Resolve + estimate only until a consented fixture exists |
| `data.enrich_company` | `apollo` | Launch | Rhumb-owned company-domain fixture |
| `geo.lookup` | `ipinfo` | Launch | Public resolver IP fixture only |
| `maps.places_search` | `google-places` | Launch | Public place-search fixture |

## Deferred Surfaces

`email.send` is a real capability but remains gated because it sends externally. It needs an owned verified sender, one-message cap, idempotency, approval policy, and receipt review before public managed execution.

`sendgrid` is a valid pass-through provider for `email.send`, but hosted Resolve currently marks it non-callable because no `RHUMB_CREDENTIAL_SENDGRID_API_KEY` is configured. This is not a launch blocker because `email.send` is deferred as an external-write surface; do not treat any email provider as part of the P0 managed launch catalog until the email-send gates above are complete.

`email.verify` is deferred because no managed verification provider is configured. Add Emailable, ZeroBounce, NeverBounce, Kickbox, or another approved provider before advertising it as managed.

## Error Contract

If `resolve` returns no executable managed provider, agents should use the machine-readable recovery fields:

- `recovery_hint.resolve_url`
- `recovery_hint.credential_modes_url`
- `recovery_hint.supported_provider_slugs`
- `recovery_hint.setup_handoff`

If `execute` returns auth or funding errors, agents should stop and surface the returned handoff rather than switching to a browser, scraping credentials, or trying a public write.

## Proof Command

Run the current proof harness with:

```bash
python3 scripts/resolve_launch_catalog_smoke.py \
  --execute-safe \
  --out artifacts/resolve-launch-catalog-smoke.json
```

The artifact is redacted by design: it stores statuses, provider IDs, execution IDs, receipt IDs, hashes, and compact response shape. It does not store raw provider keys, raw generated image bytes, or full upstream payloads.
