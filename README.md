# Rhumb

Agent-native tool discovery, access, and scoring platform. Index, evaluate, and intelligently route to the best tools for your agents.

## Monorepo layout

```text
rhumb/
├── packages/
│   ├── api/      # FastAPI backend
│   ├── cli/      # Typer CLI
│   ├── web/      # Next.js 15 app router frontend
│   └── shared/   # Shared types/constants
├── supabase/
│   └── migrations/
├── .github/workflows/
├── docker-compose.yml
└── Makefile
```

## Quick start

1. Copy env:
   ```bash
   cp .env.example .env
   ```
2. Start local infra:
   ```bash
   docker compose up -d db redis
   ```
3. Apply schema v0:
   ```bash
   psql postgresql://postgres:postgres@localhost:54322/postgres -f supabase/migrations/0001_init.sql
   ```
4. API:
   ```bash
   cd packages/api
   python3.12 -m venv .venv && source .venv/bin/activate
   pip install -r requirements-dev.txt
   uvicorn main:app --reload --port 8000
   ```
5. CLI:
   ```bash
   pip install -e packages/cli[dev]
   rhumb --help
   ```
6. Web:
   ```bash
   cd packages/web
   npm ci
   npm run dev
   ```

## Common tasks

```bash
make dev        # start local infra + show run commands
make test       # api + cli + web tests
make lint       # api + cli + web lint checks
make types      # mypy + tsc checks
make build      # web production build
make db-migrate # apply schema v0
```

## Status

This scaffold implements Work Unit 0.4 foundation only (structure + skeletons). Business logic lands in WU 1.x.
