# Runbooks

Operational runbooks for Rhumb incident response. Each runbook covers a specific failure mode with detection, impact assessment, mitigation, and resolution steps.

## Index

| Runbook | Trigger | Severity |
|---------|---------|----------|
| [Supabase Outage](./supabase-outage.md) | Database unreachable or degraded | P0 |
| [Proxy Provider Failure](./proxy-provider-failure.md) | Upstream provider returning errors | P1 |
| [Billing System Failure](./billing-failure.md) | Payment processing or metering down | P0 |
| [x402 Settlement Failure](./x402-settlement-failure.md) | On-chain verification failing | P1 |
| [Deployment Rollback](./deployment-rollback.md) | Bad deploy needs reverting | P0 |

## Severity Levels

- **P0**: Service-affecting. All executions blocked or data integrity at risk. Immediate response required.
- **P1**: Degraded service. Some execution modes or endpoints affected. Response within 1 hour.
- **P2**: Non-critical. Cosmetic or edge-case issues. Response within 24 hours.

## Escalation Path

1. **T0 — Automated**: Circuit breakers, cached fallbacks, health checks
2. **T1 — Pedro (AI)**: Diagnose, apply runbook, deploy fix
3. **T2 — Tom**: Infrastructure access, vendor contact, budget decisions
