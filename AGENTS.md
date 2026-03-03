# AGENTS.md — Rhumb Development Guide

## Repo Conventions

### Python (API + CLI)
- **Format:** Black (line length 100)
- **Linting:** Ruff
- **Types:** MyPy strict mode
- **Testing:** pytest with >80% coverage target
- **Imports:** Alphabetical within groups (isort-compatible ordering)

### TypeScript (Web)
- **Format:** Prettier
- **Linting:** ESLint
- **Strict mode:** Yes (`tsconfig.strict`)
- **Testing:** Vitest
- **Build:** Next.js app router

### Git
- PR titles: `type(scope): description` (`feat`, `fix`, `docs`, `test`, `refactor`, `chore`)
- Commit messages: imperative mood ("add route skeleton")
- Main branch: PR review required and all checks passing

### Documentation
- Python docstrings: Google style
- JSDoc required for exported TypeScript functions
- Keep README in each package
- Architecture decisions go in `/docs/ADRs/`

## API Design
- RESTful where practical
- Versioning by path prefix (`/v1`, `/v2`)
- Envelope responses: `{ "data": ..., "error": null }`
- Pagination params: `?limit=20&offset=0`

## Architecture Decisions
- Database: Supabase-compatible Postgres; migrations in `supabase/migrations/`
- API: FastAPI + Pydantic + SQLAlchemy
- Frontend: Next.js 15 App Router + Tailwind 4 + Tremor charts
- CLI: Typer and `httpx` API client

## Build Tasks
- `make dev` — start local infra and print run commands
- `make test` — run all package tests
- `make lint` — lint all packages
- `make types` — run static type checks
- `make build` — build web package
- `make db-migrate` — apply v0 schema
