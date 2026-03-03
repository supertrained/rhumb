# Learnings — Rhumb Build

## Observations (single instance, may become patterns)

- **2026-03-03**: Sub-agent panels truncate at ~2 personas × 7 questions × 300 words. Split to 2-3 personas with 150-250 word limits for reliable delivery.
- **2026-03-03**: Agent personas (Felix, Zoe) generated the highest net-new product signal of any panel — 10 AN Score dimensions humans wouldn't think of. Always include the end-user's computational perspective.
- **2026-03-03**: Panel delivery via OpenClaw sub-agents has ~30% failure rate (4 of 13 sub-agents lost results). Save outputs immediately upon receipt.
- **2026-03-03**: Boris Cherny principle — build for the model 6 months from now, not current limitations. Don't over-scaffold.

## Patterns (seen 2+ times, worth following)

- **Divergent expert opinions are signal, not noise**: Omar (charge for Discover) vs Nat (make it free) — both right for different scenarios. Track tensions, don't resolve prematurely.
- **Agent autonomy requires credential autonomy**: Felix needs to switch tools without human in loop. Zoe needs to reroute without waking Elvis. Access layer's core value = operational autonomy for agents, not billing convenience.

## Guidelines (proven, follow by default)

- **Depth over breadth**: Top 50 tools deeply assessed > 17,854 indexed shallowly (Rachel, Jake, Priya independently)
- **"Read is free, route is paid"**: Information layer free forever. Infrastructure layer paid. Never gate comparison features.
- **Score WITH context**: "7.2 because async webhooks but OAuth handshake interrupts" — one sentence = 2 hours saved.

## Prevention Rules (mistakes → rules)

- NEVER run 5 personas per sub-agent panel — guaranteed truncation
- NEVER treat panel rejection as permanent law — vision > research (Tom directive)
- NEVER publish a score without a contextual explanation — numbers without context are noise
- NEVER score based on documentation claims — score based on ACTUAL behavior (probes/telemetry)
