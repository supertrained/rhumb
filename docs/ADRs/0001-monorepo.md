# ADR-0001: Monorepo scaffold baseline

## Status
Accepted

## Context
Rhumb needs coordinated delivery across API, CLI, web, and shared schema/types.

## Decision
Use a single monorepo with `/packages/{api,cli,web,shared}` plus root CI and tooling.

## Consequences
- Easier cross-package refactors
- Single source of truth for schema and conventions
- Requires disciplined package boundaries as the codebase grows
