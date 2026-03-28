# HRIS discovery expansion — 2026-03-27

## Why HRIS

HRIS is still underrepresented relative to demand. Production only had five HRIS vendors visible before this batch (`bamboohr`, `deel`, `gusto`, `rippling`, `workday-api`), which is thin for a category that agents will routinely touch for directory lookups, leave status, onboarding/offboarding, attendance, and lightweight people ops automations.

## Services added

- **HiBob** — strong breadth across people data, time off, attendance, hiring, and webhooks
- **Personio** — clean public developer hub with people, absence, attendance, projects, and webhook surfaces
- **Factorial** — public getting-started docs plus a documented GraphQL API for core HR workflows
- **Employment Hero** — important SMB/mid-market HR + payroll + ATS platform with partner/developer docs

## Phase 0 assessment

### Strongest candidate: Factorial

Factorial is the cleanest immediate Resolve candidate in this batch because:
- public docs are easy to navigate
- the GraphQL surface is broad enough for high-value reads
- the primitives map naturally to agent workflows like:
  - employee list / employee get
  - time-off list / time-off read
  - attendance or shift-adjacent reads

### Close second: Personio

Personio also looks Phase-0-worthy for:
- persons
- attendance periods
- absence periods
- project membership / assignment context
- webhooks for state changes

### Later candidates

- **HiBob** has strong long-term value but slightly higher Phase 0 setup complexity because the surface area is broader and tenant permissions matter more.
- **Employment Hero** should stay cataloged now, but Resolve work should wait until we pin down the most stable public HR and ATS endpoints.

## Recommendation

If the next discovery-to-execution bridge needs an HRIS lane, start with **Factorial**, keep **Personio** as backup, and treat HiBob as the broader but more setup-heavy follow-on candidate.
