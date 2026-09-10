SHELL := /bin/bash

.PHONY: dev test lint types build db-migrate public-truth

dev:
	@echo "Starting local infra (db + redis)..."
	docker compose up -d db redis
	@echo "Run API: cd packages/api && uvicorn main:app --reload --port 8000"
	@echo "Run Web: cd packages/astro-web && npm run dev"

test:
	cd packages/api && pytest
	cd packages/cli && pytest
	python3 scripts/generate_agent_capabilities.py --check
	python3 scripts/callable_contract.py --check

lint:
	cd packages/api && black --check . && ruff check .
	cd packages/cli && black --check . && ruff check .

types:
	cd packages/api && mypy .
	cd packages/cli && mypy .

build:
	cd packages/astro-web && npm run build

public-truth:
	python3 scripts/generate_agent_capabilities.py --from-live --write
	python3 scripts/callable_contract.py --from-live

db-migrate:
	psql postgresql://postgres:postgres@localhost:54322/postgres -f supabase/migrations/0001_init.sql
